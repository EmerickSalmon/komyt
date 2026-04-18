"""Shared fixtures for all Komyt tests."""

from __future__ import annotations

from datetime import datetime

import pytest

from komyt.core.config import KomytConfig
from komyt.core.models import (
    CommentData,
    Complexity,
    DevEnvironment,
    DevelopmentPlan,
    DevStep,
    Priority,
    TicketContract,
    TicketData,
    TicketType,
)


# ── Configuration Fixtures ────────────────────────────


@pytest.fixture
def default_config() -> KomytConfig:
    """Return a default KomytConfig for testing."""
    return KomytConfig()


@pytest.fixture
def custom_config() -> KomytConfig:
    """Return a customized KomytConfig for testing."""
    config = KomytConfig()
    config.trigger.keyword = "@testbot"
    config.opencode.default_model = "claude-haiku-4-5"
    config.opencode.max_retries_per_step = 3
    config.analysis.clarity_threshold = 80
    return config


# ── Ticket Fixtures ───────────────────────────────────


@pytest.fixture
def sample_ticket() -> TicketData:
    """Return a well-formed sample ticket."""
    return TicketData(
        id="test-1",
        source="github",
        external_id="42",
        title="Add user authentication endpoint",
        description=(
            "@komyt Add a POST /api/auth/login endpoint that accepts "
            "email and password, validates credentials against the database, "
            "and returns a JWT token.\n\n"
            "Acceptance criteria:\n"
            "- Returns 200 with JWT on valid credentials\n"
            "- Returns 401 on invalid credentials\n"
            "- Rate limited to 5 attempts per minute\n"
            "- Unit tests required"
        ),
        labels=["feature", "backend"],
        priority=Priority.HIGH,
        ticket_type=TicketType.FEATURE,
        repo_url="https://github.com/test-org/test-repo",
        repo_branch="main",
        created_at=datetime(2026, 4, 18, 10, 0, 0),
        updated_at=datetime(2026, 4, 18, 10, 0, 0),
    )


@pytest.fixture
def vague_ticket() -> TicketData:
    """Return a vague, underspecified ticket."""
    return TicketData(
        id="test-2",
        source="github",
        external_id="43",
        title="Fix the login",
        description="@komyt The login is broken, please fix it.",
        labels=["bug"],
        priority=Priority.MEDIUM,
        ticket_type=TicketType.BUGFIX,
        repo_url="https://github.com/test-org/test-repo",
        repo_branch="main",
        created_at=datetime(2026, 4, 18, 11, 0, 0),
        updated_at=datetime(2026, 4, 18, 11, 0, 0),
    )


@pytest.fixture
def ticket_without_trigger() -> TicketData:
    """Return a ticket that does NOT contain the @komyt trigger."""
    return TicketData(
        id="test-3",
        source="github",
        external_id="44",
        title="Update README",
        description="The README needs to be updated with new API docs.",
        labels=["docs"],
        repo_url="https://github.com/test-org/test-repo",
        created_at=datetime(2026, 4, 18, 12, 0, 0),
        updated_at=datetime(2026, 4, 18, 12, 0, 0),
    )


@pytest.fixture
def ticket_with_trigger_in_comment() -> TicketData:
    """Return a ticket where @komyt appears only in a comment."""
    return TicketData(
        id="test-4",
        source="github",
        external_id="45",
        title="Refactor database layer",
        description="Move from raw SQL to SQLAlchemy ORM.",
        labels=["refactor"],
        comments=[
            CommentData(
                id="c1",
                author="emerick",
                body="@komyt This is ready to be automated.",
                created_at=datetime(2026, 4, 18, 14, 0, 0),
            )
        ],
        repo_url="https://github.com/test-org/test-repo",
        created_at=datetime(2026, 4, 18, 13, 0, 0),
        updated_at=datetime(2026, 4, 18, 14, 0, 0),
    )


# ── Contract Fixtures ─────────────────────────────────


@pytest.fixture
def complete_contract() -> TicketContract:
    """Return a fully filled TicketContract."""
    return TicketContract(
        objective="Add JWT authentication endpoint",
        ticket_type=TicketType.FEATURE,
        success_criteria=[
            "POST /api/auth/login returns JWT on valid credentials",
            "Returns 401 on invalid credentials",
            "Rate limited to 5 attempts per minute",
            "Unit tests pass",
        ],
        expected_behavior="User sends email/password, receives JWT token",
        priority=Priority.HIGH,
        estimated_complexity=Complexity.MODERATE,
    )


# ── Environment Fixtures ──────────────────────────────


@pytest.fixture
def mock_dev_environment() -> DevEnvironment:
    """Return a mock DevEnvironment."""
    return DevEnvironment(
        container_id="test-container-123",
        repo_path="/workspace/test-repo",
        branch_name="komyt/feature/add-auth",
        base_branch="main",
        language="python",
        framework="fastapi",
        test_command="pytest",
        lint_command="ruff check .",
        build_command=None,
        agent_instructions="# Test Agent Instructions\nUse pytest for testing.",
    )


# ── Development Plan Fixtures ─────────────────────────


@pytest.fixture
def sample_dev_plan(sample_ticket: TicketData, complete_contract: TicketContract) -> DevelopmentPlan:
    """Return a sample DevelopmentPlan."""
    return DevelopmentPlan(
        ticket=sample_ticket,
        contract=complete_contract,
        steps=[
            DevStep(
                id="step-1",
                description="Create auth endpoint with JWT generation",
                prompt="Implement POST /api/auth/login...",
                files_involved=["src/api/auth.py"],
            ),
            DevStep(
                id="step-2",
                description="Add rate limiting middleware",
                prompt="Add rate limiting to the auth endpoint...",
                files_involved=["src/middleware/rate_limit.py"],
            ),
            DevStep(
                id="step-3",
                description="Write unit tests",
                prompt="Write comprehensive unit tests...",
                files_involved=["tests/test_auth.py"],
            ),
        ],
        estimated_complexity=Complexity.MODERATE,
        files_to_create=["src/api/auth.py", "src/middleware/rate_limit.py", "tests/test_auth.py"],
        branch_name="komyt/feature/add-auth",
        commit_strategy="progressive",
    )
