from __future__ import annotations
import json,urllib.request,urllib.error
from typing import Any
from ..base import LLMError,LLMProvider,LLMResponse,ToolCall
class DeepSeekProvider(LLMProvider):
    name="deepseek"
    @property\n    def capabilities(self):\n        return {"chat", "tools", "reasoning"}\n
    def complete(self,messages,tools=None,temperature=None,max_tokens=None,reasoning=None):
        if not self.is_available(): raise LLMError(self.unavailable_reason())
        ms=[]
        for m in messages:
            d={"role":m.role,"content":m.content or ""}
            if m.role=="tool": d["tool_call_id"]=m.tool_call_id
            if m.role=="assistant" and m.tool_calls:
                d["tool_calls"]=[{"id":c.id,"type":"function","function":{"name":c.name,"arguments":c.arguments_json()}} for c in m.tool_calls]
            if m.role=="assistant" and m.reasoning_content: d["reasoning_content"]=m.reasoning_content
            ms.append(d)
        payload={"model":self.model,"messages":ms,"max_tokens":max_tokens or self.max_tokens}
        if tools: payload["tools"]=list(tools)
        if temperature is not None: payload["temperature"]=temperature
        if reasoning: payload["reasoning_effort"]=reasoning
        req=urllib.request.Request(self._config.base_url.rstrip("/")+"/chat/completions",data=json.dumps(payload,ensure_ascii=False).encode(),headers={"Content-Type":"application/json","Authorization":"Bearer "+self.api_key()})
        try:
            with urllib.request.urlopen(req,timeout=self.timeout) as resp: body=json.loads(resp.read().decode())
        except urllib.error.HTTPError as e: raise LLMError(f"HTTP {e.code}: {e.read().decode(errors='replace')[:800]}") from e
        except (urllib.error.URLError,TimeoutError) as e: raise LLMError(f"network error: {e}") from e
        choices=body.get("choices") or []
        if not choices: raise LLMError("model returned no choices")
        msg=choices[0].get("message") or {}; calls=[]
        for c in msg.get("tool_calls") or []:
            fn=c.get("function") or {}; raw=fn.get("arguments") or "{}"
            try: args=json.loads(raw) if isinstance(raw,str) else raw
            except json.JSONDecodeError: args={}
            calls.append(ToolCall(c.get("id","tool"),fn.get("name",""),args))
        return LLMResponse(msg.get("content"),calls,self.name,self.model,body.get("usage") or {},choices[0].get("finish_reason"),msg.get("reasoning_content"))
