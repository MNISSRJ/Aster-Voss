"""Jev decision layer package."""

from __future__ import annotations

from typing import Any

from .client import JevClient, JevDecision

__all__ = ["JevClient", "JevDecision", "create_jev_client"]


def create_jev_client(agent_config: Any) -> JevClient:
    """Build a Jev client from configuration.

    A missing JEV_API_KEY never raises: the client is created in a disabled
    state so the agent starts normally (graceful degradation).
    """
    return JevClient(
        api_key=getattr(agent_config, "jev_api_key", "") or "",
        base_url=getattr(agent_config, "jev_base_url", "https://www.jevai.org"),
        timeout=float(getattr(agent_config, "jev_timeout", 8.0)),
    )
