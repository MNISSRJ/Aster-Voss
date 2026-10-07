from types import SimpleNamespace

from fastapi.testclient import TestClient

import web_app
from memory import cloud


client = TestClient(web_app.app)


def test_chat_radar_context_is_bounded_and_marked_untrusted(monkeypatch):
    monkeypatch.setenv("RADAR_2_ENABLED", "true")
    monkeypatch.setattr(web_app.cloud, "enabled", lambda: False)
    captured = {}

    def fake_chat(message):
        captured["message"] = message
        return SimpleNamespace(text="ok", provider="mock", model="mock")

    monkeypatch.setattr(web_app, "_run_local_chat", fake_chat)
    response = client.post("/api/chat", json={
        "message": "这是什么意思？",
        "radar_context": {"title": "JK post", "summary": "hi", "ignored": "must not pass"},
    })
    assert response.status_code == 200
    assert "<untrusted_radar_context>" in captured["message"]
    assert '"title": "JK post"' in captured["message"]
    assert "must not pass" not in captured["message"]
    assert "这是什么意思？" in captured["message"]


def test_flag_off_chat_ignores_radar_context(monkeypatch):
    monkeypatch.setenv("RADAR_2_ENABLED", "false")
    monkeypatch.setattr(web_app.cloud, "enabled", lambda: False)
    captured = {}
    def fake_chat(message):
        captured["message"] = message
        return SimpleNamespace(text="ok", provider="mock", model="mock")
    monkeypatch.setattr(web_app, "_run_local_chat", fake_chat)
    client.post("/api/chat", json={"message": "hello", "radar_context": {"title": "secret title"}})
    assert captured["message"] == "hello"


def test_radar_event_route_is_noop_when_flag_off(monkeypatch):
    monkeypatch.setenv("RADAR_2_ENABLED", "false")
    monkeypatch.setattr(cloud, "save_radar_event", lambda *args: (_ for _ in ()).throw(AssertionError("must not write")))
    response = client.post("/api/radar/events", json={"item_id": "one", "event_type": "item_view"})
    assert response.status_code == 200
    assert response.json()["recorded"] is False


def test_radar_event_write_failure_degrades(monkeypatch):
    monkeypatch.setenv("RADAR_2_ENABLED", "true")
    monkeypatch.setattr(cloud, "save_radar_event", lambda *args: False)
    response = client.post("/api/radar/events", json={"item_id": "one", "event_type": "item_view"})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["recorded"] is False


def test_event_writer_uses_separate_table_and_bounds_metadata(monkeypatch):
    calls = []
    monkeypatch.setattr(cloud, "enabled", lambda: True)
    monkeypatch.setattr(cloud, "_request", lambda method, path, body=None: calls.append((method, path, body)))
    assert cloud.save_radar_event("item-1", "ask_aster", {"source": "weverse", "oversized": "x" * 500})
    method, path, body = calls[0]
    assert method == "POST" and path == cloud.RADAR_EVENT_TABLE
    assert body["metadata"]["oversized"] == "x" * 160


def test_both_radar_renderers_share_action_component():
    source = (web_app.Path(__file__).resolve().parents[1] / "templates" / "index.html").read_text(encoding="utf-8")
    assert 'addRadarActions(card,item,"bts")' in source
    assert 'addRadarActions(card,item,"ai")' in source
    assert 'event.key==="Enter"' in source
    assert 'pressTimer=setTimeout' in source
