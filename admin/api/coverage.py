"""Pipeline coverage scorecard (local edition).

Checks that every part of the stack is up and producing data. The Motadata
REST cross-check ("is the appliance actually receiving it?") is wired in
Phase C once forge/register.py holds appliance credentials.
"""

import asyncio
import os

import httpx

import injection

RABBIT_MGMT = os.environ.get("RABBIT_MGMT_URL", "http://rabbitmq:15672")
RABBIT_AUTH = (os.environ.get("RABBIT_USER", "shop"), os.environ.get("RABBIT_PASSWORD", "shoppass"))
LOCUST_URL = os.environ.get("LOCUST_URL", "http://locust:8089")

HEALTH_URLS = {
    "gateway": "http://gateway:8080/health",
    "catalog": "http://catalog:8081/health",
    "order": "http://order:8082/health",
    "cart": "http://cart:8083/health",
    "search": "http://search:8084/health",
    "payment": "http://payment:8085/health",
    "storefront": "http://storefront:3000/",
}


async def _check(client: httpx.AsyncClient, name: str, url: str) -> tuple[str, dict]:
    try:
        r = await client.get(url)
        ok = r.status_code < 500
        return name, {"ok": ok, "status": r.status_code}
    except Exception as e:  # noqa: BLE001 — any transport error means "down"
        return name, {"ok": False, "error": str(e)}


async def scorecard() -> dict:
    async with httpx.AsyncClient(timeout=3) as client:
        checks = dict(
            await asyncio.gather(*(_check(client, n, u) for n, u in HEALTH_URLS.items()))
        )

        _, locust = await _check(client, "locust", f"{LOCUST_URL}/stats/requests")
        if locust.get("ok"):
            try:
                stats = (await client.get(f"{LOCUST_URL}/stats/requests")).json()
                locust["user_count"] = stats.get("user_count")
                locust["state"] = stats.get("state")
            except Exception:  # noqa: BLE001
                pass
        checks["locust"] = locust

        try:
            r = await client.get(
                f"{RABBIT_MGMT}/api/queues/%2F/order.events", auth=RABBIT_AUTH
            )
            if r.status_code == 200:
                q = r.json()
                checks["rabbitmq"] = {
                    "ok": True,
                    "queue_depth": q.get("messages"),
                    "consumers": q.get("consumers"),
                }
            else:
                checks["rabbitmq"] = {"ok": r.status_code == 404, "status": r.status_code}
        except Exception as e:  # noqa: BLE001
            checks["rabbitmq"] = {"ok": False, "error": str(e)}

    flags = await injection.get_all_flags()
    active_flags = {
        svc: kinds for svc, kinds in flags.items() if any(v > 0 for v in kinds.values())
    }

    up = sum(1 for c in checks.values() if c.get("ok"))
    return {
        "up": up,
        "total": len(checks),
        "healthy": up == len(checks),
        "checks": checks,
        "active_injection_flags": active_flags,
        "motadata": {"ok": None, "note": "appliance cross-check lands with forge/register.py (Phase C)"},
    }
