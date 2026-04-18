"""Base interfaces for ticket ingestion adapters."""

from __future__ import annotations

from typing import Protocol

from komyt.core.models import CommentData, TicketData


class TicketFilters:
    """Filters for fetching tickets."""

    def __init__(
        self,
        labels: list[str] | None = None,
        state: str = "open",
        since: str | None = None,
    ) -> None:
        self.labels = labels or []
        self.state = state
        self.since = since


class TicketUpdate:
    """Data for updating a ticket."""

    def __init__(
        self,
        state: str | None = None,
        labels_add: list[str] | None = None,
        labels_remove: list[str] | None = None,
    ) -> None:
        self.state = state
        self.labels_add = labels_add or []
        self.labels_remove = labels_remove or []


class TicketAdapter(Protocol):
    """Protocol for ticket platform adapters."""

    async def fetch_tickets(self, filters: TicketFilters) -> list[TicketData]: ...

    async def fetch_comments(self, ticket_id: str) -> list[CommentData]: ...

    async def update_ticket(self, ticket_id: str, update: TicketUpdate) -> None: ...

    async def add_comment(self, ticket_id: str, comment: str) -> None: ...

    async def set_labels(self, ticket_id: str, labels: list[str]) -> None: ...


class TicketFilter:
    """Filters tickets based on the trigger keyword."""

    def __init__(self, trigger_keyword: str = "@komyt", case_sensitive: bool = False) -> None:
        self.trigger_keyword = trigger_keyword
        self.case_sensitive = case_sensitive

    def should_process(self, ticket: TicketData) -> bool:
        """Check if a ticket contains the trigger keyword."""
        searchable = f"{ticket.title} {ticket.description}"
        for comment in ticket.comments:
            searchable += f" {comment.body}"

        if self.case_sensitive:
            return self.trigger_keyword in searchable
        return self.trigger_keyword.lower() in searchable.lower()
