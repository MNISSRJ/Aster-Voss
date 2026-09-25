from memory import cloud


def test_conversation_save_updates_existing_record(monkeypatch):
    calls = []

    def fake_request(method, path, body=None):
        calls.append((method, path, body))
        if method == "GET":
            return [{"id": "c1"}]
        return [{"id": "c1"}]

    monkeypatch.setattr(cloud, "enabled", lambda: True)
    monkeypatch.setattr(cloud, "_request", fake_request)

    assert cloud.save_conversation("c1", "title", [{"role": "user", "content": "hi"}])
    assert any(call[0] == "PATCH" for call in calls)
    assert not any(call[0] == "POST" for call in calls)
