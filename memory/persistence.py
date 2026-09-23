"""Small persistence layer for Aster Voss.

Local development writes to the project memory directory. Vercel/serverless
filesystems are not persistent, so writes there are best-effort and must never
turn a successful chat request into a 500 error.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Any
from llm.base import LLMMessage

ROOT = Path(__file__).resolve().parent
HISTORY_PATH = ROOT / "CONVERSATION_HISTORY.json"
LONG_TERM_PATH = ROOT / "LONG_TERM_MEMORY.md"
MAX_HISTORY_MESSAGES = 80


def _atomic_write(path: Path, text: str) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
        return True
    except OSError:
        return False


def load_history():
    if not HISTORY_PATH.exists():
        return []
    try:
        data = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        return [
            LLMMessage(role=x["role"], content=x["content"])
            for x in data[-MAX_HISTORY_MESSAGES:]
            if isinstance(x, dict)
            and x.get("role") in {"user", "assistant"}
            and isinstance(x.get("content"), str)
            and x["content"].strip()
        ]
    except (OSError, ValueError, TypeError):
        return []


def save_history(messages: list[LLMMessage]):
    data = [
        {"role": m.role, "content": m.content}
        for m in messages
        if m.role in {"user", "assistant"}
        and isinstance(m.content, str)
        and m.content.strip()
    ]
    # Persistence is best-effort. A read-only serverless filesystem must not
    # make an otherwise successful model response fail.
    _atomic_write(
        HISTORY_PATH,
        json.dumps(data[-MAX_HISTORY_MESSAGES:], ensure_ascii=False, indent=2),
    )


def clear_history():
    _atomic_write(HISTORY_PATH, "[]\n")


def save_long_term_note(note: str) -> bool:
    note = note.strip()
    if not note:
        return False
    try:
        LONG_TERM_PATH.parent.mkdir(parents=True, exist_ok=True)
        if not LONG_TERM_PATH.exists():
            LONG_TERM_PATH.write_text(
                "# Aster Voss Long-Term Memory\n\n", encoding="utf-8"
            )
        with LONG_TERM_PATH.open("a", encoding="utf-8") as f:
            f.write(f"- {note}\n")
        return True
    except OSError:
        return False


def long_term_context(max_chars: int = 1800) -> str:
    if not LONG_TERM_PATH.exists():
        return ""
    try:
        text = LONG_TERM_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""
    lines = [
        x.strip()
        for x in text.splitlines()
        if x.strip() and x.strip() != "# Aster Voss Long-Term Memory"
    ]
    out, used = [], 0
    for line in lines:
        if used + len(line) + 1 > max_chars:
            break
        out.append(line)
        used += len(line) + 1
    return (
        "<long_term_memory>\n"
        + "\n".join(out)
        + "\n</long_term_memory>"
        if out
        else ""
    )


def memory_stats() -> dict[str, Any]:
    return {
        "history_file": str(HISTORY_PATH),
        "history_messages": len(load_history()),
        "long_term_file": str(LONG_TERM_PATH),
        "long_term_exists": LONG_TERM_PATH.exists(),
    }
