"""Unit tests for the ticket filter (trigger keyword detection)."""

from __future__ import annotations

import pytest

from komyt.core.models import TicketData
from komyt.ingestion.base import TicketFilter


@pytest.mark.unit
class TestTicketFilter:
    def test_detects_trigger_in_description(self, sample_ticket: TicketData) -> None:
        f = TicketFilter(trigger_keyword="@komyt")
        assert f.should_process(sample_ticket) is True

    def test_ignores_ticket_without_trigger(self, ticket_without_trigger: TicketData) -> None:
        f = TicketFilter(trigger_keyword="@komyt")
        assert f.should_process(ticket_without_trigger) is False

    def test_detects_trigger_in_comment(self, ticket_with_trigger_in_comment: TicketData) -> None:
        f = TicketFilter(trigger_keyword="@komyt")
        assert f.should_process(ticket_with_trigger_in_comment) is True

    def test_case_insensitive_by_default(self, sample_ticket: TicketData) -> None:
        f = TicketFilter(trigger_keyword="@KOMYT")
        assert f.should_process(sample_ticket) is True

    def test_case_sensitive_mode(self) -> None:
        ticket = TicketData(
            id="1",
            source="github",
            external_id="1",
            title="Test",
            description="@KOMYT do something",
        )
        f = TicketFilter(trigger_keyword="@komyt", case_sensitive=True)
        assert f.should_process(ticket) is False

    def test_custom_trigger_keyword(self) -> None:
        ticket = TicketData(
            id="1",
            source="github",
            external_id="1",
            title="Test",
            description="@mybot please handle this",
        )
        f = TicketFilter(trigger_keyword="@mybot")
        assert f.should_process(ticket) is True

    def test_trigger_in_title_only(self) -> None:
        ticket = TicketData(
            id="1",
            source="github",
            external_id="1",
            title="@komyt Add new feature",
            description="Some description without trigger",
        )
        f = TicketFilter(trigger_keyword="@komyt")
        assert f.should_process(ticket) is True

    def test_empty_ticket(self) -> None:
        ticket = TicketData(
            id="1",
            source="github",
            external_id="1",
            title="",
            description="",
        )
        f = TicketFilter(trigger_keyword="@komyt")
        assert f.should_process(ticket) is False
