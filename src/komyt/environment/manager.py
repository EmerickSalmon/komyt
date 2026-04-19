"""Development environment manager — orchestrates setup of isolated environments."""

from __future__ import annotations

import logging
from pathlib import Path

from komyt.core.config import DockerConfig
from komyt.core.models import DevEnvironment, DevelopmentPlan
from komyt.environment.detection import StackInfo, detect_stack
from komyt.environment.docker import DockerClient, DockerManager, ExecResult
from komyt.environment.git_ops import GitOperations

logger = logging.getLogger(__name__)

AGENT_INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", ".cursorrules", "CONVENTIONS.md")

CONTAINER_WORK_DIR = "/workspace"


class EnvironmentManager:
    """Sets up and manages isolated development environments for tickets."""

    def __init__(
        self, docker_config: DockerConfig, docker_client: DockerClient, github_token: str = "",
    ) -> None:
        self._docker = DockerManager(config=docker_config, client=docker_client)
        self._docker_config = docker_config
        self._github_token = github_token

    async def setup(
        self,
        plan: DevelopmentPlan,
        clone_path: Path,
    ) -> DevEnvironment:
        logger.info("Setting up environment for ticket %s", plan.ticket.id)

        git_ops = GitOperations.clone(
            url=plan.ticket.repo_url,
            target=clone_path,
            branch=plan.ticket.repo_branch,
            token=self._github_token,
        )

        git_ops.create_branch(plan.branch_name)

        stack = detect_stack(clone_path)

        agent_instructions = _find_agent_instructions(clone_path)

        container_id = self._docker.create_environment(
            image=stack.docker_image,
            repo_path=str(clone_path),
            working_dir=CONTAINER_WORK_DIR,
        )

        health = await self._health_check(container_id, stack)
        if not health:
            logger.warning("Health check failed for container %s", container_id[:12])

        env = DevEnvironment(
            container_id=container_id,
            repo_path=str(clone_path),
            container_work_dir=CONTAINER_WORK_DIR,
            branch_name=plan.branch_name,
            base_branch=plan.ticket.repo_branch,
            language=stack.language,
            framework=stack.framework,
            test_command=stack.test_command,
            lint_command=stack.lint_command,
            build_command=stack.build_command,
            agent_instructions=agent_instructions,
        )
        logger.info("Environment ready: %s", env)
        return env

    async def _health_check(self, container_id: str, stack: StackInfo) -> bool:
        if stack.test_command:
            result = self._docker.exec_command(container_id, f"{stack.test_command} --co 2>/dev/null || true")
            if not result.success:
                logger.debug("Test collection check returned non-zero (may be expected)")

        return self._docker.is_running(container_id)

    def exec_in_environment(
        self, env: DevEnvironment, command: str,
    ) -> ExecResult:
        return self._docker.exec_command(
            env.container_id, command, working_dir=env.exec_cwd,
        )

    def teardown(self, env: DevEnvironment) -> None:
        logger.info("Tearing down environment for container %s", env.container_id[:12])
        self._docker.cleanup(env.container_id)


def _find_agent_instructions(repo_path: Path) -> str | None:
    for filename in AGENT_INSTRUCTION_FILES:
        filepath = repo_path / filename
        if filepath.exists():
            content = filepath.read_text(encoding="utf-8", errors="ignore")
            if content.strip():
                logger.info("Found agent instructions in %s", filename)
                return content
    return None
