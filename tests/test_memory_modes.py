from __future__ import annotations

from agent import TurnResult
from llm.base import LLMMessage
from fastapi.testclient import TestClient

from memory import brain, cloud, persistence
import web_app


def _clear_cloud(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setattr(brain, "enabled", lambda: False)


def test_local_memory_persists_without_supabase(monkeypatch, tmp_path):
    _clear_cloud(monkeypatch)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.setattr(persistence, "LOCAL_MEMORY_PATH", tmp_path / "LOCAL_MEMORY.json")

    assert brain.storage_mode() == "local"
    assert brain.add("local durable memory", user_id="test")

    reloaded = brain.load_entries("test")
    assert any(item["text"] == "local durable memory" for item in reloaded)


def test_serverless_without_supabase_rejects_memory_write(monkeypatch, tmp_path):
    _clear_cloud(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(persistence, "LOCAL_MEMORY_PATH", tmp_path / "LOCAL_MEMORY.json")

    assert brain.storage_mode() == "serverless-read-only"
    assert brain.add("must not persist", user_id="test") is False
    assert not (tmp_path / "LOCAL_MEMORY.json").exists()


def test_cloud_is_source_of_truth_without_local_fallback(monkeypatch, tmp_path):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setattr(brain, "enabled", lambda: True)
    monkeypatch.setattr(brain, "cloud_load", lambda user_id: None)
    monkeypatch.setattr(persistence, "LOCAL_MEMORY_PATH", tmp_path / "LOCAL_MEMORY.json")
    persistence.LOCAL_MEMORY_PATH.write_text(
        '[{"id":"local","text":"local-only","source":"manual","created_at":null}]',
        encoding="utf-8",
    )

    assert brain.storage_mode() == "supabase"
    assert brain.load_entries("test") == []


def test_cloud_memory_write_failure_is_logged(monkeypatch):
    monkeypatch.setattr(cloud, "enabled", lambda: True)
    monkeypatch.setattr(
        cloud,
        "_request",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("simulated failure")),
    )
    events = []
    monkeypatch.setattr(cloud.log, "error", lambda *args: events.append(args))

    assert cloud.save([{"id": "1", "text": "x"}], "test") is False
    assert events
    assert "cloud memory write failed" in str(events[0][0])


def test_serverless_memory_api_returns_503(monkeypatch):
    _clear_cloud(monkeypatch)
    monkeypatch.setenv("VERCEL", "1")

    client = TestClient(web_app.app)
    response = client.post("/api/memory", json={"text": "do not persist"})
    assert response.status_code == 503
    assert "无法保存" in response.json()["detail"]


def test_cloud_conversation_write_failure_returns_non_success(monkeypatch):
    monkeypatch.setattr(web_app.cloud, "enabled", lambda: True)
    monkeypatch.setattr(web_app.CONVERSATIONS, "get", lambda conversation_id: None)
    monkeypatch.setattr(web_app.CONVERSATIONS, "save", lambda *args, **kwargs: False)

    class FakeAgent:
        messages = []

        def run(self, message):
            self.messages = [
                LLMMessage.system("test"),
                LLMMessage.user(message),
                LLMMessage.assistant("pong"),
            ]
            return TurnResult(
                text="pong",
                provider="fake",
                model="fake-model",
                source="test",
                complexity=1,
            )

    monkeypatch.setattr(web_app, "_agent_from_messages", lambda history: FakeAgent())

    client = TestClient(web_app.app)
    response = client.post("/api/chat", json={"message": "ping"})

    assert response.status_code == 503
    body = response.json()
    assert body["ok"] is False
    assert body["text"] == "pong"
    assert body["conversation_persisted"] is False
