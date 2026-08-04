"""Ingestion control: push a chosen amount of each telemetry type into Motadata.

Two modes per data type:
  burst       N items spread evenly over a time window (paced, so the appliance sees a
              realistic distribution rather than one instantaneous spike)
  continuous  a steady rate that keeps running until stopped

Everything drives the REAL ShopVerse stack — journeys through the gateway, log lines emitted
by the services, traps from trapgen. Nothing is fabricated on the appliance side.
"""

from __future__ import annotations

import asyncio
import os
import random
import time
import uuid

import httpx

import injection
import journeys
import logstorm
import traps

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:8080")
STOREFRONT_URL = os.environ.get("STOREFRONT_URL", "http://storefront:3000")

# key -> (label, description, unit, how it reaches Motadata)
TYPES: dict[str, dict] = {
    "traces": {
        "label": "APM Traces",
        "desc": "Real checkout journeys through gateway → cart → order → payment → queue",
        "unit": "journeys",
        "pipeline": "APM (agent, ports 9474/9433)",
    },
    "logs": {
        "label": "Logs",
        "desc": "Structured JSON log lines emitted by the services themselves",
        "unit": "lines",
        "pipeline": "Log (syslog / agent tail)",
    },
    "metrics": {
        "label": "Metrics",
        "desc": "Drives CPU/memory/IO on the host so polled counters actually move",
        "unit": "load pulses",
        "pipeline": "Metric (SSH/SNMP polling)",
    },
    "rum": {
        "label": "RUM Sessions",
        "desc": "Storefront page loads — browse, product, cart, checkout",
        "unit": "page views",
        "pipeline": "RUM (browser SDK)",
    },
    "alerts": {
        "label": "Alerts",
        "desc": "Injects service errors so metric/availability policies actually trip",
        "unit": "error windows",
        "pipeline": "Policy engine → Alerts",
    },
    "traps": {
        "label": "SNMP Traps",
        "desc": "Vendor trap replays (linkDown, UPS on battery, fan failure)",
        "unit": "traps",
        "pipeline": "Trap listener (UDP 1620/1630)",
    },
    "flows": {
        "label": "Flows",
        "desc": "Service-to-service traffic captured by softflowd as NetFlow",
        "unit": "conversations",
        "pipeline": "Flow (NetFlow :2055)",
    },
}

TIMEFRAMES = {
    "instant": 0,
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "6h": 21600,
    "24h": 86400,
}

_jobs: dict[str, dict] = {}          # burst runs, keyed by job id
_continuous: dict[str, dict] = {}    # one entry per data type


# --- emitters ---------------------------------------------------------------
# Each returns the number of items it actually produced.

async def _emit_traces(n: int) -> int:
    result = await journeys.run_bulk("checkout", n, min(n, 8), 0, 0, "studio-ingest")
    return int(result.get("ok", 0))


async def _emit_logs(n: int) -> int:
    logstorm.start("INFO", "studio ingestion sample", n, 0)
    return n


async def _emit_metrics(n: int) -> int:
    # Browse journeys are the cheapest way to make CPU/IO counters move on the host.
    result = await journeys.run_bulk("browse", max(n, 1), min(max(n, 1), 8), 0, 0, "studio-metrics")
    return int(result.get("ok", 0))


async def _emit_rum(n: int) -> int:
    paths = ["/", "/cart", "/checkout"] + [f"/product/{random.randint(1, 5000)}" for _ in range(3)]
    ok = 0
    async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as c:
        for _ in range(n):
            try:
                r = await c.get(f"{STOREFRONT_URL}{random.choice(paths)}",
                                headers={"X-Trace-Id": str(uuid.uuid4())})
                ok += 1 if r.status_code < 500 else 0
            except Exception:  # noqa: BLE001 — a failed page view is still a real outcome
                pass
    return ok


async def _emit_alerts(n: int) -> int:
    """One 'item' = one error window: turn a service red, drive traffic, turn it back."""
    produced = 0
    for _ in range(n):
        svc = random.choice(["payment", "catalog", "search"])
        await injection.set_flags(svc, error_rate=100, latency_ms=None)
        try:
            await journeys.run_bulk("checkout", 5, 3, 0, 0, "studio-alert")
            produced += 1
        finally:
            await injection.clear_flags(svc)
    return produced


async def _emit_traps(n: int) -> int:
    if not await traps.available():
        raise RuntimeError("trapgen not running — start the device overlay "
                           "(docker-compose.devices.yml)")
    trap = random.choice(["linkDown", "linkUp", "upsOnBattery", "fanFailure"])
    await traps.burst(trap, n, 0.05)
    return n


async def _emit_flows(n: int) -> int:
    # Flow records come from real socket traffic; mixed journeys create varied conversations.
    total = 0
    for journey in ("browse", "search", "checkout"):
        share = max(1, n // 3)
        result = await journeys.run_bulk(journey, share, min(share, 6), 0, 0, "studio-flows")
        total += int(result.get("ok", 0))
    return total


EMITTERS = {
    "traces": _emit_traces,
    "logs": _emit_logs,
    "metrics": _emit_metrics,
    "rum": _emit_rum,
    "alerts": _emit_alerts,
    "traps": _emit_traps,
    "flows": _emit_flows,
}


# --- burst ------------------------------------------------------------------

def _chunks(total: int, slices: int) -> list[int]:
    """Split `total` into `slices` near-equal positive chunks."""
    slices = max(1, min(slices, total))
    base, extra = divmod(total, slices)
    return [base + (1 if i < extra else 0) for i in range(slices)]


async def _run_burst(job: dict) -> None:
    emit = EMITTERS[job["type"]]
    window = job["timeframe_s"]
    # Aim for a pulse roughly every 10s in a window; instant = one shot.
    slices = 1 if window <= 0 else max(1, min(job["count"], int(window // 10) or 1))
    parts = _chunks(job["count"], slices)
    gap = (window / len(parts)) if window > 0 else 0

    try:
        for index, part in enumerate(parts):
            if job["state"] != "running":
                break
            produced = await emit(part)
            job["produced"] += produced
            job["pulses"] += 1
            if gap and index < len(parts) - 1:
                await asyncio.sleep(gap)
        job["state"] = "done" if job["state"] == "running" else job["state"]
    except Exception as e:  # noqa: BLE001 — surface on the job, never crash the API
        job["state"] = "error"
        job["error"] = str(e)[:300]
    finally:
        job["finished_at"] = time.time()


def start_burst(data_type: str, count: int, timeframe: str) -> dict:
    if data_type not in EMITTERS:
        raise ValueError(f"unknown type {data_type!r}; one of {sorted(EMITTERS)}")
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unknown timeframe {timeframe!r}; one of {sorted(TIMEFRAMES)}")
    job_id = uuid.uuid4().hex[:10]
    job = {
        "id": job_id, "type": data_type, "count": count, "timeframe": timeframe,
        "timeframe_s": TIMEFRAMES[timeframe], "produced": 0, "pulses": 0,
        "state": "running", "error": None,
        "started_at": time.time(), "finished_at": None,
    }
    _jobs[job_id] = job
    job["task"] = asyncio.create_task(_run_burst(job))
    return public_job(job)


def stop_burst(job_id: str) -> dict:
    job = _jobs.get(job_id)
    if not job:
        raise KeyError(job_id)
    if job["state"] == "running":
        job["state"] = "stopped"
        task = job.get("task")
        if task:
            task.cancel()
    return public_job(job)


def public_job(job: dict) -> dict:
    return {k: v for k, v in job.items() if k != "task"}


# --- continuous -------------------------------------------------------------

async def _run_continuous(entry: dict) -> None:
    emit = EMITTERS[entry["type"]]
    while entry["enabled"]:
        cycle_started = time.monotonic()
        try:
            produced = await emit(entry["batch"])
            entry["produced"] += produced
            entry["cycles"] += 1
            entry["error"] = None
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — keep the feed alive across transient failures
            entry["error"] = str(e)[:200]
        elapsed = time.monotonic() - cycle_started
        await asyncio.sleep(max(1.0, entry["interval_s"] - elapsed))


def set_continuous(data_type: str, enabled: bool, per_minute: int = 60) -> dict:
    if data_type not in EMITTERS:
        raise ValueError(f"unknown type {data_type!r}; one of {sorted(EMITTERS)}")

    existing = _continuous.get(data_type)
    if existing and existing.get("task"):
        existing["enabled"] = False
        existing["task"].cancel()

    if not enabled:
        entry = existing or {"type": data_type, "produced": 0, "cycles": 0}
        entry.update({"enabled": False, "task": None, "error": None})
        _continuous[data_type] = entry
        return public_continuous(entry)

    per_minute = max(1, min(per_minute, 6000))
    # One cycle every 10s keeps each batch small and the feed smooth.
    batch = max(1, round(per_minute / 6))
    entry = {
        "type": data_type, "enabled": True, "per_minute": per_minute,
        "batch": batch, "interval_s": 10.0,
        "produced": (existing or {}).get("produced", 0),
        "cycles": (existing or {}).get("cycles", 0),
        "error": None, "started_at": time.time(),
    }
    _continuous[data_type] = entry
    entry["task"] = asyncio.create_task(_run_continuous(entry))
    return public_continuous(entry)


def public_continuous(entry: dict) -> dict:
    return {k: v for k, v in entry.items() if k != "task"}


def status() -> dict:
    jobs = sorted((public_job(j) for j in _jobs.values()),
                  key=lambda j: j["started_at"], reverse=True)[:20]
    return {
        "types": [{"key": k, **v,
                   "continuous": public_continuous(_continuous[k]) if k in _continuous else None}
                  for k, v in TYPES.items()],
        "timeframes": sorted(TIMEFRAMES, key=lambda t: TIMEFRAMES[t]),
        "jobs": jobs,
        "running": sum(1 for j in _jobs.values() if j["state"] == "running"),
    }
