"""Aster Voss - identity and memory package.

Two clearly separated concepts:

    identity -> who Aster Voss is          (aster/identity.py)
    memory   -> what the user wants kept   (aster/memory.py)

Both are plain standard-library data structures so the agent core can stay
independent of how identity is configured.
"""

from __future__ import annotations

from .identity import (
    AGENT_IDENTITY,
    AGENT_IDENTITY_VERSION,
    AGENT_NAME,
    AGENT_TAGLINE,
    PROJECT_VERSION,
    AgentIdentity,
    Responsibility,
)
from .memory import (
    USER_PROFILE_PATH,
    MemoryStore,
    get_memory,
    memory_context,
    scrub_secrets,
)

__all__ = [
    "AGENT_IDENTITY",
    "AGENT_IDENTITY_VERSION",
    "AGENT_NAME",
    "AGENT_TAGLINE",
    "PROJECT_VERSION",
    "AgentIdentity",
    "Responsibility",
    "MemoryStore",
    "USER_PROFILE_PATH",
    "get_memory",
    "memory_context",
    "scrub_secrets",
]
