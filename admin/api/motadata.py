"""Motadata ObserveOps auto-configuration, driven from Scenario Studio.

Every object the ecosystem needs on the appliance is declared once in ITEMS below. Each item
knows how to (a) report its state and (b) create itself, so the UI can show a live
configured/active/error board and configure things one at a time or all at once.

Field names follow forge/API_GROUND_TRUTH.md — captured from a live appliance, not the UI labels.

States:
  not_configured  the object does not exist yet
  configured      it exists but nothing has exercised it yet
  active          it exists and is doing its job (discovery ran, monitors provisioned, policy on)
  error           it exists but is unhealthy (discovery failed, nothing discovered)
  unknown         the appliance could not be queried (no token, unreachable, endpoint 403)
"""

from __future__ import annotations

import os
from typing import Any

import httpx

APPLIANCE_URL = os.environ.get("MOTADATA_URL", "https://172.16.14.71")
PAT_ENV = os.environ.get("MOTADATA_PAT", "")
# The host ShopVerse runs on, as Motadata should reach it. Defaults to this VM's LAN address.
TARGET_HOST = os.environ.get("MOTADATA_TARGET_HOST", "172.20.21.25")

NOT_CONFIGURED, CONFIGURED, ACTIVE, ERROR, UNKNOWN = (
    "not_configured", "configured", "active", "error", "unknown")

_token_override: str | None = None


def set_token(token: str | None) -> None:
    """Let the UI supply a PAT at runtime instead of baking it into the image."""
    global _token_override
    _token_override = token or None


def token() -> str:
    return _token_override or PAT_ENV


def configured_appliance() -> dict:
    return {"url": APPLIANCE_URL, "target_host": TARGET_HOST, "has_token": bool(token())}


class MotaClient:
    def __init__(self):
        self.base = APPLIANCE_URL.rstrip("/")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            verify=False, timeout=httpx.Timeout(60.0),
            headers={"Authorization": f"Bearer {token()}",
                     "Content-Type": "application/json"})

    async def get(self, path: str) -> list[dict]:
        async with self._client() as c:
            r = await c.get(f"{self.base}/api/v1{path}")
            r.raise_for_status()
            body = r.json()
        result = body.get("result", [])
        return result if isinstance(result, list) else [result]

    async def post(self, path: str, payload: dict) -> Any:
        async with self._client() as c:
            r = await c.post(f"{self.base}/api/v1{path}", json=payload)
            if r.status_code >= 400:
                raise RuntimeError(f"{r.status_code}: {r.text[:300]}")
            body = r.json()
        return body.get("result", body)

    async def find(self, path: str, field: str, value: str) -> dict | None:
        for row in await self.get(path):
            if isinstance(row, dict) and row.get(field) == value:
                return row
        return None


# --- item definitions -------------------------------------------------------
#
# Each entry: key, label, group, endpoint, name_field, name, payload builder, and an optional
# `activity` predicate that promotes "configured" to "active"/"error".

CRED_PATH = "/settings/credential-profiles"
DISCOVERY_PATH = "/settings/discoveries"
PARSER_PATH = "/settings/log-parsers"
POLICY_PATH = "/settings/metric-policies"

DB_SPECS = {
    "postgresql": ("PostgreSQL", "Database", 5432, "shopverse-postgres"),
    "mysql": ("MySQL", "Database", 3306, "shopverse-mysql"),
    "mongodb": ("MongoDB", "Database", 27017, "shopverse-mongo"),
}


def _cred_payload(name: str, protocol: str, ctx: dict) -> dict:
    return {"credential.profile.name": name,
            "credential.profile.protocol": protocol,
            "credential.profile.context": ctx}


def _discovery_payload(name, obj_type, category, port, cred_id) -> dict:
    return {
        "discovery.name": name,
        "discovery.type": "ip.address",
        "discovery.target": TARGET_HOST,
        "discovery.target.name": TARGET_HOST,
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


def _policy_payload(name, metric, condition, threshold) -> dict:
    return {
        "policy.name": name,
        "policy.type": "Metric Threshold",
        "policy.state": "yes",
        "policy.title": "$$$severity$$$ - $$$object.name$$$",
        "policy.message": ("$$$counter$$$ has entered into $$$severity$$$ state with value "
                           "$$$value$$$ on $$$object.host$$$($$$object.ip$$$)"),
        "policy.context": {
            "metric": metric,
            "filters": {"data.filter": {}},
            "entities": [],
            "policy.severity": {"CRITICAL": {"policy.condition": condition,
                                             "policy.threshold": threshold}},
            "policy.trigger.time": 300,
            "policy.trigger.occurrences": 1,
            "policy.auto.clear.timer.seconds": 0,
        },
        "policy.actions": {"Integration": {}, "Notification": {"Email": {}, "channels": {}}},
        "policy.archived": "no",
        "policy.renotify": "no",
        "policy.scheduled": "no",
    }


LOG_PARSER_PAYLOAD = {
    "log.parser.name": "ShopVerse JSON",
    "log.parser.type": "json",
    "log.parser.source.type": "Other",
    "log.parser.condition": "all",
    "log.parser.condition.keywords": [],
    "log.parser.date.time.format": "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
    "log.parser.date.time.formatter.type": "formatter",
    "log.parser.fields": [
        {"log.parser.field.name": f, "log.parser.field.type": t, "log.parser.field.value": ""}
        for f, t in [("ts", "timestamp"), ("level", "none"), ("svc", "none"), ("msg", "none"),
                     ("trace_id", "none"), ("status", "none"), ("latency_ms", "none"),
                     ("order_id", "none"), ("user_id", "none")]
    ],
}


def build_items(credentials: dict, databases: list[str]) -> list[dict]:
    """Declare every appliance object, in dependency order."""
    items: list[dict] = []

    creds = [
        ("shopverse-linux-ssh", "SSH", "Linux host over SSH",
         {"username": credentials.get("ssh_user", "motadata"),
          "password": credentials.get("ssh_password", "motadata"), "cli.enabled": "no"}),
        ("shopverse-snmp", "SNMP V1/V2c", "Host + simulated devices over SNMP",
         {"snmp.version": "v2c", "community": credentials.get("snmp_community", "shopverse")}),
    ]
    for db in databases:
        if db in DB_SPECS:
            _, _, _, cred_name = DB_SPECS[db]
            creds.append((cred_name, "JDBC", f"{db} over JDBC",
                          {"username": credentials.get(f"{db}_user", "shop"),
                           "password": credentials.get(f"{db}_password", "shoppass")}))

    for name, protocol, desc, ctx in creds:
        items.append({
            "key": f"cred:{name}", "label": name, "group": "Credentials", "desc": desc,
            "path": CRED_PATH, "name_field": "credential.profile.name", "name": name,
            "payload": _cred_payload(name, protocol, ctx), "depends_on": None,
        })

    targets = [("shopverse-host-linux", "Linux", "Server", 22, "shopverse-linux-ssh",
                "ShopVerse VM as a Linux monitor"),
               ("shopverse-host-snmp", "Linux (SNMP)", "Network", 161, "shopverse-snmp",
                "ShopVerse VM over SNMP")]
    for db in databases:
        if db in DB_SPECS:
            obj_type, category, port, cred_name = DB_SPECS[db]
            targets.append((f"shopverse-{db}", obj_type, category, port, cred_name,
                            f"{obj_type} database monitor"))

    for name, obj_type, category, port, cred_name, desc in targets:
        items.append({
            "key": f"discovery:{name}", "label": name, "group": "Discovery", "desc": desc,
            "path": DISCOVERY_PATH, "name_field": "discovery.name", "name": name,
            "payload": None,  # needs the credential id, resolved at create time
            "discovery": {"obj_type": obj_type, "category": category, "port": port,
                          "cred_name": cred_name},
            "depends_on": f"cred:{cred_name}",
        })

    items.append({
        "key": "parser:shopverse-json", "label": "ShopVerse JSON", "group": "Log",
        "desc": "Parses the service log schema (trace_id, svc, order_id)",
        "path": PARSER_PATH, "name_field": "log.parser.name", "name": "ShopVerse JSON",
        "payload": LOG_PARSER_PAYLOAD, "depends_on": None,
    })

    for name, metric, cond, thr, desc in [
        ("shopverse-cpu-critical", "system.cpu.percent", ">=", "85", "CPU ≥ 85%"),
        ("shopverse-memory-critical", "system.memory.used.percent", ">=", "90", "Memory ≥ 90%"),
        ("shopverse-disk-critical", "system.disk.used.percent", ">=", "85", "Disk ≥ 85%"),
    ]:
        items.append({
            "key": f"policy:{name}", "label": name, "group": "Policies", "desc": desc,
            "path": POLICY_PATH, "name_field": "policy.name", "name": name,
            "payload": _policy_payload(name, metric, cond, thr), "depends_on": None,
        })

    return items


def _state_of(item: dict, row: dict | None) -> tuple[str, str]:
    """Map an appliance row onto a UI state plus a short detail string."""
    if row is None:
        return NOT_CONFIGURED, "not created yet"

    if item["group"] == "Discovery":
        status = str(row.get("discovery.status") or "")
        found = row.get("discovery.discovered.objects")
        failed = row.get("discovery.failed.objects")
        if row.get("state") == "Running":
            return ACTIVE, "discovery running"
        if found:
            return ACTIVE, f"{found} object(s) discovered"
        if failed:
            return ERROR, f"{failed} target(s) failed — check credentials/reachability"
        if status:
            return CONFIGURED, status
        return CONFIGURED, "never run"

    if item["group"] == "Policies":
        return (ACTIVE, "enabled") if row.get("policy.state") == "yes" else (CONFIGURED, "disabled")

    if item["group"] == "Credentials":
        used = row.get("count")
        if used:
            return ACTIVE, f"used by {used} object(s)"
        return CONFIGURED, "created, not used yet"

    if item["group"] == "Log":
        entities = row.get("log.parser.entities") or []
        if entities:
            return ACTIVE, f"parsing from {len(entities)} source(s)"
        return CONFIGURED, "no log sources yet"

    return CONFIGURED, "exists"


async def status(credentials: dict, databases: list[str]) -> dict:
    items = build_items(credentials, databases)
    if not token():
        return {
            "appliance": configured_appliance(),
            "reachable": False,
            "message": "no personal access token set — add one to query the appliance",
            "items": [{**{k: i[k] for k in ("key", "label", "group", "desc")},
                       "state": UNKNOWN, "detail": "no token"} for i in items],
            "summary": {UNKNOWN: len(items)},
        }

    client = MotaClient()
    cache: dict[str, list[dict]] = {}
    reachable = True
    message = ""
    out = []
    for item in items:
        path = item["path"]
        if path not in cache:
            try:
                cache[path] = await client.get(path)
            except Exception as e:  # noqa: BLE001 — surface, don't crash the board
                cache[path] = []
                reachable = False
                message = f"{type(e).__name__} querying {path}"
        row = next((r for r in cache[path]
                    if isinstance(r, dict) and r.get(item["name_field"]) == item["name"]), None)
        state, detail = (_state_of(item, row) if reachable or cache[path]
                         else (UNKNOWN, "appliance unreachable"))
        out.append({**{k: item[k] for k in ("key", "label", "group", "desc")},
                    "state": state, "detail": detail,
                    "id": (row or {}).get("id")})

    summary: dict[str, int] = {}
    for entry in out:
        summary[entry["state"]] = summary.get(entry["state"], 0) + 1
    return {"appliance": configured_appliance(), "reachable": reachable,
            "message": message, "items": out, "summary": summary}


async def configure(credentials: dict, databases: list[str], only: str | None = None) -> dict:
    """Create missing objects. `only` restricts to a single item key."""
    if not token():
        raise RuntimeError("no personal access token set")

    client = MotaClient()
    items = build_items(credentials, databases)
    cred_ids: dict[str, int] = {}
    created, skipped, failed = [], [], []

    for item in items:
        # Credentials are always processed so their ids are available to discoveries.
        if only and item["key"] != only and not item["key"].startswith("cred:"):
            continue

        try:
            existing = await client.find(item["path"], item["name_field"], item["name"])
            if existing:
                if item["key"].startswith("cred:"):
                    cred_ids[item["name"]] = existing.get("id")
                if only and item["key"] != only:
                    continue
                skipped.append(item["key"])
                continue

            if only and item["key"] != only:
                continue  # a missing credential a targeted item depends on is created below

            payload = item.get("payload")
            if payload is None and "discovery" in item:
                d = item["discovery"]
                cred_id = cred_ids.get(d["cred_name"])
                if cred_id is None:
                    found = await client.find(CRED_PATH, "credential.profile.name", d["cred_name"])
                    cred_id = (found or {}).get("id")
                if cred_id is None:
                    failed.append({"key": item["key"],
                                   "error": f"credential {d['cred_name']} missing"})
                    continue
                payload = _discovery_payload(item["name"], d["obj_type"], d["category"],
                                             d["port"], cred_id)

            result = await client.post(item["path"], payload)
            new_id = result.get("id") if isinstance(result, dict) else None
            if item["key"].startswith("cred:") and new_id:
                cred_ids[item["name"]] = new_id
            created.append(item["key"])
        except Exception as e:  # noqa: BLE001 — one bad object must not stop the rest
            failed.append({"key": item["key"], "error": str(e)[:300]})

    return {"created": created, "skipped": skipped, "failed": failed,
            "counts": {"created": len(created), "skipped": len(skipped), "failed": len(failed)}}


async def run_discovery(name: str) -> dict:
    """Kick off a discovery profile so its monitors get provisioned."""
    if not token():
        raise RuntimeError("no personal access token set")
    client = MotaClient()
    row = await client.find(DISCOVERY_PATH, "discovery.name", name)
    if not row:
        raise RuntimeError(f"discovery profile {name!r} not found")
    return await client.post(f"{DISCOVERY_PATH}/{row['id']}/run", {})
