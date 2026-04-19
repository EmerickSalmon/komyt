"""OpenCode backend that runs the real `opencode` CLI inside the dev container.

Each call to :meth:`send_message` translates to one invocation of
``opencode run '<prompt>'`` via ``docker exec`` in the container prepared by
Komyt's :class:`~komyt.environment.manager.EnvironmentManager`.

Unlike :class:`~komyt.llm.opencode_backend.LLMOpenCodeBackend` (which only
POSTs a chat completion and parses file blocks out of the text), this backend
lets opencode drive its own agent loop: it can read/write files, run
``pytest``/``flake8``/``coverage`` and iterate until the step is green — all
inside the isolated container.
"""

from __future__ import annotations

import base64
import logging
import shlex
import uuid

from komyt.core.config import OpenCodeConfig
from komyt.devloop.opencode import CompletionResult
from komyt.environment.docker import DockerManager

logger = logging.getLogger(__name__)


class OpenCodeCLIBackend:
    """Execute ``opencode run`` inside the dev container."""

    def __init__(
        self,
        docker_manager: DockerManager,
        config: OpenCodeConfig,
        work_dir: str = "/workspace",
    ) -> None:
        self._docker = docker_manager
        self._default_model = config.default_model
        self._work_dir = work_dir
        self._sessions: dict[str, dict[str, str]] = {}

    async def create_session(
        self, working_dir: str, model: str, container_id: str = "",
    ) -> str:
        if not container_id:
            raise RuntimeError(
                "OpenCodeCLIBackend requires a container_id — make sure the "
                "environment was created before start_session() is called.",
            )
        # `working_dir` from the caller is the *host* clone path; opencode
        # runs inside the container so we always cd into the container's work
        # dir (mounted on the same volume).
        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = {
            "model": model or self._default_model,
            "container_id": container_id,
            "work_dir": self._work_dir,
        }
        return session_id

    async def send_message(self, session_id: str, message: str) -> CompletionResult:
        session = self._sessions[session_id]
        cid = session["container_id"]
        model = session["model"]
        work_dir = session["work_dir"]

        b64 = base64.b64encode(message.encode("utf-8")).decode("ascii")
        prompt_path = f"/tmp/komyt-prompt-{session_id}.txt"
        cmd = (
            f"set -e; "
            f"echo {b64} | base64 -d > {shlex.quote(prompt_path)}; "
            f"opencode run --model {shlex.quote(model)} "
            f"\"$(cat {shlex.quote(prompt_path)})\""
        )

        logger.info(
            "opencode run in %s (model=%s, prompt=%d chars)",
            cid[:12], model, len(message),
        )
        result = self._docker.exec_command(cid, cmd, working_dir=work_dir)

        if not result.success:
            logger.warning(
                "opencode run exited %d in %s — returning raw output to caller",
                result.exit_code, cid[:12],
            )

        return CompletionResult(
            text=result.stdout or result.stderr,
            input_tokens=0,
            output_tokens=0,
            estimated_cost=0.0,
            model=model,
        )

    async def close_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def close(self) -> None:
        return None
