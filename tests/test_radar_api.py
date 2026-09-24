from fastapi.testclient import TestClient
import web_app

client = TestClient(web_app.app)

def test_radar_refresh_uses_service(monkeypatch):
    expected = {
        "brief_date": "2026-09-24",
        "generated_at": "2026-09-24T12:00:00Z",
        "intro_zh": "ok",
        "items": [{"headline_zh": "test"}],
        "source_count": 1,
        "candidate_count": 1,
    }
    monkeypatch.setattr(web_app.RADAR, "generate", lambda provider=None: expected)
    response = client.post("/api/ai-radar/refresh")
    assert response.status_code == 200
    assert response.json() == expected


import web_app

def test_radar_route_builds_real_provider(monkeypatch):
    calls = {}
    class FakeConfig:
        is_configured = True

    fake_provider = object()
    monkeypatch.setattr(web_app.CONFIG, "active_provider", FakeConfig())
    monkeypatch.setattr(web_app.CONFIG, "main_provider", "deepseek")
    monkeypatch.setattr(
        web_app,
        "create_provider",
        lambda name, config: calls.setdefault("args", (name, config)) or fake_provider,
    )
    monkeypatch.setattr(web_app.RADAR, "generate", lambda provider=None: {"provider_ok": provider is fake_provider})
    result = web_app._generate_ai_brief()
    assert result["provider_ok"] is True
    assert calls["args"][0] == "deepseek"
