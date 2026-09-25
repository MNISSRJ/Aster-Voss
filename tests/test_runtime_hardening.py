from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
import time

from fastapi.testclient import TestClient

from agent import TurnResult
from llm.base import LLMMessage
from memory import cloud, persistence
from rate_limit import RateLimitDecision, RateLimiter
import web_app


def test_local_rate_limiter_is_repeatable_and_resettable(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("ASTER_RATE_LIMIT_STRICT", raising=False)
    monkeypatch.setattr(cloud, "enabled", lambda: False)

    limiter = RateLimiter()
    first = limiter.check("test", "client", 1, 60)
    second = limiter.check("test", "client", 1, 60)
    assert first.allowed is True
    assert second.allowed is False

    limiter.reset()
    again = limiter.check("test", "client", 1, 60)
    assert again.allowed is True
    assert again.backend == "process-local"


def test_serverless_without_cloud_is_explicitly_degraded(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.delenv("ASTER_RATE_LIMIT_STRICT", raising=False)
    monkeypatch.setattr(cloud, "enabled", lambda: False)

    decision = RateLimiter().check("test", "client", 10, 60)
    assert decision.allowed is True
    assert decision.backend == "disabled-serverless"
    assert decision.degraded is True


def test_serverless_strict_requires_durable_backend(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("ASTER_RATE_LIMIT_STRICT", "true")
    monkeypatch.setattr(cloud, "enabled", lambda: False)

    decision = RateLimiter().check("test", "client", 10, 60)
    assert decision.allowed is False
    assert decision.backend == "disabled-serverless"
    assert decision.error


def test_supabase_rate_limiter_is_used_when_available(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(cloud, "enabled", lambda: True)
    monkeypatch.setattr(
        cloud,
        "consume_rate_limit",
        lambda key, window_seconds, limit: {
            "allowed": True,
            "count": 1,
            "window_start": time.time(),
        },
    )

    decision = RateLimiter().check("chat", "client", 30, 60)
    assert decision.backend == "supabase"
    assert decision.allowed is True
    assert decision.remaining == 29


def test_supabase_rate_limiter_failure_is_explicit(monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("ASTER_RATE_LIMIT_STRICT", "true")
    monkeypatch.setattr(cloud, "enabled", lambda: True)
    monkeypatch.setattr(cloud, "consume_rate_limit", lambda *args, **kwargs: None)

    decision = RateLimiter().check("chat", "client", 30, 60)
    assert decision.allowed is False
    assert decision.backend == "supabase-unavailable"


def test_rate_limited_api_returns_429(monkeypatch):
    monkeypatch.setattr(
        web_app,
        "RATE_LIMITER",
        SimpleNamespace(
            check=lambda *args: RateLimitDecision(
                False,
                "process-local",
                30,
                count=31,
                remaining=0,
                retry_after=15,
            ),
            client_key=lambda value: "client",
            backend_status="process-local",
            strict=False,
        ),
    )
    response = TestClient(web_app.app).post("/api/chat", json={"message": "ping"})
    assert response.status_code == 429
    assert response.headers["Retry-After"] == "15"
    assert response.json()["rate_limit_backend"] == "process-local"


def test_constant_time_auth_path_uses_hmac(monkeypatch):
    monkeypatch.setattr(
        web_app,
        "CONFIG",
        SimpleNamespace(require_auth=True, log_level="INFO"),
    )
    monkeypatch.setenv("ASTER_ACCESS_TOKEN", "secret")
    calls = []
    monkeypatch.setattr(
        web_app.hmac,
        "compare_digest",
        lambda a, b: calls.append((a, b)) or True,
    )
    monkeypatch.setattr(web_app.CONVERSATIONS, "list", lambda: [])

    response = TestClient(web_app.app).get(
        "/api/conversations",
        headers={"Authorization": "Bearer secret"},
    )
    assert response.status_code == 200
    assert calls


def test_local_chat_transaction_prevents_lost_updates(monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    history = []
    active = 0
    max_active = 0

    class FakeAgent:
        def __init__(self, seen):
            self.messages = [LLMMessage.system("test")] + [
                LLMMessage(role=x["role"], content=x["content"]) for x in seen
            ]

        def run(self, message):
            nonlocal active, max_active
            active += 1
            max_active = max(max_active, active)
            time.sleep(0.03)
            self.messages.extend(
                [LLMMessage.user(message), LLMMessage.assistant("ok:" + message)]
            )
            active -= 1
            return TurnResult("ok:" + message, "fake", "fake", "test", 1)

    def fake_load_history():
        return [
            LLMMessage(role=x["role"], content=x["content"])
            for x in history
        ]

    def fake_agent_from_messages(seen):
        return FakeAgent(seen)

    def fake_save_history(messages):
        history[:] = [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in {"user", "assistant"}
        ]

    monkeypatch.setattr(web_app, "load_history", fake_load_history)
    monkeypatch.setattr(web_app, "_agent_from_messages", fake_agent_from_messages)
    monkeypatch.setattr(web_app, "save_history", fake_save_history)
    web_app._LOCAL_CHAT_LOCK = __import__("threading").Lock()

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(web_app._run_local_chat, ["A", "B"]))

    assert max_active == 1
    assert {item["content"] for item in history if item["role"] == "user"} == {"A", "B"}


def test_web_agent_factory_skips_duplicate_history_io(monkeypatch):
    captured = {}

    class FakeAgent:
        def __init__(self, *args, **kwargs):
            captured.update(kwargs)
            self._messages = []

    monkeypatch.setattr(web_app, "AsterVoss", FakeAgent)
    web_app._agent_from_messages([])
    assert captured["restore_history"] is False
    assert captured["persist_history"] is False
