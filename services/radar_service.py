"""AI Radar business service."""
from __future__ import annotations

import time

from ai_radar import collect_candidates, curate
from memory import cloud


class RadarService:
    def _fallback_payload(self, candidates):
        return {
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
        if cloud.enabled():
            cloud.save_ai_brief(payload["brief_date"], payload)
        return payload

    def today(self):
        date_str = time.strftime("%Y-%m-%d", time.gmtime())
        stored = cloud.load_ai_brief(date_str) if cloud.enabled() else None
        return stored["payload"] if stored and isinstance(stored.get("payload"), dict) else None
