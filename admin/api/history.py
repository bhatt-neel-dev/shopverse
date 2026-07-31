import json
import os
from datetime import datetime, timezone

HISTORY_PATH = os.environ.get("HISTORY_PATH", "/data/history.jsonl")


def append(action: str, params: dict, result: dict) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "action": action,
        "params": params,
        "result": result,
    }
    os.makedirs(os.path.dirname(HISTORY_PATH), exist_ok=True)
    with open(HISTORY_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


def last(n: int = 200) -> list[dict]:
    if not os.path.exists(HISTORY_PATH):
        return []
    entries = []
    with open(HISTORY_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries[-n:][::-1]
