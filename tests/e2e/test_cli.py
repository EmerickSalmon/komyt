"""End-to-end tests for the Komyt CLI."""

from __future__ import annotations

import subprocess

import pytest


@pytest.mark.e2e
class TestCLI:
    """Test the CLI commands via subprocess (real binary execution)."""

    def test_help_displays(self) -> None:
        result = subprocess.run(
            ["python", "-m", "komyt", "--help"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "komyt" in result.stdout.lower()

    def test_version_flag(self) -> None:
        # TODO: Add --version flag to CLI, then test it
        pass

    # TODO: Add E2E tests for full pipeline once implemented:
    # - test_run_ticket_creates_pr: submit a ticket URL, verify PR created
    # - test_analyze_ticket_dry_run: analyze without dev loop
    # - test_status_shows_running_tasks: verify status output
    # - test_gui_starts_server: verify GUI server starts on correct port
