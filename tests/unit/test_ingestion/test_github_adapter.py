"""Unit tests for the GitHub ticket adapter."""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
import respx

from komyt.core.config import GitHubConfig
from komyt.core.models import CommentData, TicketData
from komyt.ingestion.base import TicketFilters, TicketUpdate
from komyt.ingestion.github import GitHubTicketAdapter

OWNER = "test-org"
REPO = "test-repo"
BASE = "https://api.github.com"


def _make_issue(
    number: int = 1,
    title: str = "Test issue",
    body: str = "Issue body",
    labels: list[dict[str, str]] | None = None,
    assignee: dict[str, str] | None = None,
    has_pr: bool = False,
) -> dict:
    issue: dict = {
        "number": number,
        "title": title,
        "body": body,
        "labels": labels or [],
        "assignee": assignee,
        "user": {"login": "author"},
        "created_at": "2026-04-18T10:00:00Z",
        "updated_at": "2026-04-18T12:00:00Z",
    }
    if has_pr:
        issue["pull_request"] = {"url": "https://api.github.com/..."}
    return issue


def _make_comment(comment_id: int = 100, author: str = "reviewer", body: str = "LGTM") -> dict:
    return {
        "id": comment_id,
        "user": {"login": author},
        "body": body,
        "created_at": "2026-04-18T14:00:00Z",
    }


@pytest.fixture
def config() -> GitHubConfig:
    return GitHubConfig(token="ghp_test_token_123")


@pytest.fixture
def adapter(config: GitHubConfig) -> GitHubTicketAdapter:
    return GitHubTicketAdapter(config=config, owner=OWNER, repo=REPO)


@pytest.mark.unit
class TestFetchTickets:
    @respx.mock
    async def test_fetches_open_issues(self, adapter: GitHubTicketAdapter) -> None:
        route = respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues").mock(
            return_value=httpx.Response(200, json=[_make_issue(number=1), _make_issue(number=2)])
        )

        tickets = await adapter.fetch_tickets(TicketFilters())

        assert len(tickets) == 2
        assert tickets[0].external_id == "1"
        assert tickets[1].external_id == "2"
        assert route.called

    @respx.mock
    async def test_skips_pull_requests(self, adapter: GitHubTicketAdapter) -> None:
        respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues").mock(
            return_value=httpx.Response(
                200, json=[_make_issue(number=1), _make_issue(number=2, has_pr=True)]
            )
        )

        tickets = await adapter.fetch_tickets(TicketFilters())

        assert len(tickets) == 1
        assert tickets[0].external_id == "1"

    @respx.mock
    async def test_passes_filters_as_params(self, adapter: GitHubTicketAdapter) -> None:
        route = respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues").mock(
            return_value=httpx.Response(200, json=[])
        )

        await adapter.fetch_tickets(
            TicketFilters(labels=["bug", "urgent"], state="closed", since="2026-01-01T00:00:00Z")
        )

        request = route.calls.last.request
        assert "labels=bug%2Curgent" in str(request.url) or "labels=bug,urgent" in str(request.url)
        assert "state=closed" in str(request.url)
        assert "since=2026-01-01" in str(request.url)

    @respx.mock
    async def test_empty_response_returns_empty_list(self, adapter: GitHubTicketAdapter) -> None:
        respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues").mock(
            return_value=httpx.Response(200, json=[])
        )

        tickets = await adapter.fetch_tickets(TicketFilters())

        assert tickets == []

    @respx.mock
    async def test_normalizes_ticket_data(self, adapter: GitHubTicketAdapter) -> None:
        issue = _make_issue(
            number=42,
            title="Add auth",
            body="@komyt implement JWT auth",
            labels=[{"name": "feature"}, {"name": "backend"}],
            assignee={"login": "emerick"},
        )
        respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues").mock(
            return_value=httpx.Response(200, json=[issue])
        )

        tickets = await adapter.fetch_tickets(TicketFilters())
        t = tickets[0]

        assert t.id == f"github-{OWNER}-{REPO}-42"
        assert t.source == "github"
        assert t.external_id == "42"
        assert t.title == "Add auth"
        assert t.description == "@komyt implement JWT auth"
        assert t.labels == ["feature", "backend"]
        assert t.repo_url == f"https://github.com/{OWNER}/{REPO}"
        assert t.assignee == "emerick"
        assert t.created_at == datetime(2026, 4, 18, 10, 0, 0, tzinfo=timezone.utc)
        assert t.raw_data == issue

    @respx.mock
    async def test_handles_null_body(self, adapter: GitHubTicketAdapter) -> None:
        issue = _make_issue(number=1)
        issue["body"] = None
        respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues").mock(
            return_value=httpx.Response(200, json=[issue])
        )

        tickets = await adapter.fetch_tickets(TicketFilters())

        assert tickets[0].description == ""

    @respx.mock
    async def test_handles_null_assignee(self, adapter: GitHubTicketAdapter) -> None:
        issue = _make_issue(number=1, assignee=None)
        respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues").mock(
            return_value=httpx.Response(200, json=[issue])
        )

        tickets = await adapter.fetch_tickets(TicketFilters())

        assert tickets[0].assignee is None

    @respx.mock
    async def test_raises_on_api_error(self, adapter: GitHubTicketAdapter) -> None:
        respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues").mock(
            return_value=httpx.Response(401, json={"message": "Bad credentials"})
        )

        with pytest.raises(httpx.HTTPStatusError):
            await adapter.fetch_tickets(TicketFilters())


@pytest.mark.unit
class TestFetchComments:
    @respx.mock
    async def test_fetches_comments(self, adapter: GitHubTicketAdapter) -> None:
        respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues/42/comments").mock(
            return_value=httpx.Response(
                200,
                json=[
                    _make_comment(100, "alice", "Looks good"),
                    _make_comment(101, "bob", "@komyt go ahead"),
                ],
            )
        )

        comments = await adapter.fetch_comments("42")

        assert len(comments) == 2
        assert comments[0].id == "100"
        assert comments[0].author == "alice"
        assert comments[0].body == "Looks good"
        assert comments[1].author == "bob"

    @respx.mock
    async def test_empty_comments(self, adapter: GitHubTicketAdapter) -> None:
        respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues/1/comments").mock(
            return_value=httpx.Response(200, json=[])
        )

        comments = await adapter.fetch_comments("1")

        assert comments == []

    @respx.mock
    async def test_handles_null_comment_body(self, adapter: GitHubTicketAdapter) -> None:
        comment = _make_comment()
        comment["body"] = None
        respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues/1/comments").mock(
            return_value=httpx.Response(200, json=[comment])
        )

        comments = await adapter.fetch_comments("1")

        assert comments[0].body == ""


@pytest.mark.unit
class TestAddComment:
    @respx.mock
    async def test_posts_comment(self, adapter: GitHubTicketAdapter) -> None:
        route = respx.post(f"{BASE}/repos/{OWNER}/{REPO}/issues/42/comments").mock(
            return_value=httpx.Response(201, json={"id": 999})
        )

        await adapter.add_comment("42", "Analysis complete: score 85/100")

        assert route.called
        request = route.calls.last.request
        import json

        body = json.loads(request.content)
        assert body == {"body": "Analysis complete: score 85/100"}

    @respx.mock
    async def test_raises_on_error(self, adapter: GitHubTicketAdapter) -> None:
        respx.post(f"{BASE}/repos/{OWNER}/{REPO}/issues/42/comments").mock(
            return_value=httpx.Response(403, json={"message": "Forbidden"})
        )

        with pytest.raises(httpx.HTTPStatusError):
            await adapter.add_comment("42", "test")


@pytest.mark.unit
class TestSetLabels:
    @respx.mock
    async def test_replaces_labels(self, adapter: GitHubTicketAdapter) -> None:
        route = respx.put(f"{BASE}/repos/{OWNER}/{REPO}/issues/42/labels").mock(
            return_value=httpx.Response(200, json=[{"name": "komyt:in-progress"}])
        )

        await adapter.set_labels("42", ["komyt:in-progress"])

        assert route.called
        import json

        body = json.loads(route.calls.last.request.content)
        assert body == {"labels": ["komyt:in-progress"]}


@pytest.mark.unit
class TestUpdateTicket:
    @respx.mock
    async def test_updates_state(self, adapter: GitHubTicketAdapter) -> None:
        route = respx.patch(f"{BASE}/repos/{OWNER}/{REPO}/issues/10").mock(
            return_value=httpx.Response(200, json={})
        )

        await adapter.update_ticket("10", TicketUpdate(state="closed"))

        assert route.called
        import json

        body = json.loads(route.calls.last.request.content)
        assert body == {"state": "closed"}

    @respx.mock
    async def test_adds_and_removes_labels(self, adapter: GitHubTicketAdapter) -> None:
        respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues/10").mock(
            return_value=httpx.Response(
                200, json={"labels": [{"name": "bug"}, {"name": "triage"}]}
            )
        )
        patch_route = respx.patch(f"{BASE}/repos/{OWNER}/{REPO}/issues/10").mock(
            return_value=httpx.Response(200, json={})
        )

        await adapter.update_ticket(
            "10", TicketUpdate(labels_add=["komyt:wip"], labels_remove=["triage"])
        )

        import json

        body = json.loads(patch_route.calls.last.request.content)
        assert sorted(body["labels"]) == ["bug", "komyt:wip"]

    @respx.mock
    async def test_noop_when_no_changes(self, adapter: GitHubTicketAdapter) -> None:
        route = respx.patch(f"{BASE}/repos/{OWNER}/{REPO}/issues/10")

        await adapter.update_ticket("10", TicketUpdate())

        assert not route.called


@pytest.mark.unit
class TestContextManager:
    async def test_async_context_manager(self, config: GitHubConfig) -> None:
        async with GitHubTicketAdapter(config=config, owner=OWNER, repo=REPO) as adapter:
            assert adapter._owner == OWNER

    async def test_close(self, adapter: GitHubTicketAdapter) -> None:
        await adapter.close()
        assert adapter._client.is_closed


@pytest.mark.unit
class TestPagination:
    @respx.mock
    async def test_paginates_issues(self, adapter: GitHubTicketAdapter) -> None:
        page1 = [_make_issue(number=i) for i in range(1, 101)]
        page2 = [_make_issue(number=101), _make_issue(number=102)]

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json=page1)
            return httpx.Response(200, json=page2)

        respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues").mock(side_effect=side_effect)

        tickets = await adapter.fetch_tickets(TicketFilters())

        assert len(tickets) == 102
        assert call_count == 2

    @respx.mock
    async def test_paginates_comments(self, adapter: GitHubTicketAdapter) -> None:
        page1 = [_make_comment(comment_id=i) for i in range(1, 101)]
        page2 = [_make_comment(comment_id=101)]

        call_count = 0

        def side_effect(request: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return httpx.Response(200, json=page1)
            return httpx.Response(200, json=page2)

        respx.get(f"{BASE}/repos/{OWNER}/{REPO}/issues/1/comments").mock(
            side_effect=side_effect
        )

        comments = await adapter.fetch_comments("1")

        assert len(comments) == 101
        assert call_count == 2
