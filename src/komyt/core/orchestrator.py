"""Komyt Orchestrator — main pipeline coordinator."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from tempfile import mkdtemp

from komyt.adapters.git.base import GitPlatformAdapter
from komyt.analysis.contract import LLMClient
from komyt.analysis.engine import AnalysisEngine
from komyt.core.config import KomytConfig
from komyt.core.models import PipelineResult, TaskStatus, TicketData
from komyt.devloop.loop import DevelopmentLoop
from komyt.devloop.opencode import OpenCodeClient, OpenCodeBackend
from komyt.devloop.testing import TestRunner
from komyt.environment.docker import DockerClient, DockerManager
from komyt.environment.git_ops import GitOperations
from komyt.environment.manager import EnvironmentManager
from komyt.finalization.docs_updater import DocsUpdater
from komyt.finalization.pr_creator import PRCreator
from komyt.finalization.reporter import Reporter
from komyt.ingestion.base import TicketAdapter, TicketFilter, TicketFilters

logger = logging.getLogger(__name__)


class Orchestrator:
    """Coordinates the full ticket-to-PR pipeline."""

    def __init__(
        self,
        config: KomytConfig,
        ticket_adapter: TicketAdapter,
        git_platform: GitPlatformAdapter,
        docker_client: DockerClient,
        opencode_backend: OpenCodeBackend,
        llm_client: LLMClient,
    ) -> None:
        self._config = config
        self._ticket_adapter = ticket_adapter
        self._git_platform = git_platform
        self._docker_client = docker_client
        self._opencode_backend = opencode_backend
        self._llm_client = llm_client

        self._filter = TicketFilter(
            trigger_keyword=config.trigger.keyword,
            case_sensitive=config.trigger.case_sensitive,
        )
        self._analysis = AnalysisEngine(config=config.analysis, llm=llm_client)

        github_token = config.github.token
        if not config.docker.enabled:
            from komyt.environment.local import LocalEnvironmentManager
            self._env_manager = LocalEnvironmentManager(github_token=github_token)  # type: ignore[assignment]
        else:
            self._env_manager = EnvironmentManager(
                docker_config=config.docker, docker_client=docker_client,
                github_token=github_token,
            )
        self._reporter = Reporter()
        self._pr_creator = PRCreator(platform=git_platform)

    async def process_ticket(self, ticket: TicketData) -> PipelineResult:
        start = time.monotonic()
        logger.info("Pipeline started for ticket %s: %s", ticket.id, ticket.title)

        # 1. Analysis
        try:
            analysis_result = await self._analysis.analyze(ticket)
        except Exception as exc:
            logger.error("Analysis failed: %s", exc)
            duration = time.monotonic() - start
            return PipelineResult(
                ticket=ticket,
                status=TaskStatus.FAILED,
                duration_seconds=duration,
                error_summary=f"Analysis error: {exc}",
            )

        if analysis_result.plan is None:
            if analysis_result.feedback_comment:
                await self._ticket_adapter.add_comment(
                    ticket.external_id, analysis_result.feedback_comment,
                )
            duration = time.monotonic() - start
            return PipelineResult(
                ticket=ticket,
                status=TaskStatus.WAITING_CLARIFICATION
                if analysis_result.feedback_comment else TaskStatus.FAILED,
                duration_seconds=duration,
                error_summary="Ticket did not pass analysis",
            )

        plan = analysis_result.plan

        # 2. Environment setup
        clone_path = Path(mkdtemp(prefix="komyt-"))
        env = await self._env_manager.setup(plan, clone_path)

        try:
            # 3. Dev loop
            opencode = OpenCodeClient(
                backend=self._opencode_backend,
                model=self._config.opencode.default_model,
                max_tokens=self._config.opencode.max_tokens_per_task,
            )
            await opencode.start_session(env.repo_path)

            git_ops = GitOperations(Path(env.repo_path))
            docker_mgr = DockerManager(
                config=self._config.docker, client=self._docker_client,
            )
            test_runner = TestRunner(docker=docker_mgr)

            loop = DevelopmentLoop(
                opencode=opencode, docker=docker_mgr,
                git_ops=git_ops, test_runner=test_runner,
            )
            loop_result = await loop.run(plan, env)

            # 4. Docs update
            docs_updater = DocsUpdater(opencode=opencode, git_ops=git_ops)
            await docs_updater.update(plan, env)

            # 5. Push & create PR
            pr_url: str | None = None
            has_diff = bool(git_ops.get_log(max_count=1)) and git_ops.repo.git.rev_list(
                f"{env.base_branch}..HEAD", count=True,
            ) != "0"
            if loop_result.completed_count > 0 and has_diff:
                git_ops.push()
                repo_slug = _extract_repo_slug(ticket.repo_url)
                pr_result = await self._pr_creator.create(plan, loop_result, repo_slug)
                pr_url = pr_result.url
            elif loop_result.completed_count > 0:
                logger.warning("Steps completed but no diff with base branch — skipping PR")

            await opencode.close()

            # 6. Report
            duration = time.monotonic() - start
            report = self._reporter.build_report(
                plan, loop_result, pr_url=pr_url, duration_seconds=duration,
            )

            await self._ticket_adapter.add_comment(
                ticket.external_id, report.comment_body,
            )

            logger.info(
                "Pipeline completed for %s — status: %s",
                ticket.id, report.pipeline_result.status.value,
            )
            return report.pipeline_result

        finally:
            self._env_manager.teardown(env)

    async def poll_and_process(self) -> list[PipelineResult]:
        filters = TicketFilters(
            labels=self._config.github.labels_filter,
            state="open",
        )

        tickets = await self._ticket_adapter.fetch_tickets(filters)
        results: list[PipelineResult] = []

        for ticket in tickets:
            comments = await self._ticket_adapter.fetch_comments(ticket.external_id)
            ticket.comments = comments

            if not self._filter.should_process(ticket):
                continue

            logger.info("Found triggerable ticket: %s", ticket.title)
            result = await self.process_ticket(ticket)
            results.append(result)

        return results


def _extract_repo_slug(repo_url: str) -> str:
    url = repo_url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return url
