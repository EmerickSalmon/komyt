"""GitHub Issues adapter for ticket ingestion."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from komyt.core.config import GitHubConfig
from komyt.core.models import CommentData, TicketData
from komyt.ingestion.base import TicketFilters, TicketUpdate

logger = logging.getLogger(__name__)

API_BASE = "https://api.github.com"


class GitHubTicketAdapter:
    """Fetches and manages GitHub Issues as tickets."""

    def __init__(self, config: GitHubConfig, owner: str, repo: str) -> None:
        self._config = config
        self._owner = owner
        self._repo = repo
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {config.token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> GitHubTicketAdapter:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    def _issues_url(self) -> str:
        return f"/repos/{self._owner}/{self._repo}/issues"

    def _issue_url(self, issue_number: str) -> str:
        return f"{self._issues_url()}/{issue_number}"

    async def fetch_ticket(self, issue_number: str) -> TicketData:
        """Fetch a single issue by number."""
        resp = await self._client.get(self._issue_url(issue_number))
        resp.raise_for_status()
        ticket = self._to_ticket(resp.json())
        ticket.comments = await self.fetch_comments(issue_number)
        ticket.repo_branch = await self._default_branch()
        return ticket

    async def _default_branch(self) -> str:
        resp = await self._client.get(f"/repos/{self._owner}/{self._repo}")
        resp.raise_for_status()
        return resp.json().get("default_branch", "main")

    async def fetch_tickets(self, filters: TicketFilters) -> list[TicketData]:
        params: dict[str, str] = {"state": filters.state, "per_page": "100"}
        if filters.labels:
            params["labels"] = ",".join(filters.labels)
        if filters.since:
            params["since"] = filters.since

        tickets: list[TicketData] = []
        page = 1

        while True:
            params["page"] = str(page)
            resp = await self._client.get(self._issues_url(), params=params)
            resp.raise_for_status()
            items = resp.json()

            if not items:
                break

            for item in items:
                if "pull_request" in item:
                    continue
                tickets.append(self._to_ticket(item))

            if len(items) < 100:
                break
            page += 1

        return tickets

    async def fetch_comments(self, ticket_id: str) -> list[CommentData]:
        comments: list[CommentData] = []
        page = 1

        while True:
            resp = await self._client.get(
                f"{self._issue_url(ticket_id)}/comments",
                params={"per_page": "100", "page": str(page)},
            )
            resp.raise_for_status()
            items = resp.json()

            if not items:
                break

            for item in items:
                comments.append(
                    CommentData(
                        id=str(item["id"]),
                        author=item["user"]["login"],
                        body=item["body"] or "",
                        created_at=_parse_timestamp(item["created_at"]),
                    )
                )

            if len(items) < 100:
                break
            page += 1

        return comments

    async def update_ticket(self, ticket_id: str, update: TicketUpdate) -> None:
        url = self._issue_url(ticket_id)

        if update.state:
            resp = await self._client.patch(url, json={"state": update.state})
            resp.raise_for_status()

        if update.labels_add or update.labels_remove:
            resp = await self._client.get(url)
            resp.raise_for_status()
            current = {lbl["name"] for lbl in resp.json().get("labels", [])}
            current.update(update.labels_add)
            current -= set(update.labels_remove)
            resp = await self._client.patch(url, json={"labels": sorted(current)})
            resp.raise_for_status()

    async def add_comment(self, ticket_id: str, comment: str) -> None:
        resp = await self._client.post(
            f"{self._issue_url(ticket_id)}/comments",
            json={"body": comment},
        )
        resp.raise_for_status()

    async def set_labels(self, ticket_id: str, labels: list[str]) -> None:
        resp = await self._client.put(
            f"{self._issue_url(ticket_id)}/labels",
            json={"labels": labels},
        )
        resp.raise_for_status()

    def _to_ticket(self, issue: dict) -> TicketData:  # type: ignore[type-arg]
        number = str(issue["number"])
        repo_url = f"https://github.com/{self._owner}/{self._repo}"

        comments: list[CommentData] = []

        return TicketData(
            id=f"github-{self._owner}-{self._repo}-{number}",
            source="github",
            external_id=number,
            title=issue.get("title", ""),
            description=issue.get("body") or "",
            labels=[lbl["name"] for lbl in issue.get("labels", [])],
            repo_url=repo_url,
            assignee=(issue.get("assignee") or {}).get("login"),
            comments=comments,
            raw_data=issue,
            created_at=_parse_timestamp(issue["created_at"]),
            updated_at=_parse_timestamp(issue["updated_at"]),
        )


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
