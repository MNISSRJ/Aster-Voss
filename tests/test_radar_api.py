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
