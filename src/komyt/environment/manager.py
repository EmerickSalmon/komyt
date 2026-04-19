"""Development environment manager — orchestrates setup of isolated environments."""

from __future__ import annotations

import logging
from pathlib import Path

from komyt.core.config import DockerConfig
from komyt.core.models import DevelopmentPlan, DevEnvironment
from komyt.environment.bootstrap import build_dev_tool_install_commands
from komyt.environment.detection import StackInfo, detect_stack
from komyt.environment.docker import DockerClient, DockerManager, ExecResult
from komyt.environment.git_ops import GitOperations

logger = logging.getLogger(__name__)

AGENT_INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md", ".cursorrules", "CONVENTIONS.md")

CONTAINER_WORK_DIR = "/workspace"


class EnvironmentManager:
    """Sets up and manages isolated development environments for tickets."""

    def __init__(
        self,
        docker_config: DockerConfig,
        docker_client: DockerClient,
        github_token: str = "",
        container_env: dict[str, str] | None = None,
        python_image: str | None = None,
    ) -> None:
        self._docker = DockerManager(config=docker_config, client=docker_client)
        self._docker_config = docker_config
        self._github_token = github_token
        self._container_env = container_env or {}
        self._python_image = python_image

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
        if stack.language == "python" and self._python_image:
            stack.docker_image = self._python_image

        agent_instructions = _find_agent_instructions(clone_path)

        container_id = self._docker.create_environment(
            image=stack.docker_image,
            repo_path=str(clone_path),
            working_dir=CONTAINER_WORK_DIR,
            environment=self._container_env or None,
        )

        self._install_dev_tools(container_id, stack)

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

    def _install_dev_tools(self, container_id: str, stack: StackInfo) -> None:
        commands = build_dev_tool_install_commands(stack)
        if not commands:
            logger.info("No dev tool install commands for stack '%s'", stack.language)
            return
        logger.info(
            "Installing dev tools in %s for '%s' (%d commands) — this can take a while",
            container_id[:12], stack.language, len(commands),
        )
        for cmd in commands:
            result = self._docker.exec_command(
                container_id, cmd, working_dir=CONTAINER_WORK_DIR,
            )
            if not result.success:
                logger.warning(
                    "Dev tool install command exited %d (continuing): %s",
                    result.exit_code, cmd,
                )

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
