from ai_radar import _norm_title, curate
from llm.base import LLMResponse
import web_app


class CaptureProvider:
    def __init__(self, text='{}'):
        self.text = text
        self.last_messages = []

    def complete(self, messages, **kwargs):
        self.last_messages = list(messages)
        return LLMResponse(
            text=self.text,
            tool_calls=[],
            provider="fake",
            model="fake-model",
        )


def test_norm_title_preserves_chinese():
    normalized = _norm_title("hello 世界 AI 更新")
    assert "世界" in normalized
    assert "更新" in normalized


def test_radar_prompt_uses_real_newlines():
    provider = CaptureProvider(
        '{"intro_zh":"ok","items":[{"candidate":1,"company":"Example","headline_zh":"测试标题","summary_zh":"测试摘要","why_it_matters_zh":"值得关注","tags":["AI"]}]}'
    )
    candidates = [{
        "id": "1",
        "title": "测试标题",
        "url": "https://example.com/1",
        "description": "测试描述",
        "published_at": "2026-09-25T00:00:00+00:00",
        "source_list": ["Example"],
        "hot_score": 80.0,
    }]
    curate(provider, candidates)
    prompt = next(message.content for message in provider.last_messages if message.role == 'user')
    assert '\nURL:' in prompt
    assert '\nSnippet:' in prompt
    assert '\\n' not in prompt


def test_build_prompt_uses_real_newlines(monkeypatch):
    monkeypatch.setattr(type(web_app.MEMORY), "context", lambda self, max_chars=1800: "")
    prompt = web_app.build_prompt()
    assert '<shared_growth_history>\n' in prompt
    assert '\n</shared_growth_history>' in prompt
    assert '\\n' not in prompt
