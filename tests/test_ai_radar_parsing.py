from llm.base import LLMResponse
from ai_radar import _norm_title, _parse_json_object, curate


class FakeProvider:
    def __init__(self, text):
        self.text = text
        self.last_messages = None

    def complete(self, messages, **kwargs):
        self.last_messages = list(messages)
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


def test_curate_uses_code_fenced_model_json():
    provider = FakeProvider(
        '```json\n{"intro_zh":"今天的简报","items":[{"candidate":1,"company":"Example","headline_zh":"新模型发布","summary_zh":"重要更新","why_it_matters_zh":"值得关注","tags":["模型"]}]}\n```'
    )
    result = curate(provider, _candidates())

    assert result["intro_zh"] == "今天的简报"
    assert len(result["items"]) == 1
    assert result["items"][0]["headline_zh"] == "新模型发布"

