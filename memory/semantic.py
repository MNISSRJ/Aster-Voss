"""Optional semantic memory retrieval using OpenAI embeddings + Supabase pgvector."""
from __future__ import annotations

import os

from .embeddings import OpenAIEmbeddingProvider
from . import cloud


def search(query: str, user_id: str, limit: int = 6, threshold: float = 0.72):
    api_key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")
    if not api_key or not cloud.enabled():
        return []
    provider = OpenAIEmbeddingProvider(
        api_key=api_key,
        model=model,
        base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    vector = provider.embed(query)
    return cloud.match_memory_vectors(
        vector,
        user_id=user_id,
        limit=limit,
        threshold=threshold,
    )
