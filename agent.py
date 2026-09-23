"""Aster Voss core agent loop."""
from __future__ import annotations
from dataclasses import dataclass,field
from typing import Any
import log
from jev import create_jev_client
from llm.base import LLMError,LLMMessage,LLMProvider
from llm.factory import create_provider

class RouteDecision:
    def __init__(self,provider_name,source='configured',complexity=1):
        self.provider_name=provider_name; self.source=source; self.complexity=complexity
class TaskRouter:
    def __init__(self,config,jev_client=None): self.config=config; self.jev=jev_client
    def select(self,text): return RouteDecision(self.config.main_provider or 'deepseek')
    def get_provider(self,name): return create_provider(name,self.config)
    def reasoning_for(self,provider):
        import os
        return (os.getenv(f'{provider.name.upper()}_REASONING_EFFORT') or self.config.default_reasoning or '').strip() or None
from tools.registry import run_tool,tool_specs
from memory.persistence import load_history,save_history,clear_history,save_long_term_note
DEFAULT_SYSTEM_PROMPT="You are a helpful personal assistant. Answer normal conversation directly. Use tools for local files and never invent file contents."
MAX_TOOL_ITERATIONS=5
@dataclass
class TurnResult:
    text:str;provider:str;model:str;source:str;complexity:int
    tool_calls:list[str]=field(default_factory=list);usage:dict[str,Any]=field(default_factory=dict);error:str|None=None
class AsterVoss:
    def __init__(self,config,provider:LLMProvider|None=None,router:TaskRouter|None=None,jev_client=None,system_prompt=DEFAULT_SYSTEM_PROMPT,identity_name="",identity_tagline=""):
        self.config=config;self.system_prompt=system_prompt;self.identity_name=identity_name;self.identity_tagline=identity_tagline
        self.jev=jev_client if jev_client is not None else create_jev_client(config)
        self.router=router or TaskRouter(config,jev_client=self.jev)
        self._fixed_provider=provider;self._messages=[LLMMessage.system(system_prompt)];self._messages.extend(load_history())
    @property
    def identity_display(self):return f"{self.identity_name} - {self.identity_tagline}" if self.identity_name and self.identity_tagline else (self.identity_name or "Personal AI Agent")
    @property
    def display_name(self):return self.identity_name or "Personal AI Agent"
    @property
    def messages(self):return self._messages
    def reset(self):self._messages=[LLMMessage.system(self.system_prompt)];clear_history()
    def remember(self,note):return save_long_term_note(note)
    def chat(self,user_input):return self.run(user_input).text
    def run(self,user_input):
        text=(user_input or "").strip()
        if not text:return TurnResult("Please type a message.","-","-","empty",0)
        for prefix in ("记住：","记住:","请记住：","请记住:","以后记住：","以后记住:"):
            if text.startswith(prefix):
                note=text[len(prefix):].strip();ok=self.remember(note);reply="好，我已经把这条写进长期记忆了。" if ok else "我没能保存这条记忆。"
                self._messages += [LLMMessage.user(text),LLMMessage.assistant(reply)];save_history(self._messages)
                return TurnResult(reply,"memory","local","memory",0)
        decision=self.router.select(text)
        try:provider=self._fixed_provider or self.router.get_provider(decision.provider_name)
        except LLMError as exc:return TurnResult(f"Configuration error: {exc}",decision.provider_name,"-",decision.source,decision.complexity,error=str(exc))
        if not provider.is_available():
            reason=provider.unavailable_reason()
            return TurnResult(f"I cannot reach a model right now: provider '{provider.name}' is not configured ({reason}).",provider.name,provider.model,decision.source,decision.complexity,error=reason)
        self._messages.append(LLMMessage.user(text))
        return self._tool_loop(provider,decision,self.router.reasoning_for(provider))
    def _tool_loop(self,provider,decision,reasoning):
        used=[];usage={}
        for _ in range(MAX_TOOL_ITERATIONS):
            try:r=provider.complete(self._messages,tools=tool_specs(),reasoning=reasoning)
            except LLMError as exc:
                if self._messages and self._messages[-1].role=="user":self._messages.pop()
                return TurnResult(f"The model call failed: {exc}",provider.name,provider.model,decision.source,decision.complexity,used,usage,str(exc))
            usage=r.usage or usage
            if not r.has_tool_calls:
                final=r.text or "";self._messages.append(LLMMessage.assistant(final,reasoning_content=r.reasoning_content));save_history(self._messages)
                return TurnResult(final,r.provider,r.model,decision.source,decision.complexity,used,usage)
            self._messages.append(LLMMessage.assistant(r.text,tool_calls=r.tool_calls,reasoning_content=r.reasoning_content))
            for call in r.tool_calls:
                used.append(call.name);self._messages.append(LLMMessage.tool_result(call.id,run_tool(call.name,call.arguments)))
        final="I stopped after several tool calls without reaching a final answer.";self._messages.append(LLMMessage.assistant(final));save_history(self._messages)
        return TurnResult(final,provider.name,provider.model,decision.source,decision.complexity,used,usage,"tool loop limit")
MintAgent=AsterVoss
