from config import load_config
from agent import AsterVoss
from llm.base import LLMProvider, LLMResponse
from llm.base import LLMMessage


class FakeProvider(LLMProvider):
    name = "fake"

    @property
    def capabilities(self):
        return {"chat", "tools"}

    def is_available(self):
        return True

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
    assert [step["id"] for step in result.thinking] == ["understand","memory","analyze","generate"]
    assert all(step["status"] == "done" for step in result.thinking)


class ToolLoopProvider(LLMProvider):
    name = "fake"

    @property
    def capabilities(self):
        return {"chat", "tools"}

    def is_available(self):
        return True

    def __init__(self, config):
        super().__init__(config)
        self.calls = 0
        self.received_tools = []

    def complete(self, messages, tools=None, temperature=None, max_tokens=None, reasoning=None):
        self.calls += 1
        self.received_tools.append(tools)
        if self.calls == 1:
            from llm.base import ToolCall
            return LLMResponse(
                text="",
                tool_calls=[ToolCall("call-1", "read_project_file", {"path": "agent.py"})],
                provider=self.name, model="fake-model", usage={"total_tokens": 1}
            )
        if self.calls == 2:
            from llm.base import ToolCall
            return LLMResponse(
                text="",
                tool_calls=[ToolCall("call-2", "read_project_file", {"path": "agent.py"})],
                provider=self.name, model="fake-model", usage={"total_tokens": 1}
            )
        return LLMResponse(
            text="我已经读取了项目文件，并根据已有内容给出结论。",
            tool_calls=[], provider=self.name, model="fake-model", usage={"total_tokens": 1}
        )


def test_agent_stops_repeated_identical_tool_calls(monkeypatch):
    monkeypatch.setenv("ASTER_DEFAULT_USER_ID", "test")
    config = load_config()
    provider = ToolLoopProvider(config.provider("deepseek"))
    agent = AsterVoss(config, provider=provider, restore_history=False, persist_history=False)
    agent._messages = [LLMMessage.system("test")]
    result = agent.run("看看项目怎么改")
    assert result.text.startswith("我已经读取了项目文件")
    assert provider.calls == 3
    assert provider.received_tools[0]
    assert provider.received_tools[1]
    assert provider.received_tools[2] == []
    assert result.tool_calls == ["read_project_file"]
    assert result.error is None
    assert "read_project_file, read_project_file" not in result.thinking[2]["detail"]
