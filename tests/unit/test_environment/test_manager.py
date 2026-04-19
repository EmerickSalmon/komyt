"""Unit tests for the environment manager."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import git
import pytest

from komyt.core.config import DockerConfig
from komyt.core.models import DevelopmentPlan, DevStep, TicketContract, TicketData, TicketType
from komyt.environment.docker import ExecResult
from komyt.environment.manager import EnvironmentManager, _find_agent_instructions


class FakeDockerClient:
    def __init__(self) -> None:
        self.containers: dict[str, bool] = {}
        self._next_id = 0
        self.exec_history: list[tuple[str, str]] = []

    def create_container(self, **kwargs) -> str:  # type: ignore[no-untyped-def]
        self._next_id += 1
        cid = f"ctr-{self._next_id:04d}"
        self.containers[cid] = False
        return cid

    def start_container(self, container_id: str) -> None:
        self.containers[container_id] = True

    def stop_container(self, container_id: str, timeout: int = 10) -> None:
        self.containers[container_id] = False

    def remove_container(self, container_id: str, force: bool = False) -> None:
        self.containers.pop(container_id, None)

    def exec_in_container(
        self, container_id: str, command: str, working_dir: str | None = None,
    ) -> ExecResult:
        self.exec_history.append((container_id, command))
        return ExecResult(exit_code=0, stdout="ok", stderr="")

    def container_exists(self, container_id: str) -> bool:
        return container_id in self.containers

    def pull_image(self, image: str) -> None:
        pass


def _make_plan(tmp_path: Path) -> DevelopmentPlan:
    ticket = TicketData(
        id="t1", source="github", external_id="1",
        title="Test feature", description="Test",
        repo_url=str(tmp_path), repo_branch="master",
    )
    contract = TicketContract(
        objective="Test", ticket_type=TicketType.FEATURE,
        success_criteria=["It works"],
    )
    return DevelopmentPlan(
        ticket=ticket, contract=contract,
        steps=[DevStep(id="s1", description="Do it")],
        branch_name="komyt/feature/test",
    )


def _init_bare_repo(path: Path) -> None:
    """Create a minimal git repo to clone from."""
    repo = git.Repo.init(path)
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@test.com").release()
    (path / "README.md").write_text("# Test\n")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")


@pytest.mark.unit
class TestFindAgentInstructions:
    def test_finds_agents_md(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("# Agent instructions\nDo this.")
        result = _find_agent_instructions(tmp_path)
        assert result is not None
        assert "Agent instructions" in result

    def test_finds_claude_md(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("# Claude conventions")
        result = _find_agent_instructions(tmp_path)
        assert result is not None
        assert "Claude conventions" in result

    def test_priority_agents_over_claude(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("agents")
        (tmp_path / "CLAUDE.md").write_text("claude")
        result = _find_agent_instructions(tmp_path)
        assert result == "agents"

    def test_returns_none_when_absent(self, tmp_path: Path) -> None:
        assert _find_agent_instructions(tmp_path) is None

    def test_skips_empty_files(self, tmp_path: Path) -> None:
        (tmp_path / "AGENTS.md").write_text("")
        (tmp_path / "CLAUDE.md").write_text("real content")
        result = _find_agent_instructions(tmp_path)
        assert result == "real content"


@pytest.mark.unit
class TestEnvironmentManager:
    async def test_setup_creates_environment(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        source.mkdir()
        _init_bare_repo(source)
        (source / "pyproject.toml").write_text('[tool.ruff]\nline-length=100')
        repo = git.Repo(source)
        repo.index.add(["pyproject.toml"])
        repo.index.commit("Add pyproject")

        clone_target = tmp_path / "clone"
        plan = _make_plan(source)

        client = FakeDockerClient()
        mgr = EnvironmentManager(docker_config=DockerConfig(), docker_client=client)

        env = await mgr.setup(plan, clone_target)

        assert env.container_id.startswith("ctr-")
        assert env.branch_name == "komyt/feature/test"
        assert env.language == "python"
        assert env.lint_command == "ruff check ."
        assert str(clone_target) in env.repo_path
        ran_commands = " ".join(cmd for _, cmd in client.exec_history)
        assert "ruff" in ran_commands
        assert "pytest" in ran_commands

    async def test_setup_detects_agent_instructions(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        source.mkdir()
        _init_bare_repo(source)
        (source / "AGENTS.md").write_text("# Instructions for AI agents")
        repo = git.Repo(source)
        repo.index.add(["AGENTS.md"])
        repo.index.commit("Add AGENTS.md")

        clone_target = tmp_path / "clone"
        plan = _make_plan(source)

        client = FakeDockerClient()
        mgr = EnvironmentManager(docker_config=DockerConfig(), docker_client=client)

        env = await mgr.setup(plan, clone_target)

        assert env.agent_instructions is not None
        assert "Instructions for AI agents" in env.agent_instructions

    def test_teardown_cleans_up(self) -> None:
        client = FakeDockerClient()
        mgr = EnvironmentManager(docker_config=DockerConfig(), docker_client=client)

        cid = client.create_container(image="test")
        client.start_container(cid)

        from komyt.core.models import DevEnvironment
        env = DevEnvironment(container_id=cid, repo_path="/tmp/test")
        mgr.teardown(env)

        assert cid not in client.containers

    def test_exec_in_environment(self) -> None:
        client = FakeDockerClient()
        mgr = EnvironmentManager(docker_config=DockerConfig(), docker_client=client)

        from komyt.core.models import DevEnvironment
        env = DevEnvironment(container_id="ctr-0001", repo_path="/workspace")
        client.containers["ctr-0001"] = True

        result = mgr.exec_in_environment(env, "pytest")
        assert result.success
