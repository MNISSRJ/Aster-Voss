from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
WEB=ROOT/"web_app.py"

def test_enter_to_send_is_wired():
    source=WEB.read_text(encoding="utf-8")
    assert 'event.key==="Enter"' in source
    assert "sendMessage()" in source
    assert 'event.preventDefault()' in source

def test_reset_route_does_not_delete_durable_memory():
    source=WEB.read_text(encoding="utf-8")
    assert 'def reset():' in source
    assert 'Durable memory remains intact.' in source
