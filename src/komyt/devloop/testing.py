"""Test execution within dev environments."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

from komyt.environment.docker import DockerManager, ExecResult

logger = logging.getLogger(__name__)


@dataclass
class TestReport:
    """Parsed result of running tests."""

    passed: bool
    total: int = 0
    failures: int = 0
    errors: int = 0
    skipped: int = 0
    output: str = ""
    summary: str = ""

    @property
    def all_passed(self) -> bool:
        return self.passed and self.failures == 0 and self.errors == 0


class TestRunner:
    """Runs tests inside a Docker container and parses results."""

    def __init__(self, docker: DockerManager) -> None:
        self._docker = docker

    def run_tests(
        self,
        container_id: str,
        test_command: str,
        working_dir: str | None = None,
    ) -> TestReport:
        logger.info("Running tests in %s: %s", container_id[:12], test_command)

        result = self._docker.exec_command(container_id, test_command, working_dir)
        report = _parse_test_output(result)

        logger.info(
            "Tests %s: %d total, %d failures, %d errors",
            "PASSED" if report.passed else "FAILED",
            report.total, report.failures, report.errors,
        )
        return report

    def run_lint(
        self,
        container_id: str,
        lint_command: str,
        working_dir: str | None = None,
    ) -> ExecResult:
        logger.info("Running lint in %s: %s", container_id[:12], lint_command)
        return self._docker.exec_command(container_id, lint_command, working_dir)

    def run_build(
        self,
        container_id: str,
        build_command: str,
        working_dir: str | None = None,
    ) -> ExecResult:
        logger.info("Running build in %s: %s", container_id[:12], build_command)
        return self._docker.exec_command(container_id, build_command, working_dir)


def _parse_test_output(result: ExecResult) -> TestReport:
    output = result.stdout + "\n" + result.stderr

    total, failures, errors, skipped = 0, 0, 0, 0
    summary = ""

    pytest_match = re.search(
        r"(\d+) passed(?:, (\d+) failed)?(?:, (\d+) error)?(?:, (\d+) skipped)? in [\d.]+s",
        output,
    )
    if pytest_match:
        passed_count = int(pytest_match.group(1))
        failures = int(pytest_match.group(2) or 0)
        errors = int(pytest_match.group(3) or 0)
        skipped = int(pytest_match.group(4) or 0)
        total = passed_count + failures + errors + skipped
        summary = pytest_match.group(0)
        return TestReport(
            passed=result.success,
            total=total,
            failures=failures,
            errors=errors,
            skipped=skipped,
            output=output,
            summary=summary,
        )

    jest_match = re.search(
        r"Tests:\s+(?:(\d+) failed,\s+)?(?:(\d+) skipped,\s+)?(\d+) passed,\s+(\d+) total",
        output,
    )
    if jest_match:
        failures = int(jest_match.group(1) or 0)
        skipped = int(jest_match.group(2) or 0)
        total = int(jest_match.group(4))
        summary = jest_match.group(0)
        return TestReport(
            passed=result.success,
            total=total,
            failures=failures,
            errors=0,
            skipped=skipped,
            output=output,
            summary=summary,
        )

    go_match = re.search(r"(ok|FAIL)\s+\S+\s+[\d.]+s", output)
    if go_match:
        passed = go_match.group(1) == "ok"
        summary = go_match.group(0)
        return TestReport(
            passed=passed,
            total=1,
            failures=0 if passed else 1,
            output=output,
            summary=summary,
        )

    return TestReport(
        passed=result.success,
        output=output,
        summary="(unparsed output)",
    )
