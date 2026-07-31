import asyncio
import json
import os
import random
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import redis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo import MongoClient, TEXT

SVC = os.environ.get("SVC_NAME", "search")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://mongo:27017/shopverse")
REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")

mongo = MongoClient(MONGO_URL, serverSelectionTimeoutMS=2000)
products = mongo.get_default_database()["products"]
inject_r = redis.Redis.from_url(REDIS_URL, db=1, socket_timeout=1, socket_connect_timeout=1)


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def log_line(level, msg, trace_id=None, method=None, path=None, status=None, latency_ms=None, err=None):
    line = {
        "ts": _ts(),
        "level": level,
        "svc": SVC,
        "msg": msg,
        "trace_id": trace_id,
        "method": method,
        "path": path,
        "status": status,
        "latency_ms": latency_ms,
        "order_id": None,
        "user_id": None,
    }
    if err:
        line["err"] = err
    print(json.dumps(line), flush=True)


@asynccontextmanager
async def lifespan(_app):
    # create_index is a no-op when an identical index already exists
    try:
        products.create_index(
            [("name", TEXT), ("description", TEXT), ("category", TEXT)],
            name="products_text",
        )
    except Exception as e:
        log_line("ERROR", "failed to ensure text index", err=str(e))
    yield


app = FastAPI(lifespan=lifespan)

_inject_cache: dict[str, tuple[int, float]] = {}


def _inject_val(key: str) -> int:
    now = time.monotonic()
    hit = _inject_cache.get(key)
    if hit and now - hit[1] < 2.0:
        return hit[0]
    try:
        val = int(inject_r.get(key) or 0)
    except Exception:
        val = 0
    _inject_cache[key] = (val, now)
    return val


@app.middleware("http")
async def contract_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
    request.state.trace_id = trace_id
    start = time.monotonic()
    err = None
    if random.random() * 100 < _inject_val(f"inject:{SVC}:error_rate"):
        err = "injected"
        response = JSONResponse({"error": "injected", "trace_id": trace_id}, status_code=500)
    else:
        latency = _inject_val(f"inject:{SVC}:latency_ms")
        if latency > 0:
            await asyncio.sleep(latency / 1000)
        try:
            response = await call_next(request)
        except Exception as e:
            err = str(e)
            response = JSONResponse({"error": str(e), "trace_id": trace_id}, status_code=500)
    status = response.status_code
    latency_ms = int((time.monotonic() - start) * 1000)
    log_line(
        "ERROR" if status >= 500 else "INFO",
        f"{request.method} {request.url.path} {status}",
        trace_id=trace_id,
        method=request.method,
        path=request.url.path,
        status=status,
        latency_ms=latency_ms,
        err=err,
    )
    return response


_FIELDS = {"_id": 0, "id": 1, "name": 1, "price": 1, "category": 1}


def _row(doc, score=None):
    price = doc.get("price")
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None
    return {
        "id": doc.get("id"),
        "name": doc.get("name"),
        "price": price,
        "category": doc.get("category"),
        "score": score,
    }


@app.get("/search")
def search(request: Request, q: str = ""):
    if q.strip():
        cursor = (
            products.find({"$text": {"$search": q}}, {**_FIELDS, "score": {"$meta": "textScore"}})
            .sort([("score", {"$meta": "textScore"})])
            .limit(20)
        )
        results = [_row(d, score=d.get("score")) for d in cursor]
    else:
        results = [_row(d) for d in products.find({}, _FIELDS).limit(20)]
    return {"query": q, "results": results, "trace_id": request.state.trace_id}


@app.get("/health")
def health(request: Request):
    try:
        mongo.admin.command("ping")
        return {"status": "ok", "svc": SVC, "trace_id": request.state.trace_id}
    except Exception as e:
        return JSONResponse(
            {"status": "error", "svc": SVC, "err": str(e), "trace_id": request.state.trace_id},
            status_code=503,
        )
