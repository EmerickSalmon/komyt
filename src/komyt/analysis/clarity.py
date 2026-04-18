"""Ticket clarity assessment and feedback comment generation."""

from __future__ import annotations

import logging

from komyt.core.models import ContractValidation, TicketData, ValidationStatus

logger = logging.getLogger(__name__)


class ClarityAssessor:
    """Generates human-readable feedback for ticket authors based on validation results."""

    def build_feedback(self, ticket: TicketData, validation: ContractValidation) -> str | None:
        """Build a feedback comment to post on the ticket.

        Returns None if the ticket is ready (no feedback needed).
        """
        if validation.status == ValidationStatus.READY:
            return None

        parts: list[str] = []

        if validation.status == ValidationStatus.NEEDS_CLARIFICATION:
            parts.append(
                f"**Komyt Analysis** — Score: {validation.score}/100 "
                f"(threshold: 80)\n\n"
                f"This ticket needs a bit more detail before I can start working on it."
            )
        else:
            parts.append(
                f"**Komyt Analysis** — Score: {validation.score}/100\n\n"
                f"This ticket doesn't have enough information for automated implementation."
            )

        if validation.missing_fields:
            parts.append("\n**Missing information:**")
            for field in validation.missing_fields:
                parts.append(f"- {_field_label(field)}")

        if validation.ambiguities:
            parts.append("\n**Ambiguities:**")
            for amb in validation.ambiguities:
                parts.append(f"- {amb}")

        if validation.questions:
            parts.append("\n**Questions:**")
            for i, q in enumerate(validation.questions, 1):
                parts.append(f"{i}. {q}")

        if validation.status == ValidationStatus.NEEDS_CLARIFICATION:
            parts.append(
                "\nPlease update the ticket or reply with answers, "
                "then mention `@komyt` again to retry."
            )
        else:
            parts.append(_rejection_template())

        return "\n".join(parts)


def _field_label(field: str) -> str:
    labels = {
        "objective": "Clear objective / goal",
        "success_criteria": "Measurable success criteria",
        "expected_behavior": "Expected behavior after implementation",
        "scope": "Scope definition (in / out of scope)",
        "reproduction_steps": "Steps to reproduce the bug",
    }
    return labels.get(field, field.replace("_", " ").title())


def _rejection_template() -> str:
    return (
        "\n---\n"
        "**Suggested ticket template:**\n\n"
        "```\n"
        "## Objective\n"
        "What needs to be done and why.\n\n"
        "## Expected behavior\n"
        "Describe the desired outcome.\n\n"
        "## Success criteria\n"
        "- [ ] Criterion 1\n"
        "- [ ] Criterion 2\n\n"
        "## Scope\n"
        "- In scope: ...\n"
        "- Out of scope: ...\n"
        "```\n"
        "\nOnce updated, mention `@komyt` to retry."
    )
