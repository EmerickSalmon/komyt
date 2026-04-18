"""Unit tests for the orchestrator."""

from __future__ import annotations

import json

import pytest

from komyt.core.config import KomytConfig
from komyt.core.models import CommentData, StepStatus, TaskStatus, TicketData
from komyt.core.orchestrator import Orchestrator, _extract_repo_slug


@pytest.mark.unit
class TestExtractRepoSlug:
    def test_https_url(self) -> None:
        assert _extract_repo_slug("https://github.com/org/repo") == "org/repo"

    def test_https_with_git(self) -> None:
        assert _extract_repo_slug("https://github.com/org/repo.git") == "org/repo"

    def test_trailing_slash(self) -> None:
        assert _extract_repo_slug("https://github.com/org/repo/") == "org/repo"
