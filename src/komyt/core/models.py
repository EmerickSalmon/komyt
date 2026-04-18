"""Core data models for Komyt."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
import sys

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:
    from enum import Enum

    class StrEnum(str, Enum):  # type: ignore[no-redef]
        """Backport of StrEnum for Python < 3.11."""
        pass


# ── Enums ─────────────────────────────────────────────


class TicketType(StrEnum):
    FEATURE = "feature"
    BUGFIX = "bugfix"
    REFACTOR = "refactor"
    DOCS = "docs"
    CHORE = "chore"


class Priority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Complexity(StrEnum):
    TRIVIAL = "trivial"
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"


class ValidationStatus(StrEnum):
    READY = "ready"
    NEEDS_CLARIFICATION = "needs_clarification"
    REJECTED = "rejected"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    ANALYZING = "analyzing"
    WAITING_CLARIFICATION = "waiting_clarification"
    PREPARING = "preparing"
    DEVELOPING = "developing"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"


class StepStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


# ── Ticket Models ─────────────────────────────────────


@dataclass
class CommentData:
    """A comment on a ticket."""

    id: str
    author: str
    body: str
    created_at: datetime


@dataclass
class TicketData:
    """Normalized ticket data from any platform."""

    id: str
    source: str  # "github", "jira", "linear"
    external_id: str
    title: str
    description: str
    labels: list[str] = field(default_factory=list)
    priority: str = Priority.MEDIUM
    ticket_type: str = TicketType.FEATURE
    repo_url: str = ""
    repo_branch: str = "main"
    assignee: str | None = None
    comments: list[CommentData] = field(default_factory=list)
    raw_data: dict = field(default_factory=dict)  # type: ignore[type-arg]
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict = field(default_factory=dict)  # type: ignore[type-arg]


# ── Contract Models ───────────────────────────────────


@dataclass
class Scope:
    """What is included and excluded from a ticket."""

    included: list[str] = field(default_factory=list)
    excluded: list[str] = field(default_factory=list)


@dataclass
class Example:
    """An example illustrating expected behavior."""

    description: str
    input_data: str | None = None
    expected_output: str | None = None
    type: str = "behavior"  # "code", "behavior", "ui", "api"


@dataclass
class TicketContract:
    """Internal contract — what the AI needs to know to work on a ticket."""

    # Required
    objective: str = ""
    ticket_type: TicketType = TicketType.FEATURE
    success_criteria: list[str] = field(default_factory=list)

    # Important
    expected_behavior: str | None = None
    scope: Scope | None = None
    reproduction_steps: list[str] | None = None

    # Optional
    affected_files: list[str] = field(default_factory=list)
    technical_constraints: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    examples: list[Example] = field(default_factory=list)
    references: list[str] = field(default_factory=list)

    # Meta
    priority: Priority = Priority.MEDIUM
    estimated_complexity: Complexity = Complexity.MODERATE


@dataclass
class ContractValidation:
    """Result of validating a ticket against the contract."""

    score: int  # 0-100
    status: ValidationStatus
    extracted_contract: TicketContract
    filled_fields: list[str] = field(default_factory=list)
    missing_fields: list[str] = field(default_factory=list)
    ambiguities: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    confidence: float = 0.0


# ── Development Models ────────────────────────────────


@dataclass
class DevStep:
    """A single step in a development plan."""

    id: str
    description: str
    status: StepStatus = StepStatus.PENDING
    prompt: str = ""
    files_involved: list[str] = field(default_factory=list)
    attempt_count: int = 0
    max_attempts: int = 5
    error_log: list[str] = field(default_factory=list)


@dataclass
class DevelopmentPlan:
    """Structured plan for implementing a ticket."""

    ticket: TicketData
    contract: TicketContract
    steps: list[DevStep] = field(default_factory=list)
    estimated_complexity: Complexity = Complexity.MODERATE
    files_to_modify: list[str] = field(default_factory=list)
    files_to_create: list[str] = field(default_factory=list)
    tests_to_write: list[str] = field(default_factory=list)
    documentation_updates: list[str] = field(default_factory=list)
    branch_name: str = ""
    commit_strategy: str = "progressive"


@dataclass
class DevEnvironment:
    """An isolated development environment for a ticket."""

    container_id: str = ""
    repo_path: str = ""
    branch_name: str = ""
    base_branch: str = "main"
    language: str = ""
    framework: str | None = None
    test_command: str | None = None
    lint_command: str | None = None
    build_command: str | None = None
    agent_instructions: str | None = None


@dataclass
class StepResult:
    """Result of executing a single dev step."""

    status: StepStatus
    attempt: int = 0
    errors: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    commit_sha: str | None = None


@dataclass
class PipelineResult:
    """Result of the full pipeline for a ticket."""

    ticket: TicketData
    status: TaskStatus
    pr_url: str | None = None
    branch_name: str = ""
    total_steps: int = 0
    completed_steps: int = 0
    failed_steps: int = 0
    total_tokens: int = 0
    estimated_cost: float = 0.0
    duration_seconds: float = 0.0
    error_summary: str | None = None
