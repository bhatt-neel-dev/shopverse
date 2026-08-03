"""Register the ShopVerse ecosystem in Motadata ObserveOps — idempotent.

Creates credential profiles, discovery profiles, a JSON log parser for ShopVerse service logs,
trap listeners, and RUM/APM application registrations. Safe to re-run: every object is looked up
by name first and reused if present.

Usage:
    export MOTADATA_PAT=<personal access token from Settings > Personal Access Token>
    python register.py --config shopverse.yaml [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib3
import yaml
import requests

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class Motadata:
    def __init__(self, base_url: str, token: str, dry_run: bool = False):
        self.base = base_url.rstrip("/")
        self.dry_run = dry_run
        self.s = requests.Session()
        self.s.verify = False
        self.s.headers.update({"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json"})

    def get(self, path: str, **kw):
        r = self.s.get(f"{self.base}/api/v1{path}", timeout=60, **kw)
        r.raise_for_status()
        return r.json().get("result", [])

    def post(self, path: str, payload: dict):
        if self.dry_run:
            print(f"  [dry-run] POST {path}: {json.dumps(payload)[:160]}")
            return {"dry_run": True}
        r = self.s.post(f"{self.base}/api/v1{path}", json=payload, timeout=120)
        if r.status_code >= 400:
            raise RuntimeError(f"POST {path} -> {r.status_code}: {r.text[:400]}")
        return r.json()

    def find_by(self, path: str, field: str, value: str):
        for row in self.get(path) or []:
            if isinstance(row, dict) and row.get(field) == value:
                return row
        return None


def ensure(md: Motadata, kind: str, path: str, name_field: str, name: str, payload: dict):
    existing = md.find_by(path, name_field, name)
    if existing:
        print(f"  = {kind} '{name}' already exists")
        return existing
    md.post(path, payload)
    print(f"  + {kind} '{name}' created")
    return {"name": name}


CREDENTIALS = [
    # (name, protocol, extra fields) — passwords come from the config file
    ("shopverse-linux-ssh", "SSH", {}),
    ("shopverse-snmp", "SNMP V1/V2c", {}),
    ("shopverse-postgres", "JDBC", {}),
    ("shopverse-mysql", "JDBC", {}),
    ("shopverse-mongo", "JDBC", {}),
]


def register_credentials(md: Motadata, cfg: dict):
    print("credential profiles:")
    creds = cfg.get("credentials", {})
    for name, protocol, extra in CREDENTIALS:
        c = creds.get(name, {})
        if not c:
            print(f"  ! {name}: no entry in config.credentials — skipped")
            continue
        payload = {
            "credential.profile.name": name,
            "credential.profile.protocol": protocol,
            "credential.profile.context": {
                "user.name": c.get("username", ""),
                "password": c.get("password", ""),
                **({"community": c["community"]} if "community" in c else {}),
                **extra,
            },
        }
        ensure(md, "credential", "/settings/credential-profiles",
               "credential.profile.name", name, payload)


def register_discoveries(md: Motadata, cfg: dict):
    print("discovery profiles:")
    host = cfg["site"]["vm"]["host"]
    dbs = set(cfg.get("databases", []))
    profiles = [
        ("shopverse-host-linux", "Linux", host, "shopverse-linux-ssh", 22),
        ("shopverse-host-snmp", "Linux (SNMP)", host, "shopverse-snmp", 161),
    ]
    db_map = {
        "postgresql": ("PostgreSQL", 5432, "shopverse-postgres"),
        "mysql": ("MySQL", 3306, "shopverse-mysql"),
        "mongodb": ("MongoDB", 27017, "shopverse-mongo"),
    }
    for db in dbs:
        if db in db_map:
            obj_type, port, cred = db_map[db]
            profiles.append((f"shopverse-{db}", obj_type, host, cred, port))

    for name, obj_type, target, cred, port in profiles:
        payload = {
            "discovery.profile.name": name,
            "object.type": obj_type,
            "discovery.profile.context": {"host": target, "port": port},
            "credential.profiles": [cred],
            "discovery.profile.auto.provision": True,
        }
        ensure(md, "discovery", "/settings/discoveries", "discovery.profile.name", name, payload)


SHOPVERSE_LOG_PARSER = {
    "log.parser.name": "ShopVerse JSON",
    "log.parser.type": "JSON",
    "log.parser.context": {
        # Matches docs/CONTRACTS.md log schema
        "timestamp.field": "ts",
        "timestamp.format": "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
        "severity.field": "level",
        "message.field": "msg",
        "fields": ["svc", "trace_id", "method", "path", "status",
                   "latency_ms", "order_id", "user_id", "err"],
    },
}


def register_log_parser(md: Motadata, cfg: dict):
    print("log parser:")
    ensure(md, "log parser", "/settings/log-parsers", "log.parser.name",
           "ShopVerse JSON", SHOPVERSE_LOG_PARSER)


def register_rum_apps(md: Motadata, cfg: dict):
    print("RUM applications:")
    for app in cfg.get("rum", {}).get("apps", []):
        name = app["name"]
        payload = {
            "rum.application.name": name,
            "rum.application.type": app.get("type", "react"),
            "rum.application.version": app.get("version", "1.0.0"),
            "rum.application.environment": app.get("environment", "lab"),
            "rum.application.session.sample.rate": app.get("sample_rate", 100),
            "rum.application.privacy": app.get("privacy", "allow"),
        }
        ensure(md, "RUM app", "/settings/rum-applications", "rum.application.name", name, payload)


def register_trap_listeners(md: Motadata, cfg: dict):
    if not cfg.get("pipelines", {}).get("traps"):
        return
    print("trap listeners:")
    for name, version, port in [("shopverse-trap-v2c", "V1/V2c", 1620),
                                ("shopverse-trap-v3", "V3", 1630)]:
        payload = {"snmp.trap.listener.name": name,
                   "snmp.trap.listener.version": version,
                   "snmp.trap.listener.port": port}
        ensure(md, "trap listener", "/settings/snmp-trap-listeners",
               "snmp.trap.listener.name", name, payload)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="shopverse.yaml")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--token", default=None, help="overrides $MOTADATA_PAT")
    args = ap.parse_args()

    cfg = yaml.safe_load(open(args.config))
    site = cfg["site"]
    import os
    token = args.token or os.environ.get(site["appliance"].get("pat_env", "MOTADATA_PAT"), "")
    if not token and not args.dry_run:
        sys.exit("no token: set $MOTADATA_PAT or pass --token (or use --dry-run)")
    if "<" in str(site["vm"]["host"]):
        sys.exit("fill in site.vm.host in the config first")

    md = Motadata(site["appliance"]["url"], token, args.dry_run)
    print(f"appliance {site['appliance']['url']} (dry-run={args.dry_run})\n")

    register_credentials(md, cfg)
    register_discoveries(md, cfg)
    register_log_parser(md, cfg)
    register_rum_apps(md, cfg)
    register_trap_listeners(md, cfg)

    print("\ndone. Next: verify discovery ran (Settings > Discovery Profile > Run) and that "
          "monitors were provisioned, then attach policies.")


if __name__ == "__main__":
    main()
