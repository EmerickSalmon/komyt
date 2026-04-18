"""Docker container management for isolated dev environments."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from komyt.core.config import DockerConfig

logger = logging.getLogger(__name__)


@dataclass
class ExecResult:
    """Result of executing a command inside a container."""

    exit_code: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class DockerClient(Protocol):
    """Protocol wrapping the Docker SDK to allow mocking."""

    def create_container(
        self,
        image: str,
        command: str | None = None,
        volumes: dict[str, dict[str, str]] | None = None,
        mem_limit: str | None = None,
        nano_cpus: int | None = None,
        working_dir: str | None = None,
        detach: bool = True,
    ) -> str: ...

    def start_container(self, container_id: str) -> None: ...

    def stop_container(self, container_id: str, timeout: int = 10) -> None: ...

    def remove_container(self, container_id: str, force: bool = False) -> None: ...

    def exec_in_container(
        self, container_id: str, command: str, working_dir: str | None = None,
    ) -> ExecResult: ...

    def container_exists(self, container_id: str) -> bool: ...

    def pull_image(self, image: str) -> None: ...


class DockerManager:
    """Manages Docker containers for isolated development environments."""

    def __init__(self, config: DockerConfig, client: DockerClient) -> None:
        self._config = config
        self._client = client

    def create_environment(
        self,
        image: str | None = None,
        repo_path: str | None = None,
        working_dir: str = "/workspace",
    ) -> str:
        img = image or self._config.default_image
        volumes: dict[str, dict[str, str]] | None = None
        if repo_path:
            volumes = {repo_path: {"bind": working_dir, "mode": "rw"}}

        nano_cpus = self._config.cpu_limit * 1_000_000_000

        container_id = self._client.create_container(
            image=img,
            volumes=volumes,
            mem_limit=self._config.memory_limit,
            nano_cpus=nano_cpus,
            working_dir=working_dir,
            detach=True,
        )

        self._client.start_container(container_id)
        logger.info("Created container %s (image=%s)", container_id[:12], img)
        return container_id

    def exec_command(
        self,
        container_id: str,
        command: str,
        working_dir: str | None = None,
    ) -> ExecResult:
        logger.debug("Exec in %s: %s", container_id[:12], command)
        result = self._client.exec_in_container(
            container_id, command, working_dir=working_dir,
        )
        if not result.success:
            logger.warning(
                "Command failed (exit=%d) in %s: %s",
                result.exit_code, container_id[:12], command,
            )
        return result

    def cleanup(self, container_id: str) -> None:
        if not self._config.cleanup_after:
            logger.info("Skipping cleanup for %s (cleanup_after=False)", container_id[:12])
            return

        try:
            self._client.stop_container(container_id, timeout=10)
        except Exception:
            logger.warning("Failed to stop container %s", container_id[:12])

        try:
            self._client.remove_container(container_id, force=True)
            logger.info("Removed container %s", container_id[:12])
        except Exception:
            logger.warning("Failed to remove container %s", container_id[:12])

    def is_running(self, container_id: str) -> bool:
        return self._client.container_exists(container_id)

    def pull_image(self, image: str) -> None:
        logger.info("Pulling image %s", image)
        self._client.pull_image(image)
