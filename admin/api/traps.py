"""Trap bursts — drives the trapgen sidecar (deploy/devices/trapgen).

Only available when the Phase C device overlay is running
(docker compose -f docker-compose.yml -f docker-compose.devices.yml up -d).
"""

import os

import httpx

TRAPGEN_URL = os.environ.get("TRAPGEN_URL", "http://trapgen:7070")

KNOWN_TRAPS = [
    "linkDown", "linkUp", "coldStart", "authFailure",
    "upsOnBattery", "upsLowBattery", "fanFailure", "tempHigh",
]


async def available() -> bool:
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            return (await c.get(TRAPGEN_URL)).status_code == 200
    except Exception:  # noqa: BLE001 — overlay not running
        return False


async def burst(trap: str, count: int, interval_s: float) -> dict:
    if trap not in KNOWN_TRAPS:
        raise ValueError(f"unknown trap {trap!r}; one of {KNOWN_TRAPS}")
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.post(TRAPGEN_URL, json={"trap": trap, "count": count,
                                            "interval": interval_s})
        r.raise_for_status()
        return r.json()
