"""Unit tests for PR creation."""

from __future__ import annotations

import pytest

from komyt.adapters.git.base import PRData, PRResult
from komyt.core.models import (
    DevelopmentPlan,
    DevStep,
    StepStatus,
    TicketContract,
    TicketData,
    TicketType,
)
from komyt.devloop.loop import LoopResult
from komyt.core.models import StepResult
from komyt.finalization.pr_creator import PRCreator, _build_pr_body, _build_pr_labels, _build_pr_title


class FakePlatform:
    def __init__(self) -> None:
        self.prs_created: list[tuple[str, PRData]] = []

    async def create_pr(self, repo: str, pr: PRData) -> PRResult:
        self.prs_created.append((repo, pr))
        return PRResult(url=f"https://github.com/{repo}/pull/1", number=1)

    async def add_pr_comment(self, repo: str, pr_number: int, comment: str) -> None:
        pass

    async def add_pr_labels(self, repo: str, pr_number: int, labels: list[str]) -> None:
        pass


def _make_plan(ticket_type: TicketType = TicketType.FEATURE) -> DevelopmentPlan:
    ticket = TicketData(
        id="t1", source="github", external_id="42",
        title="Add user authentication endpoint",
        description="@komyt Add JWT auth", repo_url="https://github.com/org/repo",
    )
    contract = TicketContract(
        objective="Add JWT auth endpoint", ticket_type=ticket_type,
        success_criteria=["POST /auth/login works", "Tests pass"],
    )
    return DevelopmentPlan(
        ticket=ticket, contract=contract,
        steps=[
            DevStep(id="s1", description="Create auth module"),
            DevStep(id="s2", description="Write tests"),
        ],
        branch_name="komyt/feature/add-auth",
    )


def _make_loop_result(completed: int = 2, failed: int = 0) -> LoopResult:
    steps = [StepResult(status=StepStatus.SUCCESS) for _ in range(completed)]
    steps += [StepResult(status=StepStatus.FAILED) for _ in range(failed)]
    return LoopResult(steps=steps, total_tokens=5000, estimated_cost=0.05)


@pytest.mark.unit
class TestBuildPrTitle:
    def test_feature_prefix(self) -> None:
        title = _build_pr_title(_make_plan(TicketType.FEATURE))
        assert title.startswith("feat:")

    def test_bugfix_prefix(self) -> None:
        title = _build_pr_title(_make_plan(TicketType.BUGFIX))
        assert title.startswith("fix:")

    def test_truncates_long_title(self) -> None:
        plan = _make_plan()
        plan.ticket.title = "A" * 100
        title = _build_pr_title(plan)
        assert len(title) <= 70


@pytest.mark.unit
class TestBuildPrBody:
    def test_contains_objective(self) -> None:
        body = _build_pr_body(_make_plan(), _make_loop_result())
        assert "Add JWT auth endpoint" in body

    def test_contains_closes_reference(self) -> None:
        body = _build_pr_body(_make_plan(), _make_loop_result())
        assert "Closes #42" in body

    def test_contains_stats(self) -> None:
        body = _build_pr_body(_make_plan(), _make_loop_result())
        assert "5,000" in body
        assert "$0.0500" in body

    def test_contains_komyt_signature(self) -> None:
        body = _build_pr_body(_make_plan(), _make_loop_result())
        assert "Komyt" in body


@pytest.mark.unit
class TestBuildPrLabels:
    def test_includes_komyt_label(self) -> None:
        labels = _build_pr_labels(_make_plan())
        assert "komyt" in labels

    def test_includes_type_label(self) -> None:
        labels = _build_pr_labels(_make_plan(TicketType.BUGFIX))
        assert "bugfix" in labels


@pytest.mark.unit
class TestPRCreator:
    async def test_creates_pr(self) -> None:
        platform = FakePlatform()
        creator = PRCreator(platform=platform)

        result = await creator.create(
            _make_plan(), _make_loop_result(), "org/repo",
        )

        assert result.url == "https://github.com/org/repo/pull/1"
        assert result.number == 1
        assert len(platform.prs_created) == 1
        _, pr_data = platform.prs_created[0]
        assert pr_data.head_branch == "komyt/feature/add-auth"
        assert "komyt" in pr_data.labels
