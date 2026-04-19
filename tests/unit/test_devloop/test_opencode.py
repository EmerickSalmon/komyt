"""Unit tests for the OpenCode client wrapper."""

from __future__ import annotations

import pytest

from komyt.devloop.opencode import (
    CompletionResult,
    OpenCodeClient,
    SessionUsage,
    TokenBudgetExceeded,
)


class FakeBackend:
    def __init__(self, responses: list[CompletionResult] | None = None) -> None:
        self._responses = responses or [
            CompletionResult(text="done", input_tokens=100, output_tokens=50)
        ]
        self._index = 0
        self.messages: list[tuple[str, str]] = []
        self.sessions_created: list[tuple[str, str]] = []
        self.sessions_closed: list[str] = []

    async def create_session(
        self, working_dir: str, model: str, container_id: str = "",
    ) -> str:
        self.sessions_created.append((working_dir, model))
        return "session-001"

    async def send_message(self, session_id: str, message: str) -> CompletionResult:
        self.messages.append((session_id, message))
        resp = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return resp

    async def close_session(self, session_id: str) -> None:
        self.sessions_closed.append(session_id)


@pytest.mark.unit
class TestSessionUsage:
    def test_add(self) -> None:
        usage = SessionUsage()
        usage.add(100, 50, 0.01)
        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150
        assert usage.estimated_cost == pytest.approx(0.01)

    def test_accumulates(self) -> None:
        usage = SessionUsage()
        usage.add(100, 50, 0.01)
        usage.add(200, 100, 0.02)
        assert usage.total_tokens == 450
        assert usage.estimated_cost == pytest.approx(0.03)


@pytest.mark.unit
class TestOpenCodeClient:
    async def test_start_session(self) -> None:
        backend = FakeBackend()
        client = OpenCodeClient(backend=backend, model="test-model")

        sid = await client.start_session("/workspace")

        assert sid == "session-001"
        assert backend.sessions_created == [("/workspace", "test-model")]

    async def test_send_message(self) -> None:
        backend = FakeBackend()
        client = OpenCodeClient(backend=backend)
        await client.start_session("/workspace")

        result = await client.send("implement feature")

        assert result.text == "done"
        assert backend.messages == [("session-001", "implement feature")]

    async def test_tracks_usage(self) -> None:
        backend = FakeBackend([
            CompletionResult(text="a", input_tokens=100, output_tokens=50, estimated_cost=0.01),
            CompletionResult(text="b", input_tokens=200, output_tokens=100, estimated_cost=0.02),
        ])
        client = OpenCodeClient(backend=backend)
        await client.start_session("/workspace")

        await client.send("step 1")
        await client.send("step 2")

        assert client.usage.total_tokens == 450
        assert client.usage.estimated_cost == pytest.approx(0.03)

    async def test_budget_remaining(self) -> None:
        backend = FakeBackend([
            CompletionResult(text="ok", input_tokens=1000, output_tokens=500),
        ])
        client = OpenCodeClient(backend=backend, max_tokens=5000)
        await client.start_session("/workspace")

        await client.send("test")

        assert client.budget_remaining == 3500
        assert client.budget_exhausted is False

    async def test_budget_exceeded_raises(self) -> None:
        backend = FakeBackend([
            CompletionResult(text="ok", input_tokens=300, output_tokens=200),
        ])
        client = OpenCodeClient(backend=backend, max_tokens=500)
        await client.start_session("/workspace")

        await client.send("first")  # 500 tokens, hits limit

        with pytest.raises(TokenBudgetExceeded):
            await client.send("second")

    async def test_send_without_session_raises(self) -> None:
        backend = FakeBackend()
        client = OpenCodeClient(backend=backend)

        with pytest.raises(RuntimeError, match="No active session"):
            await client.send("test")

    async def test_close_session(self) -> None:
        backend = FakeBackend()
        client = OpenCodeClient(backend=backend)
        await client.start_session("/workspace")

        await client.close()

        assert backend.sessions_closed == ["session-001"]

    async def test_context_manager(self) -> None:
        backend = FakeBackend()
        async with OpenCodeClient(backend=backend) as client:
            await client.start_session("/workspace")

        assert backend.sessions_closed == ["session-001"]
