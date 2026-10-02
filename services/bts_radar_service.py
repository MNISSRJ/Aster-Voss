"""BTS Radar business service."""
from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone

from bts_radar import SOURCES, collect_candidates, summarize
from memory import cloud


class BTSRadarService:
    def __init__(self, repository=None, user_id: str | None = None):
        from .bts_radar_repository import BTSRadarRepository
        self.repository = repository or BTSRadarRepository()
        self.user_id = user_id or (os.getenv("ASTER_DEFAULT_USER_ID") or "mint").strip() or "mint"

    def generate(self, provider=None):
        items = collect_candidates()
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
        # Serve the saved feed immediately. Collection remains on the refresh and
        # cron paths so a slow external platform cannot block the page on entry.
        media_cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        def recent_media(item):
            if item.get("source_type") != "media" or not item.get("published_at"):
                return True
            try:
                published = datetime.fromisoformat(item["published_at"].replace("Z", "+00:00"))
                return published >= media_cutoff
            except (TypeError, ValueError):
                return False
        items = [
            item for item in cached
            if item.get("id") and item.get("source_type") not in {"instagram", "tiktok"}
            and recent_media(item)
        ]
        items.sort(
            key=lambda item: item.get("published_at") or item.get("discovered_at") or "",
            reverse=True,
        )
        items = items[:30]
        if items:
            return {
                "status": "ready",
                "generated_at": max((item.get("discovered_at") or "" for item in items), default=None) or None,
                "source_count": len({item.get("source_id") for item in items}),
                "item_count": len(items),
                "items": items,
            }
        return {"status": "empty", "generated_at": None, "source_count": len(SOURCES), "item_count": 0, "items": []}
