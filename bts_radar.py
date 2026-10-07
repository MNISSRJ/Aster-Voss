"""BTS Radar: collect official BTS announcements with region-aware preferred links."""
from __future__ import annotations

import hashlib
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Callable

USER_AGENT = "Aster-Voss-BTS-Radar/1.0"
MAX_ITEMS = 30
MEDIA_FEED_URL = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
    {"q": 'BTS OR Jungkook OR Jimin OR J-Hope OR SUGA OR RM OR Jin OR Taehyung', "hl": "en-US", "gl": "US", "ceid": "US:en"}
)
TRUSTED_MEDIA_DOMAINS = (
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "yonhapnews.co.kr",
    "koreaherald.com", "koreatimes.co.kr", "soompi.com", "billboard.com",
    "variety.com", "rollingstone.com", "nme.com", "kpopherald.com", "theguardian.com",
    "allkpop.com", "koreaboo.com", "kstartrend.com",
)

MEMBERS = {
    "rm": {"name": "RM", "instagram": "rkive"},
    "jin": {"name": "Jin", "instagram": "jin"},
    "suga": {"name": "SUGA", "instagram": "agustd"},
    "jhope": {"name": "j-hope", "instagram": "uarmyhope", "tiktok": "iamurhope"},
    "jimin": {"name": "Jimin", "instagram": "j.m"},
    "v": {"name": "V", "instagram": "thv"},
    "jungkook": {"name": "Jung Kook", "instagram": "mnijungkook"},
}

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
    {
        "id": "weverse-bts-live",
        "name": "Weverse BTS LIVE",
        "url": "https://weverse.io/bts/live",
        "source_type": "weverse_live",
        "language": "ko",
        "official": True,
        "official_account": "BTS Official Weverse community",
        "provenance_url": "https://weverse.io/bts/notice/288",
        "preferred_region": "global",
        "accessibility_score": 0.55,
        "accessibility_confidence": 0.65,
        "automatic": True,
    },
    {
        "id": "weverse-bts-artist",
        "name": "Weverse BTS Artist",
        "url": "https://weverse.io/bts/artist",
        "source_type": "weverse_artist",
        "language": "ko",
        "official": True,
        "official_account": "BTS members on official Weverse community",
        "provenance_url": "https://weverse.io/bts/notice/288",
        "preferred_region": "global",
        "accessibility_score": 0.55,
        "accessibility_confidence": 0.65,
        "automatic": True,
    },
    *[
        {
            "id": f"instagram-{key}",
            "name": f"Instagram · {member['name']}",
            "url": f"https://www.instagram.com/{member['instagram']}/",
            "source_type": "instagram",
            "member": member["name"],
            "language": "und",
            "official": True,
            "official_account": f"@{member['instagram']} (member account)",
            # Use the curated member profile itself as the first-party identity
            # reference; the app must not imply it can read the account's feed.
            "provenance_url": f"https://www.instagram.com/{member['instagram']}/",
            "preferred_region": "global",
            "accessibility_score": 0.35,
            "accessibility_confidence": 0.8,
            "automatic": False,
        }
        for key, member in MEMBERS.items()
    ],
    {
        "id": "tiktok-jhope",
        "name": "TikTok · j-hope",
        "url": "https://www.tiktok.com/@iamurhope",
        "source_type": "tiktok",
        "member": "j-hope",
        "language": "und",
        "official": True,
        "official_account": "@iamurhope (verified artist account)",
        "provenance_url": "https://newsroom.tiktok.com/vi-VN/j-hope-sweet-dream",
        "preferred_region": "global",
        "accessibility_score": 0.35,
        "accessibility_confidence": 0.95,
        "automatic": False,
    },
    {
        "id": "bts-media-news",
        "name": "BTS 媒体报道",
        "url": MEDIA_FEED_URL,
        "source_type": "media",
        "language": "zh-CN",
        "official": False,
        "official_account": "Google News 聚合的可信媒体",
        "preferred_region": "global",
        "accessibility_score": 0.75,
        "accessibility_confidence": 0.7,
        "automatic": True,
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
    try:
        parsed = parsedate_to_datetime(value)
        return parsed.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        pass
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
    if source["source_type"] == "weverse_live":
        return "/bts/live/" in url
    if source["source_type"] == "weverse_artist":
        return "/bts/artist/" in url
    if source["source_type"] == "instagram":
        return bool(re