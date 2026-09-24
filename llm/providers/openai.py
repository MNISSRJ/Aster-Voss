from __future__ import annotations

import json
import urllib.error
import urllib.request

from ..base import LLMError, LLMProvider, LLMResponse, ToolCall


class OpenAIProvider(LLMProvider):
    name = "openai"
    @property\n    def capabilities(self):\n        return {"chat", "tools", "reasoning"}\n

    def complete(
        self,
        messages,
        tools=None,
        temperature=None,
        max_tokens=None,
        reasoning=None,
    ):
        if not self.is_available():
            raise LLMError(self.unavailable_reason())

        payload_messages = []
        for message in messages:
            item = {"role": message.role, "content": message.content or ""}
            if message.role == "tool":
                item["tool_call_id"] = message.tool_call_id
            if message.role == "assistant" and message.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.name,
                            "arguments": call.arguments_json(),
                        },
                    }
                    for call in message.tool_calls
                ]
            payload_messages.append(item)

        payload = {
            "model": self.model,
            "messages": payload_messages,
            "max_tokens": max_tokens or self.max_tokens,
        }
        if tools:
            payload["tools"] = list(tools)
        if temperature is not None:
            payload["temperature"] = temperature
        if reasoning:
            payload["reasoning_effort"] = reasoning

        request = urllib.request.Request(
            self._config.base_url.rstrip("/") + "/chat/completions",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key(),
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:800]
            raise LLMError(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise LLMError(f"network error: {exc}") from exc

        choices = body.get("choices") or []
        if not choices:
            raise LLMError("model returned no choices")

        message = choices[0].get("message") or {}
        calls = []
        for raw_call in message.get("tool_calls") or []:
            function = raw_call.get("function") or {}
            raw_arguments = function.get("arguments") or "{}"
            try:
                arguments = (
                    json.loads(raw_arguments)
                    if isinstance(raw_arguments, str)
                    else raw_arguments
                )
            except json.JSONDecodeError:
                arguments = {}
            calls.append(
                ToolCall(
                    raw_call.get("id", "tool"),
                    function.get("name", ""),
                    arguments,
                )
            )

        return LLMResponse(
            message.get("content"),
            calls,
            self.name,
            self.model,
            body.get("usage") or {},
            choices[0].get("finish_reason"),
            message.get("reasoning_content"),
        )
