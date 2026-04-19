"""Install lint, test and verification tools inside a freshly created container.

The detected language base images (``python:3.12-slim``, ``node:20-slim``…) ship
without the linters, type checkers and test runners that the devloop relies on,
so we install them at startup. Project dependencies are installed too so that
test/lint commands can resolve imports.

This phase is intentionally best-effort: any failure is logged by the caller
and does not abort environment setup. Speed will be revisited later (image
caching, layered base images).
"""

from __future__ import annotations

from komyt.environment.detection import StackInfo


def build_dev_tool_install_commands(stack: StackInfo) -> list[str]:
    """Return the shell commands to install dev tools for the detected stack."""
    if stack.language == "python":
        return _python_commands(stack)
    if stack.language == "node":
        return _node_commands(stack)
    if stack.language == "go":
        return _go_commands(stack)
    if stack.language == "rust":
        return _rust_commands(stack)
    if stack.language == "java":
        return _java_commands(stack)
    return []


def _python_commands(stack: StackInfo) -> list[str]:
    cmds: list[str] = [
        "pip install --no-cache-dir --quiet "
        "ruff mypy flake8 pytest pytest-asyncio pytest-cov",
    ]
    pm = stack.package_manager
    if pm == "uv":
        cmds.append(
            "pip install --no-cache-dir --quiet uv && "
            "uv sync --frozen 2>/dev/null || uv sync 2>/dev/null || true",
        )
    elif pm == "poetry":
        cmds.append(
            "pip install --no-cache-dir --quiet poetry && "
            "poetry install --no-root --no-interaction 2>/dev/null || true",
        )
    elif pm == "pipenv":
        cmds.append(
            "pip install --no-cache-dir --quiet pipenv && "
            "pipenv install --dev --deploy 2>/dev/null || pipenv install --dev 2>/dev/null || true",
        )
    else:
        cmds.append(
            "pip install --no-cache-dir --quiet -e '.[dev]' 2>/dev/null || "
            "pip install --no-cache-dir --quiet -e . 2>/dev/null || "
            "pip install --no-cache-dir --quiet -r requirements.txt 2>/dev/null || true",
        )
    return cmds


def _node_commands(stack: StackInfo) -> list[str]:
    pm = stack.package_manager or "npm"
    if pm == "yarn":
        install = "yarn install --frozen-lockfile 2>/dev/null || yarn install"
    elif pm == "pnpm":
        install = "corepack enable pnpm && pnpm install --frozen-lockfile 2>/dev/null || pnpm install"
    elif pm == "bun":
        install = "bun install"
    else:
        install = "npm ci 2>/dev/null || npm install"
    return [
        "npm install -g --silent eslint prettier typescript",
        install,
    ]


def _go_commands(stack: StackInfo) -> list[str]:
    return [
        "go install github.com/golangci/golangci-lint/cmd/golangci-lint@latest",
        "go mod download 2>/dev/null || true",
    ]


def _rust_commands(stack: StackInfo) -> list[str]:
    return [
        "rustup component add clippy rustfmt 2>/dev/null || true",
        "cargo fetch 2>/dev/null || true",
    ]


def _java_commands(stack: StackInfo) -> list[str]:
    return []
