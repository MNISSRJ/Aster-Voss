from pathlib import Path
from fastapi.testclient import TestClient
import web_app

client = TestClient(web_app.app)


def test_home_comes_from_template():
    response = client.get("/")
    assert response.status_code == 200
    assert "Aster Voss" in response.text
    assert "sendMessage()" in response.text
    assert Path("templates/index.html").exists()


def test_status_contains_server_time_and_version():
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["server_time"], int)
    assert body["version"] == "0.2.0"
