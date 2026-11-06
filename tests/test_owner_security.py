import pytest
from auth import OwnerTokenProvider, UserContext
from config import load_config

def test_owner_token_resolves_configured_owner():
    provider = OwnerTokenProvider("temporary-secret", "owner-123")
    assert provider.authenticate("Bearer temporary-secret") == UserContext("owner-123")
    assert provider.authenticate("Bearer wrong") is None

def test_production_requires_owner_and_token(monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.delenv("ASTER_OWNER_ID", raising=False)
    monkeypatch.delenv("ASTER_ACCESS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="ASTER_OWNER_ID"):
        load_config()

def test_production_requires_token(monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("ASTER_OWNER_ID", "owner-123")
    monkeypatch.delenv("ASTER_ACCESS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="ASTER_ACCESS_TOKEN"):
        load_config()

def test_production_forces_auth(monkeypatch):
    monkeypatch.setenv("VERCEL_ENV", "production")
    monkeypatch.setenv("ASTER_OWNER_ID", "owner-123")
    monkeypatch.setenv("ASTER_ACCESS_TOKEN", "temporary-secret")
    monkeypatch.setenv("ASTER_REQUIRE_AUTH", "false")
    config = load_config()
    assert config.require_auth is True
    assert config.owner_id == "owner-123"

def test_local_keeps_owner_compatibility(monkeypatch):
    monkeypatch.delenv("VERCEL_ENV", raising=False)
    monkeypatch.delenv("VERCEL", raising=False)
    monkeypatch.delenv("ASTER_OWNER_ID", raising=False)
    config = load_config()
    assert config.owner_id == "mint"
