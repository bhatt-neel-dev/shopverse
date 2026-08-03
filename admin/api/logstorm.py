"""Log storms: bursts of contract-format log lines through the studio-api
logger (stdout → docker → rsyslog/log pipeline), tagged with a storm id so
they are easy to isolate in Motadata."""

import logging
import threading
import uuid

logger = logging.getLogger("studio-api")

LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
}

MAX_COUNT = 100_000


def start(severity: str, pattern: str, count: int, interval_ms: int = 0) -> dict:
    severity = severity.upper()
    if severity not in LEVELS:
        raise ValueError(f"severity must be one of {sorted(LEVELS)}")
    count = max(1, min(int(count), MAX_COUNT))
    interval_ms = max(0, min(int(interval_ms), 10_000))
    storm_id = str(uuid.uuid4())[:8]

    def emit() -> None:
        stop = threading.Event()
        for i in range(count):
            extra = {"err": pattern} if severity == "ERROR" else {}
            logger.log(
                LEVELS[severity],
                f"logstorm {storm_id} [{i + 1}/{count}] {pattern}",
                extra=extra,
            )
            if interval_ms and i + 1 < count:
                stop.wait(interval_ms / 1000)

    thread = threading.Thread(target=emit, daemon=True, name=f"storm-{storm_id}")
    thread.start()
    return {"storm_id": storm_id, "severity": severity, "count": count, "interval_ms": interval_ms}
