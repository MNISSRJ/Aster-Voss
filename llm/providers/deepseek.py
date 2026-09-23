from __future__ import annotations
import os
from typing import Any
from .openai_compatible import OpenAICompatibleProvider
class DeepSeekProvider(OpenAICompatibleProvider):
    name="deepseek"
    reasoning_style="deepseek"
    def __init__(self,provider_config:Any):
        super().__init__(provider_config)
        self._default_reasoning=(os.getenv("DEEPSEEK_REASONING_EFFORT") or "").strip().lower() or None
    def default_reasoning(self): return self._default_reasoning
