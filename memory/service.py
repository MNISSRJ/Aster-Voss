"""Unified memory facade used by the Agent runtime and API layer."""
from __future__ import annotations

from dataclasses import dataclass

from . import brain


@dataclass(frozen=True)
class MemoryService:
    user_id: str = "mint"

    @property
    def cloud_enabled(self) -> bool:
        return brain.enabled()

    def list(self):
        return brain.load_entries(self.user_id)

    def context(self, max_chars: int = 1800) -> str:
        return brain.context_block(self.user_id, max_chars=max_chars)

    def add(self, text: str, source: str = "manual") -> bool:
        return brain.add(text, source=source, user_id=self.user_id)

    def delete(self, memory_id: str) -> bool:
        return brain.delete(memory_id, user_id=self.user_id)

    def replace(self, entries) -> bool:
        return brain.replace(entries, user_id=self.user_id)
