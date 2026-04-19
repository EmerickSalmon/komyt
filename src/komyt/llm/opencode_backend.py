"""OpenCode backend backed by an OpenAI-compatible LLM API.

Sends prompts to the LLM, parses file-write instructions from the response,
and applies them to the working directory.
"""

from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

import httpx

from komyt.core.config import OpenCodeConfig
from komyt.devloop.opencode import CompletionResult

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are an autonomous coding agent. When asked to implement something, \
respond ONLY with file blocks in this exact format:

--- FILE: path/to/file.ext ---
<file content here>
--- END FILE ---

You may output multiple file blocks. Do NOT include explanations, \
markdown fences, or commentary outside of file blocks. \
Paths are relative to the project root.\
"""

_FILE_BLOCK_RE = re.compile(
    r"---\s*FILE:\s*(.+?)\s*---\n(.*?)---\s*END\s*FILE\s*---",
    re.DOTALL,
)


class LLMOpenCodeBackend:
    """Uses a local or remote LLM API as the OpenCode agent backend.

    Parses structured file blocks from LLM responses and writes them to disk.
    """

    def __init__(self, config: OpenCodeConfig) -> None:
        self._model = config.default_model
        url = config.server_url.rstrip("/")
        if not url.endswith("/v1"):
            url = url.rstrip("/")
        self._url = f"{url}/chat/completions"
        self._client = httpx.AsyncClient(timeout=180.0)
        self._sessions: dict[str, dict[str, str]] = {}

    async def create_session(
        self, working_dir: str, model: str, container_id: str = "",
    ) -> str:
        session_id = uuid.uuid4().hex[:12]
        self._sessions[session_id] = {
            "working_dir": working_dir,
            "model": model or self._model,
            "container_id": container_id,
        }
        return session_id

    async def send_message(self, session_id: str, message: str) -> CompletionResult:
        session = self._sessions[session_id]
        working_dir = session["working_dir"]

        resp = await self._client.post(
            self._url,
            headers={"content-type": "application/json"},
            json={
                "model": session["model"],
                "max_tokens": 4096,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": message},
                ],
            },
        )
        resp.raise_for_status()
        data = resp.json()
        choice = data["choices"][0]
        text = choice["message"]["content"]
        usage = data.get("usage", {})

        files_written = _apply_file_blocks(text, working_dir)
        if files_written:
            logger.info("Wrote %d file(s): %s", len(files_written), ", ".join(files_written))
        else:
            logger.warning("No file blocks found in LLM response")

        return CompletionResult(
            text=text,
            input_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            model=data.get("model", session["model"]),
        )

    async def close_session(self, session_id: str) -> None:
        self._sessions.pop(session_id, None)

    async def close(self) -> None:
        await self._client.aclose()


def _apply_file_blocks(response: str, working_dir: str) -> list[str]:
    """Parse file blocks from the LLM response and write them to disk."""
    root = Path(working_dir)
    written: list[str] = []

    for match in _FILE_BLOCK_RE.finditer(response):
        rel_path = match.group(1).strip()
        content = match.group(2)

        if rel_path.startswith("/") or ".." in rel_path:
            logger.warning("Skipping unsafe path: %s", rel_path)
            continue

        target = root / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        written.append(rel_path)

    return written
