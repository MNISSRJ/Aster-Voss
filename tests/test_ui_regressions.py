from pathlib import Path

SOURCE = (Path(__file__).resolve().parents[1] / "web_app.py").read_text(encoding="utf-8")

def test_new_chat_returns_from_radar_to_chat():
    assert 'function resetChat(){' in SOURCE
    assert 'setWorkspace("chat");' in SOURCE

def test_settings_button_has_stable_click_handler():
    assert 'id="settings-side"' in SOURCE
    assert 'addEventListener("click",event=>{' in SOURCE
    assert 'event.preventDefault();' in SOURCE
    assert 'openSettings();' in SOURCE

def test_enter_still_submits_chat():
    assert 'event.key==="Enter"' in SOURCE
    assert 'sendMessage();' in SOURCE

def test_radar_has_refresh_and_safe_fallback():
    assert '"/api/ai-radar/refresh"' in SOURCE
    from services.radar_service import RadarService
    assert "AI 编辑暂时不可用" in RadarService()._fallback_payload([{"id":"x","title":"t","description":"","url":"u","published_at":"p","source_list":["s"],"hot_score":1}])["intro_zh"]


def test_new_chat_does_not_clear_conversation_archive():
    start = SOURCE.index("async function resetChat()")
    end = SOURCE.index('document.querySelector("#new-chat-side")', start)
    block = SOURCE[start:end]
    assert 'setWorkspace("chat");' in block
    assert 'loadConversations(false);' in block
    assert 'renderConversations([]);' not in block
