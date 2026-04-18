"""Unit tests for git operations."""

from __future__ import annotations

from pathlib import Path

import git
import pytest

from komyt.environment.git_ops import GitOperations


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create a minimal git repo for testing."""
    repo = git.Repo.init(tmp_path)
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@test.com").release()

    (tmp_path / "README.md").write_text("# Test repo\n")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")
    return tmp_path


@pytest.mark.unit
class TestGitOperations:
    def test_open_existing_repo(self, git_repo: Path) -> None:
        ops = GitOperations(git_repo)
        assert ops.repo is not None
        assert ops.current_branch() == "master"

    def test_create_branch(self, git_repo: Path) -> None:
        ops = GitOperations(git_repo)
        ops.create_branch("komyt/feature/test")
        assert ops.current_branch() == "komyt/feature/test"

    def test_create_branch_idempotent(self, git_repo: Path) -> None:
        ops = GitOperations(git_repo)
        ops.create_branch("komyt/feature/test")
        ops.create_branch("komyt/feature/test")
        assert ops.current_branch() == "komyt/feature/test"

    def test_commit(self, git_repo: Path) -> None:
        ops = GitOperations(git_repo)
        (git_repo / "new_file.py").write_text("print('hello')\n")

        sha = ops.commit("Add new file")

        assert sha is not None
        assert len(sha) == 40
        assert ops.repo.head.commit.message == "Add new file"

    def test_commit_nothing_returns_none(self, git_repo: Path) -> None:
        ops = GitOperations(git_repo)
        sha = ops.commit("Empty commit")
        assert sha is None

    def test_has_changes(self, git_repo: Path) -> None:
        ops = GitOperations(git_repo)
        assert ops.has_changes() is False

        (git_repo / "new.txt").write_text("content")
        assert ops.has_changes() is True

    def test_get_log(self, git_repo: Path) -> None:
        ops = GitOperations(git_repo)
        log = ops.get_log()
        assert len(log) == 1
        assert "Initial commit" in log[0]

    def test_get_log_multiple_commits(self, git_repo: Path) -> None:
        ops = GitOperations(git_repo)
        (git_repo / "a.txt").write_text("a")
        ops.commit("Second commit")
        (git_repo / "b.txt").write_text("b")
        ops.commit("Third commit")

        log = ops.get_log()
        assert len(log) == 3

    def test_read_file(self, git_repo: Path) -> None:
        ops = GitOperations(git_repo)
        content = ops.read_file("README.md")
        assert content == "# Test repo\n"

    def test_read_file_missing(self, git_repo: Path) -> None:
        ops = GitOperations(git_repo)
        assert ops.read_file("nonexistent.txt") is None

    def test_get_diff_summary(self, git_repo: Path) -> None:
        ops = GitOperations(git_repo)
        (git_repo / "README.md").write_text("# Updated\n")
        diff = ops.get_diff_summary()
        assert "README.md" in diff
