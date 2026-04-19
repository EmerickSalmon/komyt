"""Real Docker client implementation using the docker Python SDK."""

from __future__ import annotations

import logging

import docker

from komyt.environment.docker import ExecResult

logger = logging.getLogger(__name__)


class RealDockerClient:
    """Wraps the docker-py SDK to satisfy the DockerClient protocol."""

    def __init__(self) -> None:
        self._docker = docker.from_env()

    def create_container(
        self,
        image: str,
        command: str | None = None,
        volumes: dict[str, dict[str, str]] | None = None,
        mem_limit: str | None = None,
        nano_cpus: int | None = None,
        working_dir: str | None = None,
        detach: bool = True,
        environment: dict[str, str] | None = None,
    ) -> str:
        kwargs: dict[str, object] = {
            "image": image,
            "detach": detach,
            "stdin_open": True,
            "tty": True,
        }
        if command:
            kwargs["command"] = command
        if volumes:
            kwargs["volumes"] = volumes
        if mem_limit:
            kwargs["mem_limit"] = mem_limit
        if nano_cpus:
            kwargs["nano_cpus"] = nano_cpus
        if working_dir:
            kwargs["working_dir"] = working_dir
        if environment:
            kwargs["environment"] = environment

        try:
            container = self._docker.containers.create(**kwargs)
        except docker.errors.ImageNotFound:
            logger.info("Image %s not found locally, pulling...", image)
            self._docker.images.pull(image)
            container = self._docker.containers.create(**kwargs)
        return container.id

    def start_container(self, container_id: str) -> None:
        container = self._docker.containers.get(container_id)
        container.start()

    def stop_container(self, container_id: str, timeout: int = 10) -> None:
        container = self._docker.containers.get(container_id)
        container.stop(timeout=timeout)

    def remove_container(self, container_id: str, force: bool = False) -> None:
        container = self._docker.containers.get(container_id)
        container.remove(force=force)

    def exec_in_container(
        self, container_id: str, command: str, working_dir: str | None = None,
    ) -> ExecResult:
        container = self._docker.containers.get(container_id)
        kwargs: dict[str, object] = {"cmd": ["sh", "-c", command], "demux": True}
        if working_dir:
            kwargs["workdir"] = working_dir
        exit_code, output = container.exec_run(**kwargs)
        stdout = ""
        stderr = ""
        if isinstance(output, tuple):
            stdout = (output[0] or b"").decode(errors="replace")
            stderr = (output[1] or b"").decode(errors="replace")
        elif isinstance(output, bytes):
            stdout = output.decode(errors="replace")
        return ExecResult(exit_code=exit_code, stdout=stdout, stderr=stderr)

    def container_exists(self, container_id: str) -> bool:
        try:
            self._docker.containers.get(container_id)
            return True
        except docker.errors.NotFound:
            return False

    def pull_image(self, image: str) -> None:
        self._docker.images.pull(image)
