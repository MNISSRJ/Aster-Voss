"""Optional migration helper for the local history file.
Run only locally after backing up the JSON file and configuring Supabase.
"""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from memory import cloud

HISTORY = Path(__file__).resolve().parents[1] / "memory" / "CONVERSATION_HISTORY.local.json"


def migrate():
    if not cloud.enabled():
        raise SystemExit("Supabase is not configured.")
    data = json.loads(HISTORY.read_text(encoding="utf-8"))
    messages = [
        item for item in data
        if isinstance(item, dict)
        and item.get("role") in {"user", "assistant"}
        and isinstance(item.get("content"), str)
        and item["content"].strip()
    ]
    if not messages:
        print("No legacy messages found.")
        return
    title = "迁移的历史对话"
    conversation_id = str(uuid4())
    ok = cloud.save_conversation(conversation_id, title, messages)
    print("migrated" if ok else "failed", conversation_id)


if __name__ == "__main__":
    migrate()
