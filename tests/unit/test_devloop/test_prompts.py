"""Unit tests for prompt templates."""

from __future__ import annotations

import pytest

from komyt.core.models import (
    DevEnvironment,
    DevelopmentPlan,
    DevStep,
    TicketContract,
    TicketData,
    TicketType,
)
from komyt.devloop.prompts import (
    build_commit_message,
    build_docs_update_prompt,
    build_pr_description_prompt,
    build_retry_prompt,
    build_step_prompt,
)


@pytest.fixture
def env() -> DevEnvironment:
    return DevEnvironment(
        container_id="ctr-001",
        repo_path="/workspace",
        branch_name="komyt/feature/auth",
        language="python",
        framework="fastapi",
        test_command="pytest",
        lint_command="ruff check .",
        agent_instructions="Use pytest for testing.",
    )


@pytest.fixture
def step() -> DevStep:
    return DevStep(
        id="step-1",
        description="Create auth endpoint",
        prompt="Implement POST /api/auth/login with JWT...",
        files_involved=["src/api/auth.py"],
    )


@pytest.mark.unit
class TestBuildStepPrompt:
    def test_contains_step_description(
        self, step: DevStep, sample_dev_plan: DevelopmentPlan, env: DevEnvironment,
    ) -> None:
        prompt = build_step_prompt(step, sample_dev_plan, env)
        assert "Create auth endpoint" in prompt

    def test_contains_objective(
        self, step: DevStep, sample_dev_plan: DevelopmentPlan, env: DevEnvironment,
    ) -> None:
        prompt = build_step_prompt(step, sample_dev_plan, env)
        assert sample_dev_plan.contract.objective in prompt

    def test_contains_language_and_framework(
        self, step: DevStep, sample_dev_plan: DevelopmentPlan, env: DevEnvironment,
    ) -> None:
        prompt = build_step_prompt(step, sample_dev_plan, env)
        assert "python" in prompt.lower()
        assert "fastapi" in prompt.lower()

    def test_contains_files(
        self, step: DevStep, sample_dev_plan: DevelopmentPlan, env: DevEnvironment,
    ) -> None:
        prompt = build_step_prompt(step, sample_dev_plan, env)
        assert "src/api/auth.py" in prompt

    def test_contains_test_command(
        self, step: DevStep, sample_dev_plan: DevelopmentPlan, env: DevEnvironment,
    ) -> None:
        prompt = build_step_prompt(step, sample_dev_plan, env)
        assert "`pytest`" in prompt

    def test_contains_agent_instructions(
        self, step: DevStep, sample_dev_plan: DevelopmentPlan, env: DevEnvironment,
    ) -> None:
        prompt = build_step_prompt(step, sample_dev_plan, env)
        assert "Use pytest for testing" in prompt

    def test_no_framework_when_none(
        self, step: DevStep, sample_dev_plan: DevelopmentPlan,
    ) -> None:
        env = DevEnvironment(language="go")
        prompt = build_step_prompt(step, sample_dev_plan, env)
        assert "Framework" not in prompt


@pytest.mark.unit
class TestBuildRetryPrompt:
    def test_includes_errors(
        self, step: DevStep, sample_dev_plan: DevelopmentPlan, env: DevEnvironment,
    ) -> None:
        prompt = build_retry_prompt(
            step, sample_dev_plan, env,
            errors=["AssertionError in test_login", "Lint: unused import"],
            attempt=2,
        )
        assert "AssertionError" in prompt
        assert "unused import" in prompt
        assert "attempt 2/" in prompt

    def test_includes_original_context(
        self, step: DevStep, sample_dev_plan: DevelopmentPlan, env: DevEnvironment,
    ) -> None:
        prompt = build_retry_prompt(step, sample_dev_plan, env, errors=["err"], attempt=3)
        assert "Create auth endpoint" in prompt
        assert sample_dev_plan.contract.objective in prompt


@pytest.mark.unit
class TestBuildCommitMessage:
    def test_format(self, step: DevStep, sample_dev_plan: DevelopmentPlan) -> None:
        msg = build_commit_message(step, sample_dev_plan)
        assert msg.startswith("feature:")
        assert "Create auth endpoint" in msg
        assert sample_dev_plan.ticket.external_id in msg


@pytest.mark.unit
class TestBuildPrDescriptionPrompt:
    def test_contains_objective(self, sample_dev_plan: DevelopmentPlan) -> None:
        prompt = build_pr_description_prompt(sample_dev_plan)
        assert sample_dev_plan.contract.objective in prompt

    def test_contains_steps(self, sample_dev_plan: DevelopmentPlan) -> None:
        prompt = build_pr_description_prompt(sample_dev_plan)
        for step in sample_dev_plan.steps:
            assert step.description in prompt


@pytest.mark.unit
class TestBuildDocsUpdatePrompt:
    def test_contains_files(self, sample_dev_plan: DevelopmentPlan) -> None:
        prompt = build_docs_update_prompt(sample_dev_plan, ["README.md", "docs/api.md"])
        assert "README.md" in prompt
        assert "docs/api.md" in prompt
