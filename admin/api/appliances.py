"""Registry of Motadata appliances the Studio can drive.

Multiple appliances, each with its own URL, PAT and monitored host. Persisted to the
studio-data volume so they survive restarts; tokens never enter the image or git.
"""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

STORE = Path(os.environ.get("STUDIO_DATA_DIR", "/data")) / "appliances.json"

# Seeded from env on first run so a fresh deployment already has one entry to click into.
SEED = {
    "name": os.environ.get("MOTADATA_NAME", "Primary appliance"),
    "url": os.environ.get("MOTADATA_URL", "https://172.16.14.71"),
    "target_host": os.environ.get("MOTADATA_TARGET_HOST", "172.20.21.25"),
    "token": os.environ.get("MOTADATA_PAT", ""),
}

_items: dict[str, dict] = {}
_loaded = False


def _persist() -> None:
    try:
        STORE.parent.mkdir(parents=True, exist_ok=True)
        STORE.write_text(json.dumps(_items, indent=1))
    except Exception:  # noqa: BLE001 — a read-only volume just makes this session-only
        pass


def _load() -> None:
    global _loaded
    if _loaded:
        return
    _loaded = True
    try:
        if STORE.exists():
            saved = json.loads(STORE.read_text())
            if isinstance(saved, dict):
                _items.update(saved)
    except Exception:  # noqa: BLE001 — corrupt store must not stop the API
        pass
    if not _items and SEED["url"]:
        add(SEED["name"], SEED["url"], SEED["target_host"], SEED["token"])


def _public(item: dict) -> dict:
    """Never hand the token back to the browser — only whether one is set."""
    return {k: v for k, v in item.items() if k != "token"} | {"has_token": bool(item.get("token"))}


def add(name: str, url: str, target_host: str, token: str = "") -> dict:
    item_id = uuid.uuid4().hex[:12]
    _items[item_id] = {
        "id": item_id,
        "name": (name or url).strip(),
        "url": url.strip().rstrip("/"),
        "target_host": (target_host or "").strip(),
        "token": (token or "").strip(),
    }
    _persist()
    return _public(_items[item_id])


def update(item_id: str, **fields) -> dict:
    _load()
    item = _items.get(item_id)
    if not item:
        raise KeyError(item_id)
    for key in ("name", "url", "target_host", "token"):
        value = fields.get(key)
        if value is None:
            continue
        value = str(value).strip()
        if key == "url":
            value = value.rstrip("/")
        # Blank token means "leave as is"; blank anything else clears to empty.
        if key == "token" and not value:
            continue
        item[key] = value
    _persist()
    return _public(item)


def remove(item_id: str) -> None:
    _load()
    if _items.pop(item_id, None) is None:
        raise KeyError(item_id)
    _persist()


def get(item_id: str) -> dict:
    _load()
    item = _items.get(item_id)
    if not item:
        raise KeyError(item_id)
    return item


def listing() -> list[dict]:
    _load()
    return [_public(i) for i in _items.values()]
