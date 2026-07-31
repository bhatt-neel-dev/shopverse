"""Redis db 1 fault-injection flags per docs/CONTRACTS.md §fault-injection."""

import os

import redis.asyncio as aioredis

SERVICES = ["catalog", "order", "cart", "search", "payment", "storefront"]
FLAG_KINDS = ("error_rate", "latency_ms")

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")

_client: aioredis.Redis | None = None


def client() -> aioredis.Redis:
    global _client
    if _client is None:
        _client = aioredis.from_url(REDIS_URL, db=1, decode_responses=True)
    return _client


def key(svc: str, kind: str) -> str:
    return f"inject:{svc}:{kind}"


async def get_all_flags() -> dict:
    keys = [key(svc, kind) for svc in SERVICES for kind in FLAG_KINDS]
    values = await client().mget(keys)
    it = iter(values)
    return {
        svc: {kind: int(v) if (v := next(it)) is not None else 0 for kind in FLAG_KINDS}
        for svc in SERVICES
    }


async def set_flags(svc: str, error_rate: int | None = None, latency_ms: int | None = None) -> None:
    r = client()
    if error_rate is not None:
        await r.set(key(svc, "error_rate"), error_rate)
    if latency_ms is not None:
        await r.set(key(svc, "latency_ms"), latency_ms)


async def clear_flags(svc: str) -> None:
    await client().delete(*(key(svc, kind) for kind in FLAG_KINDS))


async def snapshot(svcs: list[str]) -> dict[str, str | None]:
    keys = [key(svc, kind) for svc in svcs for kind in FLAG_KINDS]
    values = await client().mget(keys)
    return dict(zip(keys, values))


async def restore(snap: dict[str, str | None]) -> None:
    r = client()
    for k, v in snap.items():
        if v is None:
            await r.delete(k)
        else:
            await r.set(k, v)
