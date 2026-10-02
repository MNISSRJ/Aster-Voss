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
    {"q": 'BTS OR Jungkook OR Jimin OR J-Hope OR SUGA OR RM OR Jin OR Taehyung', "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"}
)
TRUSTED_MEDIA_DOMAINS = (
    "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "yonhapnews.co.kr",
    "koreaherald.com", "koreatimes.co.kr", "soompi.com", "billboard.com",
    "variety.com", "rollingstone.com", "nme.com", "kpopherald.com", "theguardian.com",
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
        return bool(re.match(r"https://(?:www\.)?instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+/?$", url))
    if source["source_type"] == "tiktok":
        return bool(re.match(r"https://(?:www\.)?tiktok\.com/@iamurhope/video/\d+/?$", url))
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


def _member_from_title(title: str, source: dict[str, Any]) -> str | None:
    if source.get("member"):
        return source["member"]
    value = title.casefold()
    aliases = {
        "RM": ("rm", "namjoon", "nam jun"),
        "Jin": ("jin", "seokjin"),
        "SUGA": ("suga", "yoongi", "agust d"),
        "j-hope": ("j-hope", "jhope", "hoseok"),
        "Jimin": ("jimin",),
        "V": ("taehyung", "tae-hyung"),
        "Jung Kook": ("jungkook", "jung kook"),
    }
    for name, keys in aliases.items():
        if any(re.search(r"(?<![a-z])" + re.escape(key) + r"(?![a-z])", value) for key in keys):
            return name
    return None


def _fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7"})
    with urllib.request.urlopen(req, timeout=12) as response:
        return response.read().decode("utf-8", errors="ignore")


def _extract(source: dict[str, Any], body: str) -> list[dict[str, Any]]:
    parser = _AnchorParser()
    parser.feed(body)
    return _extract_rows(source, parser.rows)


def _extract_media(source: dict[str, Any], body: str) -> list[dict[str, Any]]:
    """Collect recent coverage from an allowlist of established news outlets."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return []
    member_pattern = re.compile(r"\b(?:BTS|Jung\s*Kook|Jungkook|Jimin|Jin|SUGA|Yoongi|RM|Namjoon|j-hope|Hoseok|Taehyung)\b", re.I)
    rows = []
    for entry in root.findall(".//item"):
        title = _clean(entry.findtext("title"))
        link = _clean(entry.findtext("link"))
        if not title or not link or not member_pattern.search(title):
            continue
        publisher = entry.find("source")
        source_name = _clean(publisher.text if publisher is not None else "")
        publisher_url = _clean(publisher.get("url") if publisher is not None else "")
        host = (urllib.parse.urlparse(publisher_url or link).hostname or "").lower()
        if not any(host == domain or host.endswith("." + domain) for domain in TRUSTED_MEDIA_DOMAINS):
            continue
        summary = _clean(entry.findtext("description"))
        published_at = _parse_date(entry.findtext("pubDate"))
        if published_at:
            published_dt = datetime.fromisoformat(published_at)
            if published_dt < datetime.now(timezone.utc) - timedelta(days=7):
                continue
        rows.append({
            "id": _id(title, link), "title": title,
            "summary_zh": summary[:240] or "媒体报道，详情以原文为准。",
            "category": "热门报道", "source_id": source["id"], "source_name": source_name or host,
            "source_type": "media", "source_url": source["url"], "language": source["language"],
            "original_url": link, "preferred_url": link, "preferred_url_region": "global",
            "published_at": published_at, "official": False, "official_account": source_name or host,
            "member": _member_from_title(title, {}) or "BTS", "provenance_url": link,
            "verification_status": "reported_by_media", "accessibility_score": source["accessibility_score"],
            "accessibility_confidence": source["accessibility_confidence"], "importance": 0.7,
            "status": "reported", "dedupe_hash": hashlib.sha256(_normalize_title(title).encode("utf-8")).hexdigest(),
            "discovered_at": datetime.now(timezone.utc).isoformat(),
        })
    return rows


def _extract_social_posts(source: dict[str, Any], body: str) -> list[dict[str, Any]]:
    """Accept only post permalinks and captions rendered by a verified profile page."""
    parser = _AnchorParser()
    parser.feed(body)
    platform = source["source_type"]
    if platform == "instagram":
        pattern = re.compile(r"^https?://(?:www\.)?instagram\.com/(?:p|reel)/[A-Za-z0-9_-]+/?$")
    else:
        pattern = re.compile(r"^https?://(?:www\.)?tiktok\.com/@iamurhope/video/\d+/?$")
    rows = []
    published_by_url = {}
    for title, href in parser.rows:
        url = _absolute_url(source["url"], href).split("?", 1)[0]
        if not pattern.match(url) or not _clean(title):
            continue
        rows.append((title, url))
    if platform == "instagram":
        for match in re.finditer(r'"shortcode"\s*:\s*"([A-Za-z0-9_-]+)"', body):
            shortcode = match.group(1)
            url = f"https://www.instagram.com/p/{shortcode}/"
            context = body[match.start():match.start() + 8000]
            caption_match = re.search(r'"text"\s*:\s*"((?:\\.|[^"\\])*)"', context)
            if caption_match and url not in {href for _, href in rows}:
                try:
                    caption = _clean(json.loads('"' + caption_match.group(1) + '"'))
                except (ValueError, TypeError):
                    caption = ""
                if caption:
                    rows.append((caption[:240], url))
            timestamp = re.search(r'"taken_at_timestamp"\s*:\s*(\d{9,12})', context)
            if timestamp:
                published_by_url[url] = datetime.fromtimestamp(int(timestamp.group(1)), timezone.utc).isoformat()
    else:
        for match in re.finditer(r'"id"\s*:\s*"(\d{15,25})"\s*,\s*"desc"\s*:\s*"((?:\\.|[^"\\])*)"', body):
            video_id = match.group(1)
            try:
                caption = _clean(json.loads('"' + match.group(2) + '"'))
            except (ValueError, TypeError):
                caption = ""
            url = f"https://www.tiktok.com/@iamurhope/video/{video_id}"
            if caption and url not in {href for _, href in rows}:
                rows.append((caption[:240], url))
            context = body[match.start():match.start() + 1000]
            timestamp = re.search(r'"createTime"\s*:\s*(\d{9,12})', context)
            if timestamp:
                published_by_url[url] = datetime.fromtimestamp(int(timestamp.group(1)), timezone.utc).isoformat()
    items = _extract_rows(source, rows)
    for item in items:
        item["published_at"] = published_by_url.get(item["original_url"], item["published_at"])
    return items


def _extract_rows(source: dict[str, Any], anchors: list[tuple[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for title, href in anchors:
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
        elif source["source_type"] == "weverse_shop":
            notice_id = url.rstrip("/").rsplit("/", 1)[-1].split("?", 1)[0]
            preferred_url = source["url"].rstrip("/") + "/" + notice_id
        rows.append(
            {
                "id": _id(title, url),
                "title": title,
                "summary_zh": f"来自{source['name']}的已核验动态，查看原帖了解详情。",
                "category": _category(title),
                "source_id": source["id"],
                "source_name": source["name"],
                "source_type": source["source_type"],
                "source_url": source["url"],
                "language": source.get("language", "und"),
                "original_url": url,
                "preferred_url": preferred_url,
                "preferred_url_region": source["preferred_region"],
                "published_at": _parse_date(title),
                "official": True,
                "official_account": source["official_account"],
                "member": _member_from_title(title, source) or "BTS",
                "provenance_url": source.get("provenance_url", "https://weverse.io/bts/notice/288"),
                "verification_status": "verified_official",
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
    def collect_source(source):
        if not source.get("automatic", True):
            return []
        try:
            body = fetcher(source["url"])
        except Exception:
            return []
        if source["source_type"] == "media":
            return _extract_media(source, body)
        if source["source_type"] in {"instagram", "tiktok"}:
            return _extract_social_posts(source, body)
        return _extract(source, body)

    with ThreadPoolExecutor(max_workers=8) as executor:
        source_rows = list(executor.map(collect_source, SOURCES))
    for rows in source_rows:
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
        "你是 Aster Voss 的 BTS Radar 编辑。只处理来自已核验官方账号或 BTS 官方社区的内容。"
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
