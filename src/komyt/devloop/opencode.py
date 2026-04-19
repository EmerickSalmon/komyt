"""OpenCode SDK wrapper for Komyt."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

logger = logging.getLogger(__name__)


@dataclass
class SessionUsage:
    """Tracks token usage and cost for a session."""

    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0

    def add(self, input_tok: int, output_tok: int, cost: float = 0.0) -> None:
        self.input_tokens += input_tok
        self.output_tokens += output_tok
        self.total_tokens += input_tok + output_tok
        self.estimated_cost += cost


@dataclass
class CompletionResult:
    """Result of a single OpenCode completion."""

    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    estimated_cost: float = 0.0
    model: str = ""


class OpenCodeBackend(Protocol):
    """Protocol for the OpenCode SDK backend — allows mocking."""

    async def send_message(self, session_id: str, message: str) -> CompletionResult: ...

    async def create_session(
        self, working_dir: str, model: str, container_id: str = "",
    ) -> str: ...

    async def close_session(self, session_id: str) -> None: ...


class OpenCodeClient:
    """High-level wrapper around the OpenCode SDK for development tasks."""

    def __init__(
        self,
        backend: OpenCodeBackend,
        model: str = "claude-sonnet-4-6",
        max_tokens: int = 500_000,
    ) -> None:
        self._backend = backend
        self._model = model
        self._max_tokens = max_tokens
        self._session_id: str | None = None
        self._usage = SessionUsage()

    @property
    def usage(self) -> SessionUsage:
        return self._usage

    @property
    def budget_remaining(self) -> int:
        return max(0, self._max_tokens - self._usage.total_tokens)

    @property
    def budget_exhausted(self) -> bool:
        return self._usage.total_tokens >= self._max_tokens

    async def start_session(self, working_dir: str, container_id: str = "") -> str:
        self._session_id = await self._backend.create_session(
            working_dir, self._model, container_id=container_id,
        )
        logger.info(
            "OpenCode session started: %s (model=%s, container=%s)",
            self._session_id, self._model, container_id[:12] or "n/a",
        )
        return self._session_id

    async def send(self, prompt: str) -> CompletionResult:
        if self._session_id is None:
            raise RuntimeError("No active session — call start_session() first")

        if self.budget_exhausted:
            raise TokenBudgetExceeded(
                f"Token budget exhausted: {self._usage.total_tokens}/{self._max_tokens}"
            )

        result = await self._backend.send_message(self._session_id, prompt)
        self._usage.add(result.input_tokens, result.output_tokens, result.estimated_cost)

        logger.debug(
            "OpenCode response: %d input + %d output tokens (total: %d/%d)",
            result.input_tokens, result.output_tokens,
            self._usage.total_tokens, self._max_tokens,
        )
        return result

    async def close(self) -> None:
        if self._session_id:
            await self._backend.close_session(self._session_id)
            logger.info(
                "Session closed. Total usage: %d tokens, $%.4f",
                self._usage.total_tokens, self._usage.estimated_cost,
            )
            self._session_id = None

    async def __aenter__(self) -> OpenCodeClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


class TokenBudgetExceeded(Exception):
    """Raised when the token budget for a task is exhausted."""
