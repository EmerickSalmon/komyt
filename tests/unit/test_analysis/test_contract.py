"""Unit tests for contract extraction and validation."""

from __future__ import annotations

import json

import pytest

from komyt.analysis.contract import (
    ContractExtractor,
    _build_contract,
    _compute_score,
    _generate_questions,
    _get_filled_fields,
    _get_missing_fields,
    _parse_json,
    _score_to_status,
)
from komyt.core.config import AnalysisConfig
from komyt.core.models import (
    Complexity,
    ContractValidation,
    Priority,
    TicketData,
    TicketType,
    ValidationStatus,
)


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt: str | None = None

    async def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


def _full_contract_json() -> dict:
    return {
        "objective": "Add JWT auth endpoint",
        "ticket_type": "feature",
        "success_criteria": ["Returns JWT on valid creds", "Returns 401 on invalid"],
        "expected_behavior": "User sends email/password, gets JWT",
        "scope_included": ["auth endpoint", "JWT generation"],
        "scope_excluded": ["password reset"],
        "reproduction_steps": None,
        "affected_files": ["src/api/auth.py"],
        "technical_constraints": ["Must use HS256"],
        "dependencies": ["pyjwt"],
        "references": ["https://jwt.io"],
        "priority": "high",
        "estimated_complexity": "moderate",
    }


def _minimal_contract_json() -> dict:
    return {
        "objective": "",
        "ticket_type": "feature",
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
    }


@pytest.mark.unit
class TestParseJson:
    def test_parses_plain_json(self) -> None:
        result = _parse_json('{"key": "value"}')
        assert result == {"key": "value"}

    def test_strips_markdown_fences(self) -> None:
        raw = '```json\n{"key": "value"}\n```'
        result = _parse_json(raw)
        assert result == {"key": "value"}

    def test_strips_bare_fences(self) -> None:
        raw = '```\n{"key": "value"}\n```'
        result = _parse_json(raw)
        assert result == {"key": "value"}

    def test_raises_on_invalid_json(self) -> None:
        with pytest.raises(json.JSONDecodeError):
            _parse_json("not json")


@pytest.mark.unit
class TestBuildContract:
    def test_builds_full_contract(self) -> None:
        data = _full_contract_json()
        contract = _build_contract(data)

        assert contract.objective == "Add JWT auth endpoint"
        assert contract.ticket_type == TicketType.FEATURE
        assert len(contract.success_criteria) == 2
        assert contract.expected_behavior == "User sends email/password, gets JWT"
        assert contract.scope is not None
        assert contract.scope.included == ["auth endpoint", "JWT generation"]
        assert contract.scope.excluded == ["password reset"]
        assert contract.reproduction_steps is None
        assert contract.affected_files == ["src/api/auth.py"]
        assert contract.technical_constraints == ["Must use HS256"]
        assert contract.dependencies == ["pyjwt"]
        assert contract.references == ["https://jwt.io"]
        assert contract.priority == Priority.HIGH
        assert contract.estimated_complexity == Complexity.MODERATE

    def test_builds_minimal_contract(self) -> None:
        contract = _build_contract(_minimal_contract_json())

        assert contract.objective == ""
        assert contract.ticket_type == TicketType.FEATURE
        assert contract.success_criteria == []
        assert contract.scope is None

    def test_handles_invalid_enum_values(self) -> None:
        data = _full_contract_json()
        data["ticket_type"] = "invalid"
        data["priority"] = "super_critical"
        data["estimated_complexity"] = "impossible"

        contract = _build_contract(data)

        assert contract.ticket_type == TicketType.FEATURE
        assert contract.priority == Priority.MEDIUM
        assert contract.estimated_complexity == Complexity.MODERATE


@pytest.mark.unit
class TestFilledMissingFields:
    def test_full_contract_all_filled(self) -> None:
        contract = _build_contract(_full_contract_json())
        filled = _get_filled_fields(contract)

        assert "objective" in filled
        assert "success_criteria" in filled
        assert "ticket_type" in filled
        assert "expected_behavior" in filled
        assert "scope" in filled

    def test_minimal_contract_missing_fields(self) -> None:
        contract = _build_contract(_minimal_contract_json())
        missing = _get_missing_fields(contract)

        assert "objective" in missing
        assert "success_criteria" in missing
        assert "expected_behavior" in missing
        assert "scope" in missing


@pytest.mark.unit
class TestComputeScore:
    def test_full_score(self) -> None:
        filled = [
            "objective", "success_criteria", "ticket_type", "expected_behavior",
            "scope", "affected_files", "technical_constraints", "dependencies",
            "references",
        ]
        score = _compute_score(filled, [])
        assert score == 93

    def test_minimal_score(self) -> None:
        score = _compute_score(["ticket_type"], ["objective", "success_criteria"])
        assert score == 5

    def test_capped_at_100(self) -> None:
        filled = [
            "objective", "success_criteria", "ticket_type", "expected_behavior",
            "scope", "reproduction_steps", "affected_files", "technical_constraints",
            "dependencies", "examples", "references",
        ]
        score = _compute_score(filled, [])
        assert score == 100


@pytest.mark.unit
class TestScoreToStatus:
    def test_ready(self) -> None:
        assert _score_to_status(80, 70) == ValidationStatus.READY
        assert _score_to_status(95, 70) == ValidationStatus.READY

    def test_needs_clarification(self) -> None:
        assert _score_to_status(50, 70) == ValidationStatus.NEEDS_CLARIFICATION
        assert _score_to_status(79, 70) == ValidationStatus.NEEDS_CLARIFICATION

    def test_rejected(self) -> None:
        assert _score_to_status(10, 70) == ValidationStatus.REJECTED
        assert _score_to_status(34, 70) == ValidationStatus.REJECTED


@pytest.mark.unit
class TestGenerateQuestions:
    def test_generates_questions_for_missing(self) -> None:
        questions = _generate_questions(["objective", "success_criteria"], [])
        assert len(questions) == 2
        assert any("objective" in q.lower() for q in questions)

    def test_includes_ambiguities(self) -> None:
        questions = _generate_questions([], ["Bug without repro steps"])
        assert "Bug without repro steps" in questions

    def test_empty_when_nothing_missing(self) -> None:
        assert _generate_questions([], []) == []


@pytest.mark.unit
class TestContractExtractor:
    async def test_extracts_ready_contract(self, sample_ticket: TicketData) -> None:
        llm = FakeLLM(json.dumps(_full_contract_json()))
        extractor = ContractExtractor(llm=llm, config=AnalysisConfig())

        result = await extractor.extract(sample_ticket)

        assert isinstance(result, ContractValidation)
        assert result.status == ValidationStatus.READY
        assert result.score >= 80
        assert result.extracted_contract.objective == "Add JWT auth endpoint"
        assert llm.last_prompt is not None
        assert sample_ticket.title in llm.last_prompt

    async def test_extracts_vague_contract(self, vague_ticket: TicketData) -> None:
        llm = FakeLLM(json.dumps(_minimal_contract_json()))
        extractor = ContractExtractor(llm=llm, config=AnalysisConfig())

        result = await extractor.extract(vague_ticket)

        assert result.status in (ValidationStatus.NEEDS_CLARIFICATION, ValidationStatus.REJECTED)
        assert result.score < 80
        assert len(result.missing_fields) > 0

    async def test_bug_without_repro_adds_ambiguity(self) -> None:
        data = _full_contract_json()
        data["ticket_type"] = "bugfix"
        data["reproduction_steps"] = None
        llm = FakeLLM(json.dumps(data))
        extractor = ContractExtractor(llm=llm, config=AnalysisConfig())

        ticket = TicketData(
            id="t1", source="github", external_id="1",
            title="Bug", description="@komyt something broke",
        )
        result = await extractor.extract(ticket)

        assert any("reproduction" in a.lower() for a in result.ambiguities)

    async def test_includes_comments_in_prompt(
        self, ticket_with_trigger_in_comment: TicketData,
    ) -> None:
        llm = FakeLLM(json.dumps(_full_contract_json()))
        extractor = ContractExtractor(llm=llm, config=AnalysisConfig())

        await extractor.extract(ticket_with_trigger_in_comment)

        assert llm.last_prompt is not None
        assert "emerick" in llm.last_prompt
        assert "ready to be automated" in llm.last_prompt
