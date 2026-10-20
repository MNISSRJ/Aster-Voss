from datetime import datetime, timezone

from fastapi.testclient import TestClient

import research_pool
import web_app
from services.research_service import ResearchService


ATOM = b'''<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom">
 <entry><id>https://arxiv.org/abs/2601.12345v2</id><title>Agent Memory Architecture</title>
 <summary>A new method for long term memory in an AI agent.</summary><published>2026-10-06T10:00:00Z</published>
 <author><name>Author A</name></author><category term="cs.AI"/><arxiv:doi>10.1234/example</arxiv:doi></entry>
 <entry><id>https://arxiv.org/abs/2601.99999v1</id><title>Retrieval-Augmented Generation</title>
 <summary>A benchmark for retrieval augmented generation methods.</summary><published>2026-10-05T10:00:00Z</published>
 <author><name>Author B</name></author><category term="cs.CL"/></entry>
</feed>'''


def test_atom_parser_keeps_only_bibliographic_metadata():
    papers = research_pool.parse_arxiv_atom(ATOM)
    assert len(papers) == 2
    assert papers[0]["arxiv_id"] == "2601.12345v2"
    assert papers[0]["id"] == "arxiv:2601.12345"
    assert papers[0]["source_type"] == "paper"
    assert papers[0]["topics"] == ["AI Agent", "新架构", "研究方法"]
    assert "full_text" not in papers[0]


def test_versions_dedupe_and_merge_source_provenance():
    old = {"arxiv_id": "2601.12345v1", "title_original": "A paper", "url": "old", "source": "arXiv"}
    new = {"arxiv_id": "2601.12345v2", "title_original": "A paper", "url": "new", "source": "Conference"}
    result = research_pool.deduplicate_papers([old, new])
    assert len(result) == 1
    assert result[0]["arxiv_id"] == "2601.12345v2"
    assert result[0]["source_list"] == ["Conference", "arXiv"]


def test_weights_are_exact_and_each_component_contributes_independently():
    assert sum(research_pool.WEIGHTS.values()) == 1.0
    now = datetime(2026, 10, 7, tzinfo=timezone.utc)
    paper = {"title_original": "novel agent method", "summary_original": "new agent memory", "published_at": "2026-10-07T00:00:00Z", "citation_count": 0}
    score, values = research_pool.score_paper(paper, interests=["agent"], learning_directions=["memory"], now=now)
    assert values["interest"] > 0.5
    assert values["novelty"] > 0.5
    assert values["influence"] == 0
    assert values["community"] == 0.5  # no real trend source configured
    assert values["learning_direction"] == 1
    assert values["freshness"] == 1
    assert 0 <= score <= 1


def test_repeat_penalty_is_separate_and_configurable():
    item = {"title_original": "Agent paper", "published_at": "2026-10-07T00:00:00Z", "seen_before": True}
    base, _ = research_pool.score_paper(item, repeat_penalty=0, now=datetime(2026, 10, 7, tzinfo=timezone.utc))
    repeated, _ = research_pool.score_paper(item, repeat_penalty=0.3, now=datetime(2026, 10, 7, tzinfo=timezone.utc))
    assert round(base - repeated, 2) == 0.30


def test_zero_citation_new_paper_stays_in_pool_and_500_rank_without_llm():
    papers = [
        {"id": str(index), "title_original": f"Agent memory method {index}", "published_at": "2026-10-07T00:00:00Z", "citation_count": 0}
        for index in range(500)
    ]
    ranked = research_pool.rank_papers(papers, now=datetime(2026, 10, 7, tzinfo=timezone.utc))
    assert len(ranked) == 500
    assert sum(p["citation_count"] == 0 for p in ranked) == 500
    assert all("_score" in item for item in ranked)


def test_knowledge_budget_is_soft_and_within_expected_ranges():
    papers = [{"id": str(n)} for n in range(20)]
    assert len(research_pool.knowledge_budget_items(papers, 10)) == 3
    assert 5 <= len(research_pool.knowledge_budget_items(papers, 20)) <= 8
    assert 7 <= len(research_pool.knowledge_budget_items(papers, 30)) <= 10


def test_pool_search_covers_unrecommended_items():
    papers = [{"id": "1", "title_original": "Agent Memory"}, {"id": "2", "title_original": "RAG benchmark"}]
    assert research_pool.search_pool(papers, "agent memory")[0]["id"] == "1"


def test_service_keeps_cached_pool_if_source_fails():
    responses = [[{"arxiv_id": "2601.00001v1", "title_original": "Agent Memory", "source": "arXiv"}], RuntimeError("limited")]
    def fetcher(**kwargs):
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value
    service = ResearchService(fetcher=fetcher, ttl_seconds=60)
    assert service.refresh(force=True)["pool_count"] == 1
    stale = service.refresh(force=True)
    assert stale["pool_count"] == 1
    assert stale["source_errors"] == {"arXiv": "RuntimeError"}


def test_selected_summary_is_cached_and_ranking_does_not_call_llm(monkeypatch):
    import ai_radar
    calls = []
    def curate(provider, candidates):
        calls.append(len(candidates))
        return [{"id": candidates[0]["id"], "ai_status": "ready", "title_zh": "中文标题", "summary_zh": "中文速览", "source_type": "ai_summary", "core_concepts": ["Agent"]}]
    monkeypatch.setattr(ai_radar, "curate_v2", curate)
    paper = {"id": "arxiv:one", "title_original": "Agent memory paper", "summary_original": "A new agent memory method", "source": "arXiv", "url": "https://arxiv.org/abs/one", "published_at": "2026-10-07T00:00:00Z"}
    service = ResearchService(fetcher=lambda **kwargs: [paper])
    class Provider:
        def is_available(self):
            return True
    # Ranking path omits provider calls; only final shortlist enrichment uses it.
    ranked = research_pool.rank_papers([paper])
    assert len(ranked) == 1 and not calls
    first = service.recommended(provider=Provider())
    second = service.recommended(provider=Provider())
    assert first["items"][0]["title_zh"] == "中文标题"
    assert second["items"][0]["title_zh"] == "中文标题"
    assert calls == [1]


def test_research_api_returns_items_and_internal_scores_are_not_exposed(monkeypatch):
    fake = ResearchService(fetcher=lambda **kwargs: [{"id": "arxiv:abc", "arxiv_id": "abc", "title_original": "RAG research", "summary_original": "retrieval augmented generation", "source": "arXiv", "published_at": "2026-10-07T00:00:00Z", "url": "https://arxiv.org/abs/abc"}])
    monkeypatch.setattr(web_app, "RESEARCH", fake)
    monkeypatch.setattr(web_app, "_research_provider", lambda: None)
    monkeypatch.setattr(web_app, "radar_2_enabled", lambda: True)
    response = TestClient(web_app.app).get("/api/research/today?minutes=20")
    assert response.status_code == 200
    data = response.json()
    assert data["pool_count"] == 1
    assert data["items"][0]["source_type"] == "paper"
    assert data["items"][0]["url"] == "https://arxiv.org/abs/abc"
    assert "_score" not in data["items"][0]

