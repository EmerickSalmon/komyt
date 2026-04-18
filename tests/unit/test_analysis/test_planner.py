"""Unit tests for development plan generation."""

from __future__ import annotations

import json

import pytest

from komyt.analysis.planner import DevPlanner, _generate_branch_name, _parse_json
from komyt.core.models import (
    Complexity,
    DevelopmentPlan,
    TicketContract,
    TicketData,
    TicketType,
)


class FakeLLM:
    def __init__(self, response: str) -> None:
        self.response = response
        self.last_prompt: str | None = None

    async def complete(self, prompt: str) -> str:
        self.last_prompt = prompt
        return self.response


def _plan_response() -> dict:
    return {
        "steps": [
            {
                "description": "Create auth module",
                "prompt": "Create src/auth.py with login endpoint...",
                "files_involved": ["src/auth.py"],
            },
            {
                "description": "Write tests",
                "prompt": "Write unit tests for auth...",
                "files_involved": ["tests/test_auth.py"],
            },
        ],
        "files_to_modify": ["src/app.py"],
        "files_to_create": ["src/auth.py", "tests/test_auth.py"],
        "tests_to_write": ["tests/test_auth.py"],
        "documentation_updates": ["README.md"],
    }


@pytest.mark.unit
class TestDevPlanner:
    async def test_generates_plan(
        self, sample_ticket: TicketData, complete_contract: TicketContract,
    ) -> None:
        llm = FakeLLM(json.dumps(_plan_response()))
        planner = DevPlanner(llm=llm)

        plan = await planner.plan(sample_ticket, complete_contract)

        assert isinstance(plan, DevelopmentPlan)
        assert len(plan.steps) == 2
        assert plan.steps[0].description == "Create auth module"
        assert plan.steps[0].files_involved == ["src/auth.py"]
        assert plan.steps[1].description == "Write tests"
        assert plan.files_to_modify == ["src/app.py"]
        assert plan.files_to_create == ["src/auth.py", "tests/test_auth.py"]
        assert plan.tests_to_write == ["tests/test_auth.py"]
        assert plan.documentation_updates == ["README.md"]
        assert plan.commit_strategy == "progressive"
        assert plan.ticket is sample_ticket
        assert plan.contract is complete_contract

    async def test_step_ids_are_unique(
        self, sample_ticket: TicketData, complete_contract: TicketContract,
    ) -> None:
        llm = FakeLLM(json.dumps(_plan_response()))
        planner = DevPlanner(llm=llm)

        plan = await planner.plan(sample_ticket, complete_contract)

        ids = [s.id for s in plan.steps]
        assert len(ids) == len(set(ids))

    async def test_includes_contract_info_in_prompt(
        self, sample_ticket: TicketData, complete_contract: TicketContract,
    ) -> None:
        llm = FakeLLM(json.dumps(_plan_response()))
        planner = DevPlanner(llm=llm)

        await planner.plan(sample_ticket, complete_contract)

        assert llm.last_prompt is not None
        assert complete_contract.objective in llm.last_prompt
        assert sample_ticket.title in llm.last_prompt

    async def test_empty_steps(
        self, sample_ticket: TicketData, complete_contract: TicketContract,
    ) -> None:
        llm = FakeLLM(json.dumps({"steps": [], "files_to_modify": [], "files_to_create": [], "tests_to_write": [], "documentation_updates": []}))
        planner = DevPlanner(llm=llm)

        plan = await planner.plan(sample_ticket, complete_contract)

        assert plan.steps == []


@pytest.mark.unit
class TestGenerateBranchName:
    def test_feature_branch(self) -> None:
        ticket = TicketData(
            id="1", source="github", external_id="1",
            title="Add user authentication endpoint", description="",
        )
        contract = TicketContract(ticket_type=TicketType.FEATURE)
        name = _generate_branch_name(ticket, contract)
        assert name.startswith("komyt/feature/")
        assert "add-user-authentication" in name

    def test_bugfix_branch(self) -> None:
        ticket = TicketData(
            id="1", source="github", external_id="1",
            title="Fix login crash", description="",
        )
        contract = TicketContract(ticket_type=TicketType.BUGFIX)
        name = _generate_branch_name(ticket, contract)
        assert name.startswith("komyt/fix/")

    def test_truncates_long_titles(self) -> None:
        ticket = TicketData(
            id="1", source="github", external_id="1",
            title="A" * 100, description="",
        )
        contract = TicketContract(ticket_type=TicketType.FEATURE)
        name = _generate_branch_name(ticket, contract)
        slug = name.split("/", 2)[2]
        assert len(slug) <= 40

    def test_handles_special_characters(self) -> None:
        ticket = TicketData(
            id="1", source="github", external_id="1",
            title="Fix: crash on @mention (urgent!)", description="",
        )
        contract = TicketContract(ticket_type=TicketType.BUGFIX)
        name = _generate_branch_name(ticket, contract)
        assert " " not in name
        assert "@" not in name
        assert "(" not in name
