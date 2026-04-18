"""Local environment manager — runs without Docker."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from komyt.core.models import DevEnvironment, DevelopmentPlan
from komyt.environment.detection import detect_stack
from komyt.environment.docker import ExecResult
from komyt.environment.git_ops import GitOperations
from komyt.environment.manager import AGENT_INSTRUCTION_FILES

logger = logging.getLogger(__name__)


class LocalEnvironmentManager:
    """Sets up a dev environment directly on the host filesystem (no Docker)."""

    def __init__(self, github_token: str = "") -> None:
        self._github_token = github_token

    async def setup(
        self,
        plan: DevelopmentPlan,
        clone_path: Path,
    ) -> DevEnvironment:
        logger.info("Setting up local environment for ticket %s", plan.ticket.id)

        git_ops = GitOperations.clone(
            url=plan.ticket.repo_url,
            target=clone_path,
            branch=plan.ticket.repo_branch,
            token=self._github_token,
        )
        git_ops.create_branch(plan.branch_name)

        stack = detect_stack(clone_path)
        agent_instructions = _find_agent_instructions(clone_path)

        env = DevEnvironment(
            container_id="local",
            repo_path=str(clone_path),
            branch_name=plan.branch_name,
            base_branch=plan.ticket.repo_branch,
            language=stack.language,
            framework=stack.framework,
            test_command=stack.test_command,
            lint_command=stack.lint_command,
            build_command=stack.build_command,
            agent_instructions=agent_instructions,
        )
        logger.info("Local environment ready: %s", env.repo_path)
        return env

    def exec_in_environment(self, env: DevEnvironment, command: str) -> ExecResult:
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                cwd=env.repo_path, timeout=300,
            )
            return ExecResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(exit_code=1, stdout="", stderr="Command timed out (300s)")

    def teardown(self, env: DevEnvironment) -> None:
        logger.info("Local environment teardown (nothing to clean)")


class LocalDockerClient:
    """Fake DockerClient that executes commands locally via subprocess."""

    def create_container(self, **kwargs: object) -> str:
        return "local"

    def start_container(self, container_id: str) -> None:
        pass

    def stop_container(self, container_id: str, timeout: int = 10) -> None:
        pass

    def remove_container(self, container_id: str, force: bool = False) -> None:
        pass

    def exec_in_container(
        self, container_id: str, command: str, working_dir: str | None = None,
    ) -> ExecResult:
        try:
            proc = subprocess.run(
                command, shell=True, capture_output=True, text=True,
                cwd=working_dir, timeout=300,
            )
            return ExecResult(
                exit_code=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
            )
        except subprocess.TimeoutExpired:
            return ExecResult(exit_code=1, stdout="", stderr="Command timed out (300s)")

    def container_exists(self, container_id: str) -> bool:
        return True

    def pull_image(self, image: str) -> None:
        pass


def _find_agent_instructions(repo_path: Path) -> str | None:
    for filename in AGENT_INSTRUCTION_FILES:
        filepath = repo_path / filename
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8", errors="ignore")
            if content.strip():
                return content
    return None
