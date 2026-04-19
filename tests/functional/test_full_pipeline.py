"""Functional tests for the full pipeline orchestration (with mocked externals)."""

from __future__ import annotations

import json
from pathlib import Path

import git
import pytest

from komyt.adapters.git.base import PRData, PRResult
from komyt.core.config import KomytConfig
from komyt.core.models import CommentData, StepStatus, TaskStatus, TicketData
from komyt.core.orchestrator import Orchestrator
from komyt.devloop.opencode import CompletionResult
from komyt.environment.docker import ExecResult


class FakeTicketAdapter:
    def __init__(self, tickets: list[TicketData]) -> None:
        self.tickets = tickets
        self.comments_posted: list[tuple[str, str]] = []
        self.labels_set: list[tuple[str, list[str]]] = []

    async def fetch_tickets(self, filters):  # type: ignore[no-untyped-def]
        return self.tickets

    async def fetch_comments(self, ticket_id: str) -> list[CommentData]:
        return []

    async def update_ticket(self, ticket_id: str, update) -> None:  # type: ignore[no-untyped-def]
        pass

    async def add_comment(self, ticket_id: str, comment: str) -> None:
        self.comments_posted.append((ticket_id, comment))

    async def set_labels(self, ticket_id: str, labels: list[str]) -> None:
        self.labels_set.append((ticket_id, labels))


class FakeGitPlatform:
    def __init__(self) -> None:
        self.prs: list[tuple[str, PRData]] = []

    async def create_pr(self, repo: str, pr: PRData) -> PRResult:
        self.prs.append((repo, pr))
        return PRResult(url=f"https://github.com/{repo}/pull/1", number=1)

    async def add_pr_comment(self, repo: str, pr_number: int, comment: str) -> None:
        pass

    async def add_pr_labels(self, repo: str, pr_number: int, labels: list[str]) -> None:
        pass


class FakeDockerClient:
    def __init__(self) -> None:
        self.containers: dict[str, bool] = {}
        self._next_id = 0

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
        return ExecResult(exit_code=0, stdout="5 passed in 0.5s", stderr="")

    def container_exists(self, container_id: str) -> bool:
        return container_id in self.containers

    def pull_image(self, image: str) -> None:
        pass


class FakeOpenCodeBackend:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def create_session(
        self, working_dir: str, model: str, container_id: str = "",
    ) -> str:
        return "session-func"

    async def send_message(self, session_id: str, message: str) -> CompletionResult:
        self.calls.append(message)
        return CompletionResult(text="done", input_tokens=100, output_tokens=100)

    async def close_session(self, session_id: str) -> None:
        pass


class FakeLLMClient:
    def __init__(self) -> None:
        self._call_count = 0

    async def complete(self, prompt: str) -> str:
        self._call_count += 1
        if self._call_count == 1:
            return json.dumps({
                "objective": "Add auth endpoint",
                "ticket_type": "feature",
                "success_criteria": ["Login works", "Tests pass"],
                "expected_behavior": "JWT auth works",
                "scope_included": ["auth"],
                "scope_excluded": [],
                "reproduction_steps": None,
                "affected_files": ["src/auth.py"],
                "technical_constraints": [],
                "dependencies": [],
                "references": [],
                "priority": "high",
                "estimated_complexity": "moderate",
            })
        return json.dumps({
            "steps": [{"description": "Implement auth", "prompt": "Do it", "files_involved": ["src/auth.py"]}],
            "files_to_modify": [],
            "files_to_create": ["src/auth.py"],
            "tests_to_write": ["tests/test_auth.py"],
            "documentation_updates": [],
        })


def _create_source_repo(path: Path) -> None:
    repo = git.Repo.init(path)
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@test.com").release()
    (path / "pyproject.toml").write_text('[tool.ruff]\nline-length=100')
    (path / "README.md").write_text("# Test\n")
    repo.index.add(["pyproject.toml", "README.md"])
    repo.index.commit("Initial commit")


@pytest.mark.functional
class TestFullPipeline:
    async def test_vague_ticket_posts_feedback(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        source.mkdir()
        _create_source_repo(source)

        ticket = TicketData(
            id="t1", source="github", external_id="10",
            title="Fix bug", description="@komyt it's broken",
            repo_url=str(source), repo_branch="master",
        )

        class VagueLLM:
            async def complete(self, prompt: str) -> str:
                return json.dumps({
                    "objective": "", "ticket_type": "bugfix",
                    "success_criteria": [], "expected_behavior": None,
                    "scope_included": [], "scope_excluded": [],
                    "reproduction_steps": None, "affected_files": [],
                    "technical_constraints": [], "dependencies": [],
                    "references": [], "priority": "medium",
                    "estimated_complexity": "moderate",
                })

        adapter = FakeTicketAdapter([ticket])
        orch = Orchestrator(
            config=KomytConfig(),
            ticket_adapter=adapter,
            git_platform=FakeGitPlatform(),
            docker_client=FakeDockerClient(),
            opencode_backend=FakeOpenCodeBackend(),
            llm_client=VagueLLM(),
        )

        result = await orch.process_ticket(ticket)

        assert result.status == TaskStatus.WAITING_CLARIFICATION
        assert len(adapter.comments_posted) == 1
        assert "Komyt Analysis" in adapter.comments_posted[0][1]
