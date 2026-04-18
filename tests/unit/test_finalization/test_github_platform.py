"""Unit tests for the GitHub platform adapter (PR creation)."""

from __future__ import annotations

import httpx
import pytest
import respx

from komyt.adapters.git.base import PRData, PRResult
from komyt.adapters.git.github import GitHubPlatformAdapter

BASE = "https://api.github.com"
REPO = "org/repo"


@pytest.fixture
def adapter() -> GitHubPlatformAdapter:
    return GitHubPlatformAdapter(token="ghp_test_token")


@pytest.mark.unit
class TestGitHubPlatformAdapter:
    @respx.mock
    async def test_create_pr(self, adapter: GitHubPlatformAdapter) -> None:
        respx.post(f"{BASE}/repos/{REPO}/pulls").mock(
            return_value=httpx.Response(201, json={
                "html_url": f"https://github.com/{REPO}/pull/42",
                "number": 42,
            })
        )

        pr_data = PRData(
            title="feat: add auth",
            body="## Summary\nAdd auth",
            head_branch="komyt/feature/auth",
            base_branch="main",
        )
        result = await adapter.create_pr(REPO, pr_data)

        assert result.url == f"https://github.com/{REPO}/pull/42"
        assert result.number == 42

    @respx.mock
    async def test_create_pr_with_labels(self, adapter: GitHubPlatformAdapter) -> None:
        respx.post(f"{BASE}/repos/{REPO}/pulls").mock(
            return_value=httpx.Response(201, json={
                "html_url": f"https://github.com/{REPO}/pull/1",
                "number": 1,
            })
        )
        label_route = respx.post(f"{BASE}/repos/{REPO}/issues/1/labels").mock(
            return_value=httpx.Response(200, json=[])
        )

        pr_data = PRData(
            title="fix: bug", body="fix", head_branch="fix/bug",
            labels=["komyt", "bugfix"],
        )
        await adapter.create_pr(REPO, pr_data)

        assert label_route.called

    @respx.mock
    async def test_create_pr_with_reviewers(self, adapter: GitHubPlatformAdapter) -> None:
        respx.post(f"{BASE}/repos/{REPO}/pulls").mock(
            return_value=httpx.Response(201, json={
                "html_url": f"https://github.com/{REPO}/pull/1",
                "number": 1,
            })
        )
        reviewer_route = respx.post(
            f"{BASE}/repos/{REPO}/pulls/1/requested_reviewers"
        ).mock(return_value=httpx.Response(201, json={}))

        pr_data = PRData(
            title="feat: test", body="test", head_branch="feat/test",
            reviewers=["reviewer1"],
        )
        await adapter.create_pr(REPO, pr_data)

        assert reviewer_route.called

    @respx.mock
    async def test_add_pr_comment(self, adapter: GitHubPlatformAdapter) -> None:
        route = respx.post(f"{BASE}/repos/{REPO}/issues/42/comments").mock(
            return_value=httpx.Response(201, json={"id": 1})
        )

        await adapter.add_pr_comment(REPO, 42, "LGTM")

        assert route.called
        import json
        body = json.loads(route.calls.last.request.content)
        assert body == {"body": "LGTM"}

    @respx.mock
    async def test_add_pr_labels(self, adapter: GitHubPlatformAdapter) -> None:
        route = respx.post(f"{BASE}/repos/{REPO}/issues/10/labels").mock(
            return_value=httpx.Response(200, json=[])
        )

        await adapter.add_pr_labels(REPO, 10, ["komyt", "feature"])

        assert route.called

    @respx.mock
    async def test_raises_on_error(self, adapter: GitHubPlatformAdapter) -> None:
        respx.post(f"{BASE}/repos/{REPO}/pulls").mock(
            return_value=httpx.Response(422, json={"message": "Validation failed"})
        )

        pr_data = PRData(title="t", body="b", head_branch="h")
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.create_pr(REPO, pr_data)
