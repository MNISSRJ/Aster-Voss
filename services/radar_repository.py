"""Repository wrapper for AI Radar persistence."""
from __future__ import annotations

from memory import cloud


class RadarRepository:
    def list(self, limit: int = 14, user_id: str = "mint"):
        return cloud.list_ai_briefs(limit=limit, user_id=user_id) if cloud.enabled() else []

    def save(self, brief_date: str, payload: dict, user_id: str = "mint") -> bool:
        return cloud.save_ai_brief(brief_date, payload, user_id=user_id) if cloud.enabled() else False

    def get(self, brief_date: str, user_id: str = "mint"):
        return cloud.load_ai_brief(brief_date, user_id=user_id) if cloud.enabled() else None
