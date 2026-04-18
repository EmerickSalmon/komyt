"""GitHub adapter for PR creation and management."""

from __future__ import annotations

import logging

import httpx

from komyt.adapters.git.base import PRData, PRResult

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


class GitHubPlatformAdapter:
    """Creates and manages pull requests on GitHub."""

    def __init__(self, token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def create_pr(self, repo: str, pr: PRData) -> PRResult:
        payload: dict[str, object] = {
            "title": pr.title,
            "body": pr.body,
            "head": pr.head_branch,
            "base": pr.base_branch,
        }

        resp = await self._client.post(f"/repos/{repo}/pulls", json=payload)
        if resp.status_code >= 400:
            logger.error(
                "PR creation failed (%d): %s", resp.status_code, resp.text,
            )
        resp.raise_for_status()
        data = resp.json()

        result = PRResult(url=data["html_url"], number=data["number"])
        logger.info("Created PR #%d: %s", result.number, result.url)

        if pr.labels:
            await self.add_pr_labels(repo, result.number, pr.labels)

        if pr.reviewers:
            await self._request_reviewers(repo, result.number, pr.reviewers)

        return result

    async def add_pr_comment(self, repo: str, pr_number: int, comment: str) -> None:
        resp = await self._client.post(
            f"/repos/{repo}/issues/{pr_number}/comments",
            json={"body": comment},
        )
        resp.raise_for_status()

    async def add_pr_labels(self, repo: str, pr_number: int, labels: list[str]) -> None:
        resp = await self._client.post(
            f"/repos/{repo}/issues/{pr_number}/labels",
            json={"labels": labels},
        )
        resp.raise_for_status()

    async def _request_reviewers(self, repo: str, pr_number: int, reviewers: list[str]) -> None:
        resp = await self._client.post(
            f"/repos/{repo}/pulls/{pr_number}/requested_reviewers",
            json={"reviewers": reviewers},
        )
        resp.raise_for_status()
