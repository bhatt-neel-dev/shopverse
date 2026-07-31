"""Real user journeys fired against the gateway for bulk trace generation."""

import asyncio
import os
import random
import time
import uuid

import httpx

import injection

GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://gateway:8080")

# Services whose injection flags matter for each journey (checkout hits payment via order).
JOURNEY_SERVICES = {
    "browse": ["catalog"],
    "search": ["search"],
    "checkout": ["cart", "order", "payment"],
}

SEARCH_WORDS = [
    "laptop", "phone", "headphones", "camera", "monitor", "keyboard", "mouse",
    "chair", "desk", "lamp", "backpack", "watch", "speaker", "tablet", "charger",
]

REQUEST_TIMEOUT = httpx.Timeout(15.0)


async def _product_pool(client: httpx.AsyncClient) -> list[dict]:
    """Fetch real products once per run so checkout items carry real ids/prices."""
    try:
        r = await client.get(f"{GATEWAY_URL}/api/catalog/products", params={"limit": 100})
        data = r.json()
        products = data if isinstance(data, list) else data.get("products", [])
        pool = [
            {"id": p["id"], "price": float(p.get("price", 9.99))}
            for p in products
            if isinstance(p, dict) and "id" in p
        ]
        if pool:
            return pool
    except Exception:
        pass
    return [{"id": i, "price": round(random.uniform(5, 500), 2)} for i in range(1, 101)]


async def _run_one(client: httpx.AsyncClient, journey: str, pool: list[dict], tag: str) -> bool:
    headers = {"X-Trace-Id": str(uuid.uuid4())}
    if tag:
        headers["X-Load-Tag"] = tag
    statuses: list[int] = []

    if journey == "browse":
        r = await client.get(f"{GATEWAY_URL}/api/catalog/products",
                             params={"limit": 20}, headers=headers)
        statuses.append(r.status_code)
        pid = random.choice(pool)["id"]
        r = await client.get(f"{GATEWAY_URL}/api/catalog/products/{pid}", headers=headers)
        statuses.append(r.status_code)

    elif journey == "search":
        r = await client.get(f"{GATEWAY_URL}/api/search",
                             params={"q": random.choice(SEARCH_WORDS)}, headers=headers)
        statuses.append(r.status_code)

    else:  # checkout
        user_id = random.randint(1000, 1999)
        picks = random.sample(pool, k=min(len(pool), random.randint(1, 3)))
        items = []
        for p in picks:
            qty = random.randint(1, 3)
            r = await client.post(f"{GATEWAY_URL}/api/cart/{user_id}/items",
                                  json={"product_id": p["id"], "qty": qty}, headers=headers)
            statuses.append(r.status_code)
            items.append({"product_id": p["id"], "qty": qty, "price": p["price"]})
        r = await client.post(f"{GATEWAY_URL}/api/orders",
                              json={"user_id": user_id, "items": items}, headers=headers)
        statuses.append(r.status_code)

    # 5xx = failure (incl. injected errors); 402 payment-declined is a valid business outcome
    return all(s < 500 for s in statuses)


async def run_bulk(journey: str, count: int, concurrency: int,
                   error_rate: int, latency_ms: int, tag: str) -> dict:
    run_id = str(uuid.uuid4())
    touched = JOURNEY_SERVICES[journey]
    snap = None
    if error_rate or latency_ms:
        snap = await injection.snapshot(touched)
        for svc in touched:
            await injection.set_flags(
                svc,
                error_rate=error_rate if error_rate else None,
                latency_ms=latency_ms if latency_ms else None,
            )

    sem = asyncio.Semaphore(concurrency)
    start = time.perf_counter()
    try:
        limits = httpx.Limits(max_connections=concurrency)
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT, limits=limits) as client:
            pool = await _product_pool(client)

            async def guarded() -> bool:
                async with sem:
                    try:
                        return await _run_one(client, journey, pool, tag)
                    except Exception:
                        return False

            results = await asyncio.gather(*(guarded() for _ in range(count)))
    finally:
        if snap is not None:
            await injection.restore(snap)

    ok = sum(results)
    return {
        "run_id": run_id,
        "journey": journey,
        "sent": count,
        "ok": ok,
        "failed": count - ok,
        "duration_s": round(time.perf_counter() - start, 2),
    }
