"""Aster Voss v0.1 - the vendor-neutral LLM interface.

The agent core depends on THIS module only. It never imports a vendor class
and never knows a concrete model name.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Iterable, Sequence, TypeAlias


MessageContent: TypeAlias = str | list[dict[str, Any]]


class LLMError(Exception):
    """Single error type the agent core has to handle.

    Covers missing credentials, timeouts, HTTP failures and malformed bodies.
    """


@dataclass
class LLMMessage:
    """One conversation turn in the vendor-neutral format."""

    role: str
    content: MessageContent | None = None
    tool_calls: list["ToolCall"] = field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None
    reasoning_content: str | None = None

    @classmethod
    def system(cls, content: str) -> "LLMMessage":
        return cls(role="system", content=content)

    @classmethod
    def user(cls, content: str) -> "LLMMessage":
        return cls(role="user", content=content)

    @classmethod
    def assistant(
        cls,
        content: str | None = None,
        tool_calls: Sequence["ToolCall"] | None = None,
        reasoning_content: str | None = None,
    ) -> "LLMMessage":
        return cls(
            role="assistant",
            content=content,
            tool_calls=list(tool_calls or []),
            reasoning_content=reasoning_content,
        )

    @classmethod
    def tool_result(cls, tool_call_id: str, content: str) -> "LLMMessage":
        return cls(role="tool", content=content, tool_call_id=tool_call_id)


@dataclass
class ToolCall:
    """A tool invocation requested by the model."""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def arguments_json(self) -> str:
        return json.dumps(self.arguments, ensure_ascii=False)


@dataclass
class LLMResponse:
    """Normalized model output, identical for every provider."""

    text: str | None
    tool_calls: list[ToolCall]
    provider: str
    model: str
    usage: dict[str, Any] = field(default_factory=dict)
    finish_reason: str | None = None
    reasoning_content: str | None = None

    @property
    def has_tool_calls(self) -> bool:
        return bool(self.tool_calls)

    @property
    def total_tokens(self) -> int:
        value = self.usage.get("total_tokens")
        return value if isinstance(value, int) else 0


class LLMProvider(ABC):
    """Unified interface every vendor adapter must implement."""

    name: str = "unknown"

    def __init__(self, provider_config: Any) -> None:
        self._config = provider_config

    @property
    def model(self) -> str:
        return getattr(self._config, "model", "")

    @property
    def timeout(self) -> float:
        return float(getattr(self._config, "timeout", 60.0))

    @property
    def max_tokens(self) -> int:
        return int(getattr(self._config, "max_tokens", 2048))

    def api_key(self) -> str:
        return getattr(self._config, "api_key", "") or ""

    def is_available(self) -> bool:
        return bool(self.api_key()) and bool(self.model)

    @property
    def capabilities(self) -> set[str]:
        return {"chat"}

    def supports(self, capability: str) -> bool:
        return capability in self.capabilities

    def supports_content(self, content: Any) -> bool:
        if isinstance(content, list):
            return self.supports("vision")
        return True

    def unavailable_reason(self) -> str:
        if not self.api_key():
            return "API key is not set"
        if not self.model:
            return "model name is not set"
        return ""

    def describe(self) -> str:
        return f"{self.name} (model={self.model or '<unset>'})"

    @abstractmethod
    def complete(
        self,
        messages: Iterable[LLMMessage],
        tools: Sequence[dict[str, Any]] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning: str | None = None,
    ) -> LLMResponse:
        raise NotImplementedError
