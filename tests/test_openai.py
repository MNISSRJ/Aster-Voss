from types import SimpleNamespace

from config import ProviderConfig
from llm.base import LLMMessage
from llm.providers.openai import OpenAIProvider


def test_openai_provider_normalizes_response(monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return b'{"choices":[{"message":{"content":"hello","tool_calls":[]},"finish_reason":"stop"}],"usage":{"total_tokens":3}}'

    def fake_urlopen(request, timeout):
        assert request.full_url.endswith("/chat/completions")
        assert timeout == 5
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    cfg = ProviderConfig("openai", "key", "model", "https://example.com/v1", 5, 10)
    provider = OpenAIProvider(cfg)
    response = provider.complete([LLMMessage.user("hi")])
    assert response.text == "hello"
    assert response.total_tokens == 3
