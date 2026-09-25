"""Aster Voss AI Radar: collect fresh AI news and produce a daily brief."""
from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any

from llm.base import LLMMessage

FEEDS = [
    ("TechCrunch AI", "https://techcrunch.com/category/artificial-intelligence/feed/"),
    ("The Verge AI", "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml"),
    (
        "Google News AI",
        "https://news.google.com/rss/search?"
        + urllib.parse.urlencode(
            {
                "q": "AI artificial intelligence AI agents LLM",
                "hl": "en-US",
                "gl": "US",
                "ceid": "US:en",
            }
        ),
    ),
]
MAX_AGE_HOURS = 48
MAX_CANDIDATES = 20
MAX_ITEMS = 6
USER_AGENT = "Aster-Voss-AI-Radar/1.0"


class RadarCurationError(ValueError):
    """Raised when the model response cannot produce usable radar items."""



def _clean(value: str | None) -> str:
    value = html.unescape(value or "")
    return re.sub(r"<[^>]+>", " ", value).strip()


def _norm_title(value: str) -> str:
    value = _clean(value).lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value)
    return " ".join(value.split())


def _id(title: str, url: str) -> str:
    return hashlib.sha256((title + "|" + url).encode("utf-8")).hexdigest()[:20]


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            dt = datetime.strptime(value.strip(), fmt)
            return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _fetch(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as response:
        return response.read()


def _read_feed(feed_name: str, url: str) -> list[dict[str, Any]]:
    root = ET.fromstring(_fetch(url))
    rows: list[dict[str, Any]] = []
    for item in root.findall(".//item"):
        title = _clean(item.findtext("title"))
        link = (item.findtext("link") or "").strip()
        if not title or not link:
            continue
        dt = _parse_date(item.findtext("pubDate")) or datetime.now(timezone.utc)
        rows.append(
            {
                "id": _id(title, link),
                "title": title,
                "url": link,
                "description": _clean(item.findtext("description"))[:700],
                "published_at": dt.astimezone(timezone.utc).isoformat(),
                "feed": feed_name,
                "source": _clean(item.findtext("source")) or feed_name,
            }
        )
    return rows


def collect_candidates() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=MAX_AGE_HOURS)
    groups: dict[str, dict[str, Any]] = {}

    for feed_name, url in FEEDS:
        try:
            rows = _read_feed(feed_name, url)
        except Exception:
            continue
        for row in rows:
            dt = _parse_date(row["published_at"]) or now
            if dt < cutoff:
                continue
            key = _norm_title(row["title"])
            if not key:
                continue
            group = groups.setdefault(key, {**row, "feeds": set(), "sources": set()})
            group["feeds"].add(feed_name)
            group["sources"].add(row["source"])
            if dt > (_parse_date(group["published_at"]) or cutoff):
                group["published_at"] = row["published_at"]
                group["url"] = row["url"]
                group["description"] = row["description"]

    items = list(groups.values())
    for item in items:
        dt = _parse_date(item["published_at"]) or now
        age_hours = max(0.0, (now - dt).total_seconds() / 3600)
        freshness = max(0.0, 60.0 - age_hours * 2.0)
        cross_feed = min(25.0, max(0, len(item["feeds"]) - 1) * 12.5)
        source_diversity = min(15.0, len(item["sources"]) * 5.0)
        item["hot_score"] = round(min(100.0, freshness + cross_feed + source_diversity), 1)
        item["source_list"] = sorted(item["sources"])
        item["feeds"] = sorted(item["feeds"])
        del item["sources"]
    items.sort(key=lambda x: (x["hot_score"], x["published_at"]), reverse=True)
    return items[:MAX_CANDIDATES]




def _parse_json_object(raw: str) -> dict[str, Any]:
    """Parse a JSON object from plain JSON, a markdown code fence, or text around JSON."""
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()

    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    if start < 0:
        return {}

    try:
        value, _ = json.JSONDecoder().raw_decode(text[start:])
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def curate(
    provider,
    candidates: list[dict[str, Any]],
    attempt: int = 1,
) -> dict[str, Any]:
    """Curate candidates into a validated, displayable radar brief.

    ``attempt`` is used only to tighten the prompt on the retry path. A
    successful result must contain at least one item that points to a real
    candidate; otherwise a RadarCurationError is raised so the service can
    retry or fall back to the raw candidates.
    """
    prompt_rows = []
    for idx, item in enumerate(candidates, 1):
        prompt_rows.append(
            f"[{idx}] {item['title']} | hot={item['hot_score']} | "
            f"sources={', '.join(item['source_list'])}\n"
            f"URL: {item['url']}\nSnippet: {item['description']}"
        )

    retry_instruction = ""
    max_output_items = MAX_ITEMS
    if attempt > 1:
        max_output_items = min(4, MAX_ITEMS)
        retry_instruction = (
            "\nRetry instruction: the previous attempt did not produce usable items. "
            f"Select 1 to {max_output_items} valid candidates now. "
            "Every item MUST use a candidate number from 1 to N. "
            "Do not return an empty items array when candidates are available."
        )

    prompt = (
        "You are the editor of Aster Voss's daily AI radar. Select at most "
        f"{max_output_items} important developments from the candidates. "
        "The ranking is not personalized. Prefer new, consequential stories "
        "with cross-source support. Treat rumors as rumors and never invent facts. "
        "Return valid JSON only: "
        '{"intro_zh":"...","items":[{"candidate":1,"company":"...","headline_zh":"...",'
        '"summary_zh":"...","why_it_matters_zh":"...","tags":["..."]}]}."'
        "Keep each Chinese summary under 70 characters. "
        "When candidates are available, select at least one valid candidate."
        + retry_instruction
        + "\n\n"
        + "\n\n".join(prompt_rows)
    )

    response = provider.complete(
        [
            LLMMessage.system(
                "Return valid JSON only. Never invent candidate numbers."
            ),
            LLMMessage.user(prompt),
        ],
        temperature=0.2,
        max_tokens=1800 if attempt > 1 else 1600,
        reasoning=None,
    )

    finish_reason = getattr(response, "finish_reason", None)
    if finish_reason == "length":
        raise RadarCurationError("model output was truncated")

    raw = (getattr(response, "text", "") or "").strip()
    if not raw:
        raise RadarCurationError("model returned empty content")

    data = _parse_json_object(raw)
    if not data:
        raise RadarCurationError("model response was not a JSON object")

    selected = data.get("items")
    if not isinstance(selected, list):
        raise RadarCurationError("model response has no valid items list")

    by_index = {i: item for i, item in enumerate(candidates, 1)}
    result_items: list[dict[str, Any]] = []
    used_candidates: set[int] = set()

    for entry in selected[:MAX_ITEMS]:
        if not isinstance(entry, dict):
            continue
        try:
            candidate_index = int(entry.get("candidate"))
        except (TypeError, ValueError):
            continue
        if candidate_index in used_candidates:
            continue
        source = by_index.get(candidate_index)
        if source is None:
            continue

        tags = entry.get("tags")
        if not isinstance(tags, list):
            tags = []

        result_items.append(
            {
                "id": source["id"],
                "headline_zh": str(
                    entry.get("headline_zh") or source["title"]
                ).strip(),
                "summary_zh": str(
                    entry.get("summary_zh") or source.get("description", "")
                ).strip(),
                "why_it_matters_zh": str(
                    entry.get("why_it_matters_zh") or ""
                ).strip(),
                "company": str(entry.get("company") or "").strip(),
                "tags": [str(x).strip() for x in tags][:4],
                "url": source["url"],
                "source_list": source["source_list"],
                "published_at": source["published_at"],
                "hot_score": source["hot_score"],
            }
        )
        used_candidates.add(candidate_index)

    if not result_items:
        raise RadarCurationError(
            f"model produced no usable radar items from {len(candidates)} candidates"
        )

    return {
        "brief_date": datetime.now(timezone.utc).date().isoformat(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "intro_zh": str(
            data.get("intro_zh") or "Aster 已为你整理今天的 AI 热点。"
        ).strip(),
        "items": result_items,
        "source_count": len(
            {s for item in candidates for s in item["source_list"]}
        ),
        "candidate_count": len(candidates),
    }
