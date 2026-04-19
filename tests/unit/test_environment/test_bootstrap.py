"""Unit tests for the dev-tool bootstrap commands."""

from __future__ import annotations

import pytest

from komyt.environment.bootstrap import build_dev_tool_install_commands
from komyt.environment.detection import StackInfo


@pytest.mark.unit
class TestBuildDevToolInstallCommands:
    def test_unknown_language_returns_empty(self) -> None:
        cmds = build_dev_tool_install_commands(StackInfo(language="unknown"))
        assert cmds == []

    def test_python_pip_installs_linters_and_test_tools(self) -> None:
        cmds = build_dev_tool_install_commands(
            StackInfo(language="python", package_manager="pip"),
        )
        joined = " ".join(cmds)
        assert "ruff" in joined
        assert "mypy" in joined
        assert "pytest" in joined
        assert "flake8" in joined

    def test_python_uv_installs_uv_and_syncs(self) -> None:
        cmds = build_dev_tool_install_commands(
            StackInfo(language="python", package_manager="uv"),
        )
        joined = " ".join(cmds)
        assert "uv sync" in joined

    def test_python_poetry_installs_poetry(self) -> None:
        cmds = build_dev_tool_install_commands(
            StackInfo(language="python", package_manager="poetry"),
        )
        joined = " ".join(cmds)
        assert "poetry install" in joined

    def test_node_npm_installs_global_linters_and_deps(self) -> None:
        cmds = build_dev_tool_install_commands(
            StackInfo(language="node", package_manager="npm"),
        )
        joined = " ".join(cmds)
        assert "eslint" in joined
        assert "prettier" in joined
        assert "typescript" in joined
        assert "npm ci" in joined or "npm install" in joined

    def test_node_pnpm_uses_pnpm(self) -> None:
        cmds = build_dev_tool_install_commands(
            StackInfo(language="node", package_manager="pnpm"),
        )
        assert any("pnpm install" in c for c in cmds)

    def test_node_yarn_uses_yarn(self) -> None:
        cmds = build_dev_tool_install_commands(
            StackInfo(language="node", package_manager="yarn"),
        )
        assert any("yarn install" in c for c in cmds)

    def test_go_installs_golangci_lint(self) -> None:
        cmds = build_dev_tool_install_commands(StackInfo(language="go"))
        joined = " ".join(cmds)
        assert "golangci-lint" in joined
        assert "go mod download" in joined

    def test_rust_adds_clippy(self) -> None:
        cmds = build_dev_tool_install_commands(StackInfo(language="rust"))
        joined = " ".join(cmds)
        assert "clippy" in joined

    def test_java_returns_empty(self) -> None:
        cmds = build_dev_tool_install_commands(StackInfo(language="java"))
        assert cmds == []
