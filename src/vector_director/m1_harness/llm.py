"""One small seam for "ask a model for JSON that matches this Pydantic schema".

The generator and the judge talk to this, never to a vendor SDK, so the model behind
them is a command-line flag. Three backends:

  anthropic  Claude via the official SDK. Needs ANTHROPIC_API_KEY (or `ant auth login`).
  gemini     Google Gemini over REST. Needs GEMINI_API_KEY; the free tier works.
  ollama     Any local model in Ollama (http://localhost:11434, or OLLAMA_HOST).

Every backend constrains decoding to the JSON schema where the provider supports it.
Cross-field rules still have to be checked by the caller with Pydantic.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol

from pydantic import BaseModel

# (input, output) USD per million tokens, for cost estimates only. Unknown models cost 0.
PRICES_PER_MTOK = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}

DEFAULT_MODELS = {
    # provider: (generator model, vision judge model)
    "anthropic": ("claude-opus-5-5", "claude-opus-5-5"),
    "gemini": ("gemini-3.8-flash", "gemini-3.8-flash"),
    "ollama": ("qwen2.5-coder:7b", "qwen2.5vl:7b"),
}


@dataclass
class Reply:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    stop: str = "end"  # "end" when the model finished normally, else the provider's reason

    @property
    def ok(self) -> bool:
        return self.stop == "end" and bool(self.text)


class JsonLLM(Protocol):
    provider: str
    model: str

    def ask(
        self,
        system: str,
        prompt: str,
        schema: type[BaseModel],
        images: Sequence[bytes] = (),
        max_tokens: int = 16000,
    ) -> Reply: ...


def make_llm(
    provider: str = "anthropic", model: str | None = None, *, vision: bool = False, **kw
) -> JsonLLM:
    """Backend by name. `model=None` picks the provider's default for the role."""
    if provider not in DEFAULT_MODELS:
        raise ValueError(f"unknown provider {provider!r}; pick one of {sorted(DEFAULT_MODELS)}")
    model = model or DEFAULT_MODELS[provider][1 if vision else 0]
    backend = {"anthropic": AnthropicLLM, "gemini": GeminiLLM, "ollama": OllamaLLM}[provider]
    return backend(model, **kw)


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    pin, pout = PRICES_PER_MTOK.get(model, (0.0, 0.0))
    return (input_tokens * pin + output_tokens * pout) / 1e6


def inline_schema(schema: type[BaseModel]) -> dict:
    """Pydantic's JSON schema with every $ref expanded, for providers that dislike $defs."""
    raw = schema.model_json_schema()
    defs = raw.pop("$defs", {})

    def expand(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return expand(defs[node["$ref"].rsplit("/", 1)[-1]])
            # drop schema "title" strings, keep any property that happens to be named title
            return {
                k: expand(v) for k, v in node.items() if not (k == "title" and isinstance(v, str))
            }
        if isinstance(node, list):
            return [expand(v) for v in node]
        return node

    return expand(raw)


def _post_json(url: str, body: dict, headers: dict | None = None, timeout: float = 600) -> dict:
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"{url.split('?')[0]} -> HTTP {exc.code}: {exc.read()[:500]!r}") from exc


class AnthropicLLM:
    provider = "anthropic"

    def __init__(self, model: str, effort: str | None = None, client=None) -> None:
        self.model, self.effort = model, effort
        self._client = client

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def ask(self, system, prompt, schema, images=(), max_tokens=16000) -> Reply:
        from anthropic import transform_schema

        content: list[dict] = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": base64.b64encode(png).decode(),
                },
            }
            for png in images
        ]
        content.append({"type": "text", "text": prompt})
        output_config: dict = {
            "format": {"type": "json_schema", "schema": transform_schema(schema)}
        }
        if self.effort:
            output_config["effort"] = self.effort
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": content}],
            output_config=output_config,
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        stop = "end" if response.stop_reason == "end_turn" else str(response.stop_reason)
        return Reply(text, response.usage.input_tokens, response.usage.output_tokens, stop)


class GeminiLLM:
    """Gemini's generateContent REST endpoint with a JSON-schema response format."""

    provider = "gemini"
    url = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, model: str, api_key: str | None = None) -> None:
        self.model = model
        self.api_key = (
            api_key or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        )

    def ask(self, system, prompt, schema, images=(), max_tokens=16000) -> Reply:
        if not self.api_key:
            raise RuntimeError("set GEMINI_API_KEY (free key: https://aistudio.google.com/apikey)")
        parts: list[dict] = [
            {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(png).decode()}}
            for png in images
        ]
        parts.append({"text": prompt})
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "responseMimeType": "application/json",
                "responseJsonSchema": inline_schema(schema),
            },
        }
        data = _post_json(
            self.url.format(model=self.model), body, headers={"x-goog-api-key": self.api_key}
        )
        candidate = (data.get("candidates") or [{}])[0]
        text = "".join(p.get("text", "") for p in candidate.get("content", {}).get("parts", []))
        reason = candidate.get("finishReason", "UNKNOWN")
        usage = data.get("usageMetadata", {})
        return Reply(
            text,
            usage.get("promptTokenCount", 0),
            usage.get("candidatesTokenCount", 0),
            "end" if reason == "STOP" else reason,
        )


class OllamaLLM:
    """A local model through Ollama's /api/chat, with `format` set to the JSON schema.

    Pull models first, e.g. `ollama pull qwen2.5-coder:7b` and `ollama pull qwen2.5vl:7b`.
    """

    provider = "ollama"

    def __init__(self, model: str, host: str | None = None, num_ctx: int = 16384) -> None:
        self.model = model
        self.host = (host or os.environ.get("OLLAMA_HOST") or "http://localhost:11434").rstrip("/")
        if not self.host.startswith("http"):
            self.host = "http://" + self.host
        self.num_ctx = num_ctx

    def ask(self, system, prompt, schema, images=(), max_tokens=16000) -> Reply:
        user: dict = {"role": "user", "content": prompt}
        if images:
            user["images"] = [base64.b64encode(png).decode() for png in images]
        body = {
            "model": self.model,
            "stream": False,
            "format": inline_schema(schema),
            "options": {"num_predict": max_tokens, "num_ctx": self.num_ctx, "temperature": 0.7},
            "messages": [{"role": "system", "content": system}, user],
        }
        data = _post_json(f"{self.host}/api/chat", body)
        reason = data.get("done_reason", "stop")
        return Reply(
            data.get("message", {}).get("content", ""),
            data.get("prompt_eval_count", 0),
            data.get("eval_count", 0),
            "end" if reason == "stop" else reason,
        )
