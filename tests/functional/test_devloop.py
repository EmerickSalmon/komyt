"""Functional tests for the dev loop — end-to-end with fake OpenCode backend."""

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
from komyt.devloop.loop import DevelopmentLoop
from komyt.devloop.opencode import CompletionResult, OpenCodeClient
from komyt.devloop.testing import TestRunner
from komyt.environment.docker import ExecResult


class FakeBackend:
    def __init__(self) -> None:
        self.prompts: list[str] = []

    async def create_session(self, working_dir: str, model: str) -> str:
        return "func-session"

    async def send_message(self, session_id: str, message: str) -> CompletionResult:
        self.prompts.append(message)
        return CompletionResult(text="implemented", input_tokens=50, output_tokens=50)

    async def close_session(self, session_id: str) -> None:
        pass


class SimulatedDocker:
    """Simulates Docker exec — creates files to simulate code generation."""

    def __init__(self, repo_path: Path, pass_tests: bool = True) -> None:
        self._repo = repo_path
        self._pass_tests = pass_tests
        self._call_count = 0

    def exec_command(
        self, container_id: str, command: str, working_dir: str | None = None,
    ) -> ExecResult:
        self._call_count += 1

        if "pytest" in command or "test" in command:
            if self._pass_tests:
                return ExecResult(exit_code=0, stdout="3 passed in 0.2s", stderr="")
            return ExecResult(exit_code=1, stdout="1 passed, 1 failed in 0.3s", stderr="")

        if "ruff" in command or "lint" in command:
            return ExecResult(exit_code=0, stdout="All checks passed", stderr="")

        return ExecResult(exit_code=0, stdout="ok", stderr="")


def _init_repo(path: Path) -> git.Repo:
    repo = git.Repo.init(path)
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@test.com").release()
    (path / "README.md").write_text("# Project\n")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")
    return repo


@pytest.mark.functional
class TestDevLoopPipeline:
    async def test_successful_two_step_loop(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        repo = _init_repo(repo_path)

        ticket = TicketData(
            id="func-1", source="github", external_id="42",
            title="Add auth endpoint", description="@komyt implement JWT auth",
            repo_url=str(repo_path),
        )
        contract = TicketContract(
            objective="Add JWT auth", ticket_type=TicketType.FEATURE,
            success_criteria=["POST /auth/login works", "Tests pass"],
        )
        plan = DevelopmentPlan(
            ticket=ticket, contract=contract,
            steps=[
                DevStep(id="s1", description="Create auth module",
                        prompt="Create src/auth.py", files_involved=["src/auth.py"]),
                DevStep(id="s2", description="Write tests",
                        prompt="Write tests", files_involved=["tests/test_auth.py"]),
            ],
            branch_name="komyt/feature/auth",
        )
        env = DevEnvironment(
            container_id="ctr-func",
            repo_path=str(repo_path),
            branch_name="komyt/feature/auth",
            language="python",
            framework="fastapi",
            test_command="pytest",
            lint_command="ruff check .",
        )

        backend = FakeBackend()
        opencode = OpenCodeClient(backend=backend, max_tokens=100_000)
        await opencode.start_session(str(repo_path))

        docker = SimulatedDocker(repo_path, pass_tests=True)
        test_runner = TestRunner(docker=docker)  # type: ignore[arg-type]

        from komyt.environment.git_ops import GitOperations
        git_ops = GitOperations(repo_path)
        git_ops.create_branch("komyt/feature/auth")

        # Simulate file creation for each step
        (repo_path / "src").mkdir(exist_ok=True)
        (repo_path / "src" / "auth.py").write_text("def login(): pass\n")

        loop = DevelopmentLoop(
            opencode=opencode, docker=docker, git_ops=git_ops, test_runner=test_runner,  # type: ignore[arg-type]
        )
        result = await loop.run(plan, env)

        assert result.completed_count >= 1
        assert result.total_tokens > 0
        assert len(backend.prompts) >= 2

        # Verify prompts contain context
        assert "auth" in backend.prompts[0].lower()
        assert "JWT" in backend.prompts[0] or "jwt" in backend.prompts[0].lower()

    async def test_failing_tests_trigger_retries(self, tmp_path: Path) -> None:
        repo_path = tmp_path / "repo"
        repo_path.mkdir()
        _init_repo(repo_path)

        plan = DevelopmentPlan(
            ticket=TicketData(
                id="func-2", source="github", external_id="43",
                title="Fix bug", description="@komyt fix it",
            ),
            contract=TicketContract(
                objective="Fix bug", ticket_type=TicketType.BUGFIX,
            ),
            steps=[DevStep(id="s1", description="Fix the bug", max_attempts=2)],
            branch_name="komyt/fix/bug",
        )
        env = DevEnvironment(
            container_id="ctr-func2",
            repo_path=str(repo_path),
            branch_name="komyt/fix/bug",
            language="python",
            test_command="pytest",
        )

        backend = FakeBackend()
        opencode = OpenCodeClient(backend=backend, max_tokens=100_000)
        await opencode.start_session(str(repo_path))

        docker = SimulatedDocker(repo_path, pass_tests=False)
        test_runner = TestRunner(docker=docker)  # type: ignore[arg-type]
        from komyt.environment.git_ops import GitOperations
        git_ops = GitOperations(repo_path)

        loop = DevelopmentLoop(
            opencode=opencode, docker=docker, git_ops=git_ops, test_runner=test_runner,  # type: ignore[arg-type]
        )
        result = await loop.run(plan, env)

        assert result.failed_count == 1
        assert result.steps[0].attempt == 2
        # Second prompt should be a retry with error context
        assert len(backend.prompts) == 2
        assert "retry" in backend.prompts[1].lower() or "failed" in backend.prompts[1].lower()
