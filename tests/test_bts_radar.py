from bts_radar import SOURCES, _extract, collect_candidates
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
