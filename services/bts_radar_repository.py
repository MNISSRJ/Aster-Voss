"""Persistence boundary for BTS Radar."""
from __future__ import annotations

from bts_radar import SOURCES
from memory import cloud
import os


class BTSRadarRepository:
    @property
    def default_user_id(self):
        return (os.getenv("ASTER_DEFAULT_USER_ID") or "mint").strip() or "mint"

    def save(self, items: list[dict], user_id: str | None = None) -> bool:
        return cloud.save_bts_radar_items(items, user_id=user_id or self.default_user_id) if cloud.enabled() else False

    def today(self, user_id: str | None = None):
        return cloud.list_bts_radar_items(limit=30, user_id=user_id or self.default_user_id)

    def sources(self):
        return cloud.list_bts_radar_sources(limit=20) or SOURCES
