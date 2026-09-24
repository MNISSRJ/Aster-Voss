from config import load_config
from agent import AsterVoss
from llm.base import LLMProvider, LLMResponse
from llm.base import LLMMessage


class FakeProvider(LLMProvider):
    name = "fake"

    @property
    def capabilities(self):
        return {"chat", "tools"}

    def complete(self, messages, tools=None, temperature=None, max_tokens=None, reasoning=None):
        return LLMResponse(
            text="pong",
            tool_calls=[],
            provider=self.name,
            model="fake-model",
            usage={"total_tokens": 1},
            finish_reason="stop",
        )


def test_agent_returns_model_text(monkeypatch, tmp_path):
    monkeypatch.setenv("ASTER_DEFAULT_USER_ID", "test")
    config = load_config()
    agent = AsterVoss(config, provider=FakeProvider(config.provider("deepseek")))
    agent._messages = [LLMMessage.system("test")]
    result = agent.run("ping")
    assert result.text == "pong"
