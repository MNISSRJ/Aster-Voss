"""AI Radar business service."""
from __future__ import annotations

import os
import time

from ai_radar import collect_candidates, curate
from memory import cloud


class RadarService:
    def __init__(self, repository=None, user_id: str | None = None):
        from .radar_repository import RadarRepository
        self.repository = repository or RadarRepository()
        self.user_id = user_id or (os.getenv("ASTER_DEFAULT_USER_ID") or "mint").strip() or "mint"

    def _fallback_payload(self, candidates):
        return {
            "status": "ready" if candidates else "empty",
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
        candidates = collect_candidates()
        if not candidates:
            payload = self._fallback_payload([])
        elif provider and provider.is_available():
            try:
                payload = curate(provider, candidates)
            except Exception:
                payload = self._fallback_payload(candidates)
        else:
            payload = self._fallback_payload(candidates)
        payload.setdefault("status", "ready" if payload.get("items") else "empty")
        payload["saved"] = bool(self.repository.save(payload["brief_date"], payload, self.user_id)) if cloud.enabled() else False
        return payload

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
