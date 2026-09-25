"""Aster Voss configuration. Real API keys live only in local .env."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path

def _load_dotenv_file():
    p=Path(__file__).resolve().parent/".env"
    if not p.exists(): return
    try:
        for raw in p.read_text(encoding="utf-8-sig").splitlines():
            line=raw.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            key,value=line.split("=",1); key=key.strip(); value=value.strip()
            if key and key not in os.environ:
                if len(value)>=2 and value[0]==value[-1] and value[0] in {"\"", "'"}:
                    value=value[1:-1]
                os.environ[key]=value
    except OSError:
        pass
_load_dotenv_file()

def _get(name,default=""): return (os.environ.get(name,default) or "").strip()
def _int(name,default):
    try: return int(_get(name,str(default)))
    except ValueError: return default
def _float(name,default):
    try: return float(_get(name,str(default)))
    except ValueError: return default
def _bool(name,default=False): return _get(name,str(default)).lower() in {"1","true","yes","y","on"}

@dataclass(frozen=True)
class ProviderConfig:
    name:str; api_key:str; model:str; base_url:str; timeout:float; max_tokens:int
    @property
    def is_configured(self): return bool(self.api_key and self.model)

@dataclass(frozen=True)
class AgentConfig:
    main_provider:str; auto_routing:bool; providers:dict; jev_enabled:bool
    jev_api_key:str; jev_base_url:str; jev_timeout:float
    default_reasoning:str|None; log_level:str; require_auth:bool
    def provider(self,name): return self.providers.get(name)
    @property
    def active_provider(self): return self.providers.get(self.main_provider)

def load_config():
    timeout=_float("LLM_TIMEOUT",60); tokens=_int("MAX_TOKENS",2048)
    providers={
      "deepseek":ProviderConfig("deepseek",_get("DEEPSEEK_API_KEY"),_get("DEEPSEEK_MODEL","deepseek-flash"),_get("DEEPSEEK_BASE_URL","https://api.deepseek.com"),_float("DEEPSEEK_TIMEOUT",timeout),_int("DEEPSEEK_MAX_TOKENS",tokens)),
      "openai":ProviderConfig("openai",_get("OPENAI_API_KEY"),_get("OPENAI_MODEL"),_get("OPENAI_BASE_URL","https://api.openai.com/v1"),_float("OPENAI_TIMEOUT",timeout),_int("OPENAI_MAX_TOKENS",tokens)),
    }
    main_provider = _get("MAIN_PROVIDER","deepseek").lower()
    if main_provider not in providers:
        main_provider = "deepseek"
    return AgentConfig(main_provider,_bool("AUTO_ROUTING",False),providers,bool(_get("JEV_API_KEY")), _get("JEV_API_KEY"),_get("JEV_BASE_URL","https://www.jevai.org"),_float("JEV_TIMEOUT",8),_get("DEFAULT_REASONING_EFFORT") or None,_get("LOG_LEVEL","INFO").upper(),_bool("ASTER_REQUIRE_AUTH",False))

DEEPSEEK_EFFORTS={"low","high","max"}
OPENAI_EFFORTS={"none","minimal","low","medium","high","xhigh"}
def normalize_reasoning(raw): return raw.strip().lower() if raw and raw.strip() else None
