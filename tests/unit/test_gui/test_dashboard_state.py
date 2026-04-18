"""Unit tests for the dashboard state management."""

from __future__ import annotations

import asyncio

import pytest

from komyt.core.models import PipelineResult, TaskStatus, TicketData
from komyt.gui.app import DashboardState, TaskEntry


@pytest.mark.unit
class TestTaskEntry:
    def test_create(self) -> None:
        entry = TaskEntry(
            ticket_id="t1", title="Test", status="completed",
            branch="komyt/feature/test", tokens=5000, cost=0.05,
        )
        assert entry.ticket_id == "t1"
        assert entry.status == "completed"


@pytest.mark.unit
class TestDashboardState:
    def test_upsert_task(self) -> None:
        state = DashboardState()
        entry = TaskEntry(ticket_id="t1", title="Test", status="developing")
        state.upsert_task(entry)

        assert "t1" in state.tasks
        assert state.tasks["t1"].status == "developing"
        assert state.tasks["t1"].updated_at != ""

    def test_upsert_overwrites(self) -> None:
        state = DashboardState()
        state.upsert_task(TaskEntry(ticket_id="t1", title="Test", status="developing"))
        state.upsert_task(TaskEntry(ticket_id="t1", title="Test", status="completed"))

        assert state.tasks["t1"].status == "completed"

    def test_record_from_result(self) -> None:
        state = DashboardState()
        ticket = TicketData(
            id="t1", source="github", external_id="42",
            title="Add auth", description="test",
        )
        result = PipelineResult(
            ticket=ticket, status=TaskStatus.COMPLETED,
            pr_url="https://github.com/org/repo/pull/1",
            branch_name="komyt/feature/auth",
            total_tokens=10000, estimated_cost=0.10,
            duration_seconds=120.0,
        )
        state.record_from_result(result)

        assert "t1" in state.tasks
        assert state.tasks["t1"].title == "Add auth"
        assert state.tasks["t1"].status == "completed"
        assert state.tasks["t1"].pr_url == "https://github.com/org/repo/pull/1"

    def test_events_recorded(self) -> None:
        state = DashboardState()
        state.upsert_task(TaskEntry(ticket_id="t1", title="Test", status="queued"))

        assert len(state.events) == 1
        assert state.events[0]["event"] == "task_update"

    def test_subscribe_receives_events(self) -> None:
        state = DashboardState()
        q = state.subscribe()

        state.upsert_task(TaskEntry(ticket_id="t1", title="Test", status="queued"))

        assert not q.empty()
        event = q.get_nowait()
        assert event["event"] == "task_update"

    def test_unsubscribe(self) -> None:
        state = DashboardState()
        q = state.subscribe()
        state.unsubscribe(q)

        state.upsert_task(TaskEntry(ticket_id="t1", title="Test", status="queued"))

        assert q.empty()

    def test_events_capped_at_100(self) -> None:
        state = DashboardState()
        for i in range(150):
            state.upsert_task(TaskEntry(ticket_id=f"t{i}", title=f"T{i}", status="queued"))

        assert len(state.events) == 100
