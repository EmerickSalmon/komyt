"""Unit tests for the analysis engine."""

from __future__ import annotations

import json

import pytest

from komyt.analysis.engine import AnalysisEngine, AnalysisResult
from komyt.core.config import AnalysisConfig
from komyt.core.models import TicketData, ValidationStatus


def _full_contract_response() -> str:
    return json.dumps({
        "objective": "Add JWT auth endpoint",
        "ticket_type": "feature",
        "success_criteria": ["Returns JWT on valid creds", "Returns 401 on invalid"],
        "expected_behavior": "User sends email/password, gets JWT",
        "scope_included": ["auth endpoint"],
        "scope_excluded": ["password reset"],
        "reproduction_steps": None,
        "affected_files": ["src/api/auth.py"],
        "technical_constraints": ["Must use HS256"],
        "dependencies": ["pyjwt"],
        "references": ["https://jwt.io"],
        "priority": "high",
        "estimated_complexity": "moderate",
    })


def _plan_response() -> str:
    return json.dumps({
        "steps": [
            {
                "description": "Create auth module",
                "prompt": "Create src/auth.py...",
                "files_involved": ["src/auth.py"],
            },
        ],
        "files_to_modify": [],
        "files_to_create": ["src/auth.py"],
        "tests_to_write": ["tests/test_auth.py"],
        "documentation_updates": [],
    })


def _vague_response() -> str:
    return json.dumps({
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
    })


class FakeLLM:
    """Returns different responses based on call order."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self._call_index = 0

    async def complete(self, prompt: str) -> str:
        response = self._responses[min(self._call_index, len(self._responses) - 1)]
        self._call_index += 1
        return response


@pytest.mark.unit
class TestAnalysisEngine:
    async def test_ready_ticket_produces_plan(self, sample_ticket: TicketData) -> None:
        llm = FakeLLM([_full_contract_response(), _plan_response()])
        engine = AnalysisEngine(config=AnalysisConfig(), llm=llm)

        result = await engine.analyze(sample_ticket)

        assert isinstance(result, AnalysisResult)
        assert result.validation.status == ValidationStatus.READY
        assert result.plan is not None
        assert len(result.plan.steps) == 1
        assert result.feedback_comment is None

    async def test_vague_ticket_no_plan(self, vague_ticket: TicketData) -> None:
        llm = FakeLLM([_vague_response()])
        engine = AnalysisEngine(config=AnalysisConfig(), llm=llm)

        result = await engine.analyze(vague_ticket)

        assert result.validation.status != ValidationStatus.READY
        assert result.plan is None
        assert result.feedback_comment is not None

    async def test_validate_returns_contract_validation(
        self, sample_ticket: TicketData,
    ) -> None:
        llm = FakeLLM([_full_contract_response()])
        engine = AnalysisEngine(config=AnalysisConfig(), llm=llm)

        validation = await engine.validate(sample_ticket)

        assert validation.score >= 80
        assert validation.status == ValidationStatus.READY

    async def test_result_references_original_ticket(
        self, sample_ticket: TicketData,
    ) -> None:
        llm = FakeLLM([_full_contract_response(), _plan_response()])
        engine = AnalysisEngine(config=AnalysisConfig(), llm=llm)

        result = await engine.analyze(sample_ticket)

        assert result.ticket is sample_ticket
