"""Persistent memory store for SkyVault (Assignment 5 Part 1).

Provides `remember(key, value, source)` and `recall(query)` functions and a
`summary()` helper to produce a short startup summary folded into the system
prompt. Memory is stored as JSON on disk with a simple last-writer-wins
conflict resolution rule (same key overwrites previous value).
"""
import json
from pathlib import Path
from datetime import datetime

import config

MEMORY_FILE = config.STATE_PATH / "preferences.json"


def _load():
    if not MEMORY_FILE.exists():
        return {}
    try:
        with MEMORY_FILE.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        # If the file is corrupted, start fresh but keep caller aware via empty dict
        return {}


def _save(store):
    with MEMORY_FILE.open("w", encoding="utf-8") as fh:
        json.dump(store, fh, ensure_ascii=False, indent=2)


def remember(key, value, source="user"):
    """Persist a fact under `key` with `value` and `source`.

    Conflict rule: last-writer-wins — a new `remember` for the same `key`
    overwrites the previous value and records an updated timestamp.
    Returns a structured result similar to other tools.
    """
    key = str(key)
    store = _load()
    now = datetime.utcnow().isoformat() + "Z"
    store[key] = {"value": value, "source": source, "updated_at": now}
    _save(store)
    return {"status": "ok", "key": key, "value": value, "source": source, "updated_at": now}


def recall(query):
    """Lookup facts by key. If an exact key exists return it; otherwise return
    any keys that contain the query substring (case-insensitive).

    Returns a result object with `status` and `matches` list.
    """
    q = str(query).strip()
    store = _load()
    if q in store:
        entry = store[q]
        return {"status": "ok", "matches": [{"key": q, **entry}]}

    # substring search (case-insensitive)
    qlow = q.lower()
    matches = []
    for k, v in store.items():
        if qlow in k.lower() or qlow in str(v.get("value", "")).lower():
            matches.append({"key": k, **v})

    if not matches:
        return {"status": "error", "message": f"No memory found matching: {query}"}
    return {"status": "ok", "matches": matches}


def summary():
    """Return a short human-readable summary of stored facts for folding into the
    system prompt at startup.
    """
    store = _load()
    if not store:
        return "(no persisted memory)"
    parts = []
    for k, v in store.items():
        parts.append(f"{k}: {v.get('value')} (source={v.get('source')}, updated={v.get('updated_at')})")
    return "; ".join(parts)
