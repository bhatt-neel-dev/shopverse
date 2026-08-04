"""Scenario Studio control plane — see admin/README.md and docs/PLAN.md Phase B."""

import time
import uuid

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

import chaos
import coverage
import history
import injection
import journeys
import loadspike
import logstorm
import motadata
import traps
from logconf import setup_logging

logger = setup_logging()

app = FastAPI(title="ShopVerse Scenario Studio", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def contract_middleware(request: Request, call_next):
    trace_id = request.headers.get("X-Trace-Id") or str(uuid.uuid4())
    request.state.trace_id = trace_id
    start = time.monotonic()
    err = None
    try:
        response = await call_next(request)
    except Exception as e:  # noqa: BLE001 — surface as contract-format 500
        err = str(e)
        response = JSONResponse({"error": str(e), "trace_id": trace_id}, status_code=500)
    status = response.status_code
    logger.info(
        f"{request.method} {request.url.path} {status}",
        extra={
            "trace_id": trace_id,
            "method": request.method,
            "path": request.url.path,
            "status": status,
            "latency_ms": int((time.monotonic() - start) * 1000),
            **({"err": err} if err else {}),
        },
    )
    response.headers["X-Trace-Id"] = trace_id
    return response


@app.get("/health")
async def health():
    return {"status": "ok", "svc": "studio-api"}


# ---- fault injection --------------------------------------------------------

class InjectBody(BaseModel):
    svc: str
    error_rate: int | None = Field(None, ge=0, le=100)
    latency_ms: int | None = Field(None, ge=0, le=60_000)


@app.get("/inject")
async def get_inject():
    return await injection.get_all_flags()


@app.post("/inject")
async def set_inject(body: InjectBody):
    if body.svc not in injection.SERVICES:
        raise HTTPException(400, f"unknown svc {body.svc!r}; one of {injection.SERVICES}")
    await injection.set_flags(body.svc, body.error_rate, body.latency_ms)
    flags = await injection.get_all_flags()
    history.append("inject", body.model_dump(), flags[body.svc])
    return {body.svc: flags[body.svc]}


@app.post("/inject/clear")
async def clear_inject(svc: str | None = None):
    targets = [svc] if svc else injection.SERVICES
    for s in targets:
        if s not in injection.SERVICES:
            raise HTTPException(400, f"unknown svc {s!r}")
        await injection.clear_flags(s)
    history.append("inject.clear", {"svc": svc or "all"}, {"cleared": targets})
    return {"cleared": targets}


# ---- bulk trace generation --------------------------------------------------

class BulkTracesBody(BaseModel):
    journey: str = "checkout"
    count: int = Field(50, ge=1, le=5000)
    concurrency: int = Field(10, ge=1, le=100)
    error_rate: int = Field(0, ge=0, le=100)
    latency_ms: int = Field(0, ge=0, le=60_000)
    tag: str = "studio-bulk"


@app.post("/traces/bulk")
async def traces_bulk(body: BulkTracesBody):
    if body.journey not in journeys.JOURNEY_SERVICES:
        raise HTTPException(
            400, f"unknown journey {body.journey!r}; one of {sorted(journeys.JOURNEY_SERVICES)}"
        )
    result = await journeys.run_bulk(
        body.journey, body.count, body.concurrency, body.error_rate, body.latency_ms, body.tag
    )
    history.append("traces.bulk", body.model_dump(), result)
    return result


# ---- load spike -------------------------------------------------------------

class SpikeBody(BaseModel):
    magnitude: float = Field(2.0, ge=1.1, le=50)
    duration_s: int = Field(120, ge=10, le=3600)


@app.post("/load/spike")
async def load_spike(body: SpikeBody):
    try:
        result = loadspike.start(body.magnitude, body.duration_s)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except Exception as e:  # noqa: BLE001 — locust unreachable etc.
        raise HTTPException(502, f"locust error: {e}")
    history.append("load.spike", body.model_dump(), result)
    return result


@app.post("/load/spike/stop")
async def load_spike_stop():
    try:
        result = loadspike.stop()
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    history.append("load.spike.stop", {}, result)
    return result


@app.get("/load/spike")
async def load_spike_status():
    return loadspike.status()


# ---- log storm --------------------------------------------------------------

class StormBody(BaseModel):
    severity: str = "ERROR"
    pattern: str = "synthetic disk latency warning"
    count: int = Field(500, ge=1, le=100_000)
    interval_ms: int = Field(0, ge=0, le=10_000)


@app.post("/logs/storm")
async def logs_storm(body: StormBody):
    try:
        result = logstorm.start(body.severity, body.pattern, body.count, body.interval_ms)
    except ValueError as e:
        raise HTTPException(400, str(e))
    history.append("logs.storm", body.model_dump(), result)
    return result


# ---- chaos ------------------------------------------------------------------

class ChaosBody(BaseModel):
    duration_s: int = Field(120, ge=5, le=1800)


@app.get("/chaos")
async def chaos_list():
    return chaos.list_all()


@app.post("/chaos/{scenario}")
async def chaos_start(scenario: str, body: ChaosBody):
    try:
        result = chaos.start(scenario, body.duration_s)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    except Exception as e:  # noqa: BLE001 — docker socket problems
        raise HTTPException(502, f"docker error: {e}")
    history.append("chaos.start", {"scenario": scenario, **body.model_dump()}, result)
    return result


@app.post("/chaos/{scenario}/stop")
async def chaos_stop(scenario: str):
    try:
        result = chaos.stop(scenario)
    except RuntimeError as e:
        raise HTTPException(409, str(e))
    history.append("chaos.stop", {"scenario": scenario}, result)
    return result


# ---- trap bursts (Phase C device overlay) -----------------------------------

class TrapBody(BaseModel):
    trap: str = "linkDown"
    count: int = Field(1, ge=1, le=500)
    interval_s: float = Field(0.2, ge=0.0, le=10.0)


@app.get("/traps")
async def traps_status():
    return {"available": await traps.available(), "traps": traps.KNOWN_TRAPS}


@app.post("/traps/burst")
async def traps_burst(body: TrapBody):
    try:
        result = await traps.burst(body.trap, body.count, body.interval_s)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001 — trapgen not deployed
        raise HTTPException(502, f"trapgen unreachable ({e}); start the device overlay")
    history.append("traps.burst", body.model_dump(), result)
    return result


# ---- Motadata auto-configuration --------------------------------------------

DEFAULT_DATABASES = ["postgresql", "mysql", "mongodb"]


class MotadataSettingsBody(BaseModel):
    url: str | None = Field(None, description="appliance base URL, e.g. https://172.16.14.71")
    target_host: str | None = Field(None, description="host Motadata should monitor (the VM)")
    token: str | None = Field(None, description="personal access token")
    reset: bool = Field(False, description="drop overrides and fall back to env defaults")


class MotadataConfigureBody(BaseModel):
    only: str | None = Field(None, description="configure just this item key; omit for all")
    databases: list[str] = DEFAULT_DATABASES
    ssh_user: str = "motadata"
    ssh_password: str = "motadata"
    snmp_community: str = "shopverse"

    def credentials(self) -> dict:
        return {"ssh_user": self.ssh_user, "ssh_password": self.ssh_password,
                "snmp_community": self.snmp_community}


@app.get("/motadata/status")
async def motadata_status(databases: str = ",".join(DEFAULT_DATABASES)):
    dbs = [d.strip() for d in databases.split(",") if d.strip()]
    return await motadata.status({}, dbs)


@app.get("/motadata/settings")
async def motadata_get_settings():
    return motadata.configured_appliance()


@app.post("/motadata/settings")
async def motadata_set_settings(body: MotadataSettingsBody):
    result = motadata.set_settings(url=body.url, target_host_value=body.target_host,
                                   token_value=body.token, reset=body.reset)
    # never log the token itself
    history.append("motadata.settings",
                   {"url": body.url, "target_host": body.target_host,
                    "token_set": bool(body.token), "reset": body.reset},
                   {k: v for k, v in result.items() if k != "defaults"})
    return result


@app.post("/motadata/token")
async def motadata_token(body: MotadataSettingsBody):
    """Kept for compatibility — same as POST /motadata/settings with only a token."""
    result = motadata.set_token(body.token)
    history.append("motadata.token", {"set": bool(body.token)}, {"has_token": result["has_token"]})
    return result


@app.post("/motadata/configure")
async def motadata_configure(body: MotadataConfigureBody):
    try:
        result = await motadata.configure(body.credentials(), body.databases, body.only)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001 — appliance unreachable etc.
        raise HTTPException(502, f"appliance error: {e}")
    history.append("motadata.configure", body.model_dump(), result["counts"])
    return result


@app.post("/motadata/discovery/{name}/run")
async def motadata_run_discovery(name: str):
    try:
        result = await motadata.run_discovery(name)
    except RuntimeError as e:
        raise HTTPException(400, str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"appliance error: {e}")
    history.append("motadata.discovery.run", {"name": name}, result or {"started": True})
    return {"started": name}


# ---- coverage + history -----------------------------------------------------

@app.get("/coverage")
async def get_coverage():
    return await coverage.scorecard()


@app.get("/history")
async def get_history(n: int = 200):
    return history.last(min(max(n, 1), 1000))
