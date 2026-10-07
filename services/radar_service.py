"""AI Radar business service."""
from __future__ import annotations

import os
import time

import log

from ai_radar import collect_candidates, curate, curate_v2, generate_story, _raw_item
from memory import cloud
from ai_radar_enrichment import LANGUAGE, STORY_PROMPT_VERSION, cache_key, classify_importance, content_hash
from feature_flags import radar_2_enabled


class RadarService:
    def __init__(self, repository=None, user_id: str | None = None):
        from .radar_repository import RadarRepository
        self.repository = repository or RadarRepository()
        self.user_id = user_id or (os.getenv("ASTER_DEFAULT_USER_ID") or "mint").strip() or "mint"
        self._story_cache = {}

    def _fallback_payload(self, candidates):
        return {
            "status": "fallback" if candidates else "empty",
            "brief_date": time.strftime("%Y-%m-%d", time.gmtime()),
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "intro_zh": (
                "AI 编辑暂时不可用，以下按新鲜度与跨来源出现情况展示实时候选。"
                if candidates else "今天暂时没有抓到可用的 AI 热点。"
            ),
            "items": [
                {
                    "id": item["id"],
                    "headline_zh": item["title"],
                    "summary_zh": item.get("description", "")[:180],
                    "why_it_matters_zh": "按新鲜度与跨来源出现情况排序。",
                    "company": "",
                    "tags": ["AI 热点"],
                    "url": item["url"],
                    "source_list": item.get("source_list", []),
                    "published_at": item["published_at"],
                    "hot_score": item["hot_score"],
                }
                for item in candidates[:6]
            ],
            "source_count": len({s for item in candidates for s in item.get("source_list", [])}),
            "candidate_count": len(candidates),
        }

    def generate(self, provider=None):
        if radar_2_enabled():
            return self._generate_v2(provider)
        candidates = collect_candidates()
        if not candidates:
            payload = self._fallback_payload([])
        elif provider and provider.is_available():
            payload = None
            last_error = None
            for attempt in (1, 2):
                try:
                    payload = curate(provider, candidates, attempt=attempt)
                    break
                except Exception as exc:
                    last_error = exc
                    log.info(
                        "radar curation failed attempt=%s error=%s",
                        attempt,
                        f"{type(exc).__name__}: {str(exc)[:240]}",
                    )
            if payload is None:
                log.error(
                    "radar curation exhausted attempts error=%s",
                    type(last_error).__name__ if last_error else "unknown",
                )
                payload = self._fallback_payload(candidates)
        else:
            payload = self._fallback_payload(candidates)

        payload.setdefault("status", "ready" if payload.get("items") else "empty")
        payload["saved"] = (
            bool(self.repository.save(payload["brief_date"], payload, self.user_id))
            if cloud.enabled()
            else False
        )
        return payload

    @staticmethod
    def _cached_enrichments(briefs):
        cached = {}
        for brief in briefs or []:
            payload = brief.get("payload") if isinstance(brief, dict) else None
            for item in payload.get("items", []) if isinstance(payload, dict) else []:
                if isinstance(item, dict) and item.get("ai_status") == "ready" and item.get("ai_cache_key"):
                    cached[item["ai_cache_key"]] = item
        return cached

    def _generate_v2(self, provider=None):
        candidates = collect_candidates()
        for candidate in candidates:
            candidate["importance"] = classify_importance(candidate)
        # Keep selection bounded and predictable; the score remains internal.
        selected = candidates[:6]
        historical = self.repository.list(limit=14, user_id=self.user_id) if cloud.enabled() else []
        cached = self._cached_enrichments(historical)
        ai_candidates = [item for item in selected if item["importance"] in {"A", "B"}]
        generated_by_key = {}
        uncached = [item for item in ai_candidates if cache_key(item) not in cached]
        if uncached and provider and provider.is_available():
            try:
                generated = curate_v2(provider, uncached)
                generated_by_key = {item["ai_cache_key"]: item for item in generated}
            except Exception as exc:
                log.info("radar v2 enrichment failed error=%s", type(exc).__name__)

        results = []
        for candidate in selected:
            importance = candidate["importance"]
            if importance == "C":
                # C items are rendered from source text and never sent to an LLM.
                item = _raw_item(candidate, importance, "source_only")
                item["source_type"] = "official" if item["source_type"] == "official" else "ai_summary"
            else:
                key = cache_key(candidate)
                item = cached.get(key) or generated_by_key.get(key) or _raw_item(candidate, importance)
                # Refresh transient feed metadata while reusing only cached AI fields.
                item = {**item, "source_list": candidate.get("source_list", []), "hot_score": candidate.get("hot_score", 0)}
            results.append(item)

        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        payload = {
            "status": "ready" if results else "empty",
            "brief_date": time.strftime("%Y-%m-%d", time.gmtime()),
            "generated_at": now,
            "intro_zh": "今天的 AI 动态已按重要性整理；低重要性条目使用原始摘要。" if results else "今天暂时没有抓到可用的 AI 热点。",
            "items": results,
            "source_count": len({source for item in candidates for source in item.get("source_list", [])}),
            "candidate_count": len(candidates),
            "saved": False,
            "radar_version": 2,
        }
        if cloud.enabled():
            payload["saved"] = bool(self.repository.save(payload["brief_date"], payload, self.user_id))
        return payload

    def story(self, item: dict, provider=None):
        if not radar_2_enabled():
            return {"status": "disabled", "ai_generated": False}
        if not isinstance(item, dict):
            return {"status": "unavailable", "message": "找不到这条 Radar 内容。"}
        item_hash = str(item.get("content_hash") or content_hash(item))
        key = ":".join((item_hash, STORY_PROMPT_VERSION, LANGUAGE))
        cache = item.get("story_cache") if isinstance(item.get("story_cache"), dict) else {}
        if key in cache:
            return cache[key]
        if key in self._story_cache:
            return self._story_cache[key]
        if not provider or not provider.is_available():
            return {"status": "unavailable", "message": "故事解释暂不可用；你仍可查看原文或询问 Aster。"}
        try:
            result = generate_story(provider, item)
        except Exception as exc:
            log.info("radar story failed error=%s", type(exc).__name__)
            return {"status": "unavailable", "message": "故事解释暂不可用；你仍可查看原文或询问 Aster。"}
        self._story_cache[key] = result
        while len(self._story_cache) > 64:
            self._story_cache.pop(next(iter(self._story_cache)))
        # Persist inside the existing daily brief JSON payload; no schema change.
        today = self.today()
        if today:
            for saved_item in today.get("items", []):
                if saved_item.get("id") == item.get("id") and saved_item.get("content_hash") == item_hash:
                    saved_item.setdefault("story_cache", {})[key] = result
                    self.repository.save(today.get("brief_date", ""), today, self.user_id)
                    break
        return result
    def today(self):
        date_str = time.strftime("%Y-%m-%d", time.gmtime())
        stored = self.repository.get(date_str, self.user_id)
        if stored and isinstance(stored.get("payload"), dict):
            payload = dict(stored["payload"])
            payload.setdefault("status", "ready" if payload.get("items") else "empty")
            return payload
        return None

    def history(self, limit=14):
        return self.repository.list(limit=limit, user_id=self.user_id)

