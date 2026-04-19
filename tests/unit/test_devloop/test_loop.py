"""Unit tests for the development loop."""

from __future__ import annotations

from pathlib import Path

import git
import pytest

from komyt.core.models import (
    DevEnvironment,
    DevelopmentPlan,
    DevStep,
    StepStatus,
    TicketContract,
    TicketData,
    TicketType,
)
from komyt.devloop.loop import DevelopmentLoop, LoopResult
from komyt.devloop.opencode import CompletionResult, OpenCodeClient, TokenBudgetExceeded
from komyt.devloop.testing import TestReport, TestRunner
from komyt.environment.docker import DockerManager, ExecResult
from komyt.environment.git_ops import GitOperations


class FakeBackend:
    def __init__(self, tokens_per_call: int = 100) -> None:
        self._tokens = tokens_per_call

    async def create_session(
        self, working_dir: str, model: str, container_id: str = "",
    ) -> str:
        return "sess-001"

    async def send_message(self, session_id: str, message: str) -> CompletionResult:
        return CompletionResult(
            text="done", input_tokens=self._tokens, output_tokens=self._tokens,
        )

    async def close_session(self, session_id: str) -> None:
        pass


class FakeDockerManager:
    def __init__(self, test_passes: bool = True, lint_passes: bool = True) -> None:
        self._test_passes = test_passes
        self._lint_passes = lint_passes

    def exec_command(
        self, container_id: str, command: str, working_dir: str | None = None,
    ) -> ExecResult:
        if "test" in command.lower() or "pytest" in command.lower():
            if self._test_passes:
                return ExecResult(exit_code=0, stdout="5 passed in 0.5s", stderr="")
            return ExecResult(exit_code=1, stdout="2 passed, 1 failed in 0.5s", stderr="")
        if "lint" in command.lower() or "ruff" in command.lower():
            if self._lint_passes:
                return ExecResult(exit_code=0, stdout="All checks passed", stderr="")
            return ExecResult(exit_code=1, stdout="", stderr="error: unused import")
        return ExecResult(exit_code=0, stdout="ok", stderr="")


def _make_env() -> DevEnvironment:
    return DevEnvironment(
        container_id="ctr-001",
        repo_path="/workspace",
        branch_name="komyt/feature/test",
        language="python",
        test_command="pytest",
        lint_command="ruff check .",
    )


def _make_plan(steps: int = 2) -> DevelopmentPlan:
    ticket = TicketData(
        id="t1", source="github", external_id="1",
        title="Test", description="test",
    )
    contract = TicketContract(
        objective="Test feature", ticket_type=TicketType.FEATURE,
        success_criteria=["It works"],
    )
    return DevelopmentPlan(
        ticket=ticket, contract=contract,
        steps=[
            DevStep(id=f"s{i}", description=f"Step {i}", max_attempts=3)
            for i in range(1, steps + 1)
        ],
        branch_name="komyt/feature/test",
    )


def _make_git_ops(tmp_path: Path) -> GitOperations:
    repo = git.Repo.init(tmp_path)
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@test.com").release()
    (tmp_path / "README.md").write_text("# Test\n")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")
    return GitOperations(tmp_path)


@pytest.mark.unit
class TestDevelopmentLoop:
    async def test_all_steps_pass(self, tmp_path: Path) -> None:
        docker = FakeDockerManager(test_passes=True, lint_passes=True)
        git_ops = _make_git_ops(tmp_path)
        test_runner = TestRunner(docker=docker)  # type: ignore[arg-type]
        backend = FakeBackend()
        opencode = OpenCodeClient(backend=backend, max_tokens=100_000)
        await opencode.start_session("/workspace")

        # Create files so commits have content
        (tmp_path / "step1.py").write_text("# step 1")
        git_ops.commit("pre-step1")
        (tmp_path / "step2.py").write_text("# step 2")

        loop = DevelopmentLoop(
            opencode=opencode, docker=docker, git_ops=git_ops, test_runner=test_runner,  # type: ignore[arg-type]
        )

        result = await loop.run(_make_plan(steps=2), _make_env())

        assert result.all_succeeded
        assert result.completed_count == 2
        assert result.failed_count == 0
        assert result.total_tokens > 0

    async def test_step_failure_retries(self, tmp_path: Path) -> None:
        docker = FakeDockerManager(test_passes=False)
        git_ops = _make_git_ops(tmp_path)
        test_runner = TestRunner(docker=docker)  # type: ignore[arg-type]
        backend = FakeBackend()
        opencode = OpenCodeClient(backend=backend, max_tokens=100_000)
        await opencode.start_session("/workspace")

        loop = DevelopmentLoop(
            opencode=opencode, docker=docker, git_ops=git_ops, test_runner=test_runner,  # type: ignore[arg-type]
        )

        plan = _make_plan(steps=1)
        result = await loop.run(plan, _make_env())

        assert result.failed_count == 1
        assert result.steps[0].attempt == 3  # max_attempts

    async def test_failed_step_commits_wip_and_continues(self, tmp_path: Path) -> None:
        docker = FakeDockerManager(test_passes=False)
        git_ops = _make_git_ops(tmp_path)
        test_runner = TestRunner(docker=docker)  # type: ignore[arg-type]
        backend = FakeBackend()
        opencode = OpenCodeClient(backend=backend, max_tokens=100_000)
        await opencode.start_session("/workspace")

        (tmp_path / "attempt.py").write_text("# broken attempt\n")

        loop = DevelopmentLoop(
            opencode=opencode, docker=docker, git_ops=git_ops, test_runner=test_runner,  # type: ignore[arg-type]
            stop_on_step_failure=False,
        )

        plan = _make_plan(steps=2)
        result = await loop.run(plan, _make_env())

        assert not result.aborted
        assert result.failed_count == 2
        assert result.steps[0].commit_sha, "WIP commit should be created on failure"
        log = git_ops.get_log(max_count=5)
        assert any("WIP" in line or "wip" in line for line in log)

    async def test_token_budget_abort(self, tmp_path: Path) -> None:
        docker = FakeDockerManager(test_passes=True)
        git_ops = _make_git_ops(tmp_path)
        test_runner = TestRunner(docker=docker)  # type: ignore[arg-type]
        backend = FakeBackend(tokens_per_call=300)
        opencode = OpenCodeClient(backend=backend, max_tokens=500)
        await opencode.start_session("/workspace")

        (tmp_path / "s.py").write_text("# s")

        loop = DevelopmentLoop(
            opencode=opencode, docker=docker, git_ops=git_ops, test_runner=test_runner,  # type: ignore[arg-type]
        )

        result = await loop.run(_make_plan(steps=3), _make_env())

        assert result.aborted
        assert "budget" in result.abort_reason.lower()


@pytest.mark.unit
class TestLoopResult:
    def test_all_succeeded(self) -> None:
        from komyt.core.models import StepResult
        r = LoopResult(steps=[
            StepResult(status=StepStatus.SUCCESS),
            StepResult(status=StepStatus.SUCCESS),
        ])
        assert r.all_succeeded

    def test_not_all_succeeded(self) -> None:
        from komyt.core.models import StepResult
        r = LoopResult(steps=[
            StepResult(status=StepStatus.SUCCESS),
            StepResult(status=StepStatus.FAILED),
        ])
        assert not r.all_succeeded
        assert r.completed_count == 1
        assert r.failed_count == 1
