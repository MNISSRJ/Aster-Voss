"""BTS Radar business service."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

from bts_radar import SOURCES, classify_importance, collect_candidates, summarize
from memory import cloud


class BTSRadarService:
    def __init__(self, repository=None, user_id: str | None = None):
        from .bts_radar_repository import BTSRadarRepository
        self.repository = repository or BTSRadarRepository()
        self.user_id = user_id or (os.getenv("ASTER_DEFAULT_USER_ID") or "mint").strip() or "mint"

    def generate(self, provider=None):
        items = collect_candidates()
        for item in items:
            item["importance_level"] = classify_importance(item)
        items = summarize(provider, items)
        saved = bool(self.repository.save(items, self.user_id)) if cloud.enabled() else False
        return {
            "status": "ready" if items else "empty",
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_count": len(SOURCES),
            "item_count": len(items),
            "items": items,
            "saved": saved,
        }

    def today(self):
        cached = self.repository.today(self.user_id)
        # Refresh on page entry so recent official notices and media coverage
        # remain visible even when Preview has no persisted Supabase cache.
        media_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        def recent_media(item):
            if item.get("source_type") != "media" or not item.get("published_at"):
                return True
            try:
                published = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
                return published >= media_cutoff
            except (TypeError, ValueError):
                return False
        by_id = {
            str(item.get("id")): item for item in cached
            if item.get("id") and item.get("source_type") not in {"instagram", "tiktok"}
            and recent_media(item)
        }
        fresh = summarize(None, collect_candidates())
        by_id.update({str(item.get("id")): item for item in fresh if item.get("id")})
        items = list(by_id.values())
        for item in items:
            item["importance_level"] = classify_importance(item)
        items.sort(
            key=lambda item: item.get("published_at") or item.get("discovered_at") or "",
            reverse=True,
        )
        items = items[:30]
        if items:
            return {
                "status": "ready",
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "source_count": len({item.get("source_id") for item in items}),
                "item_count": len(items),
                "items": items,
            }
        return {"status": "empty", "generated_at": None, "source_count": len(SOURCES), "item_count": 0, "items": []}

    def archive(self, limit: int = 50):
        history = getattr(self.repository, "history", None)
        if not callable(history):
            return {"status": "empty", "item_count": 0, "items": []}
        items = history(self.user_id, limit)
        items = [item for item in items if item.get("source_type") not in {"instagram", "tiktok"}]
        for item in items:
            item["importance_level"] = classify_importance(item)
        items.sort(key=lambda item: item.get("published_at") or item.get("discovered_at") or "", reverse=True)
        return {"status": "ready" if items else "empty", "item_count": len(items), "items": items[:limit]}

