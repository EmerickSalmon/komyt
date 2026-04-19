"""Unit tests for Docker container management."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from komyt.core.config import DockerConfig
from komyt.environment.docker import DockerManager, ExecResult


class FakeDockerClient:
    """In-memory fake Docker client for unit tests."""

    def __init__(self) -> None:
        self.containers: dict[str, bool] = {}
        self.created: list[dict] = []
        self.started: list[str] = []
        self.stopped: list[str] = []
        self.removed: list[str] = []
        self.exec_calls: list[tuple[str, str]] = []
        self.pulled: list[str] = []
        self._next_id = 0

    def create_container(
        self,
        image: str,
        command: str | None = None,
        volumes: dict | None = None,
        mem_limit: str | None = None,
        nano_cpus: int | None = None,
        working_dir: str | None = None,
        detach: bool = True,
        environment: dict | None = None,
    ) -> str:
        self._next_id += 1
        cid = f"container-{self._next_id:04d}"
        self.created.append({
            "id": cid, "image": image, "volumes": volumes,
            "mem_limit": mem_limit, "nano_cpus": nano_cpus,
            "working_dir": working_dir, "environment": environment,
        })
        self.containers[cid] = False
        return cid

    def start_container(self, container_id: str) -> None:
        self.started.append(container_id)
        self.containers[container_id] = True

    def stop_container(self, container_id: str, timeout: int = 10) -> None:
        self.stopped.append(container_id)
        self.containers[container_id] = False

    def remove_container(self, container_id: str, force: bool = False) -> None:
        self.removed.append(container_id)
        self.containers.pop(container_id, None)

    def exec_in_container(
        self, container_id: str, command: str, working_dir: str | None = None,
    ) -> ExecResult:
        self.exec_calls.append((container_id, command))
        return ExecResult(exit_code=0, stdout="ok", stderr="")

    def container_exists(self, container_id: str) -> bool:
        return container_id in self.containers

    def pull_image(self, image: str) -> None:
        self.pulled.append(image)


@pytest.fixture
def fake_client() -> FakeDockerClient:
    return FakeDockerClient()


@pytest.fixture
def manager(fake_client: FakeDockerClient) -> DockerManager:
    return DockerManager(config=DockerConfig(), client=fake_client)


@pytest.mark.unit
class TestDockerManager:
    def test_create_environment(
        self, manager: DockerManager, fake_client: FakeDockerClient,
    ) -> None:
        cid = manager.create_environment(image="python:3.12-slim")

        assert cid == "container-0001"
        assert len(fake_client.created) == 1
        assert fake_client.created[0]["image"] == "python:3.12-slim"
        assert cid in fake_client.started

    def test_create_with_repo_volume(
        self, manager: DockerManager, fake_client: FakeDockerClient,
    ) -> None:
        cid = manager.create_environment(
            repo_path="/tmp/repo", working_dir="/workspace",
        )

        created = fake_client.created[0]
        assert created["volumes"] == {"/tmp/repo": {"bind": "/workspace", "mode": "rw"}}

    def test_default_image_from_config(self, fake_client: FakeDockerClient) -> None:
        config = DockerConfig(default_image="custom:v1")
        mgr = DockerManager(config=config, client=fake_client)

        mgr.create_environment()

        assert fake_client.created[0]["image"] == "custom:v1"

    def test_cpu_and_memory_limits(
        self, manager: DockerManager, fake_client: FakeDockerClient,
    ) -> None:
        manager.create_environment()

        created = fake_client.created[0]
        assert created["mem_limit"] == "4g"
        assert created["nano_cpus"] == 2_000_000_000

    def test_exec_command(
        self, manager: DockerManager, fake_client: FakeDockerClient,
    ) -> None:
        cid = manager.create_environment()
        result = manager.exec_command(cid, "pytest")

        assert result.success
        assert result.stdout == "ok"
        assert (cid, "pytest") in fake_client.exec_calls

    def test_cleanup_stops_and_removes(
        self, manager: DockerManager, fake_client: FakeDockerClient,
    ) -> None:
        cid = manager.create_environment()
        manager.cleanup(cid)

        assert cid in fake_client.stopped
        assert cid in fake_client.removed

    def test_cleanup_skipped_when_disabled(self, fake_client: FakeDockerClient) -> None:
        config = DockerConfig(cleanup_after=False)
        mgr = DockerManager(config=config, client=fake_client)

        cid = mgr.create_environment()
        mgr.cleanup(cid)

        assert cid not in fake_client.stopped
        assert cid not in fake_client.removed

    def test_is_running(
        self, manager: DockerManager, fake_client: FakeDockerClient,
    ) -> None:
        cid = manager.create_environment()
        assert manager.is_running(cid) is True
        assert manager.is_running("nonexistent") is False

    def test_pull_image(
        self, manager: DockerManager, fake_client: FakeDockerClient,
    ) -> None:
        manager.pull_image("python:3.12-slim")
        assert "python:3.12-slim" in fake_client.pulled


@pytest.mark.unit
class TestExecResult:
    def test_success(self) -> None:
        r = ExecResult(exit_code=0, stdout="ok", stderr="")
        assert r.success is True

    def test_failure(self) -> None:
        r = ExecResult(exit_code=1, stdout="", stderr="error")
        assert r.success is False
