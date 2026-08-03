"""Chaos scenarios: stop real containers, auto-recover after a duration.

Uses the docker socket mounted into studio-api (see deploy/docker-compose.yml).
Each scenario is the ground truth for a Motadata alert: the exact stop/start
timestamps land in history.jsonl.
"""

import threading
import time

import docker

# scenario -> containers it takes down (names from deploy/docker-compose.yml)
SCENARIOS = {
    "payment-outage": ["shopverse-payment"],
    "db-outage": ["shopverse-mysql"],
    "cache-outage": ["shopverse-redis"],
    "queue-outage": ["shopverse-rabbitmq"],
    "search-outage": ["shopverse-mongo"],
}

MAX_DURATION_S = 1800

_client: docker.DockerClient | None = None
_lock = threading.Lock()
_active: dict[str, dict] = {}


def client() -> docker.DockerClient:
    global _client
    if _client is None:
        _client = docker.from_env()
    return _client


def start(scenario: str, duration_s: int) -> dict:
    if scenario not in SCENARIOS:
        raise ValueError(f"unknown scenario {scenario!r}; one of {sorted(SCENARIOS)}")
    duration_s = max(5, min(int(duration_s), MAX_DURATION_S))
    with _lock:
        if scenario in _active:
            raise RuntimeError(f"{scenario} already running")
        stopped = []
        for name in SCENARIOS[scenario]:
            container = client().containers.get(name)
            container.stop(timeout=5)
            stopped.append(name)
        timer = threading.Timer(duration_s, _recover, args=(scenario,))
        timer.daemon = True
        _active[scenario] = {
            "scenario": scenario,
            "containers": stopped,
            "started_at": time.time(),
            "duration_s": duration_s,
            "timer": timer,
        }
        timer.start()
    return status(scenario)


def stop(scenario: str) -> dict:
    with _lock:
        if scenario not in _active:
            raise RuntimeError(f"{scenario} is not running")
        _active[scenario]["timer"].cancel()
    _recover(scenario)
    return {"scenario": scenario, "state": "recovered"}


def _recover(scenario: str) -> None:
    with _lock:
        info = _active.pop(scenario, None)
    if not info:
        return
    for name in info["containers"]:
        try:
            client().containers.get(name).start()
        except Exception:  # noqa: BLE001 — best effort; container may be gone
            pass


def status(scenario: str) -> dict:
    info = _active.get(scenario)
    if not info:
        return {"scenario": scenario, "state": "idle"}
    remaining = info["duration_s"] - (time.time() - info["started_at"])
    return {
        "scenario": scenario,
        "state": "running",
        "containers": info["containers"],
        "remaining_s": max(0, round(remaining)),
    }


def list_all() -> dict:
    return {name: status(name) for name in SCENARIOS}
