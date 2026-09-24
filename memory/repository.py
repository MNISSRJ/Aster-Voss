"""Repository boundaries for durable Aster data."""
from __future__ import annotations

from dataclasses import dataclass
from . import brain, cloud


@dataclass(frozen=True)
class MemoryRepository:
    user_id: str

    def list(self):
        return brain.load_entries(self.user_id)

    def save(self, entries) -> bool:
        return brain.save_entries(entries, self.user_id)


@dataclass(frozen=True)
class ConversationRepository:
    user_id: str

    def list(self):
        return cloud.list_conversations(self.user_id) if cloud.enabled() else []

    def get(self, conversation_id: str):
        return cloud.load_conversation(conversation_id, self.user_id) if cloud.enabled() else None

    def save(self, conversation_id: str, title: str, messages, created_at=None) -> bool:
        return cloud.save_conversation(
            conversation_id, title, messages, self.user_id, created_at=created_at
        )

    def delete(self, conversation_id: str) -> bool:
        return cloud.delete_conversation(conversation_id, self.user_id) if cloud.enabled() else False
