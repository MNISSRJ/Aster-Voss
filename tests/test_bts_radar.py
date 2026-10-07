from bts_radar import SOURCES, _extract, _extract_media, _extract_social_posts, classify_importance, collect_candidates, summarize
from services.bts_radar_service import BTSRadarService


HTML = """
<a href="/bts/notice/123?hl=zh-cn">[公告] BTS WORLD TOUR ARIRANG 门票公告</a>
<a href="/bts/notice/124?hl=zh-cn">[公告] BTS The 5th Album ARIRANG 发售公告 2026/03/20</a>
<a href="/bts/notice/124?hl=zh-cn">[公告] BTS The 5th Album ARIRANG 发售公告 2026/03/20</a>
"""


def test_extracts_direct_official_weverse_links():
    rows = _extract(SOURCES[0], HTML)
    assert len(rows) == 2
    assert all(item["official"] for item in rows)
    assert all("/bts/notice/" in item["preferred_url"] for item in rows)
    assert all(item["preferred_url_region"] == "CN" for item in rows)


def test_collect_candidates_deduplicates_titles_across_sources():
    bodies = {
        SOURCES[0]["url"]: HTML,
        SOURCES[1]["url"]: '<a href="/zh-cn/shop/CNY/artists/2/notices/123">BTS World Tour ARIRANG Merch 公告</a>',
    }
    rows = collect_candidates(lambda url: bodies[url])
    assert len(rows) == 3
    assert len({row["dedupe_hash"] for row in rows}) == 3
    shop_item = next(item for item in rows if item["source_type"] == "weverse_shop")
    assert "/zh-cn/shop/CNY/" in shop_item["preferred_url"]


def test_service_empty_without_cloud(monkeypatch):
    class Repo:
        def save(self, items, user_id):
            return True
        def today(self, user_id):
            return []
    service = BTSRadarService(repository=Repo(), user_id="test")
    monkeypatch.setattr("services.bts_radar_service.collect_candidates", lambda: [])
    result = service.generate()
    assert result["status"] == "empty"
    assert result["item_count"] == 0


def test_member_sources_only_include_curated_verified_profiles():
    instagram = [source for source in SOURCES if source["source_type"] == "instagram"]
    assert len(instagram) == 7
    assert {source["member"] for source in instagram} == {"RM", "Jin", "SUGA", "j-hope", "Jimin", "V", "Jung Kook"}
    assert all(source["official"] and source["provenance_url"] for source in instagram)
    tiktok = [source for source in SOURCES if source["source_type"] == "tiktok"]
    assert [(source["member"], source["url"]) for source in tiktok] == [
        ("j-hope", "https://www.tiktok.com/@iamurhope")
    ]


def test_social_extractor_accepts_only_post_links_from_curated_profile():
    source = next(source for source in SOURCES if source["id"] == "instagram-rm")
    body = """
    <a href="https://www.instagram.com/p/AbCdEf123/">RM photo caption</a>
    <a href="https://www.instagram.com/fan_repost/p/AbCdEf123/">fan copy</a>
    <a href="https://example.com/p/AbCdEf123">external repost</a>
    """
    rows = _extract_social_posts(source, body)
    assert len(rows) == 1
    assert rows[0]["member"] == "RM"
    assert rows[0]["source_type"] == "instagram"
    assert rows[0]["official"] is True
    assert rows[0]["verification_status"] == "verified_official"
    assert rows[0]["provenance_url"] == source["provenance_url"]
    assert rows[0]["original_url"] == "https://www.instagram.com/p/AbCdEf123/"


def test_social_json_payload_produces_original_permalink_and_published_at():
    source = next(source for source in SOURCES if source["id"] == "tiktok-jhope")
    body = r'''{"id":"1234567890123456789","desc":"A verified post","createTime":1790928000}'''
    rows = _extract_social_posts(source, body)
    assert len(rows) == 1
    assert rows[0]["title"] == "A verified post"
    assert rows[0]["original_url"] == "https://www.tiktok.com/@iamurhope/video/1234567890123456789"
    assert rows[0]["published_at"]


def test_media_feed_marks_coverage_as_reported_not_official_and_rejects_fan_sites():
    source = next(source for source in SOURCES if source["source_type"] == "media")
    body = """<?xml version="1.0"?><rss><channel>
      <item><title>BTS announces new project - Soompi</title><link>https://news.google.com/rss/articles/abc</link>
        <source url="https://www.soompi.com">Soompi</source><pubDate>Fri, 02 Oct 2026 00:00:00 GMT</pubDate></item>
      <item><title>BTS update - Fan Blog</title><link>https://fan.example.com/bts</link>
        <source url="https://fan.example.com">Fan Blog</source></item>
    </channel></rss>"""
    rows = _extract_media(source, body)
    assert len(rows) == 1
    assert rows[0]["source_type"] == "media"
    assert rows[0]["official"] is False
    assert rows[0]["verification_status"] == "reported_by_media"
    assert rows[0]["original_url"].startswith("https://news.google.com/")
    assert rows[0]["published_at"].startswith("2026-10-02")


def test_collection_skips_member_social_profiles():
    requested = []
    def fetcher(url):
        requested.append(url)
        if url == SOURCES[0]["url"]:
            return HTML
        if url == SOURCES[1]["url"]:
            return ""
        raise ValueError("not needed")
    collect_candidates(fetcher)
    assert all("instagram.com" not in url and "tiktok.com" not in url for url in requested)


def test_weverse_artist_and_live_items_keep_direct_original_links():
    for source_id, path in (
        ("weverse-bts-live", "/bts/live/4-216221564"),
        ("weverse-bts-artist", "/bts/artist/3-224457001"),
    ):
        source = next(source for source in SOURCES if source["id"] == source_id)
        rows = _extract(source, f'<a href="{path}">member update 2026.10.02</a>')
        assert len(rows) == 1
        assert rows[0]["original_url"].endswith(path)
        assert rows[0]["source_type"] == source["source_type"]
        assert rows[0]["published_at"].startswith("2026-10-02")
        assert rows[0]["provenance_url"]


def test_today_refreshes_feed_and_filters_legacy_social_posts(monkeypatch):
    class Repo:
        def today(self, user_id):
            return [
                {"id": "notice-1", "source_type": "weverse_shop", "discovered_at": "2026-10-01T00:00:00Z"},
                {"id": "old-social", "source_type": "instagram", "member": "RM"},
            ]
    monkeypatch.setattr("services.bts_radar_service.collect_candidates", lambda: [
        {"id": "member-1", "source_type": "weverse_artist", "member": "RM", "discovered_at": "2026-10-02T00:00:00Z"}
    ])
    service = BTSRadarService(repository=Repo(), user_id="test")
    result = service.today()
    assert result["item_count"] == 2
    assert [item["id"] for item in result["items"]] == ["member-1", "notice-1"]


def test_bts_importance_rules_put_major_events_a_products_c_and_unknown_b():
    assert classify_importance({"source_type": "weverse", "official": True, "title": "BTS WORLD TOUR announcement"}) == "A"
    assert classify_importance({"source_type": "weverse_live", "official": True, "title": "Good night LIVE"}) == "B"
    assert classify_importance({"source_type": "weverse_shop", "official": True, "title": "BTS merch"}) == "C"
    assert classify_importance({"source_type": "unknown", "official": True, "title": "Mystery update"}) == "B"


def test_bts_summarization_only_calls_llm_for_a_tier_and_fences_source_text():
    import json
    from types import SimpleNamespace

    class Provider:
        def __init__(self):
            self.messages = None
        def is_available(self):
            return True
        def complete(self, messages, **kwargs):
            self.messages = messages
            return SimpleNamespace(text=json.dumps({"items": [{"candidate": 1, "summary_zh": "官方宣布巡演。"}]}))

    provider = Provider()
    items = [
        {"title": "BTS WORLD TOUR announcement", "category": "演出", "source_type": "weverse", "official": True,
         "importance_level": "A", "preferred_url": "https://weverse.io/bts/notice/1"},
        {"title": "BTS merch", "category": "周边", "source_type": "weverse_shop", "official": True,
         "importance_level": "C", "preferred_url": "https://shop.weverse.io/notice/2", "summary_zh": "原文摘要"},
    ]
    result = summarize(provider, items)
    assert result[0]["summary_zh"] == "官方宣布巡演。"
    assert result[1]["summary_zh"] == "原文摘要"
    prompt = provider.messages[1].content
    assert "UNTRUSTED SOURCE CONTENT" in prompt
    assert "BTS merch" not in prompt


def test_social_sources_are_built_only_from_the_official_account_whitelist():
    import json
    from pathlib import Path

    config = json.loads((Path(__file__).parents[1] / "config" / "official_accounts.json").read_text(encoding="utf-8"))
    approved = {(row["name"], platform, account["handle"])
                for row in config["members"]
                for platform, account in row.get("accounts", {}).items()
                if account.get("verified") is True}
    actual = {(source["member"], source["source_type"], source["url"].rstrip("/").split("/")[-1].lstrip("@"))
              for source in SOURCES if source["source_type"] in {"instagram", "tiktok"}}
    assert actual == approved


def test_archive_uses_read_only_repository_history_and_excludes_social_items():
    class Repo:
        def history(self, user_id, limit):
            assert user_id == "test"
            assert limit == 20
            return [
                {"id": "archive-notice", "source_type": "weverse", "official": True,
                 "title": "BTS WORLD TOUR announcement", "published_at": "2026-10-01T00:00:00Z"},
                {"id": "legacy-social", "source_type": "instagram", "official": True,
                 "title": "A social post"},
            ]

    result = BTSRadarService(repository=Repo(), user_id="test").archive(20)
    assert result["status"] == "ready"
    assert [item["id"] for item in result["items"]] == ["archive-notice"]
    assert result["items"][0]["importance_level"] == "A"

