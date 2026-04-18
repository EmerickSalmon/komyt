"""Tech stack detection for target repositories."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class StackInfo:
    """Detected technology stack of a repository."""

    language: str
    framework: str | None = None
    test_command: str | None = None
    lint_command: str | None = None
    build_command: str | None = None
    docker_image: str = "ubuntu:24.04"
    package_manager: str | None = None


_LANGUAGE_MARKERS: list[tuple[str, str]] = [
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
    ("setup.cfg", "python"),
    ("requirements.txt", "python"),
    ("Pipfile", "python"),
    ("package.json", "node"),
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
    ("pom.xml", "java"),
    ("build.gradle", "java"),
    ("Gemfile", "ruby"),
    ("composer.json", "php"),
]

_DOCKER_IMAGES: dict[str, str] = {
    "python": "python:3.12-slim",
    "node": "node:20-slim",
    "go": "golang:1.22-bookworm",
    "rust": "rust:1.78-slim",
    "java": "eclipse-temurin:21-jdk",
    "ruby": "ruby:3.3-slim",
    "php": "php:8.3-cli",
}


def detect_stack(repo_path: Path) -> StackInfo:
    """Detect the tech stack of a repository by inspecting marker files."""
    language = _detect_language(repo_path)
    framework = _detect_framework(repo_path, language)
    test_cmd = _detect_test_command(repo_path, language, framework)
    lint_cmd = _detect_lint_command(repo_path, language)
    build_cmd = _detect_build_command(repo_path, language)
    docker_image = _DOCKER_IMAGES.get(language, "ubuntu:24.04")
    pkg_manager = _detect_package_manager(repo_path, language)

    info = StackInfo(
        language=language,
        framework=framework,
        test_command=test_cmd,
        lint_command=lint_cmd,
        build_command=build_cmd,
        docker_image=docker_image,
        package_manager=pkg_manager,
    )
    logger.info("Detected stack: %s", info)
    return info


def _detect_language(repo_path: Path) -> str:
    for marker, lang in _LANGUAGE_MARKERS:
        if (repo_path / marker).exists():
            return lang
    return "unknown"


def _detect_framework(repo_path: Path, language: str) -> str | None:
    if language == "python":
        return _detect_python_framework(repo_path)
    if language == "node":
        return _detect_node_framework(repo_path)
    if language == "go":
        return _detect_go_framework(repo_path)
    return None


def _detect_python_framework(repo_path: Path) -> str | None:
    pyproject = repo_path / "pyproject.toml"
    requirements = repo_path / "requirements.txt"

    searchable = ""
    if pyproject.exists():
        searchable += pyproject.read_text(encoding="utf-8", errors="ignore")
    if requirements.exists():
        searchable += requirements.read_text(encoding="utf-8", errors="ignore")

    searchable_lower = searchable.lower()
    if "fastapi" in searchable_lower:
        return "fastapi"
    if "django" in searchable_lower:
        return "django"
    if "flask" in searchable_lower:
        return "flask"
    return None


def _detect_node_framework(repo_path: Path) -> str | None:
    pkg_json = repo_path / "package.json"
    if not pkg_json.exists():
        return None

    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
    if "next" in deps:
        return "nextjs"
    if "nuxt" in deps:
        return "nuxt"
    if "react" in deps:
        return "react"
    if "vue" in deps:
        return "vue"
    if "express" in deps:
        return "express"
    return None


def _detect_go_framework(repo_path: Path) -> str | None:
    go_mod = repo_path / "go.mod"
    if not go_mod.exists():
        return None

    content = go_mod.read_text(encoding="utf-8", errors="ignore").lower()
    if "gin-gonic" in content:
        return "gin"
    if "labstack/echo" in content:
        return "echo"
    if "gorilla/mux" in content:
        return "gorilla"
    return None


def _detect_test_command(repo_path: Path, language: str, framework: str | None) -> str | None:
    if language == "python":
        if (repo_path / "pyproject.toml").exists() or (repo_path / "pytest.ini").exists():
            return "pytest"
        return "python -m unittest discover"
    if language == "node":
        return _detect_node_script(repo_path, "test")
    if language == "go":
        return "go test ./..."
    if language == "rust":
        return "cargo test"
    if language == "java":
        if (repo_path / "gradlew").exists():
            return "./gradlew test"
        return "mvn test"
    return None


def _detect_lint_command(repo_path: Path, language: str) -> str | None:
    if language == "python":
        if _file_contains(repo_path / "pyproject.toml", "ruff"):
            return "ruff check ."
        return "flake8"
    if language == "node":
        return _detect_node_script(repo_path, "lint")
    if language == "go":
        return "golangci-lint run"
    if language == "rust":
        return "cargo clippy"
    return None


def _detect_build_command(repo_path: Path, language: str) -> str | None:
    if language == "node":
        return _detect_node_script(repo_path, "build")
    if language == "go":
        return "go build ./..."
    if language == "rust":
        return "cargo build"
    if language == "java":
        if (repo_path / "gradlew").exists():
            return "./gradlew build"
        return "mvn package"
    return None


def _detect_package_manager(repo_path: Path, language: str) -> str | None:
    if language == "python":
        if (repo_path / "poetry.lock").exists():
            return "poetry"
        if (repo_path / "Pipfile.lock").exists():
            return "pipenv"
        if (repo_path / "uv.lock").exists():
            return "uv"
        return "pip"
    if language == "node":
        if (repo_path / "pnpm-lock.yaml").exists():
            return "pnpm"
        if (repo_path / "yarn.lock").exists():
            return "yarn"
        if (repo_path / "bun.lockb").exists():
            return "bun"
        return "npm"
    return None


def _detect_node_script(repo_path: Path, script_name: str) -> str | None:
    pkg_json = repo_path / "package.json"
    if not pkg_json.exists():
        return None
    try:
        data = json.loads(pkg_json.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
        if script_name in scripts:
            return f"npm run {script_name}"
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _file_contains(path: Path, keyword: str) -> bool:
    if not path.exists():
        return False
    try:
        return keyword in path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False
