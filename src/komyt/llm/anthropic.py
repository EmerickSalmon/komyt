"""LLM clients — implements the LLMClient protocol for various backends."""

from __future__ import annotations

import logging
import os

import httpx

from komyt.core.config import OpenCodeConfig

logger = logging.getLogger(__name__)

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"


class OpenAICompatibleClient:
    """Calls any OpenAI-compatible API (LM Studio, Ollama, vLLM, OpenAI, etc.)."""

    def __init__(
        self,
        base_url: str = "http://localhost:1234/v1",
        model: str = "default",
        api_key: str = "",
        max_tokens: int = 4096,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._max_tokens = max_tokens
        url = base_url.rstrip("/")
        if not url.endswith("/v1"):
            url = url.rstrip("/")
        self._url = f"{url}/chat/completions"
        self._client = httpx.AsyncClient(timeout=120.0)

    async def complete(self, prompt: str) -> str:
        headers: dict[str, str] = {"content-type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        logger.debug(
            "OpenAI-compatible call -> %s (model=%s, prompt=%d chars)",
            self._url, self._model, len(prompt),
        )
        resp = await self._client.post(
            self._url,
            headers=headers,
            json={
                "model": self._model,
                "max_tokens": self._max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        logger.debug(
            "OpenAI-compatible response: %d chars, usage=%s",
            len(content), usage,
        )
        return content

    async def close(self) -> None:
        await self._client.aclose()


class AnthropicClient:
    """Calls the Anthropic Messages API via httpx."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str | None = None,
        max_tokens: int = 4096,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._max_tokens = max_tokens
        self._client = httpx.AsyncClient(timeout=120.0)

    async def complete(self, prompt: str) -> str:
        if not self._api_key:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. "
                "Set it via environment variable or komyt.toml."
            )
        logger.debug(
            "Anthropic call (model=%s, prompt=%d chars)", self._model, len(prompt),
        )
        resp = await self._client.post(
            ANTHROPIC_API_URL,
            headers={
                "x-api-key": self._api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": self._model,
                "max_tokens": self._max_tokens,
                "messages": [{"role": "user", "content": prompt}],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        text = data["content"][0]["text"]
        logger.debug(
            "Anthropic response: %d chars, usage=%s", len(text), data.get("usage", {}),
        )
        return text

    async def close(self) -> None:
        await self._client.aclose()


def create_llm_client(config: OpenCodeConfig) -> OpenAICompatibleClient | AnthropicClient:
    """Create the right LLM client based on config."""
    if "anthropic.com" in config.server_url:
        return AnthropicClient(
            model=config.default_model,
            api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
        )
    return OpenAICompatibleClient(
        base_url=config.server_url,
        model=config.default_model,
    )
