import feature_flags
import web_app


def test_radar_2_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("RADAR_2_ENABLED", raising=False)
    assert feature_flags.radar_2_enabled() is False


def test_radar_2_flag_accepts_explicit_preview_opt_in(monkeypatch):
    monkeypatch.setenv("RADAR_2_ENABLED", "TrUe")
    assert feature_flags.radar_2_enabled() is True


def test_radar_2_flag_rejects_unrecognized_values(monkeypatch):
    monkeypatch.setenv("RADAR_2_ENABLED", "sometimes")
    assert feature_flags.radar_2_enabled() is False


def test_flag_off_preserves_legacy_ai_radar_response(monkeypatch):
    legacy = {"status": "ready", "brief_date": "2026-10-02", "items": [{"id": "old"}]}
    monkeypatch.setenv("RADAR_2_ENABLED", "false")
    monkeypatch.setattr(web_app.RADAR, "today", lambda: legacy)

    assert web_app.ai_radar_today() == legacy


def test_flag_off_preserves_legacy_bts_radar_response(monkeypatch):
    legacy = {"status": "ready", "item_count": 1, "items": [{"id": "old"}]}
    monkeypatch.setenv("RADAR_2_ENABLED", "false")
    monkeypatch.setattr(web_app.BTS_RADAR, "today", lambda: legacy)

    assert web_app.bts_radar_today() == legacy
