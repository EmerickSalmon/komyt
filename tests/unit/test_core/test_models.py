"""Unit tests for core data models."""

from __future__ import annotations

import pytest

from komyt.core.models import (
    Complexity,
    ContractValidation,
    DevStep,
    Priority,
    StepStatus,
    TicketContract,
    TicketData,
    TicketType,
    ValidationStatus,
)


@pytest.mark.unit
class TestTicketData:
    def test_create_with_defaults(self) -> None:
        ticket = TicketData(
            id="1",
            source="github",
            external_id="42",
            title="Test",
            description="Test description",
        )
        assert ticket.id == "1"
        assert ticket.source == "github"
        assert ticket.priority == Priority.MEDIUM
        assert ticket.ticket_type == TicketType.FEATURE
        assert ticket.labels == []
        assert ticket.comments == []

    def test_create_with_all_fields(self, sample_ticket: TicketData) -> None:
        assert sample_ticket.title == "Add user authentication endpoint"
        assert sample_ticket.labels == ["feature", "backend"]
        assert sample_ticket.priority == Priority.HIGH


@pytest.mark.unit
class TestTicketContract:
    def test_empty_contract(self) -> None:
        contract = TicketContract()
        assert contract.objective == ""
        assert contract.success_criteria == []
        assert contract.estimated_complexity == Complexity.MODERATE

    def test_complete_contract(self, complete_contract: TicketContract) -> None:
        assert complete_contract.objective != ""
        assert len(complete_contract.success_criteria) > 0
        assert complete_contract.ticket_type == TicketType.FEATURE


@pytest.mark.unit
class TestContractValidation:
    def test_ready_validation(self, complete_contract: TicketContract) -> None:
        validation = ContractValidation(
            score=85,
            status=ValidationStatus.READY,
            extracted_contract=complete_contract,
            filled_fields=["objective", "ticket_type", "success_criteria"],
            confidence=0.9,
        )
        assert validation.status == ValidationStatus.READY
        assert validation.score >= 80

    def test_needs_clarification(self) -> None:
        validation = ContractValidation(
            score=55,
            status=ValidationStatus.NEEDS_CLARIFICATION,
            extracted_contract=TicketContract(),
            missing_fields=["expected_behavior", "scope"],
            questions=["What behavior do you expect?"],
            confidence=0.4,
        )
        assert validation.status == ValidationStatus.NEEDS_CLARIFICATION
        assert len(validation.questions) > 0


@pytest.mark.unit
class TestDevStep:
    def test_default_values(self) -> None:
        step = DevStep(id="1", description="Test step")
        assert step.status == StepStatus.PENDING
        assert step.attempt_count == 0
        assert step.max_attempts == 5

    def test_error_accumulation(self) -> None:
        step = DevStep(id="1", description="Test step")
        step.error_log.append("Error 1")
        step.error_log.append("Error 2")
        step.attempt_count = 2
        assert len(step.error_log) == 2
        assert step.attempt_count == 2
