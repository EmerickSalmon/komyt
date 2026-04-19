"""Functional tests for environment — real git repos + stack detection."""

from __future__ import annotations

import json
from pathlib import Path

import git
import pytest

from komyt.environment.detection import detect_stack
from komyt.environment.git_ops import GitOperations


def _init_repo(path: Path, files: dict[str, str] | None = None) -> git.Repo:
    repo = git.Repo.init(path)
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@test.com").release()

    (path / "README.md").write_text("# Test\n")
    repo.index.add(["README.md"])
    for name, content in (files or {}).items():
        (path / name).write_text(content)
        repo.index.add([name])
    repo.index.commit("Initial commit")
    return repo


@pytest.mark.functional
class TestGitWorkflow:
    def test_clone_create_branch_commit_flow(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        source.mkdir()
        _init_repo(source)

        target = tmp_path / "clone"
        ops = GitOperations.clone(str(source), target, branch="master")

        ops.create_branch("komyt/feature/auth")
        assert ops.current_branch() == "komyt/feature/auth"

        (target / "auth.py").write_text("def login(): pass\n")
        sha = ops.commit("Add auth module")
        assert sha is not None

        log = ops.get_log()
        assert any("Add auth module" in entry for entry in log)
        assert any("Initial commit" in entry for entry in log)

    def test_multiple_commits_on_branch(self, tmp_path: Path) -> None:
        source = tmp_path / "source"
        source.mkdir()
        _init_repo(source)

        target = tmp_path / "clone"
        ops = GitOperations.clone(str(source), target, branch="master")
        ops.create_branch("komyt/fix/bug")

        (target / "fix1.py").write_text("# fix 1\n")
        sha1 = ops.commit("First fix")

        (target / "fix2.py").write_text("# fix 2\n")
        sha2 = ops.commit("Second fix")

        assert sha1 != sha2
        log = ops.get_log()
        assert len(log) == 3


@pytest.mark.functional
class TestStackDetectionRealFiles:
    def test_python_fastapi_project(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[project]\nname = "myapi"\ndependencies = ["fastapi", "uvicorn"]\n'
            '[tool.ruff]\nline-length = 100\n'
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )
        (tmp_path / "requirements.txt").write_text("fastapi>=0.100\nuvicorn\n")

        info = detect_stack(tmp_path)

        assert info.language == "python"
        assert info.framework == "fastapi"
        assert info.test_command == "pytest"
        assert info.lint_command == "ruff check ."
        assert info.package_manager == "pip"
        assert info.docker_image == "komyt-python:latest"

    def test_node_nextjs_project(self, tmp_path: Path) -> None:
        pkg = {
            "name": "myapp",
            "scripts": {"dev": "next dev", "build": "next build", "test": "jest", "lint": "eslint ."},
            "dependencies": {"next": "^14", "react": "^18"},
            "devDependencies": {"jest": "^29"},
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        (tmp_path / "pnpm-lock.yaml").write_text("")

        info = detect_stack(tmp_path)

        assert info.language == "node"
        assert info.framework == "nextjs"
        assert info.test_command == "npm run test"
        assert info.build_command == "npm run build"
        assert info.lint_command == "npm run lint"
        assert info.package_manager == "pnpm"

    def test_go_gin_project(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").write_text(
            "module github.com/org/app\n\ngo 1.22\n\n"
            "require github.com/gin-gonic/gin v1.9.1\n"
        )

        info = detect_stack(tmp_path)

        assert info.language == "go"
        assert info.framework == "gin"
        assert info.test_command == "go test ./..."
        assert info.build_command == "go build ./..."
