"""Development loop — iterative code/test/commit cycle."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from komyt.core.models import (
    DevEnvironment,
    DevelopmentPlan,
    DevStep,
    StepResult,
    StepStatus,
)
from komyt.devloop.opencode import OpenCodeClient, TokenBudgetExceeded
from komyt.devloop.prompts import build_commit_message, build_retry_prompt, build_step_prompt
from komyt.devloop.testing import TestRunner
from komyt.environment.docker import DockerManager
from komyt.environment.git_ops import GitOperations

logger = logging.getLogger(__name__)

_ERROR_OUTPUT_MAX = 3000


def _truncate_output(text: str) -> str:
    """Keep errors readable in the retry prompt without blowing the token budget."""
    text = text.strip()
    if len(text) <= _ERROR_OUTPUT_MAX:
        return text
    half = _ERROR_OUTPUT_MAX // 2
    return f"{text[:half]}\n... [truncated {len(text) - _ERROR_OUTPUT_MAX} chars] ...\n{text[-half:]}"


@dataclass
class LoopResult:
    """Result of executing the full development loop."""

    steps: list[StepResult] = field(default_factory=list)
    total_tokens: int = 0
    estimated_cost: float = 0.0
    aborted: bool = False
    abort_reason: str = ""

    @property
    def all_succeeded(self) -> bool:
        return all(s.status == StepStatus.SUCCESS for s in self.steps)

    @property
    def completed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.SUCCESS)

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.FAILED)


class DevelopmentLoop:
    """Executes dev steps in an iterative code → test → lint → commit cycle."""

    def __init__(
        self,
        opencode: OpenCodeClient,
        docker: DockerManager,
        git_ops: GitOperations,
        test_runner: TestRunner,
        stop_on_step_failure: bool = True,
    ) -> None:
        self._opencode = opencode
        self._docker = docker
        self._git = git_ops
        self._test_runner = test_runner
        self._stop_on_step_failure = stop_on_step_failure

    async def run(
        self,
        plan: DevelopmentPlan,
        env: DevEnvironment,
    ) -> LoopResult:
        logger.info(
            "Starting dev loop for %s (%d steps)",
            plan.ticket.id, len(plan.steps),
        )

        result = LoopResult()

        for step in plan.steps:
            try:
                step_result = await self._execute_step(step, plan, env)
            except TokenBudgetExceeded as exc:
                logger.warning("Token budget exhausted: %s", exc)
                step_result = StepResult(
                    status=StepStatus.FAILED, errors=[str(exc)],
                )
                result.aborted = True
                result.abort_reason = str(exc)
                result.steps.append(step_result)
                break

            result.steps.append(step_result)

            if step_result.status == StepStatus.FAILED:
                if self._stop_on_step_failure:
                    logger.warning(
                        "Step '%s' failed after %d attempts — aborting pipeline "
                        "(stop_on_step_failure=true)",
                        step.description, step.attempt_count,
                    )
                    result.aborted = True
                    result.abort_reason = (
                        f"Step '{step.description}' failed after "
                        f"{step.attempt_count} attempts"
                    )
                    break
                logger.warning(
                    "Step '%s' failed after %d attempts — continuing to next step",
                    step.description, step.attempt_count,
                )

        result.total_tokens = self._opencode.usage.total_tokens
        result.estimated_cost = self._opencode.usage.estimated_cost

        logger.info(
            "Dev loop finished: %d/%d steps succeeded, %d tokens used",
            result.completed_count, len(plan.steps), result.total_tokens,
        )
        return result

    async def _execute_step(
        self,
        step: DevStep,
        plan: DevelopmentPlan,
        env: DevEnvironment,
    ) -> StepResult:
        step.status = StepStatus.IN_PROGRESS
        logger.info("Executing step: %s", step.description)

        for attempt in range(1, step.max_attempts + 1):
            step.attempt_count = attempt

            if attempt == 1:
                prompt = build_step_prompt(step, plan, env)
            else:
                prompt = build_retry_prompt(step, plan, env, step.error_log[-3:], attempt)

            await self._opencode.send(prompt)

            errors = await self._validate_step(env)

            if not errors:
                commit_msg = build_commit_message(step, plan)
                sha = self._git.commit(commit_msg)
                step.status = StepStatus.SUCCESS
                logger.info("Step succeeded on attempt %d (sha=%s)", attempt, sha)
                return StepResult(
                    status=StepStatus.SUCCESS,
                    attempt=attempt,
                    files_changed=self._get_changed_files(),
                    commit_sha=sha,
                )

            step.error_log.extend(errors)
            logger.info(
                "Step failed on attempt %d/%d: %s",
                attempt, step.max_attempts, "; ".join(errors[:2]),
            )

        step.status = StepStatus.FAILED
        return StepResult(
            status=StepStatus.FAILED,
            attempt=step.max_attempts,
            errors=step.error_log,
        )

    async def _validate_step(self, env: DevEnvironment) -> list[str]:
        errors: list[str] = []

        if env.test_command:
            report = self._test_runner.run_tests(
                env.container_id, env.test_command, env.exec_cwd,
            )
            if not report.passed:
                detail = _truncate_output(report.output) or report.summary
                errors.append(
                    f"Tests failed (command: `{env.test_command}`, "
                    f"summary: {report.summary}):\n{detail}"
                )

        if env.lint_command:
            lint_result = self._test_runner.run_lint(
                env.container_id, env.lint_command, env.exec_cwd,
            )
            if not lint_result.success:
                output = _truncate_output(
                    (lint_result.stdout + "\n" + lint_result.stderr).strip()
                ) or "(no output captured)"
                errors.append(
                    f"Lint failed (command: `{env.lint_command}`, "
                    f"exit={lint_result.exit_code}):\n{output}"
                )

        if env.build_command:
            build_result = self._test_runner.run_build(
                env.container_id, env.build_command, env.exec_cwd,
            )
            if not build_result.success:
                output = _truncate_output(
                    (build_result.stdout + "\n" + build_result.stderr).strip()
                ) or "(no output captured)"
                errors.append(
                    f"Build failed (command: `{env.build_command}`, "
                    f"exit={build_result.exit_code}):\n{output}"
                )

        return errors

    def _get_changed_files(self) -> list[str]:
        try:
            diff = self._git.get_diff_summary()
            return [
                line.split("|")[0].strip()
                for line in diff.splitlines()
                if "|" in line
            ]
        except Exception:
            return []
