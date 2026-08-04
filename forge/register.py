"""One-shot onboarding of the ShopVerse ecosystem into a fresh Motadata instance.

Idempotent: every object is looked up by name and reused, so re-running is safe and only
creates what is missing. Field names follow forge/API_GROUND_TRUTH.md (captured from a live
appliance) — not the UI labels, which differ.

Order matters: credentials must exist before discoveries (which reference credential *ids*),
and parsers before log collectors.

Usage:
    export MOTADATA_PAT=<Settings > User Settings > Personal Access Token>
    python register.py --config shopverse.yaml            # create everything
    python register.py --config shopverse.yaml --dry-run  # print payloads, touch nothing
    python register.py --config shopverse.yaml --run-discovery   # also kick off discovery
"""

from __future__ import annotations

import argparse
import json
import os
import sys

import requests
import urllib3
import yaml

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# object.type -> (discovery category, default port, credential key in config)
DB_TYPES = {
    "postgresql": ("PostgreSQL", "Database", 5432, "shopverse-postgres"),
    "mysql": ("MySQL", "Database", 3306, "shopverse-mysql"),
    "mongodb": ("MongoDB", "Database", 27017, "shopverse-mongo"),
}

CREDENTIAL_SPECS = {
    "shopverse-linux-ssh": ("SSH", lambda c: {
        "username": c.get("username", ""), "password": c.get("password", ""),
        "cli.enabled": "no"}),
    # snmp.community, not community — the latter is accepted then sent empty
    "shopverse-snmp": ("SNMP V1/V2c", lambda c: {
        "snmp.version": "v2c", "snmp.community": c.get("community", "public")}),
    "shopverse-postgres": ("JDBC", lambda c: {
        "username": c.get("username", ""), "password": c.get("password", "")}),
    "shopverse-mysql": ("JDBC", lambda c: {
        "username": c.get("username", ""), "password": c.get("password", "")}),
    "shopverse-mongo": ("JDBC", lambda c: {
        "username": c.get("username", ""), "password": c.get("password", "")}),
}

# A representative ShopVerse log line (docs/CONTRACTS.md), required by the parser create.
PARSER_SAMPLE = {
    "ts": "2026-08-04T10:00:00.123Z", "level": "INFO", "svc": "catalog",
    "msg": "GET /products 200", "trace_id": "3f1c9a52-0d2b-4f77-9a1e-6c2f0b8d4e11",
    "method": "GET", "path": "/products", "status": 200, "latency_ms": 12,
    "order_id": 1024, "user_id": 777,
}

# Baseline policies. entities=[] means "all monitors".
POLICIES = [
    ("shopverse-cpu-critical", "Metric Threshold", "system.cpu.percent", ">=", "85"),
    ("shopverse-memory-critical", "Metric Threshold", "system.memory.used.percent", ">=", "90"),
    ("shopverse-disk-critical", "Metric Threshold", "system.disk.used.percent", ">=", "85"),
]


class Motadata:
    def __init__(self, base_url: str, token: str, dry_run: bool = False):
        self.base = base_url.rstrip("/")
        self.dry_run = dry_run
        self.s = requests.Session()
        self.s.verify = False
        self.s.headers.update({"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json"})

    def get(self, path: str):
        r = self.s.get(f"{self.base}/api/v1{path}", timeout=90)
        r.raise_for_status()
        return r.json().get("result", [])

    def get_safe(self, path: str):
        """A failed lookup must not abort the run — it degrades to 'not present'."""
        try:
            return self.get(path)
        except Exception as e:  # noqa: BLE001
            print(f"    ~ lookup {path} failed ({type(e).__name__}); assuming empty")
            return []

    def post(self, path: str, payload: dict):
        if self.dry_run:
            print(f"    [dry-run] POST {path}")
            print(f"      {json.dumps(payload)[:400]}")
            return None
        r = self.s.post(f"{self.base}/api/v1{path}", json=payload, timeout=180)
        if r.status_code >= 400:
            raise RuntimeError(f"POST {path} -> {r.status_code}: {r.text[:500]}")
        body = r.json()
        return body.get("result", body)


def ensure(md: Motadata, path: str, name_field: str, name: str, payload: dict, kind: str):
    """Create `payload` unless an object with the same name exists. Returns its id (or None)."""
    for row in (md.get_safe(path) if not md.dry_run else []):
        # Deleting a policy only archives it; an archived row must not count as existing.
        if str(row.get("policy.archived", "no")).lower() == "yes":
            continue
        if isinstance(row, dict) and row.get(name_field) == name:
            print(f"    = {kind} '{name}' exists (id {row.get('id')})")
            return row.get("id")
    result = md.post(path, payload)
    new_id = None
    if isinstance(result, dict):
        new_id = result.get("id")
    elif isinstance(result, list) and result and isinstance(result[0], dict):
        new_id = result[0].get("id")
    print(f"    + {kind} '{name}' created" + (f" (id {new_id})" if new_id else ""))
    return new_id


def register_credentials(md: Motadata, cfg: dict) -> dict[str, int]:
    print("\n[1/5] credential profiles")
    configured = cfg.get("credentials", {})
    ids: dict[str, int] = {}
    for name, (protocol, ctx_fn) in CREDENTIAL_SPECS.items():
        entry = configured.get(name)
        if entry is None:
            print(f"    ! {name}: absent from config.credentials — skipped")
            continue
        if any("<" in str(v) for v in entry.values()):
            print(f"    ! {name}: placeholder value still in config — skipped")
            continue
        payload = {
            "credential.profile.name": name,
            "credential.profile.protocol": protocol,
            "credential.profile.context": ctx_fn(entry),
        }
        cid = ensure(md, "/settings/credential-profiles",
                     "credential.profile.name", name, payload, "credential")
        if cid:
            ids[name] = cid
    return ids


def register_discoveries(md: Motadata, cfg: dict, cred_ids: dict[str, int]) -> list[int]:
    print("\n[2/5] discovery profiles")
    host = cfg["site"]["vm"]["host"]
    targets = [
        ("shopverse-host-linux", "Linux", "Server", 22, "shopverse-linux-ssh"),
        ("shopverse-host-snmp", "Linux (SNMP)", "Network", 161, "shopverse-snmp"),
    ]
    for db in cfg.get("databases", []):
        if db in DB_TYPES:
            obj_type, category, port, cred = DB_TYPES[db]
            targets.append((f"shopverse-{db}", obj_type, category, port, cred))

    created = []
    for name, obj_type, category, port, cred_name in targets:
        cred_id = cred_ids.get(cred_name)
        if cred_id is None and not md.dry_run:
            print(f"    ! {name}: credential '{cred_name}' unavailable — skipped")
            continue
        payload = {
            "discovery.name": name,
            "discovery.type": "ip.address",
            "discovery.target": host,
            "discovery.target.name": host,
            "discovery.category": category,
            "discovery.object.type": obj_type,
            "discovery.context": {"port": port, "ping.check.status": "yes"},
            "discovery.credential.profiles": [cred_id] if cred_id else [],
            "discovery.groups": [],
            "discovery.user.tags": [],
            "discovery.exclude.targets": [],
            "discovery.exclude.target.type": "ip.address",
            "discovery.config.management.status": "no",
            "discovery.scheduler": "no",
        }
        did = ensure(md, "/settings/discoveries", "discovery.name", name, payload, "discovery")
        if did:
            created.append(did)
    return created


def register_log_parser(md: Motadata, cfg: dict) -> int | None:
    print("\n[3/5] log parser")
    payload = {
        "log.parser.name": "ShopVerse JSON",
        "log.parser.type": "json",
        # The API derives the parser from this sample line and rejects the create without it
        # (400 MD022 "Event is a required field").
        "log.parser.event": json.dumps(PARSER_SAMPLE),
        "log.parser.source.type": "Other",
        "log.parser.condition": "all",
        "log.parser.condition.keywords": [],
        "log.parser.upload": "no",
        "log.parser.date.time.format": "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
        "log.parser.date.time.formatter.type": "formatter",
        # matches the one-JSON-line-per-request schema in docs/CONTRACTS.md
        "log.parser.fields": [
            {"log.parser.field.name": f, "log.parser.field.type": t,
             "log.parser.field.value": str(PARSER_SAMPLE[f])}
            for f, t in [("ts", "timestamp"), ("level", "none"), ("svc", "none"),
                         ("msg", "none"), ("trace_id", "none"), ("status", "none"),
                         ("latency_ms", "none"), ("order_id", "none"), ("user_id", "none")]
        ],
    }
    return ensure(md, "/settings/log-parsers", "log.parser.name",
                  "ShopVerse JSON", payload, "log parser")


def register_policies(md: Motadata, cfg: dict):
    print("\n[4/5] policies")
    for name, ptype, metric, condition, threshold in POLICIES:
        payload = {
            "policy.name": name,
            "policy.type": ptype,
            "policy.state": "yes",
            "policy.title": "$$$severity$$$ - $$$object.name$$$",
            "policy.message": ("$$$counter$$$ has entered into $$$severity$$$ state with value "
                               "$$$value$$$ on $$$object.host$$$($$$object.ip$$$)"),
            "policy.context": {
                "metric": metric,
                "filters": {"data.filter": {}},
                "entities": [],
                "policy.severity": {
                    "CRITICAL": {"policy.condition": condition, "policy.threshold": threshold}
                },
                "policy.trigger.time": 300,
                "policy.trigger.occurrences": 1,
                "policy.auto.clear.timer.seconds": 0,
            },
            "policy.actions": {"Integration": {}, "Notification": {"Email": {}, "channels": {}}},
            "policy.archived": "no",
            "policy.renotify": "no",
            "policy.scheduled": "no",
        }
        ensure(md, "/settings/metric-policies", "policy.name", name, payload, "policy")


def run_discoveries(md: Motadata, discovery_ids: list[int]):
    print("\n[5/5] running discoveries")
    if md.dry_run:
        print(f"    [dry-run] would run {len(discovery_ids)} discovery profile(s)")
        return
    for did in discovery_ids:
        try:
            md.post(f"/settings/discoveries/{did}/run", {})
            print(f"    > discovery {did} started")
        except Exception as e:  # noqa: BLE001 — endpoint shape unconfirmed
            print(f"    ! could not start discovery {did}: {str(e)[:160]}")
            print("      run it from Settings > Discovery Profile instead")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="shopverse.yaml")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--token", default=None, help="overrides $MOTADATA_PAT")
    ap.add_argument("--run-discovery", action="store_true",
                    help="start each discovery profile after creating it")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    site = cfg["site"]
    token = args.token or os.environ.get(site["appliance"].get("pat_env", "MOTADATA_PAT"), "")
    if not token and not args.dry_run:
        sys.exit("no token: set $MOTADATA_PAT, pass --token, or use --dry-run")
    if "<" in str(site["vm"]["host"]):
        sys.exit("fill in site.vm.host in the config first")

    md = Motadata(site["appliance"]["url"], token, args.dry_run)
    print(f"target appliance: {site['appliance']['url']}  (dry-run={args.dry_run})")

    cred_ids = register_credentials(md, cfg)
    discovery_ids = register_discoveries(md, cfg, cred_ids)
    register_log_parser(md, cfg)
    register_policies(md, cfg)
    if args.run_discovery:
        run_discoveries(md, discovery_ids)

    print("\ndone.")
    print("Not yet automated (REST endpoints unconfirmed — see forge/API_GROUND_TRUTH.md):")
    print("  * SNMP trap listeners   — Settings > SNMP Trap > SNMP Trap Listener")
    print("  * RUM/APM app registration — Settings > Real User Monitoring / APM")
    print("  * dashboards and SLO profiles")
    if not args.run_discovery:
        print("\nNext: Settings > Discovery Profile > Run (or re-run with --run-discovery).")


if __name__ == "__main__":
    main()
