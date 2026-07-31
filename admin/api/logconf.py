import json
import logging
import sys
from datetime import datetime, timezone

SVC = "studio-api"

_LEVEL_MAP = {"WARNING": "WARN", "CRITICAL": "ERROR"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": _LEVEL_MAP.get(record.levelname, record.levelname),
            "svc": SVC,
            "msg": record.getMessage(),
            "trace_id": getattr(record, "trace_id", None),
            "method": getattr(record, "method", None),
            "path": getattr(record, "path", None),
            "status": getattr(record, "status", None),
            "latency_ms": getattr(record, "latency_ms", None),
            "order_id": None,
            "user_id": None,
        }
        err = getattr(record, "err", None)
        if err is None and record.exc_info and record.exc_info[1]:
            err = str(record.exc_info[1])
        if err is not None:
            line["err"] = err
        return json.dumps(line)


def setup_logging() -> logging.Logger:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(logging.INFO)
    # uvicorn's access log is replaced by the contract-format request log in main.py
    logging.getLogger("uvicorn.access").disabled = True
    return logging.getLogger(SVC)
