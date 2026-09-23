"""Jev compatibility layer.

Jev is optional in the first public Aster Voss deployment.  The classes below
keep the original interface importable while safely disabling the service when
no JEV credentials are configured.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class JevDecision:
    """Minimal decision object kept for API compatibility."""
    provider: str = ""
    reason: str = ""
    complexity: int = 1


class JevClient:
    """No-op Jev client used when the optional service is not configured."""

    def __init__(self, api_key: str = "", base_url: str = "", timeout: float = 8.0):
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.enabled = bool(api_key)

    def decide(self, *args: Any, **kwargs: Any) -> JevDecision | None:
        return None


class NullJev(JevClient):
    def __init__(self):
        super().__init__()

    def decide(self, *args: Any, **kwargs: Any) -> None:
        return None


def create_jev_client(config: Any) -> JevClient:
    return JevClient(
        api_key=getattr(config, "jev_api_key", "") or "",
        base_url=getattr(config, "jev_base_url", "https://www.jevai.org"),
        timeout=float(getattr(config, "jev_timeout", 8.0)),
    )
