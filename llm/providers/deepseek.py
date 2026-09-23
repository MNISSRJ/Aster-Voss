"""DeepSeek adapter.

Official facts (verified against https://api-docs.deepseek.com):
  base_url          https://api.deepseek.com   POST /chat/completions
  auth              Authorization: Bearer $DEEPSEEK_API_KEY
  system role       "system"
  thinking mode     {"thinking": {"type": "enabled"|"disabled"}}
                    + {"reasoning_effort": "low"|"high"|"max"}
                    enabled by DEFAULT with effort "high"
  tools             OpenAI-compatible; with thinking enabled the
                    reasoning_content MUST be echoed back or the API 400s.

Aster Voss therefore defaults to thinking DISABLED for the cheap, fast
path, and lets DEEPSEEK_REASONING_EFFORT opt in explicitly.
"""

from __future__ import annotations

import os
from typing import Any

from .openai_compatible import OpenAICompatibleProvider


class DeepSeekProvider(OpenAICompatibleProvider):
    name = "deepseek"
    system_role = "system"
    reasoning_style = "deepseek"
    max_tokens_field = "max_tokens"

    def __init__(self, provider_config: Any) -> None:
        super().__init__(provider_config)
        env_effort = (os.environ.get("DEEPSEEK_REASONING_EFFORT") or "").strip().lower()
        self._default_reasoning: str | None = env_effort or None

    def default_reasoning(self) -> str | None:
        return self._default_reasoning
