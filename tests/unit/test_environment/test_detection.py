"""Unit tests for tech stack detection."""

from __future__ import annotations

import json

import pytest

from komyt.environment.detection import StackInfo, detect_stack


@pytest.mark.unit
class TestDetectLanguage:
    def test_detects_python_from_pyproject(self, tmp_path) -> None:
        (tmp_path / "pyproject.toml").write_text("[build-system]")
        info = detect_stack(tmp_path)
        assert info.language == "python"

    def test_detects_python_from_requirements(self, tmp_path) -> None:
        (tmp_path / "requirements.txt").write_text("flask\n")
        info = detect_stack(tmp_path)
        assert info.language == "python"

    def test_detects_node_from_package_json(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text('{"name": "app"}')
        info = detect_stack(tmp_path)
        assert info.language == "node"

    def test_detects_go_from_go_mod(self, tmp_path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/app")
        info = detect_stack(tmp_path)
        assert info.language == "go"

    def test_detects_rust_from_cargo(self, tmp_path) -> None:
        (tmp_path / "Cargo.toml").write_text("[package]")
        info = detect_stack(tmp_path)
        assert info.language == "rust"

    def test_unknown_language(self, tmp_path) -> None:
        info = detect_stack(tmp_path)
        assert info.language == "unknown"

    def test_priority_order(self, tmp_path) -> None:
        (tmp_path / "pyproject.toml").write_text("[build-system]")
        (tmp_path / "package.json").write_text('{"name": "app"}')
        info = detect_stack(tmp_path)
        assert info.language == "python"


@pytest.mark.unit
class TestDetectFramework:
    def test_detects_fastapi(self, tmp_path) -> None:
        (tmp_path / "pyproject.toml").write_text('dependencies = ["fastapi"]')
        info = detect_stack(tmp_path)
        assert info.framework == "fastapi"

    def test_detects_django(self, tmp_path) -> None:
        (tmp_path / "requirements.txt").write_text("Django>=4.0\n")
        info = detect_stack(tmp_path)
        assert info.framework == "django"

    def test_detects_flask(self, tmp_path) -> None:
        (tmp_path / "requirements.txt").write_text("flask\n")
        info = detect_stack(tmp_path)
        assert info.framework == "flask"

    def test_detects_react(self, tmp_path) -> None:
        pkg = {"name": "app", "dependencies": {"react": "^18"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        info = detect_stack(tmp_path)
        assert info.framework == "react"

    def test_detects_nextjs(self, tmp_path) -> None:
        pkg = {"name": "app", "dependencies": {"next": "^14", "react": "^18"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        info = detect_stack(tmp_path)
        assert info.framework == "nextjs"

    def test_detects_gin_go(self, tmp_path) -> None:
        (tmp_path / "go.mod").write_text("require github.com/gin-gonic/gin v1.9")
        info = detect_stack(tmp_path)
        assert info.framework == "gin"

    def test_no_framework_for_unknown(self, tmp_path) -> None:
        info = detect_stack(tmp_path)
        assert info.framework is None


@pytest.mark.unit
class TestDetectCommands:
    def test_python_test_command(self, tmp_path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.pytest]")
        info = detect_stack(tmp_path)
        assert info.test_command == "pytest"

    def test_python_lint_with_ruff(self, tmp_path) -> None:
        (tmp_path / "pyproject.toml").write_text("[tool.ruff]\nline-length=100")
        info = detect_stack(tmp_path)
        assert info.lint_command == "ruff check ."

    def test_node_test_script(self, tmp_path) -> None:
        pkg = {"name": "app", "scripts": {"test": "jest"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        info = detect_stack(tmp_path)
        assert info.test_command == "npm run test"

    def test_node_build_script(self, tmp_path) -> None:
        pkg = {"name": "app", "scripts": {"build": "tsc"}}
        (tmp_path / "package.json").write_text(json.dumps(pkg))
        info = detect_stack(tmp_path)
        assert info.build_command == "npm run build"

    def test_go_commands(self, tmp_path) -> None:
        (tmp_path / "go.mod").write_text("module example.com/app")
        info = detect_stack(tmp_path)
        assert info.test_command == "go test ./..."
        assert info.build_command == "go build ./..."

    def test_rust_commands(self, tmp_path) -> None:
        (tmp_path / "Cargo.toml").write_text("[package]")
        info = detect_stack(tmp_path)
        assert info.test_command == "cargo test"
        assert info.lint_command == "cargo clippy"
        assert info.build_command == "cargo build"


@pytest.mark.unit
class TestDetectDockerImage:
    def test_python_image(self, tmp_path) -> None:
        (tmp_path / "pyproject.toml").write_text("[build-system]")
        info = detect_stack(tmp_path)
        assert info.docker_image == "komyt-python:latest"

    def test_node_image(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text('{"name": "app"}')
        info = detect_stack(tmp_path)
        assert info.docker_image == "node:20-slim"

    def test_go_image(self, tmp_path) -> None:
        (tmp_path / "go.mod").write_text("module app")
        info = detect_stack(tmp_path)
        assert info.docker_image == "golang:1.22-bookworm"

    def test_unknown_gets_base(self, tmp_path) -> None:
        info = detect_stack(tmp_path)
        assert info.docker_image == "ubuntu:24.04"


@pytest.mark.unit
class TestDetectPackageManager:
    def test_pip_default(self, tmp_path) -> None:
        (tmp_path / "pyproject.toml").write_text("[build-system]")
        info = detect_stack(tmp_path)
        assert info.package_manager == "pip"

    def test_poetry(self, tmp_path) -> None:
        (tmp_path / "pyproject.toml").write_text("[build-system]")
        (tmp_path / "poetry.lock").write_text("")
        info = detect_stack(tmp_path)
        assert info.package_manager == "poetry"

    def test_uv(self, tmp_path) -> None:
        (tmp_path / "pyproject.toml").write_text("[build-system]")
        (tmp_path / "uv.lock").write_text("")
        info = detect_stack(tmp_path)
        assert info.package_manager == "uv"

    def test_npm_default(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text('{"name": "app"}')
        info = detect_stack(tmp_path)
        assert info.package_manager == "npm"

    def test_pnpm(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text('{"name": "app"}')
        (tmp_path / "pnpm-lock.yaml").write_text("")
        info = detect_stack(tmp_path)
        assert info.package_manager == "pnpm"

    def test_yarn(self, tmp_path) -> None:
        (tmp_path / "package.json").write_text('{"name": "app"}')
        (tmp_path / "yarn.lock").write_text("")
        info = detect_stack(tmp_path)
        assert info.package_manager == "yarn"
