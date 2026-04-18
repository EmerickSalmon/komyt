"""Unit tests for the test runner and output parsing."""

from __future__ import annotations

import pytest

from komyt.devloop.testing import TestReport, TestRunner, _parse_test_output
from komyt.environment.docker import ExecResult


class FakeDockerManager:
    def __init__(self, result: ExecResult | None = None) -> None:
        self._result = result or ExecResult(exit_code=0, stdout="ok", stderr="")
        self.exec_calls: list[tuple[str, str]] = []

    def exec_command(
        self, container_id: str, command: str, working_dir: str | None = None,
    ) -> ExecResult:
        self.exec_calls.append((container_id, command))
        return self._result


@pytest.mark.unit
class TestParsePytestOutput:
    def test_all_passed(self) -> None:
        result = ExecResult(
            exit_code=0,
            stdout="collected 42 items\n\n42 passed in 3.21s",
            stderr="",
        )
        report = _parse_test_output(result)

        assert report.passed is True
        assert report.total == 42
        assert report.failures == 0

    def test_with_failures(self) -> None:
        result = ExecResult(
            exit_code=1,
            stdout="10 passed, 2 failed in 1.5s",
            stderr="",
        )
        report = _parse_test_output(result)

        assert report.passed is False
        assert report.total == 12
        assert report.failures == 2

    def test_with_errors_and_skipped(self) -> None:
        result = ExecResult(
            exit_code=1,
            stdout="8 passed, 1 failed, 1 error, 2 skipped in 2.0s",
            stderr="",
        )
        report = _parse_test_output(result)

        assert report.total == 12
        assert report.failures == 1
        assert report.errors == 1
        assert report.skipped == 2


@pytest.mark.unit
class TestParseJestOutput:
    def test_jest_all_passed(self) -> None:
        result = ExecResult(
            exit_code=0,
            stdout="Tests:  15 passed, 15 total",
            stderr="",
        )
        report = _parse_test_output(result)

        assert report.passed is True
        assert report.total == 15

    def test_jest_with_failures(self) -> None:
        result = ExecResult(
            exit_code=1,
            stdout="Tests:  3 failed, 12 passed, 15 total",
            stderr="",
        )
        report = _parse_test_output(result)

        assert report.passed is False
        assert report.total == 15
        assert report.failures == 3


@pytest.mark.unit
class TestParseGoOutput:
    def test_go_pass(self) -> None:
        result = ExecResult(
            exit_code=0,
            stdout="ok  \texample.com/app\t0.123s",
            stderr="",
        )
        report = _parse_test_output(result)

        assert report.passed is True

    def test_go_fail(self) -> None:
        result = ExecResult(
            exit_code=1,
            stdout="FAIL\texample.com/app\t0.456s",
            stderr="",
        )
        report = _parse_test_output(result)

        assert report.passed is False
        assert report.failures == 1


@pytest.mark.unit
class TestParseUnknownOutput:
    def test_unparsed_success(self) -> None:
        result = ExecResult(exit_code=0, stdout="all good", stderr="")
        report = _parse_test_output(result)
        assert report.passed is True
        assert report.summary == "(unparsed output)"

    def test_unparsed_failure(self) -> None:
        result = ExecResult(exit_code=1, stdout="something broke", stderr="error")
        report = _parse_test_output(result)
        assert report.passed is False


@pytest.mark.unit
class TestTestRunner:
    def test_run_tests(self) -> None:
        docker = FakeDockerManager(ExecResult(
            exit_code=0, stdout="5 passed in 0.5s", stderr="",
        ))
        runner = TestRunner(docker=docker)  # type: ignore[arg-type]

        report = runner.run_tests("ctr-001", "pytest", "/workspace")

        assert report.passed is True
        assert report.total == 5
        assert docker.exec_calls == [("ctr-001", "pytest")]

    def test_run_lint(self) -> None:
        docker = FakeDockerManager()
        runner = TestRunner(docker=docker)  # type: ignore[arg-type]

        result = runner.run_lint("ctr-001", "ruff check .")

        assert result.success
        assert ("ctr-001", "ruff check .") in docker.exec_calls

    def test_run_build(self) -> None:
        docker = FakeDockerManager()
        runner = TestRunner(docker=docker)  # type: ignore[arg-type]

        result = runner.run_build("ctr-001", "npm run build")

        assert result.success


@pytest.mark.unit
class TestTestReport:
    def test_all_passed_property(self) -> None:
        r = TestReport(passed=True, total=10, failures=0, errors=0)
        assert r.all_passed is True

    def test_not_all_passed_with_failures(self) -> None:
        r = TestReport(passed=False, total=10, failures=2, errors=0)
        assert r.all_passed is False

    def test_not_all_passed_with_errors(self) -> None:
        r = TestReport(passed=True, total=10, failures=0, errors=1)
        assert r.all_passed is False
