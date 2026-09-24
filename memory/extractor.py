"""Durable-memory suggestion extraction.
Suggestions are generated separately from saving so the user can review them.
"""
from __future__ import annotations

import json
import re
from llm.base import LLMMessage


def build_prompt(messages) -> str:
    transcript = "\n".join(
        f"{m.role.upper()}: {m.content.strip()}"
        for m in messages
        if m.role in {"user", "assistant"} and isinstance(m.content, str) and m.content.strip()
    )
    return (
        "Extract only durable, useful memories about the user from this conversation. "
        "Prefer stable preferences, long-term goals, ongoing projects, recurring workflows, "
        "and explicitly shared identity facts. Do not include passwords, API keys, tokens, "
        "financial secrets, highly sensitive personal data, temporary emotions, or one-off details. "
        "Return JSON only: {\"memories\":[\"...\"]}. "
        "Return an empty list when nothing should be remembered.\n\n" + transcript
    )


def parse(text: str) -> list[str]:
    cleaned = (text or "").strip()
    match = re.search(r"\{.*\}", cleaned, re.S)
    try:
        data = json.loads(match.group(0) if match else cleaned)
    except Exception:
        return []
    values = data.get("memories") if isinstance(data, dict) else []
    return [str(value).strip() for value in values if str(value).strip()][:8]


def messages_for_agent(items: list[dict]):
    return [
        LLMMessage(role=item["role"], content=item["content"])
        for item in items
        if isinstance(item, dict)
        and item.get("role") in {"user", "assistant"}
        and isinstance(item.get("content"), str)
        and item["content"].strip()
    ]
