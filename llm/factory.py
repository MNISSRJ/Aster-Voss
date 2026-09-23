"""Provider factory.

Turns a provider id plus configuration into an LLMProvider instance. This is
the only place that knows which concrete vendors exist, so the agent core can
stay vendor agnostic.

Adding a vendor:
  1. add llm/providers/<vendor>.py with a Provider class
  2. add one line to PROVIDER_REGISTRY below
  3. set MAIN_PROVIDER=<vendor>, <VENDOR>_API_KEY, <VENDOR>_MODEL
"""

from __future__ import annotations

import os
from typing import Any

from config import ProviderConfig, load_config

from .base import LLMError, LLMProvider
from .providers.deepseek import DeepSeekProvider

PROVIDER_REGISTRY: dict[str, type[LLMProvider]] = {
    "deepseek": DeepSeekProvider,
}

_KNOWN_FIELDS = ("API_KEY", "MODEL", "BASE_URL", "TIMEOUT", "MAX_TOKENS")


def register_provider(name: str, provider_cls: type[LLMProvider]) -> None:
    PROVIDER_REGISTRY[name.strip().lower()] = provider_cls


def _generic_provider_config(name: str) -> ProviderConfig:
    prefix = name.upper().replace("-", "_").replace(".", "_")
    base_url = (os.environ.get(f"{prefix}_BASE_URL") or "").strip()
    if not base_url:
        raise LLMError(
            f"provider '{name}' is registered but {prefix}_BASE_URL is not set"
        )

    def _number(field: str, fallback: float) -> float:
        raw = (os.environ.get(f"{prefix}_{field}") or "").strip()
        try:
            return float(raw) if raw else fallback
        except ValueError:
            return fallback

    return ProviderConfig(
        name=name,
        api_key=(os.environ.get(f"{prefix}_API_KEY") or "").strip(),
        model=(os.environ.get(f"{prefix}_MODEL") or "").strip(),
        base_url=base_url,
        timeout=_number("TIMEOUT", 60.0),
        max_tokens=int(_number("MAX_TOKENS", 2048)),
    )


def resolve_provider_config(name: str, agent_config: Any | None = None) -> ProviderConfig:
    config = agent_config or load_config()
    provider_config = config.provider(name)
    if provider_config is None:
        return _generic_provider_config(name)
    return provider_config


def create_provider(name: str, agent_config: Any | None = None) -> LLMProvider:
    key = (name or "").strip().lower()
    if not key:
        raise LLMError("no provider name was given")

    provider_cls = PROVIDER_REGISTRY.get(key)
    if provider_cls is None:
        known = ", ".join(sorted(PROVIDER_REGISTRY))
        raise LLMError(f"unknown provider '{name}' (known providers: {known})")

    return provider_cls(resolve_provider_config(key, agent_config))


def available_providers(agent_config: Any | None = None) -> dict[str, bool]:
    config = agent_config or load_config()
    result: dict[str, bool] = {}
    for key, provider_cls in PROVIDER_REGISTRY.items():
        try:
            result[key] = provider_cls(resolve_provider_config(key, config)).is_available()
        except LLMError:
            result[key] = False
    return result
