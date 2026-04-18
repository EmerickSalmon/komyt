"""Functional tests for the analysis pipeline — end-to-end with mock LLM."""

from __future__ import annotations

import json

import pytest

from komyt.analysis.engine import AnalysisEngine, AnalysisResult
from komyt.core.config import AnalysisConfig
from komyt.core.models import (
    CommentData,
    TicketData,
    TicketType,
    ValidationStatus,
)
from datetime import datetime


class FakeLLM:
    """Simulates LLM responses for the full pipeline."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._index = 0
        self.prompts: list[str] = []

    async def complete(self, prompt: str) -> str:
        self.prompts.append(prompt)
        resp = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return resp


def _contract_response(
    objective: str = "Implement feature",
    ticket_type: str = "feature",
    criteria: list[str] | None = None,
    expected_behavior: str | None = "Feature works as described",
    scope_included: list[str] | None = None,
) -> str:
    return json.dumps({
        "objective": objective,
        "ticket_type": ticket_type,
        "success_criteria": criteria or ["Feature is implemented", "Tests pass"],
        "expected_behavior": expected_behavior,
        "scope_included": scope_included or ["main feature"],
        "scope_excluded": [],
        "reproduction_steps": None,
        "affected_files": ["src/feature.py"],
        "technical_constraints": [],
        "dependencies": [],
        "references": [],
        "priority": "medium",
        "estimated_complexity": "moderate",
    })


def _plan_response(steps: int = 3) -> str:
    return json.dumps({
        "steps": [
            {
                "description": f"Step {i}",
                "prompt": f"Implement step {i}...",
                "files_involved": [f"src/step{i}.py"],
            }
            for i in range(1, steps + 1)
        ],
        "files_to_modify": ["src/app.py"],
        "files_to_create": [f"src/step{i}.py" for i in range(1, steps + 1)],
        "tests_to_write": ["tests/test_feature.py"],
        "documentation_updates": [],
    })


@pytest.mark.functional
class TestAnalysisPipeline:
    async def test_clear_ticket_full_pipeline(self) -> None:
        ticket = TicketData(
            id="func-1",
            source="github",
            external_id="100",
            title="Add user registration endpoint",
            description=(
                "@komyt Add a POST /api/users/register endpoint.\n"
                "- Validate email format\n"
                "- Hash password with bcrypt\n"
                "- Return 201 with user ID\n"
                "- Return 409 if email exists"
            ),
            labels=["feature", "backend"],
            repo_url="https://github.com/org/repo",
        )

        llm = FakeLLM([
            _contract_response(
                objective="Add user registration endpoint",
                criteria=[
                    "POST /api/users/register works",
                    "Email validation",
                    "Password hashing with bcrypt",
                    "201 on success, 409 on duplicate",
                ],
            ),
            _plan_response(steps=3),
        ])

        engine = AnalysisEngine(config=AnalysisConfig(), llm=llm)
        result = await engine.analyze(ticket)

        assert result.validation.status == ValidationStatus.READY
        assert result.validation.score >= 80
        assert result.plan is not None
        assert len(result.plan.steps) == 3
        assert result.plan.branch_name.startswith("komyt/feature/")
        assert result.feedback_comment is None
        assert result.ticket is ticket

    async def test_vague_ticket_gets_feedback(self) -> None:
        ticket = TicketData(
            id="func-2",
            source="github",
            external_id="101",
            title="Fix the thing",
            description="@komyt it's broken",
            labels=["bug"],
        )

        llm = FakeLLM([json.dumps({
            "objective": "",
            "ticket_type": "bugfix",
            "success_criteria": [],
            "expected_behavior": None,
            "scope_included": [],
            "scope_excluded": [],
            "reproduction_steps": None,
            "affected_files": [],
            "technical_constraints": [],
            "dependencies": [],
            "references": [],
            "priority": "medium",
            "estimated_complexity": "moderate",
        })])

        engine = AnalysisEngine(config=AnalysisConfig(), llm=llm)
        result = await engine.analyze(ticket)

        assert result.validation.status != ValidationStatus.READY
        assert result.plan is None
        assert result.feedback_comment is not None
        assert "Komyt Analysis" in result.feedback_comment

    async def test_ticket_with_comments_included_in_analysis(self) -> None:
        ticket = TicketData(
            id="func-3",
            source="github",
            external_id="102",
            title="Refactor database layer",
            description="Move from raw SQL to SQLAlchemy ORM.",
            comments=[
                CommentData(
                    id="c1",
                    author="lead-dev",
                    body="@komyt Focus on the User and Order models only. "
                         "Keep backward compat with existing API responses.",
                    created_at=datetime(2026, 4, 18, 10, 0, 0),
                ),
            ],
            labels=["refactor"],
            repo_url="https://github.com/org/repo",
        )

        llm = FakeLLM([
            _contract_response(
                objective="Refactor database layer to SQLAlchemy ORM",
                ticket_type="refactor",
                scope_included=["User model", "Order model"],
            ),
            _plan_response(steps=2),
        ])

        engine = AnalysisEngine(config=AnalysisConfig(), llm=llm)
        result = await engine.analyze(ticket)

        assert "lead-dev" in llm.prompts[0]
        assert "backward compat" in llm.prompts[0]
        assert result.validation.status == ValidationStatus.READY

    async def test_custom_clarity_threshold(self) -> None:
        ticket = TicketData(
            id="func-4",
            source="github",
            external_id="103",
            title="Add logging",
            description="@komyt Add structured logging to the API",
        )

        llm = FakeLLM([json.dumps({
            "objective": "Add structured logging",
            "ticket_type": "feature",
            "success_criteria": ["Logging works"],
            "expected_behavior": None,
            "scope_included": [],
            "scope_excluded": [],
            "reproduction_steps": None,
            "affected_files": [],
            "technical_constraints": [],
            "dependencies": [],
            "references": [],
            "priority": "low",
            "estimated_complexity": "simple",
        })])

        strict_config = AnalysisConfig(clarity_threshold=90)
        engine = AnalysisEngine(config=strict_config, llm=llm)
        result = await engine.analyze(ticket)

        assert result.validation.score < 80
        assert result.validation.status == ValidationStatus.NEEDS_CLARIFICATION
