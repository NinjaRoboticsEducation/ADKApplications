"""Small explicit Ollama chat wrapper for bounded local workflow calls."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import requests


class OllamaError(RuntimeError):
    """Raised when a local Ollama request cannot complete safely."""


@dataclass(frozen=True)
class OllamaChatClient:
    """Thin wrapper around Ollama's `/api/chat` endpoint."""

    model: str = field(default_factory=lambda: os.environ.get("YTTRANSCRIPT_MODEL", "gemma4-agent"))
    api_base: str = field(default_factory=lambda: os.environ.get("OLLAMA_API_BASE", "http://localhost:11434"))
    keep_alive: str = field(default_factory=lambda: os.environ.get("YTTRANSCRIPT_KEEP_ALIVE", "15m"))
    timeout_seconds: int = field(default_factory=lambda: int(os.environ.get("YTTRANSCRIPT_TIMEOUT_SECONDS", "120")))
    num_ctx: int = field(default_factory=lambda: int(os.environ.get("YTTRANSCRIPT_NUM_CTX", "8192")))
    temperature: float = field(default_factory=lambda: float(os.environ.get("YTTRANSCRIPT_TEMPERATURE", "0.0")))

    def chat(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        schema: dict[str, Any] | None = None,
    ) -> str:
        """Run one bounded chat completion and return the message content."""
        payload: dict[str, Any] = {
            "model": self.model,
            "stream": False,
            "keep_alive": self.keep_alive,
            "options": {
                "num_ctx": self.num_ctx,
                "temperature": self.temperature,
            },
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        if schema is not None:
            payload["format"] = schema

        try:
            response = requests.post(
                f"{self.api_base.rstrip('/')}/api/chat",
                json=payload,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaError(
                "Could not reach Ollama. Make sure `ollama serve` is running and "
                f"the model `{self.model}` is available. Original error: {exc}"
            ) from exc

        data = response.json()
        content = (data.get("message") or {}).get("content", "")
        if not content or not content.strip():
            raise OllamaError(f"Ollama returned an empty response for model `{self.model}`.")
        return content.strip()

    def chat_json(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        """Run one structured-output chat completion and parse the JSON content."""
        content = self.chat(system_prompt, user_prompt, schema=schema)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"Ollama returned invalid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise OllamaError("Ollama JSON response must be an object.")
        return parsed
