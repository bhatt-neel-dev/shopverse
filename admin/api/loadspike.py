"""Load spikes via the Locust REST API: ramp user count up by a magnitude,
hold for a duration, then restore the pre-spike state."""

import os
import threading
import time

import httpx

LOCUST_URL = os.environ.get("LOCUST_URL", "http://locust:8089")
BASELINE_USERS = int(os.environ.get("BASELINE_USERS", "5"))
MAX_USERS = 500
MAX_DURATION_S = 3600

_lock = threading.Lock()
_active: dict | None = None


def _swarm(user_count: int) -> None:
    httpx.post(
        f"{LOCUST_URL}/swarm",
        data={"user_count": user_count, "spawn_rate": max(1, user_count // 5)},
        timeout=5,
    ).raise_for_status()


def _current_users() -> int:
    stats = httpx.get(f"{LOCUST_URL}/stats/requests", timeout=5).json()
    return int(stats.get("user_count") or 0)


def start(magnitude: float, duration_s: int) -> dict:
    global _active
    magnitude = max(1.1, min(float(magnitude), 50.0))
    duration_s = max(10, min(int(duration_s), MAX_DURATION_S))
    with _lock:
        if _active:
            raise RuntimeError("a spike is already running")
        baseline = _current_users() or BASELINE_USERS
        target = min(MAX_USERS, max(baseline + 1, round(baseline * magnitude)))
        _swarm(target)
        timer = threading.Timer(duration_s, _restore)
        timer.daemon = True
        _active = {
            "baseline_users": baseline,
            "target_users": target,
            "magnitude": magnitude,
            "duration_s": duration_s,
            "started_at": time.time(),
            "timer": timer,
        }
        timer.start()
    return status()


def stop() -> dict:
    with _lock:
        if not _active:
            raise RuntimeError("no spike is running")
        _active["timer"].cancel()
    _restore()
    return {"state": "restored"}


def _restore() -> None:
    global _active
    with _lock:
        info, _active = _active, None
    if not info:
        return
    try:
        _swarm(info["baseline_users"])
    except Exception:  # noqa: BLE001 — locust may be down; nothing to restore then
        pass


def status() -> dict:
    info = _active
    if not info:
        return {"state": "idle"}
    remaining = info["duration_s"] - (time.time() - info["started_at"])
    return {
        "state": "spiking",
        "baseline_users": info["baseline_users"],
        "target_users": info["target_users"],
        "magnitude": info["magnitude"],
        "remaining_s": max(0, round(remaining)),
    }
