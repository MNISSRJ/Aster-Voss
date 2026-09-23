"""Aster Voss v0.1 - central configuration.

The ONLY module in this project that reads API keys from the environment.
Nothing here is ever logged, printed or exported.

No python-dotenv dependency: environment variables come from the OS.
Use .env.example as documentation, and set real values in your shell.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _load_dotenv_file() -> None:
    """Load the local .env file once, without an extra dependency.

    Existing OS environment variables win. Values in .env are only used when
    the variable is not already present in the process environment.
    """
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return
    try:
        for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key or key in os.environ:
                continue
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {""", "'"}:
                value = value[1:-1]
            os.environ[key] = value
    except OSError:
        return


_load_dotenv_file()

# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _get(name: str, default: str = "") -> str:
    value = os.environ.get(name)
    return default if value is None else value.strip()


def _get_optional(name: str) -> str:
    """Return the value, or '' when unset/blank (meaning: not configured)."""
    return _get(name, "")


def _get_int(name: str, default: int) -> int:
    raw = _get(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _get_bool(name: str, default: bool) -> bool:
    raw = _get(name).lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "y", "on"}


def _get_float(name: str, default: float) -> float:
    raw = _get(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# --------------------------------------------------------------------------
# provider configuration
# --------------------------------------------------------------------------

# Provider ids are NOT hardcoded in the agent core. These two are only the
# built-in registry entries; adding a vendor means adding a provider class.
DEFAULT_PROVIDER = "deepseek"

# Model names are volatile vendor data and therefore never hardcoded as a
# required value:
#   * DeepSeek: default documented below, overridable with DEEPSEEK_MODEL.
#   * OpenAI:   NO default. Unset OPENAI_MODEL => provider unavailable.
DEEPSEEK_DEFAULT_MODEL = "deepseek-flash"


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for one LLM vendor."""

    name: str
    api_key: str
    model: str
    base_url: str
    timeout: float
    max_tokens: int

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key) and bool(self.model)


@dataclass(frozen=True)
class AgentConfig:
    """Top level agent configuration."""

    main_provider: str
    auto_routing: bool
    providers: dict
    jev_enabled: bool
    jev_api_key: str
    jev_base_url: str
    jev_timeout: float
    default_reasoning: str | None
    log_level: str

    def provider(self, name: str) -> ProviderConfig | None:
        return self.providers.get(name)

    @property
    def active_provider(self) -> ProviderConfig | None:
        return self.providers.get(self.main_provider)


def load_config() -> AgentConfig:
    """Build the configuration from the current environment."""
    llm_timeout = _get_float("LLM_TIMEOUT", 60.0)
    max_tokens = _get_int("MAX_TOKENS", 2048)

    providers: dict[str, ProviderConfig] = {
        "deepseek": ProviderConfig(
            name="deepseek",
            api_key=_get_optional("DEEPSEEK_API_KEY"),
            model=_get("DEEPSEEK_MODEL", DEEPSEEK_DEFAULT_MODEL),
            base_url=_get("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            timeout=_get_float("DEEPSEEK_TIMEOUT", llm_timeout),
            max_tokens=_get_int("DEEPSEEK_MAX_TOKENS", max_tokens),
        ),
        "openai": ProviderConfig(
            name="openai",
            api_key=_get_optional("OPENAI_API_KEY"),
            # Deliberately NO default model name.
            model=_get("OPENAI_MODEL", ""),
            base_url=_get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            timeout=_get_float("OPENAI_TIMEOUT", llm_timeout),
            max_tokens=_get_int("OPENAI_MAX_TOKENS", max_tokens),
        ),
    }

    # Optional reasoning control. Empty string means "do not send any
    # reasoning parameter" -> cheapest, fastest path on both vendors.
    default_reasoning = _get("DEFAULT_REASONING_EFFORT", "") or None

    return AgentConfig(
        main_provider=_get("MAIN_PROVIDER", DEFAULT_PROVIDER).lower(),
        auto_routing=_get_bool("AUTO_ROUTING", False),
        providers=providers,
        jev_enabled=bool(_get_optional("JEV_API_KEY")),
        jev_api_key=_get_optional("JEV_API_KEY"),
        jev_base_url=_get("JEV_BASE_URL", "https://www.jevai.org"),
        jev_timeout=_get_float("JEV_TIMEOUT", 8.0),
        default_reasoning=default_reasoning,
        log_level=_get("LOG_LEVEL", "INFO").upper(),
    )


# Reasoning efforts each vendor accepts, from the official docs.
DEEPSEEK_EFFORTS = {"low", "high", "max"}
OPENAI_EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh"}


def normalize_reasoning(raw: str | None) -> str | None:
    """Normalize a reasoning effort value; blank means 'not requested'."""
    if raw is None:
        return None
    value = raw.strip().lower()
    return value or None
