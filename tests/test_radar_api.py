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
    from types import SimpleNamespace

    calls = {}
    class FakeProvider:
        def is_available(self):
            return True
    fake_provider = FakeProvider()
    fake_config = SimpleNamespace(
        active_provider=SimpleNamespace(is_configured=True),
        main_provider="deepseek",
    )
    monkeypatch.setattr(web_app, "CONFIG", fake_config)
    monkeypatch.setattr(
        web_app,
        "create_provider",
        lambda name, config: (calls.setdefault("args", (name, config)), fake_provider)[1],
    )
    monkeypatch.setattr(web_app.RADAR, "generate", lambda provider=None: {"provider_ok": provider is fake_provider})
    result = web_app._generate_ai_brief()
    assert result["provider_ok"] is True
    assert calls["args"][0] == "deepseek"
