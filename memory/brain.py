"""Aster's durable cloud-brain abstraction."""
from __future__ import annotations
from datetime import datetime, timezone
from uuid import uuid4
from .cloud import enabled, load as cloud_load, save as cloud_save
from .memory import get_memory

USER_ID = "mint"

def _now():
    return datetime.now(timezone.utc).isoformat()

def _entry_id():
    return str(uuid4())

def load_entries(user_id: str = USER_ID):
    if enabled():
        data = cloud_load(user_id)
        if data:
            return data
    # Convert existing local profile into editable memory cards.
    out = []
    for line in get_memory().entries(reload=True):
        if line.startswith("- "):
            text = line[2:].strip()
            if text and text != "## Preferences":
                out.append({
                    "id": _entry_id(),
                    "text": text,
                    "source": "local",
                    "created_at": _now(),
                })
    return out

def save_entries(entries, user_id: str = USER_ID):
    return cloud_save(entries, user_id)

def add(text, source="manual", user_id: str = USER_ID):
    text = text.strip()
    if not text:
        return False
    entries = load_entries(user_id)
    if any(x.get("text", "").strip() == text for x in entries):
        return True
    entries.append({
        "id": _entry_id(),
        "text": text,
        "source": source,
        "created_at": _now(),
    })
    return save_entries(entries, user_id)

def delete(memory_id, user_id: str = USER_ID):
    entries = [x for x in load_entries(user_id) if str(x.get("id")) != str(memory_id)]
    return save_entries(entries, user_id)

def replace(entries, user_id: str = USER_ID):
    clean = []
    for x in entries:
        text = str(x.get("text", "")).strip()
        if text:
            clean.append({
                "id": str(x.get("id") or _entry_id()),
                "text": text,
                "source": x.get("source", "manual"),
                "created_at": x.get("created_at") or _now(),
            })
    return save_entries(clean, user_id)
