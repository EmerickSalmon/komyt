"""Unit tests for the pipeline reporter."""

from __future__ import annotations

import pytest

from komyt.core.models import (
    DevelopmentPlan,
    DevStep,
    StepResult,
    StepStatus,
    TaskStatus,
    TicketContract,
    TicketData,
    TicketType,
)
from komyt.devloop.loop import LoopResult
from komyt.finalization.reporter import Reporter, _determine_status, _format_duration


def _make_plan() -> DevelopmentPlan:
    ticket = TicketData(
        id="t1", source="github", external_id="42",
        title="Test", description="test",
    )
    contract = TicketContract(objective="Test", ticket_type=TicketType.FEATURE)
    return DevelopmentPlan(
        ticket=ticket, contract=contract,
        steps=[DevStep(id="s1", description="Step 1")],
        branch_name="komyt/feature/test",
    )


@pytest.mark.unit
class TestDetermineStatus:
    def test_completed_with_pr(self) -> None:
        result = LoopResult(steps=[StepResult(status=StepStatus.SUCCESS)])
        assert _determine_status(result, "https://pr") == TaskStatus.COMPLETED

    def test_failed_on_abort(self) -> None:
        result = LoopResult(aborted=True, abort_reason="budget")
        assert _determine_status(result, None) == TaskStatus.FAILED

    def test_failed_with_failures(self) -> None:
        result = LoopResult(steps=[StepResult(status=StepStatus.FAILED)])
        assert _determine_status(result, None) == TaskStatus.FAILED


@pytest.mark.unit
class TestFormatDuration:
    def test_seconds(self) -> None:
        assert _format_duration(45) == "45s"

    def test_minutes(self) -> None:
        assert _format_duration(125) == "2m 5s"

    def test_zero(self) -> None:
        assert _format_duration(0) == "0s"


@pytest.mark.unit
class TestReporter:
    def test_successful_report(self) -> None:
        reporter = Reporter()
        loop_result = LoopResult(
            steps=[StepResult(status=StepStatus.SUCCESS)],
            total_tokens=10000, estimated_cost=0.10,
        )

        report = reporter.build_report(
            _make_plan(), loop_result,
            pr_url="https://github.com/org/repo/pull/1",
            duration_seconds=120,
        )

        assert report.pipeline_result.status == TaskStatus.COMPLETED
        assert report.pipeline_result.pr_url == "https://github.com/org/repo/pull/1"
        assert "Complete" in report.comment_body
        assert "10,000" in report.comment_body
        assert "2m 0s" in report.comment_body

    def test_failed_report(self) -> None:
        reporter = Reporter()
        loop_result = LoopResult(
            steps=[StepResult(status=StepStatus.FAILED, errors=["test failed"])],
            total_tokens=5000, aborted=True, abort_reason="Token budget exhausted",
        )

        report = reporter.build_report(_make_plan(), loop_result, duration_seconds=60)

        assert report.pipeline_result.status == TaskStatus.FAILED
        assert "Failed" in report.comment_body
        assert "Token budget" in report.comment_body

    def test_report_references_ticket(self) -> None:
        reporter = Reporter()
        loop_result = LoopResult(steps=[StepResult(status=StepStatus.SUCCESS)])
        report = reporter.build_report(_make_plan(), loop_result)
        assert report.ticket.id == "t1"
