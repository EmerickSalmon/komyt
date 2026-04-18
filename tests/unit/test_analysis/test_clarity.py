"""Unit tests for clarity assessment and feedback generation."""

from __future__ import annotations

import pytest

from komyt.analysis.clarity import ClarityAssessor
from komyt.core.models import (
    ContractValidation,
    TicketContract,
    TicketData,
    ValidationStatus,
)


def _make_validation(
    score: int,
    status: ValidationStatus,
    missing: list[str] | None = None,
    ambiguities: list[str] | None = None,
    questions: list[str] | None = None,
) -> ContractValidation:
    return ContractValidation(
        score=score,
        status=status,
        extracted_contract=TicketContract(),
        missing_fields=missing or [],
        ambiguities=ambiguities or [],
        questions=questions or [],
    )


@pytest.fixture
def assessor() -> ClarityAssessor:
    return ClarityAssessor()


@pytest.fixture
def ticket() -> TicketData:
    return TicketData(
        id="t1", source="github", external_id="1",
        title="Test", description="test ticket",
    )


@pytest.mark.unit
class TestClarityAssessor:
    def test_no_feedback_when_ready(
        self, assessor: ClarityAssessor, ticket: TicketData,
    ) -> None:
        validation = _make_validation(85, ValidationStatus.READY)
        assert assessor.build_feedback(ticket, validation) is None

    def test_needs_clarification_feedback(
        self, assessor: ClarityAssessor, ticket: TicketData,
    ) -> None:
        validation = _make_validation(
            60,
            ValidationStatus.NEEDS_CLARIFICATION,
            missing=["success_criteria", "scope"],
            questions=["What are the acceptance criteria?", "What is in scope?"],
        )

        feedback = assessor.build_feedback(ticket, validation)

        assert feedback is not None
        assert "60/100" in feedback
        assert "Missing information" in feedback
        assert "Success Criteria" in feedback or "success criteria" in feedback.lower()
        assert "Questions" in feedback
        assert "mention `@komyt` again" in feedback

    def test_rejected_feedback_includes_template(
        self, assessor: ClarityAssessor, ticket: TicketData,
    ) -> None:
        validation = _make_validation(
            20,
            ValidationStatus.REJECTED,
            missing=["objective", "success_criteria", "expected_behavior", "scope"],
        )

        feedback = assessor.build_feedback(ticket, validation)

        assert feedback is not None
        assert "20/100" in feedback
        assert "enough information" in feedback.lower()
        assert "## Objective" in feedback
        assert "## Success criteria" in feedback

    def test_includes_ambiguities(
        self, assessor: ClarityAssessor, ticket: TicketData,
    ) -> None:
        validation = _make_validation(
            60,
            ValidationStatus.NEEDS_CLARIFICATION,
            ambiguities=["Bug report without reproduction steps"],
        )

        feedback = assessor.build_feedback(ticket, validation)

        assert feedback is not None
        assert "Bug report without reproduction steps" in feedback

    def test_empty_missing_and_questions(
        self, assessor: ClarityAssessor, ticket: TicketData,
    ) -> None:
        validation = _make_validation(60, ValidationStatus.NEEDS_CLARIFICATION)

        feedback = assessor.build_feedback(ticket, validation)

        assert feedback is not None
        assert "Missing information" not in feedback
        assert "Questions" not in feedback
