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

import json
import os
from pathlib import Path
from typing import Any

import httpx

# Env values are only defaults — everything here is settable at runtime from the UI so a new
# appliance (or a moved ShopVerse host) needs no rebuild.
ENV_DEFAULTS = {
    "url": os.environ.get("MOTADATA_URL", "https://172.16.14.71"),
    # The host ShopVerse runs on, as Motadata should reach it.
    "target_host": os.environ.get("MOTADATA_TARGET_HOST", "172.20.21.25"),
    "token": os.environ.get("MOTADATA_PAT", ""),
}

# Survives container restarts; lives on the studio-data volume, never in the image or git.
SETTINGS_FILE = Path(os.environ.get("STUDIO_DATA_DIR", "/data")) / "motadata.json"

NOT_CONFIGURED, CONFIGURED, ACTIVE, ERROR, UNKNOWN = (
    "not_configured", "configured", "active", "error", "unknown")

_overrides: dict[str, str] = {}


def _load_overrides() -> None:
    try:
        if SETTINGS_FILE.exists():
            saved = json.loads(SETTINGS_FILE.read_text())
            _overrides.update({k: v for k, v in saved.items()
                               if k in ENV_DEFAULTS and isinstance(v, str) and v})
    except Exception:  # noqa: BLE001 — a corrupt settings file must not stop the API
        pass


def _save_overrides() -> None:
    try:
        SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(_overrides))
    except Exception:  # noqa: BLE001 — read-only volume just means settings are session-only
        pass


def _setting(key: str) -> str:
    return _overrides.get(key) or ENV_DEFAULTS[key]


def appliance_url() -> str:
    return _setting("url")


def target_host() -> str:
    return _setting("target_host")


def token() -> str:
    return _setting("token")


def set_settings(url: str | None = None, target_host_value: str | None = None,
                 token_value: str | None = None, reset: bool = False) -> dict:
    """Update any subset at runtime. `reset` drops overrides and falls back to env defaults."""
    if reset:
        _overrides.clear()
    for key, value in (("url", url), ("target_host", target_host_value),
                       ("token", token_value)):
        if value is None:
            continue
        cleaned = value.strip()
        if cleaned:
            _overrides[key] = cleaned.rstrip("/") if key == "url" else cleaned
        else:
            _overrides.pop(key, None)
    _save_overrides()
    return configured_appliance()


def set_token(token_value: str | None) -> dict:
    return set_settings(token_value=token_value)


def configured_appliance() -> dict:
    return {
        "url": appliance_url(),
        "target_host": target_host(),
        "has_token": bool(token()),
        "overridden": sorted(_overrides),
        "defaults": {"url": ENV_DEFAULTS["url"], "target_host": ENV_DEFAULTS["target_host"]},
    }


_load_overrides()


def _appliance_public(appliance: dict) -> dict:
    return {"id": appliance.get("id"), "name": appliance.get("name"),
            "url": appliance.get("url"), "target_host": appliance.get("target_host"),
            "has_token": bool(appliance.get("token"))}


def _archived(row: dict) -> bool:
    """Deleting a policy only archives it; an archived row must read as not configured."""
    return str(row.get("policy.archived", "no")).lower() == "yes"


class MotaClient:
    """Scoped to one appliance: {url, token, target_host}."""

    def __init__(self, appliance: dict):
        self.appliance = appliance
        self.base = str(appliance["url"]).rstrip("/")

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            verify=False, timeout=httpx.Timeout(60.0),
            headers={"Authorization": f"Bearer {self.appliance.get('token', '')}",
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
            if isinstance(row, dict) and row.get(field) == value and not _archived(row):
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

# object type, discovery category, port, credential key, database to connect to.
# PostgreSQL/MySQL refuse a connection without a database name — working discoveries on the
# appliance all carry one in discovery.context.
DB_SPECS = {
    "postgresql": ("PostgreSQL", "Database", 5432, "shopverse-postgres", "shopverse"),
    "mysql": ("MySQL", "Database", 3306, "shopverse-mysql", "shopverse"),
    "mongodb": ("MongoDB", "Database", 27017, "shopverse-mongo", "shopverse"),
}


def _cred_payload(name: str, protocol: str, ctx: dict) -> dict:
    return {"credential.profile.name": name,
            "credential.profile.protocol": protocol,
            "credential.profile.context": ctx}


def _discovery_payload(name, obj_type, category, port, cred_id, host,
                       database: str = "", ping_check: str = "yes") -> dict:
    context = {"port": port, "ping.check.status": ping_check,
               # the appliance's own profiles repeat the type inside the context
               "discovery.object.type": obj_type}
    if database:
        context["database"] = database
    return {
        "discovery.name": name,
        "discovery.type": "ip.address",
        "discovery.target": host,
        "discovery.target.name": host,
        "discovery.category": category,
        "discovery.object.type": obj_type,
        "discovery.context": context,
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


# A representative ShopVerse log line (docs/CONTRACTS.md). The API derives the parser from this
# sample, and rejects the create without it: 400 MD022 "Event is a required field".
_PARSER_SAMPLE = {
    "ts": "2026-08-04T10:00:00.123Z", "level": "INFO", "svc": "catalog",
    "msg": "GET /products 200", "trace_id": "3f1c9a52-0d2b-4f77-9a1e-6c2f0b8d4e11",
    "method": "GET", "path": "/products", "status": 200, "latency_ms": 12,
    "order_id": 1024, "user_id": 777,
}

LOG_PARSER_PAYLOAD = {
    "log.parser.name": "ShopVerse JSON",
    "log.parser.type": "json",
    "log.parser.event": json.dumps(_PARSER_SAMPLE),
    "log.parser.source.type": "Other",
    "log.parser.condition": "all",
    "log.parser.condition.keywords": [],
    "log.parser.upload": "no",
    "log.parser.date.time.format": "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
    "log.parser.date.time.formatter.type": "formatter",
    "log.parser.fields": [
        {"log.parser.field.name": f, "log.parser.field.type": t,
         "log.parser.field.value": str(_PARSER_SAMPLE[f])}
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
        # the community key is snmp.community — a plain "community" is silently accepted and
        # then sent as an EMPTY community, which every agent rejects
        ("shopverse-snmp", "SNMP V1/V2c", "Host + simulated devices over SNMP",
         {"snmp.version": "v2c",
          "snmp.community": credentials.get("snmp_community", "shopverse")}),
    ]
    for db in databases:
        if db in DB_SPECS:
            _, _, _, cred_name, _ = DB_SPECS[db]
            ctx = {"username": credentials.get(f"{db}_user", "shop"),
                   "password": credentials.get(f"{db}_password", "shoppass")}
            if db == "mongodb":
                # the root user created by MONGO_INITDB_* lives in the admin database
                ctx["database"] = "admin"
            creds.append((cred_name, "JDBC", f"{db} over JDBC", ctx))

    for name, protocol, desc, ctx in creds:
        items.append({
            "key": f"cred:{name}", "label": name, "group": "Credentials", "desc": desc,
            "path": CRED_PATH, "name_field": "credential.profile.name", "name": name,
            "payload": _cred_payload(name, protocol, ctx), "depends_on": None,
        })

    targets = [("shopverse-host-linux", "Linux", "Server", 22, "shopverse-linux-ssh",
                "ShopVerse VM as a Linux monitor", ""),
               ("shopverse-host-snmp", "Linux (SNMP)", "Network", 161, "shopverse-snmp",
                "ShopVerse VM over SNMP", "")]
    for db in databases:
        if db in DB_SPECS:
            obj_type, category, port, cred_name, database = DB_SPECS[db]
            targets.append((f"shopverse-{db}", obj_type, category, port, cred_name,
                            f"{obj_type} database monitor", database))

    for name, obj_type, category, port, cred_name, desc, database in targets:
        items.append({
            "key": f"discovery:{name}", "label": name, "group": "Discovery", "desc": desc,
            "path": DISCOVERY_PATH, "name_field": "discovery.name", "name": name,
            "payload": None,  # needs the credential id, resolved at create time
            "discovery": {"obj_type": obj_type, "category": category, "port": port,
                          "cred_name": cred_name, "database": database},
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


async def status(appliance: dict, databases: list[str], credentials: dict | None = None) -> dict:
    credentials = credentials or {}
    items = build_items(credentials, databases)
    if not appliance.get("token"):
        return {
            "appliance": _appliance_public(appliance),
            "reachable": False,
            "message": "no personal access token set — add one to query the appliance",
            "items": [{**{k: i[k] for k in ("key", "label", "group", "desc")},
                       "state": UNKNOWN, "detail": "no token"} for i in items],
            "summary": {UNKNOWN: len(items)},
        }

    client = MotaClient(appliance)
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
                    if isinstance(r, dict) and r.get(item["name_field"]) == item["name"]
                    and not _archived(r)), None)
        state, detail = (_state_of(item, row) if reachable or cache[path]
                         else (UNKNOWN, "appliance unreachable"))
        out.append({**{k: item[k] for k in ("key", "label", "group", "desc")},
                    "state": state, "detail": detail,
                    "id": (row or {}).get("id")})

    summary: dict[str, int] = {}
    for entry in out:
        summary[entry["state"]] = summary.get(entry["state"], 0) + 1
    return {"appliance": _appliance_public(appliance), "reachable": reachable,
            "message": message, "items": out, "summary": summary}


async def configure(appliance: dict, databases: list[str], only: str | None = None,
                    credentials: dict | None = None) -> dict:
    """Create missing objects on one appliance. `only` restricts to a single item key."""
    if not appliance.get("token"):
        raise RuntimeError("no personal access token set for this appliance")
    credentials = credentials or {}
    client = MotaClient(appliance)
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
                payload = _discovery_payload(
                    item["name"], d["obj_type"], d["category"], d["port"], cred_id,
                    appliance.get("target_host", ""), d.get("database", ""),
                    # DB profiles on the appliance all skip the ICMP pre-check
                    "no" if d.get("database") else "yes")

            result = await client.post(item["path"], payload)
            new_id = result.get("id") if isinstance(result, dict) else None
            if item["key"].startswith("cred:") and new_id:
                cred_ids[item["name"]] = new_id
            created.append(item["key"])
        except Exception as e:  # noqa: BLE001 — one bad object must not stop the rest
            failed.append({"key": item["key"], "error": str(e)[:300]})

    return {"created": created, "skipped": skipped, "failed": failed,
            "counts": {"created": len(created), "skipped": len(skipped), "failed": len(failed)}}


async def run_discovery(appliance: dict, name: str) -> dict:
    """Kick off a discovery profile so its monitors get provisioned."""
    if not appliance.get("token"):
        raise RuntimeError("no personal access token set for this appliance")
    client = MotaClient(appliance)
    row = await client.find(DISCOVERY_PATH, "discovery.name", name)
    if not row:
        raise RuntimeError(f"discovery profile {name!r} not found")
    return await client.post(f"{DISCOVERY_PATH}/{row['id']}/run", {})
