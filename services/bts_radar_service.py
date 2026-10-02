"""BTS Radar business service."""
from __future__ import annotations

import os
import time

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
        # Refresh on each visit so a cache containing notices cannot hide newer
        # member posts. Stable item IDs let fresh source data replace stale rows.
        fresh = summarize(None, collect_candidates())
        by_id = {str(item.get("id")): item for item in cached if item.get("id")}
        by_id.update({str(item.get("id")): item for item in fresh if item.get("id")})
        items = list(by_id.values())
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
