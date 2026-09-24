"""Provider-neutral embeddings interface with an optional OpenAI implementation."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from abc import ABC, abstractmethod


class EmbeddingError(Exception):
    pass


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError


class OpenAIEmbeddingProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model: str = "text-embedding-3-small", base_url: str = "https://api.openai.com/v1", timeout: float = 30.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def embed(self, text: str) -> list[float]:
        if not self.api_key:
            raise EmbeddingError("OpenAI API key is not configured")
        payload = {"model": self.model, "input": text}
        request = urllib.request.Request(
            self.base_url + "/embeddings",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.api_key,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode(errors="replace")[:800]
            raise EmbeddingError(f"HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError) as exc:
            raise EmbeddingError(f"network error: {exc}") from exc

        data = body.get("data") or []
        if not data or not isinstance(data[0].get("embedding"), list):
            raise EmbeddingError("embedding response is malformed")
        return [float(value) for value in data[0]["embedding"]]
