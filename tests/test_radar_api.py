from fastapi.testclient import TestClient
from types import SimpleNamespace
import web_app


class FakeRadar:
    def __init__(self, user_id):
        self.user_id = user_id

    def generate(self, provider=None):
        return {"provider_ok": provider is not None, "user_id": self.user_id}

    def today(self):
        return None

    def history(self, limit=14):
        return []


def test_radar_refresh_uses_trusted_owner_service(monkeypatch):
    monkeypatch.setattr(web_app, "RadarService", FakeRadar)
    response = TestClient(web_app.app).post("/api/ai-radar/refresh")
    assert response.status_code == 200
    assert response.json()["user_id"] == web_app.CONFIG.owner_id


def test_radar_route_builds_real_provider(monkeypatch):
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
    monkeypatch.setattr(web_app, "RadarService", FakeRadar)
    monkeypatch.setattr(
        web_app,
        "create_provider",
        lambda name, config: (calls.setdefault("args", (name, config)), fake_provider)[1],
    )
    result = web_app._generate_ai_brief("owner-test")
    assert result["provider_ok"] is True
    assert result["user_id"] == "owner-test"
    assert calls["args"][0] == "deepseek"
