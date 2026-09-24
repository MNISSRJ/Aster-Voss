import os
from fastapi.testclient import TestClient

os.environ.pop("SUPABASE_URL", None)
os.environ.pop("SUPABASE_SECRET_KEY", None)
os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)

from web_app import app

client = TestClient(app)

def test_status_has_server_time():
    response = client.get("/api/status")
    assert response.status_code == 200
    body = response.json()
    assert "server_time" in body
    assert isinstance(body["server_time"], int)

def test_home_page_loads():
    response = client.get("/")
    assert response.status_code == 200
    assert "Aster Voss" in response.text
