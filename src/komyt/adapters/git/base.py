"""Base interface for git platform adapters."""

from __future__ import annotations

from typing import Protocol


class PRData:
    """Data for creating a pull request."""

    def __init__(
        self,
        title: str,
        body: str,
        head_branch: str,
        base_branch: str = "main",
        labels: list[str] | None = None,
        reviewers: list[str] | None = None,
    ) -> None:
        self.title = title
        self.body = body
        self.head_branch = head_branch
        self.base_branch = base_branch
        self.labels = labels or []
        self.reviewers = reviewers or []


class PRResult:
    """Result of PR creation."""

    def __init__(self, url: str, number: int) -> None:
        self.url = url
        self.number = number


class GitPlatformAdapter(Protocol):
    """Protocol for git platform adapters (GitHub, GitLab, Bitbucket)."""

    async def create_pr(self, repo: str, pr: PRData) -> PRResult: ...

    async def add_pr_comment(self, repo: str, pr_number: int, comment: str) -> None: ...

    async def add_pr_labels(self, repo: str, pr_number: int, labels: list[str]) -> None: ...
