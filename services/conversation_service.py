"""Conversation business logic separated from the HTTP layer."""
from __future__ import annotations

from dataclasses import dataclass

from memory import cloud


@dataclass(frozen=True)
class ConversationService:
    user_id: str = "mint"

    @property
    def enabled(self) -> bool:
        return cloud.enabled()

    def list(self):
        return cloud.list_conversations(self.user_id) if self.enabled else []

    def get(self, conversation_id: str):
        return cloud.load_conversation(conversation_id, self.user_id)

    def delete(self, conversation_id: str) -> bool:
        return cloud.delete_conversation(conversation_id, self.user_id)

    def save(self, conversation_id: str, title: str, messages, created_at=None) -> bool:
        return cloud.save_conversation(
            conversation_id,
            title,
            messages,
            self.user_id,
            created_at=created_at,
        )
