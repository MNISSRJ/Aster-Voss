"""BTS Radar: collect official BTS announcements with region-aware preferred links."""
from __future__ import annotations

import hashlib
import html
import re
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Callable

USER_AGENT = "Aster-Voss-BTS-Radar/1.0"
MAX_ITEMS = 30

SOURCES = [
    {
        "id": "weverse-bts-cn",
        "name": "Weverse BTS（中文）",
        "url": "https://weverse.io/bts/notice?hl=zh-cn",
        "source_type": "weverse",
        "language": "zh-CN",
        "official": True,
        "official_account": "BTS / BIGHIT MUSIC / HYBE",
        "preferred_region": "CN",
        "accessibility_score": 0.95,
        "accessibility_confidence": 0.85,
    },
    {
        "id": "weverse-shop-bts-cn",
        "name": "Weverse Shop BTS（中文）",
        "url": "https://shop.weverse.io/zh-cn/shop/CNY/artists/2/notices",
        "source_type": "weverse_shop",
        "language": "zh-CN",
        "official": True,
        "official_account": "Weverse Shop / BTS",
        "preferred_region": "CN",
        "accessibility_score": 0.90,
        "accessibility_confidence": 0.85,
    },
]


class _AnchorParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.current_href: str | None = None
        self.current_text: list[str] = []
        self.rows: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a" or self.current_href is not None:
            return
        values = dict(attrs)
        href = values.get("href")
        if href:
            self.current_href = href
            self.current_text = []

    def handle_data(self, data: str) -> None:
        if self.current_href is not None:
            self.current_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self.current_href is None:
            return
        title = _clean(" ".join(self.current_text))
        if title:
            self.rows.append((title, self.current_href))
        self.current_href = None
        self.current_text = []


def _clean(value: str | None) -> str:
    return re.sub(r"\s+", " ", html.unescape(value or "")).strip()


def _normalize_title(value: str) -> str:
    value = _clean(value).lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", value)
    return " ".join(value.split())


def _id(title: str, url: str) -> str:
    return hashlib.sha256((title + "|" + url).encode("utf-8")).hexdigest()[:24]


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    patterns = (
        (r"(20\d{2})[./-](\d{1,2})[./-](\d{1,2})", "%Y-%m-%d"),
        (r"(20\d{2})年(\d{1,2})月(\d{1,2})日", "%Y-%m-%d"),
    )
    for pattern, _ in patterns:
        match = re.search(pattern, value)
        if match:
            y, m, d = (int(x) for x in match.groups())
            return datetime(y, m, d, tzinfo=timezone.utc).isoformat()
    match = re.search(r"(20\d{2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{1,2})", value)
    if match:
        y, m, d = (int(x) for x in match.groups())
        return datetime(y, m, d, tzinfo=timezone.utc).isoformat()
    return None


def _absolute_url(base: str, href: str) -> str:
    return urllib.parse.urljoin(base, href)


def _allowed_link(source: dict[str, Any], url: str) -> bool:
    if source["source_type"] == "weverse":
        return "/bts/notice/" in url
    if source["source_type"] == "weverse_shop":
        return "/artists/2/notices/" in url
    return False


def _category(title: str) -> str:
    value = title.lower()
    if any(x in value for x in ("tour", "演出", "门票", "sound check", "concert", "演唱会")):
        return "演出"
    if any(x in value for x in ("album", "single", "release", "音乐", "专辑", "歌曲", "comeback")):
        return "音乐"
    if any(x in value for x in ("merch", "商品", "周边", "light stick", "应援棒", "pop-up", "popup")):
        return "周边"
    if any(x in value for x in ("member", "成员", "j-hope", "jin", "jimin", "jungkook", "rm", "suga", "v", "taehyung")):
        return "成员"
    return "官宣"


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"})
    with urllib.request.urlopen(req, timeout=12) as response:
        return response.read().decode("utf-8", errors="ignore")


def _extract(source: dict[str, Any], body: str) -> list[dict[str, Any]]:
    parser = _AnchorParser()
    parser.feed(body)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for title, href in parser.rows:
        url = _absolute_url(source["url"], href)
        if not _allowed_link(source, url):
            continue
        title = _clean(title)
        if source["source_type"] == "weverse_shop" and "BTS" not in title.upper():
            continue
        key = _normalize_title(title)
        if not key or key in seen:
            continue
        seen.add(key)
        preferred_url = url
        if source["source_type"] == "weverse" and "hl=" not in preferred_url:
            preferred_url += ("&" if "?" in preferred_url else "?") + "hl=zh-cn"
        rows.append(
            {
                "id": _id(title, url),
                "title": title,
                "summary_zh": "",
                "category": _category(title),
                "source_id": source["id"],
                "source_name": source["name"],
                "source_type": source["source_type"],
                "original_url": url,
                "preferred_url": preferred_url,
                "preferred_url_region": source["preferred_region"],
                "published_at": _parse_date(title),
                "official": True,
                "official_account": source["official_account"],
                "accessibility_score": source["accessibility_score"],
                "accessibility_confidence": source["accessibility_confidence"],
                "importance": 1.0,
                "status": "official",
                "dedupe_hash": hashlib.sha256(key.encode("utf-8")).hexdigest(),
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    return rows


def collect_candidates(fetcher: Callable[[str], str] = _fetch) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for source in SOURCES:
        try:
            rows = _extract(source, fetcher(source["url"]))
        except Exception:
            continue
        for row in rows:
            key = row["dedupe_hash"]
            existing = grouped.get(key)
            if existing is None or row["accessibility_score"] > existing["accessibility_score"]:
                grouped[key] = row
    items = list(grouped.values())
    items.sort(
        key=lambda item: (
            item["published_at"] or "",
            item["accessibility_score"],
            item["source_id"],
        ),
        reverse=True,
    )
    return items[:MAX_ITEMS]


def summarize(provider, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not candidates or not provider or not provider.is_available():
        return candidates
    from llm.base import LLMMessage

    rows = "\n\n".join(
        f"[{i}] {item['title']} | category={item['category']} | URL={item['preferred_url']}"
        for i, item in enumerate(candidates[:12], 1)
    )
    prompt = (
        "你是 Aster Voss 的 BTS Radar 编辑。只处理已确认来自官方 BTS/Weverse 来源的内容。"
        "请为每条候选生成一句简洁中文摘要，并保持事实，不补充候选中不存在的信息。"
        '返回 JSON：{"items":[{"candidate":1,"summary_zh":"..."}]}。'
        "只返回 JSON，不要解释。\n\n" + rows
    )
    try:
        response = provider.complete(
            [LLMMessage.system("Return valid JSON only."), LLMMessage.user(prompt)],
            temperature=0.1,
            max_tokens=1200,
            reasoning=None,
            response_format={"type": "json_object"},
        )
        import json
        data = json.loads((response.text or "").strip())
        for entry in data.get("items", []) if isinstance(data, dict) else []:
            if not isinstance(entry, dict):
                continue
            try:
                idx = int(entry.get("candidate")) - 1
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(candidates):
                summary = _clean(str(entry.get("summary_zh") or ""))
                if summary:
                    candidates[idx]["summary_zh"] = summary[:180]
    except Exception:
        pass
    return candidates
