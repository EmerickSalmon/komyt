"""Documentation updater — updates docs via OpenCode after implementation."""

from __future__ import annotations

import logging

from komyt.core.models import DevEnvironment, DevelopmentPlan
from komyt.devloop.opencode import OpenCodeClient
from komyt.devloop.prompts import build_docs_update_prompt
from komyt.environment.git_ops import GitOperations

logger = logging.getLogger(__name__)


class DocsUpdater:
    """Updates documentation files after implementation is complete."""

    def __init__(
        self,
        opencode: OpenCodeClient,
        git_ops: GitOperations,
    ) -> None:
        self._opencode = opencode
        self._git = git_ops

    async def update(self, plan: DevelopmentPlan, env: DevEnvironment) -> bool:
        doc_files = plan.documentation_updates
        if not doc_files:
            logger.info("No documentation updates needed")
            return False

        if self._opencode.budget_exhausted:
            logger.warning("Token budget exhausted — skipping docs update")
            return False

        prompt = build_docs_update_prompt(plan, doc_files)

        try:
            await self._opencode.send(prompt)
        except Exception:
            logger.warning("Failed to generate doc updates", exc_info=True)
            return False

        if self._git.has_changes():
            self._git.commit(f"docs: update documentation for #{plan.ticket.external_id}")
            logger.info("Documentation updated and committed")
            return True

        logger.info("No documentation changes were generated")
        return False
