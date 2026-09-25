from llm.base import LLMResponse
from ai_radar import _norm_title, _parse_json_object, curate


class FakeProvider:
    def __init__(self, text):
        self.text = text
        self.last_messages = None
        self.last_kwargs = None

    def complete(self, messages, **kwargs):
        self.last_messages = list(messages)
        self.last_kwargs = kwargs
        return LLMResponse(
            text=self.text,
            tool_calls=[],
            provider="fake",
            model="fake-model",
        )


def _candidates():
    return [
        {
            "id": "source-1",
            "title": "模型发布新版本",
            "url": "https://example.com/1",
            "description": "一个重要更新",
            "published_at": "2026-09-25T00:00:00+00:00",
            "source_list": ["Example"],
            "hot_score": 80.0,
        }
    ]


def test_parse_plain_json():
    assert _parse_json_object('{"intro_zh":"ok","items":[]}') == {
        "intro_zh": "ok",
        "items": [],
    }


def test_parse_json_code_fence():
    raw = '```json\n{"intro_zh":"ok","items":[]}\n```'
    assert _parse_json_object(raw) == {"intro_zh": "ok", "items": []}


def test_parse_json_with_surrounding_text():
    raw = 'Here is the brief:\n{"intro_zh":"ok","items":[]}\nDone.'
    assert _parse_json_object(raw) == {"intro_zh": "ok", "items": []}


def test_parse_invalid_json_returns_empty_object():
    assert _parse_json_object("not json") == {}


def test_curate_requests_json_mode_and_sufficient_output_budget():
    provider = FakeProvider(
        '{"intro_zh":"今天的简报","items":[{"candidate":1,"company":"Example","headline_zh":"新模型发布","summary_zh":"重要更新","why_it_matters_zh":"值得关注","tags":["模型"]}]}'
    )
    result = curate(provider, _candidates())

    assert result["items"]
    assert provider.last_kwargs["response_format"] == {"type": "json_object"}
    assert provider.last_kwargs["max_tokens"] == 3200


def test_curate_uses_code_fenced_model_json():
    provider = FakeProvider(
        '```json\n{"intro_zh":"今天的简报","items":[{"candidate":1,"company":"Example","headline_zh":"新模型发布","summary_zh":"重要更新","why_it_matters_zh":"值得关注","tags":["模型"]}]}\n```'
    )
    result = curate(provider, _candidates())

    assert result["intro_zh"] == "今天的简报"
    assert len(result["items"]) == 1
    assert result["items"][0]["headline_zh"] == "新模型发布"


def test_curate_rejects_empty_items():
    import pytest

    provider = FakeProvider('{"intro_zh":"今天的简报","items":[]}')
    with pytest.raises(Exception, match="no usable radar items"):
        curate(provider, _candidates())


def test_curate_rejects_invalid_candidate_numbers():
    import pytest

    provider = FakeProvider(
        '{"intro_zh":"今天的简报","items":[{"candidate":999,"headline_zh":"错误"}]}'
    )
    with pytest.raises(Exception, match="no usable radar items"):
        curate(provider, _candidates())


def test_curate_rejects_truncated_model_output():
    import pytest

    from llm.base import LLMResponse

    class TruncatedProvider(FakeProvider):
        def complete(self, messages, **kwargs):
            return LLMResponse(
                text='{"intro_zh":"partial"',
                tool_calls=[],
                provider="fake",
                model="fake-model",
                finish_reason="length",
            )

    with pytest.raises(Exception, match="truncated"):
        curate(TruncatedProvider(""), _candidates())


def _curated_payload():
    return {
        "brief_date": "2026-09-25",
        "generated_at": "2026-09-25T00:00:00Z",
        "intro_zh": "今天的简报",
        "items": [
            {
                "candidate": 1,
                "company": "Example",
                "headline_zh": "新模型发布",
                "summary_zh": "重要更新",
                "why_it_matters_zh": "值得关注",
                "tags": ["模型"],
            }
        ],
        "source_count": 1,
        "candidate_count": 1,
    }


def test_radar_service_retries_failed_curation_then_succeeds(monkeypatch):
    from services import radar_service as radar_module
    from services.radar_service import RadarService

    class AvailableProvider:
        def is_available(self):
            return True

    calls = []

    def fake_curate(provider, candidates, attempt=1):
        calls.append(attempt)
        if attempt == 1:
            raise ValueError("empty result")
        return _curated_payload()

    monkeypatch.setattr(radar_module, "collect_candidates", _candidates)
    monkeypatch.setattr(radar_module, "curate", fake_curate)
    monkeypatch.setattr(radar_module.cloud, "enabled", lambda: False)

    payload = RadarService().generate(AvailableProvider())

    assert calls == [1, 2]
    assert payload["status"] == "ready"
    assert len(payload["items"]) == 1


def test_radar_service_falls_back_after_two_failed_curation_attempts(monkeypatch):
    from services import radar_service as radar_module
    from services.radar_service import RadarService

    class AvailableProvider:
        def is_available(self):
            return True

    calls = []

    def fake_curate(provider, candidates, attempt=1):
        calls.append(attempt)
        raise ValueError("empty result")

    monkeypatch.setattr(radar_module, "collect_candidates", _candidates)
    monkeypatch.setattr(radar_module, "curate", fake_curate)
    monkeypatch.setattr(radar_module.cloud, "enabled", lambda: False)

    payload = RadarService().generate(AvailableProvider())

    assert calls == [1, 2]
    assert payload["status"] == "fallback"
    assert len(payload["items"]) == 1
    assert "AI 编辑暂时不可用" in payload["intro_zh"]
