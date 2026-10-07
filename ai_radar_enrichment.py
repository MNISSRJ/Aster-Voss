"""Rule-based classification and conservative validation for AI Radar output."""
from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

PROMPT_VERSION = "ai-radar-zh-v1"
STORY_PROMPT_VERSION = "ai-radar-story-v1"
LANGUAGE = "zh-CN"

DEFAULT_RULES = {
    "official_sources": ["OpenAI", "Anthropic", "Google DeepMind", "Meta AI", "Microsoft Research", "NVIDIA"],
    "a_keywords": ["launches", "launched", "introduces", "introduced", "unveils", "unveiled", "releases", "released", "发布", "推出", "开源", "重大更新", "new model", "reasoning model", "frontier model", "benchmark"],
    "c_keywords": ["opinion", "podcast", "roundup", "weekly recap", "interview", "funding round", "raises $", "融资", "专访", "播客", "盘点", "周报"],
}


def load_importance_rules() -> dict[str, list[str]]:
    """Load tunable importance rules from JSON env or the checked-in config file."""
    raw = os.getenv("AI_RADAR_IMPORTANCE_RULES_JSON", "").strip()
    path = Path(__file__).resolve().parent / "config" / "ai_radar_rules.json"
    try:
        value = json.loads(raw) if raw else json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        value = DEFAULT_RULES
    result = {}
    for key in ("official_sources", "a_keywords", "c_keywords"):
        entries = value.get(key, DEFAULT_RULES[key]) if isinstance(value, dict) else DEFAULT_RULES[key]
        result[key] = [str(x).strip() for x in entries if str(x).strip()] if isinstance(entries, list) else DEFAULT_RULES[key]
    return result


def classify_importance(candidate: dict[str, Any], rules: dict[str, list[str]] | None = None) -> str:
    rules = rules or load_importance_rules()
    text = " ".join((str(candidate.get("title", "")), str(candidate.get("description", "")))).casefold()
    if any(term.casefold() in text for term in rules["c_keywords"]):
        return "C"
    source_names = candidate.get("source_list") or [candidate.get("source", "")]
    trusted = any(
        official.casefold() in str(source).casefold()
        for official in rules["official_sources"]
        for source in source_names
    )
    major_event = any(term.casefold() in text for term in rules["a_keywords"])
    if major_event and (trusted or len(source_names) >= 2):
        return "A"
    # B is the explicit safe default for uncertain stories.
    return "B"


def content_hash(candidate: dict[str, Any]) -> str:
    raw = "\n".join((str(candidate.get("title", "")), str(candidate.get("description", "")))).strip()
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def cache_key(candidate: dict[str, Any], prompt_version: str = PROMPT_VERSION, language: str = LANGUAGE) -> str:
    return ":".join((content_hash(candidate), prompt_version, language))


def _numeric_values(text: str) -> set[Decimal]:
    values: set[Decimal] = set()
    units = {"thousand": Decimal(1_000), "k": Decimal(1_000), "million": Decimal(1_000_000), "m": Decimal(1_000_000), "billion": Decimal(1_000_000_000), "b": Decimal(1_000_000_000), "万": Decimal(10_000), "亿": Decimal(100_000_000)}
    pattern = re.compile(r"(?<![\w.])(\d+(?:,\d{3})*(?:\.\d+)?)\s*(thousand|million|billion|[kmb]|万|亿)?", re.I)
    for match in pattern.finditer(text or ""):
        try:
            number = Decimal(match.group(1).replace(",", ""))
            unit = (match.group(2) or "").casefold()
            values.add(number * units.get(unit, Decimal(1)))
        except InvalidOperation:
            continue
    return values


def _dates(text: str) -> set[str]:
    found: set[str] = set()
    for match in re.finditer(r"\b(20\d{2})[-/.年](\d{1,2})[-/.月](\d{1,2})日?", text or ""):
        try:
            found.add(date(int(match.group(1)), int(match.group(2)), int(match.group(3))).isoformat())
        except ValueError:
            pass
    for match in re.finditer(r"\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(20\d{2})\b", text or "", re.I):
        try:
            month = datetime.strptime(f"{match.group(1)} {match.group(2)} {match.group(3)}", "%B %d %Y").date()
            found.add(month.isoformat())
        except ValueError:
            pass
    return found


_ENTITY_STOP = {"The", "This", "That", "These", "Those", "What", "When", "Where", "Why", "How", "After", "Before", "Today", "Yesterday", "New", "First", "More", "AI", "ML", "LLM", "GPU", "API", "CEO", "US", "UK"}


def _proper_names(text: str) -> set[str]:
    names = set(re.findall(r"\b(?:[A-Z][A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*|[A-Z]{2,}(?:-[A-Z]+)*)\b", text or ""))
    return {name for name in names if name not in _ENTITY_STOP and not name.isdigit()}


def fact_consistency(source_text: str, generated_text: str) -> dict[str, Any]:
    """Reject added numbers, dates, or English proper names; omissions are allowed."""
    source_numbers, generated_numbers = _numeric_values(source_text), _numeric_values(generated_text)
    source_dates, generated_dates = _dates(source_text), _dates(generated_text)
    source_names, generated_names = _proper_names(source_text), _proper_names(generated_text)
    issues = []
    if not generated_numbers.issubset(source_numbers):
        issues.append("unsupported_number")
    if not generated_dates.issubset(source_dates):
        issues.append("unsupported_date")
    if not generated_names.issubset(source_names):
        issues.append("unsupported_entity")
    return {"ok": not issues, "issues": issues}


def normalize_concepts(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    cleaned = []
    seen = set()
    generic = {"technology", "news", "update", "ai", "人工智能", "技术", "新闻", "更新"}
    for entry in value:
        name = " ".join(str(entry).strip().split())[:80]
        key = name.casefold()
        if not name or key in seen or key in generic or len(name.split()) > 5:
            continue
        seen.add(key)
        cleaned.append(name)
        if len(cleaned) >= limit:
            break
    return cleaned

