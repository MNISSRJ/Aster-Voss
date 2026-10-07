"""Request-driven research discovery with a bounded process cache.

The cache is deliberately non-durable until Preview/Production DB isolation is
proven. It never writes to Supabase in this phase.
"""
from __future__ import annotations

import threading
import time
from typing import Callable

from research_pool import deduplicate_papers, fetch_arxiv, fetch_semantic_scholar, knowledge_budget_items, rank_papers, search_pool
from ai_radar_enrichment import LANGUAGE, PROMPT_VERSION, cache_key


class ResearchService:
    def __init__(self, fetcher: Callable | None = None, ttl_seconds: int = 3600):
        self.fetcher = fetcher
        self.ttl_seconds = max(60, int(ttl_seconds))
        self._lock = threading.Lock()
        self._pool: list[dict] = []
        self._fetched_at = 0.0
        self._source_errors: dict[str, str] = {}
        self._enrichment_cache: dict[str, dict] = {}

    def refresh(self, force: bool = False) -> dict:
        now = time.time()
        with self._lock:
            if not force and self._fetched_at and now - self._fetched_at < self.ttl_seconds:
                return self.snapshot()
            errors = {}
            candidates = []
            if self.fetcher:
                try:
                    candidates.extend(self.fetcher(limit=500))
                except Exception as exc:
                    errors["arXiv"] = type(exc).__name__
            else:
                try:
                    candidates.extend(fetch_arxiv(limit=500))
                except Exception as exc:
                    errors["arXiv"] = type(exc).__name__
                ids = [item.get("arxiv_id", "") for item in candidates if item.get("arxiv_id")]
                if ids:
                    try:
                        metadata = fetch_semantic_scholar(ids)
                        by_id = {}
                        for row in metadata:
                            external = row.get("externalIds") or {}
                            arxiv_id = str(external.get("ArXiv") or "").removeprefix("arXiv:")
                            if arxiv_id:
                                by_id[arxiv_id] = row
                        for paper in candidates:
                            row = by_id.get(str(paper.get("arxiv_id", "")).split("v", 1)[0])
                            if not row:
                                continue
                            paper["citation_count"] = row.get("citationCount")
                            paper["influential_citation_count"] = row.get("influentialCitationCount")
                            paper["venue"] = row.get("venue") or ""
                            paper["semantic_scholar_url"] = row.get("url") or ""
                            paper["source_list"] = ["arXiv", "Semantic Scholar"]
                    except Exception as exc:
                        errors["Semantic Scholar"] = type(exc).__name__
            if candidates:
                self._pool = deduplicate_papers(candidates)
            self._fetched_at = now
            self._source_errors = errors
            return self.snapshot()

    def snapshot(self) -> dict:
        return {
            "status": "ready" if self._pool else "empty",
            "items": [dict(item) for item in self._pool],
            "pool_count": len(self._pool),
            "sources": sorted({source for item in self._pool for source in item.get("source_list", [])}),
            "source_errors": dict(self._source_errors),
            "fetched_at": self._fetched_at or None,
            "persistence": "process-cache",
        }

    def recommended(self, minutes: int = 20, force_refresh: bool = False, provider=None) -> dict:
        pool = self.refresh(force=force_refresh)
        ranked = rank_papers(pool["items"])
        selected = knowledge_budget_items(ranked, minutes)
        enriched = {}
        for paper in selected:
            candidate = {"title": paper.get("title_original", ""), "description": paper.get("summary_original", "")}
            key = cache_key(candidate, PROMPT_VERSION, LANGUAGE)
            if key in self._enrichment_cache:
                enriched[paper["id"]] = dict(self._enrichment_cache[key])
        uncached = [paper for paper in selected if paper["id"] not in enriched]
        if uncached and provider and provider.is_available():
            try:
                from ai_radar import curate_v2
                candidates = [{
                    "id": item["id"], "title": item.get("title_original", ""),
                    "description": item.get("summary_original", ""), "url": item.get("url", ""),
                    "source_list": item.get("source_list", [item.get("source", "arXiv")]),
                    "published_at": item.get("published_at", ""), "importance": "B",
                } for item in uncached]
                generated = curate_v2(provider, candidates)
                generated_by_id = {item.get("id"): item for item in generated if item.get("id")}
                for paper in uncached:
                    translation = generated_by_id.get(paper["id"])
                    if not translation:
                        continue
                    if translation.get("ai_status") == "ready":
                        key = cache_key({"title": paper.get("title_original", ""), "description": paper.get("summary_original", "")}, PROMPT_VERSION, LANGUAGE)
                        self._enrichment_cache[key] = dict(translation)
                        enriched[paper["id"]] = dict(translation)
                while len(self._enrichment_cache) > 256:
                    self._enrichment_cache.pop(next(iter(self._enrichment_cache)))
            except Exception:
                # Original metadata remains available when model calls fail.
                pass
        output = []
        for paper in selected:
            item = self._public_item(paper)
            translation = enriched.get(item["id"])
            if translation and translation.get("ai_status") == "ready":
                item.update({key: translation.get(key) for key in (
                    "title_zh", "summary_zh", "one_liner_zh", "core_concepts",
                    "related_concepts", "ai_status", "ai_generated_at", "source_type", "fact_check",
                )})
            else:
                item.update({"ai_status": "failed", "summary_zh": "中文摘要暂不可用；以下保留论文原始摘要。", "source_type": "paper"})
            output.append(item)
        return {
            **pool,
            "budget_minutes": max(1, min(int(minutes), 60)),
            "items": output,
            "recommendation_count": len(output),
        }

    def search(self, query: str, limit: int = 50) -> dict:
        pool = self.refresh()
        matches = search_pool(pool["items"], query, limit)
        # Search results are sorted using the same deterministic non-LLM policy.
        ranked = rank_papers(matches)
        return {**pool, "query": query[:160], "items": [self._public_item(item) for item in ranked], "result_count": len(ranked)}

    @staticmethod
    def _public_item(item: dict) -> dict:
        return {key: value for key, value in item.items() if not key.startswith("_")}


RESEARCH = ResearchService()

