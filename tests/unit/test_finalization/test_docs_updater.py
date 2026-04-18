"""Unit tests for the docs updater."""

from __future__ import annotations

from pathlib import Path

import git
import pytest

from komyt.core.models import (
    DevEnvironment,
    DevelopmentPlan,
    DevStep,
    TicketContract,
    TicketData,
    TicketType,
)
from komyt.devloop.opencode import CompletionResult, OpenCodeClient
from komyt.environment.git_ops import GitOperations
from komyt.finalization.docs_updater import DocsUpdater


class FakeBackend:
    async def create_session(self, working_dir: str, model: str) -> str:
        return "sess"

    async def send_message(self, session_id: str, message: str) -> CompletionResult:
        return CompletionResult(text="updated docs", input_tokens=50, output_tokens=50)

    async def close_session(self, session_id: str) -> None:
        pass


def _make_plan(doc_updates: list[str] | None = None) -> DevelopmentPlan:
    return DevelopmentPlan(
        ticket=TicketData(id="t1", source="github", external_id="1", title="T", description="d"),
        contract=TicketContract(objective="Test", ticket_type=TicketType.FEATURE),
        steps=[],
        branch_name="komyt/feature/test",
        documentation_updates=doc_updates or [],
    )


def _init_repo(path: Path) -> GitOperations:
    repo = git.Repo.init(path)
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@test.com").release()
    (path / "README.md").write_text("# Test\n")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")
    return GitOperations(path)


@pytest.mark.unit
class TestDocsUpdater:
    async def test_skips_when_no_doc_files(self, tmp_path: Path) -> None:
        git_ops = _init_repo(tmp_path)
        backend = FakeBackend()
        opencode = OpenCodeClient(backend=backend)
        await opencode.start_session(str(tmp_path))

        updater = DocsUpdater(opencode=opencode, git_ops=git_ops)
        result = await updater.update(_make_plan(), DevEnvironment())

        assert result is False

    async def test_commits_when_changes_exist(self, tmp_path: Path) -> None:
        git_ops = _init_repo(tmp_path)
        backend = FakeBackend()
        opencode = OpenCodeClient(backend=backend)
        await opencode.start_session(str(tmp_path))

        updater = DocsUpdater(opencode=opencode, git_ops=git_ops)

        # Simulate OpenCode generating changes
        (tmp_path / "README.md").write_text("# Updated docs\n")

        result = await updater.update(
            _make_plan(doc_updates=["README.md"]), DevEnvironment(),
        )

        assert result is True
        log = git_ops.get_log()
        assert any("docs:" in entry for entry in log)

    async def test_no_commit_when_no_changes(self, tmp_path: Path) -> None:
        git_ops = _init_repo(tmp_path)
        backend = FakeBackend()
        opencode = OpenCodeClient(backend=backend)
        await opencode.start_session(str(tmp_path))

        updater = DocsUpdater(opencode=opencode, git_ops=git_ops)
        result = await updater.update(
            _make_plan(doc_updates=["README.md"]), DevEnvironment(),
        )

        assert result is False
