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
from komyt.devloop.opencode import OpenCodeBackend, OpenCodeClient
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
            logger.info("Docker disabled — using local environment manager")
            self._env_manager = LocalEnvironmentManager(github_token=github_token)  # type: ignore[assignment]
        else:
            logger.info("Docker enabled — using containerized environments")
            self._env_manager = EnvironmentManager(
                docker_config=config.docker, docker_client=docker_client,
                github_token=github_token,
                container_env=_build_container_env(),
                python_image=config.opencode.python_image,
            )
        self._reporter = Reporter()
        self._pr_creator = PRCreator(platform=git_platform)

    async def process_ticket(self, ticket: TicketData) -> PipelineResult:
        start = time.monotonic()
        logger.info("=" * 60)
        logger.info("PIPELINE START — ticket %s: %s", ticket.id, ticket.title)
        logger.info("=" * 60)

        # 1. Analysis
        logger.info("[1/6] Analyzing ticket...")
        try:
            analysis_result = await self._analysis.analyze(ticket)
        except Exception as exc:
            logger.error("[1/6] Analysis failed: %s", exc)
            duration = time.monotonic() - start
            return PipelineResult(
                ticket=ticket,
                status=TaskStatus.FAILED,
                duration_seconds=duration,
                error_summary=f"Analysis error: {exc}",
            )

        logger.info(
            "[1/6] Analysis complete — score: %d/100, status: %s",
            analysis_result.validation.score,
            analysis_result.validation.status.value,
        )

        if analysis_result.plan is None:
            if analysis_result.feedback_comment:
                logger.info("[1/6] Posting feedback comment on ticket")
                await self._ticket_adapter.add_comment(
                    ticket.external_id, analysis_result.feedback_comment,
                )
            duration = time.monotonic() - start
            logger.info("[1/6] Pipeline stopped — ticket did not pass analysis (%.1fs)", duration)
            return PipelineResult(
                ticket=ticket,
                status=TaskStatus.WAITING_CLARIFICATION
                if analysis_result.feedback_comment else TaskStatus.FAILED,
                duration_seconds=duration,
                error_summary="Ticket did not pass analysis",
            )

        plan = analysis_result.plan
        logger.info(
            "[1/6] Plan generated — branch: %s, %d steps",
            plan.branch_name, len(plan.steps),
        )
        for i, step in enumerate(plan.steps, 1):
            logger.info("  Step %d: %s", i, step.description)

        # 2. Environment setup
        logger.info("[2/6] Setting up environment...")
        clone_path = Path(mkdtemp(prefix="komyt-"))
        env = await self._env_manager.setup(plan, clone_path)
        logger.info(
            "[2/6] Environment ready — container: %s, language: %s, repo: %s",
            env.container_id[:12] if env.container_id else "local",
            env.language,
            env.repo_path,
        )
        if env.test_command:
            logger.info("  Test command: %s", env.test_command)
        if env.lint_command:
            logger.info("  Lint command: %s", env.lint_command)
        if env.build_command:
            logger.info("  Build command: %s", env.build_command)

        try:
            # 3. Dev loop
            logger.info("[3/6] Starting development loop...")
            opencode = OpenCodeClient(
                backend=self._opencode_backend,
                model=self._config.opencode.default_model,
                max_tokens=self._config.opencode.max_tokens_per_task,
            )
            await opencode.start_session(env.repo_path, container_id=env.container_id)

            git_ops = GitOperations(Path(env.repo_path))
            docker_mgr = DockerManager(
                config=self._config.docker, client=self._docker_client,
            )
            test_runner = TestRunner(docker=docker_mgr)

            loop = DevelopmentLoop(
                opencode=opencode, docker=docker_mgr,
                git_ops=git_ops, test_runner=test_runner,
                stop_on_step_failure=self._config.opencode.stop_on_step_failure,
                skip_validation=self._config.opencode.skip_validation,
            )
            loop_result = await loop.run(plan, env)
            logger.info(
                "[3/6] Dev loop complete — %d/%d steps succeeded, %d tokens used",
                loop_result.completed_count, len(plan.steps), loop_result.total_tokens,
            )

            # 4. Docs update
            logger.info("[4/6] Updating documentation...")
            docs_updater = DocsUpdater(opencode=opencode, git_ops=git_ops)
            await docs_updater.update(plan, env)

            # 5. Push & create PR
            logger.info("[5/6] Pushing and creating PR...")
            pr_url: str | None = None
            has_diff = bool(git_ops.get_log(max_count=1)) and git_ops.repo.git.rev_list(
                f"{env.base_branch}..HEAD", count=True,
            ) != "0"
            if has_diff:
                if loop_result.failed_count > 0:
                    logger.warning(
                        "[5/6] %d step(s) failed verification — opening PR anyway "
                        "so a human can pick up the WIP commits",
                        loop_result.failed_count,
                    )
                logger.info("[5/6] Diff detected — pushing to remote")
                git_ops.push()
                repo_slug = _extract_repo_slug(ticket.repo_url)
                pr_result = await self._pr_creator.create(plan, loop_result, repo_slug)
                pr_url = pr_result.url
                logger.info("[5/6] PR created: %s", pr_url)
            else:
                logger.warning("[5/6] No diff with base branch — skipping PR")

            await opencode.close()

            # 6. Report
            logger.info("[6/6] Building report...")
            duration = time.monotonic() - start
            report = self._reporter.build_report(
                plan, loop_result, pr_url=pr_url, duration_seconds=duration,
            )

            await self._ticket_adapter.add_comment(
                ticket.external_id, report.comment_body,
            )

            logger.info("=" * 60)
            logger.info(
                "PIPELINE COMPLETE — %s — status: %s, tokens: %d, duration: %.1fs",
                ticket.id, report.pipeline_result.status.value,
                report.pipeline_result.total_tokens, duration,
            )
            if pr_url:
                logger.info("PR: %s", pr_url)
            logger.info("=" * 60)
            return report.pipeline_result

        finally:
            logger.info("Cleaning up environment (container: %s)...",
                        env.container_id[:12] if env.container_id else "local")
            self._env_manager.teardown(env)

    async def poll_and_process(self) -> list[PipelineResult]:
        filters = TicketFilters(
            labels=self._config.github.labels_filter,
            state="open",
        )

        tickets = await self._ticket_adapter.fetch_tickets(filters)
        logger.info("Polled %d ticket(s)", len(tickets))
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


def _build_container_env() -> dict[str, str]:
    """Passthrough of secrets opencode needs once it runs inside the container.

    We only forward what's actually set in the host env to avoid silently
    injecting empty values that would mask missing-credential errors.
    """
    import os

    keys = (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "OPENCODE_API_KEY",
        "GITHUB_TOKEN",
    )
    return {k: os.environ[k] for k in keys if os.environ.get(k)}


def _extract_repo_slug(repo_url: str) -> str:
    url = repo_url.rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    parts = url.split("/")
    if len(parts) >= 2:
        return f"{parts[-2]}/{parts[-1]}"
    return url
