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

def test_radar_2_events_flag_defaults_off_even_when_radar_2_is_on(monkeypatch):
    monkeypatch.setenv("RADAR_2_ENABLED", "true")
    monkeypatch.delenv("RADAR_2_EVENTS_ENABLED", raising=False)
    assert feature_flags.radar_2_events_enabled() is False


def test_radar_event_api_does_not_write_until_events_are_enabled(monkeypatch):
    from web_app import RadarEventIn, radar_event

    monkeypatch.setenv("RADAR_2_ENABLED", "true")
    monkeypatch.setenv("RADAR_2_EVENTS_ENABLED", "false")
    monkeypatch.setattr(web_app.cloud, "save_radar_event", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not write")))
    result = radar_event(RadarEventIn(item_id="item-1", event_type="item_view", metadata={}))
    assert result == {"ok": True, "recorded": False, "disabled": True}
