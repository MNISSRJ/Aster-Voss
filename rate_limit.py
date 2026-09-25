"""Request rate limiting with explicit Local/Serverless/Supabase semantics."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import math
import os
import threading
import time

from memory import cloud
from memory.persistence import is_serverless_environment


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    backend: str
    limit: int
    count: int | None = None
    remaining: int | None = None
    retry_after: int | None = None
    degraded: bool = False
    error: str | None = None


class RateLimiter:
    """Use Supabase atomics in serverless and process-local state in local dev."""

    def __init__(self):
        self._lock = threading.Lock()
        self._windows: dict[tuple[str, str, int], int] = {}
        self._backend = "unknown"

    @property
    def strict(self) -> bool:
        raw = os.getenv("ASTER_RATE_LIMIT_STRICT", "")
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    @property
    def backend_status(self) -> str:
        if self._backend != "unknown":
            return self._backend
        if cloud.enabled():
            return "supabase-configured"
        return "disabled-serverless" if is_serverless_environment() else "process-local"

    @staticmethod
    def client_key(raw_identity: str) -> str:
        digest = hashlib.sha256((raw_identity or "unknown").encode("utf-8")).hexdigest()
        return digest[:32]

    def reset(self) -> None:
        with self._lock:
            self._windows.clear()
            self._backend = "unknown"

    def check(
        self,
        scope: str,
        client_key: str,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        limit = max(1, int(limit))
        window_seconds = max(1, int(window_seconds))

        if cloud.enabled():
            result = cloud.consume_rate_limit(
                f"{scope}:{client_key}",
                window_seconds,
                limit,
            )
            if result is not None:
                count = max(0, int(result.get("count") or 0))
                remaining = max(0, limit - count)
                retry_after = None
                try:
                    window_start = float(result.get("window_start"))
                    retry_after = max(
                        1,
                        int(math.ceil(window_start + window_seconds - time.time())),
                    )
                except (TypeError, ValueError):
                    pass
                self._backend = "supabase"
                return RateLimitDecision(
                    allowed=bool(result.get("allowed")),
                    backend="supabase",
                    limit=limit,
                    count=count,
                    remaining=remaining,
                    retry_after=retry_after,
                )

            # A configured cloud backend that cannot execute the RPC is a
            # degraded state, not something to silently relabel as durable.
            self._backend = "degraded"
            if is_serverless_environment():
                if self.strict:
                    return RateLimitDecision(
                        allowed=False,
                        backend="supabase-unavailable",
                        limit=limit,
                        degraded=True,
                        error="durable rate-limit backend unavailable",
                    )
                return RateLimitDecision(
                    allowed=True,
                    backend="degraded",
                    limit=limit,
                    degraded=True,
                    error="durable rate-limit backend unavailable",
                )

        if is_serverless_environment():
            self._backend = "disabled-serverless"
            if self.strict:
                return RateLimitDecision(
                    allowed=False,
                    backend="disabled-serverless",
                    limit=limit,
                    degraded=True,
                    error="serverless rate limiting requires Supabase",
                )
            return RateLimitDecision(
                allowed=True,
                backend="disabled-serverless",
                limit=limit,
                degraded=True,
                error="serverless rate limiting requires Supabase",
            )

        self._backend = "process-local"
        now = int(time.time())
        window_start = (now // window_seconds) * window_seconds
        key = (scope, client_key, window_start)
        with self._lock:
            count = self._windows.get(key, 0) + 1
            self._windows[key] = count
            if len(self._windows) > 2048:
                cutoff = window_start - (window_seconds * 2)
                self._windows = {
                    item: value
                    for item, value in self._windows.items()
                    if item[2] >= cutoff
                }
        return RateLimitDecision(
            allowed=count <= limit,
            backend="process-local",
            limit=limit,
            count=count,
            remaining=max(0, limit - count),
            retry_after=max(1, window_start + window_seconds - now),
        )


def rate_limit_rule(method: str, path: str):
    """Return (scope, limit, window_seconds) for cost-bearing mutations."""
    exact = {
        ("POST", "/api/chat"): ("chat", 30, 60),
        ("POST", "/api/ai-radar/refresh"): ("radar_refresh", 6, 60),
        ("POST", "/api/memory"): ("memory_write", 20, 60),
        ("POST", "/api/memory/summarize"): ("memory_ai", 10, 60),
        ("POST", "/api/memory/suggestions"): ("memory_ai", 10, 60),
    }
    if (method, path) in exact:
        return exact[(method, path)]
    if path.startswith("/api/memory/") and method in {"PUT", "DELETE"}:
        return ("memory_write", 20, 60)
    return None
