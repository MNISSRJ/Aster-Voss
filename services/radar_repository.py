"""Repository wrapper for AI Radar persistence."""
from __future__ import annotations

from memory import cloud
import os


class RadarRepository:
    @property
    def default_user_id(self):
        return (os.getenv("ASTER_DEFAULT_USER_ID") or "mint").strip() or "mint"

    def list(self, limit: int = 14, user_id: str | None = None):
        return cloud.list_ai_briefs(limit=limit, user_id=user_id or self.default_user_id) if cloud.enabled() else []

    def save(self, brief_date: str, payload: dict, user_id: str = "mint") -> bool:
        return cloud.save_ai_brief(brief_date, payload, user_id=user_id or self.default_user_id) if cloud.enabled() else False

    def get(self, brief_date: str, user_id: str | None = None):
        return cloud.load_ai_brief(brief_date, user_id=user_id or self.default_user_id) if cloud.enabled() else None
