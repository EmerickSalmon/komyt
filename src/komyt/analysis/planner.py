"""Development plan generation from validated ticket contracts."""

from __future__ import annotations

import json
import logging
import re
import uuid

from komyt.analysis.contract import LLMClient
from komyt.core.models import (
    Complexity,
    DevelopmentPlan,
    DevStep,
    TicketContract,
    TicketData,
    TicketType,
)

logger = logging.getLogger(__name__)

PLANNING_PROMPT = """\
You are a senior software engineer. Given the following ticket and contract, \
produce a step-by-step development plan.

Ticket title: {title}
Objective: {objective}
Type: {ticket_type}
Complexity: {complexity}
Success criteria:
{criteria}

Expected behavior: {expected_behavior}
Technical constraints: {constraints}

Respond with ONLY a JSON object (no markdown fences):
{{
  "steps": [
    {{
      "description": "short description of the step",
      "prompt": "detailed prompt for the coding agent",
      "files_involved": ["file paths"]
    }}
  ],
  "files_to_modify": ["existing files to change"],
  "files_to_create": ["new files to create"],
  "tests_to_write": ["test files to create or update"],
  "documentation_updates": ["doc files to update"]
}}
"""


class DevPlanner:
    """Generates a DevelopmentPlan from a ticket and its extracted contract."""

    def __init__(self, llm: LLMClient) -> None:
        self._llm = llm

    async def plan(self, ticket: TicketData, contract: TicketContract) -> DevelopmentPlan:
        criteria_text = "\n".join(f"- {c}" for c in contract.success_criteria) or "(none)"
        constraints_text = (
            "\n".join(f"- {c}" for c in contract.technical_constraints) or "(none)"
        )

        prompt = PLANNING_PROMPT.format(
            title=ticket.title,
            objective=contract.objective,
            ticket_type=contract.ticket_type.value,
            complexity=contract.estimated_complexity.value,
            criteria=criteria_text,
            expected_behavior=contract.expected_behavior or "(not specified)",
            constraints=constraints_text,
        )

        raw = await self._llm.complete(prompt)
        data = _parse_json(raw)

        steps = [
            DevStep(
                id=f"step-{uuid.uuid4().hex[:8]}",
                description=s.get("description", ""),
                prompt=s.get("prompt", ""),
                files_involved=s.get("files_involved", []),
            )
            for s in data.get("steps", [])
        ]

        branch_name = _generate_branch_name(ticket, contract)

        return DevelopmentPlan(
            ticket=ticket,
            contract=contract,
            steps=steps,
            estimated_complexity=contract.estimated_complexity,
            files_to_modify=data.get("files_to_modify", []),
            files_to_create=data.get("files_to_create", []),
            tests_to_write=data.get("tests_to_write", []),
            documentation_updates=data.get("documentation_updates", []),
            branch_name=branch_name,
            commit_strategy="progressive",
        )


def _parse_json(raw: str) -> dict:  # type: ignore[type-arg]
    from komyt.analysis.contract import _parse_json as _robust_parse
    return _robust_parse(raw)


def _generate_branch_name(ticket: TicketData, contract: TicketContract) -> str:
    type_map = {
        TicketType.FEATURE: "feature",
        TicketType.BUGFIX: "fix",
        TicketType.REFACTOR: "refactor",
        TicketType.DOCS: "docs",
        TicketType.CHORE: "chore",
    }
    type_slug = type_map.get(contract.ticket_type, "feature")

    slug = re.sub(r"[^a-z0-9]+", "-", ticket.title.lower()).strip("-")[:40]

    return f"komyt/{type_slug}/{slug}"
