"""Provider-neutral memory retrieval interface with a safe lexical fallback."""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class MemoryHit:
    text: str
    score: float


class MemoryRetriever:
    def search(self, query: str, memories: list[dict], limit: int = 6) -> list[MemoryHit]:
        raise NotImplementedError


class LexicalMemoryRetriever(MemoryRetriever):
    def search(self, query: str, memories: list[dict], limit: int = 6) -> list[MemoryHit]:
        terms = set(re.findall(r"\w+", (query or "").lower()))
        if not terms:
            return []
        hits = []
        for memory in memories:
            text = str(memory.get("text", ""))
            memory_terms = set(re.findall(r"\w+", text.lower()))
            overlap = len(terms & memory_terms)
            if overlap:
                hits.append(MemoryHit(text=text, score=overlap / max(1, len(terms))))
        return sorted(hits, key=lambda hit: hit.score, reverse=True)[:limit]


class VectorMemoryRetriever(MemoryRetriever):
    """Reserved for a pgvector-backed implementation; disabled until embeddings are configured."""

    def search(self, query: str, memories: list[dict], limit: int = 6) -> list[MemoryHit]:
        raise RuntimeError("vector retrieval is not configured")
