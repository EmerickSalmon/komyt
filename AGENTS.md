# AGENTS.md — Development Guide for AI Coding Agents

> This file provides comprehensive instructions for AI coding agents (Claude Code, OpenCode, etc.) working on the Komyt codebase.

## Project Overview

**Komyt** is an automated ticket-to-PR development pipeline. It fetches tickets from issue trackers, validates them against a quality contract, sets up isolated Docker environments, uses OpenCode to implement changes in an iterative loop, and delivers pull requests.

**Stack**: Python 3.12+ / asyncio / FastAPI / SQLAlchemy / Docker / OpenCode SDK

## Repository Structure

```
komyt/
├── pyproject.toml              # Project config, dependencies, tool settings
├── komyt.example.toml          # User configuration template
├── AGENTS.md                   # THIS FILE — dev instructions for AI agents
├── README.md                   # User-facing documentation
├── CONTRIBUTING.md             # Contributor guidelines
│
├── src/komyt/                  # Main source code
│   ├── __init__.py             # Package init, __version__
│   ├── __main__.py             # python -m komyt entry point
│   ├── cli.py                  # Typer CLI commands
│   │
│   ├── core/                   # Core infrastructure
│   │   ├── models.py           # All dataclasses and enums
│   │   ├── config.py           # TOML config loading/saving
│   │   ├── orchestrator.py     # Main pipeline coordinator
│   │   ├── database.py         # SQLAlchemy + SQLite
│   │   └── events.py           # Internal event system
│   │
│   ├── ingestion/              # Ticket fetching
│   │   ├── base.py             # TicketAdapter protocol + TicketFilter
│   │   └── github.py           # GitHub Issues adapter
│   │
│   ├── analysis/               # Ticket analysis
│   │   ├── engine.py           # Main analysis engine
│   │   ├── contract.py         # Contract validation & scoring
│   │   ├── clarity.py          # Clarity assessment & feedback
│   │   └── planner.py          # Dev plan generation
│   │
│   ├── environment/            # Dev environment setup
│   │   ├── manager.py          # Environment lifecycle
│   │   ├── docker.py           # Docker container management
│   │   ├── git_ops.py          # Git clone/branch/commit/push
│   │   └── detection.py        # Tech stack detection
│   │
│   ├── devloop/                # Iterative development loop
│   │   ├── loop.py             # Main loop logic
│   │   ├── opencode.py         # OpenCode SDK wrapper
│   │   ├── testing.py          # Test execution
│   │   └── prompts.py          # Prompt templates
│   │
│   ├── finalization/           # PR creation & reporting
│   │   ├── pr_creator.py       # PR creation on git platforms
│   │   ├── docs_updater.py     # Documentation updates
│   │   └── reporter.py         # Run report generation
│   │
│   ├── gui/                    # Web dashboard
│   │   ├── app.py              # FastAPI application
│   │   └── templates/          # Jinja2 HTML templates
│   │
│   └── adapters/               # Platform adapters
│       ├── git/                # Git platforms (GitHub, GitLab, ...)
│       │   ├── base.py         # GitPlatformAdapter protocol
│       │   └── github.py       # GitHub adapter
│       └── llm/
│           └── opencode.py     # OpenCode abstraction
│
├── tests/
│   ├── conftest.py             # Shared fixtures
│   ├── unit/                   # Fast, isolated tests
│   ├── functional/             # Integration tests (local resources)
│   └── e2e/                    # Full pipeline tests
│
└── docker/                     # Dockerfiles for dev environments
    ├── base/
    ├── python/
    ├── node/
    └── go/
```

## Development Conventions

### Language

- **All code, comments, docstrings, commit messages, and documentation must be in English.**
- Variable names, function names, class names: English.
- No French in the codebase.

### Python Style

- **Python 3.12+** — use modern syntax (`str | None`, `list[str]`, `match/case`, etc.)
- **Ruff** for linting and formatting (config in `pyproject.toml`)
- **mypy strict mode** for type checking
- **Line length**: 100 characters
- **Docstrings**: Google style
- **Imports**: Use `from __future__ import annotations` in every file
- **Dataclasses** for data models (in `core/models.py`)
- **Protocols** for interfaces (not abstract base classes)
- **async/await** for all I/O operations

### Code Organization Rules

1. **All data models live in `core/models.py`** — never define dataclasses in other modules
2. **Protocols live in `*/base.py` files** — each module's interface is in its `base.py`
3. **No circular imports** — core depends on nothing, modules depend on core
4. **Config is injected** — pass `KomytConfig` to constructors, don't use globals

### Dependency Hierarchy

```
core/models.py          ← depends on nothing (stdlib only)
core/config.py          ← depends on nothing (tomli/tomli_w)
core/events.py          ← depends on core/models
ingestion/base.py       ← depends on core/models
analysis/*              ← depends on core/models, core/config
environment/*           ← depends on core/models, core/config
devloop/*               ← depends on core/models, core/config, environment
finalization/*          ← depends on core/models, adapters
adapters/*              ← depends on core/models
gui/*                   ← depends on core/*, can import anything
core/orchestrator.py    ← depends on everything (top-level coordinator)
cli.py                  ← depends on core/orchestrator, core/config
```

## Testing Strategy

### CRITICAL: Every feature MUST have tests at all three levels.

### 1. Unit Tests (`tests/unit/`) — marker: `@pytest.mark.unit`

**Purpose**: Test individual functions and classes in isolation.

**Rules**:
- **Mock ALL external dependencies** (GitHub API, Docker, OpenCode, filesystem I/O)
- **No network calls, no Docker, no real files** (use `tmp_path` fixture for file tests)
- **Fast**: each test should run in < 100ms
- **Naming**: `test_<module>/test_<function_or_class>.py`
- **Coverage target**: >80% on each module

**What to test**:
- Every public function and method
- Edge cases: empty inputs, None values, invalid data
- Error handling: verify exceptions are raised correctly
- Data transformations: input → expected output

**Example pattern**:
```python
@pytest.mark.unit
class TestTicketFilter:
    def test_detects_trigger_in_description(self, sample_ticket):
        f = TicketFilter(trigger_keyword="@komyt")
        assert f.should_process(sample_ticket) is True

    def test_ignores_ticket_without_trigger(self, ticket_without_trigger):
        f = TicketFilter(trigger_keyword="@komyt")
        assert f.should_process(ticket_without_trigger) is False
```

**Mocking guidelines**:
- Use `pytest-mock` (`mocker` fixture) for mocking
- Use `respx` for mocking HTTP requests (httpx)
- Use `monkeypatch` for environment variables
- Create fixtures in `conftest.py` for reusable test data

### 2. Functional Tests (`tests/functional/`) — marker: `@pytest.mark.functional`

**Purpose**: Test module interactions with real local resources.

**Rules**:
- **May use real files, SQLite, parse real configs**
- **No network calls** — mock external APIs
- **No Docker required** (mock container operations)
- **Medium speed**: each test < 5 seconds

**What to test**:
- Config file round-trip (save → load → verify)
- Database operations (create → read → update → delete)
- Pipeline stage transitions (ingestion → analysis → plan)
- Event system (publish → subscribe → receive)
- Git operations on local test repos (use `tmp_path`)

**Example pattern**:
```python
@pytest.mark.functional
class TestAnalysisPipeline:
    async def test_clear_ticket_produces_ready_validation(self, sample_ticket, default_config):
        engine = AnalysisEngine(config=default_config, llm_client=mock_llm)
        validation = await engine.validate_ticket(sample_ticket)
        assert validation.status == ValidationStatus.READY
        assert validation.score >= 80

    async def test_vague_ticket_produces_clarification_request(self, vague_ticket, default_config):
        engine = AnalysisEngine(config=default_config, llm_client=mock_llm)
        validation = await engine.validate_ticket(vague_ticket)
        assert validation.status == ValidationStatus.NEEDS_CLARIFICATION
        assert len(validation.questions) > 0
```

### 3. End-to-End Tests (`tests/e2e/`) — marker: `@pytest.mark.e2e`

**Purpose**: Test the full system as a user would use it.

**Rules**:
- **Requires Docker running** and **OpenCode server available**
- **May make real API calls** (use a test GitHub repo)
- **Slow**: minutes per test, run sparingly
- **Use subprocess** to test CLI commands

**What to test**:
- Full CLI commands (`komyt run`, `komyt analyze`, `komyt status`)
- Complete pipeline: ticket → analysis → dev loop → PR
- GUI server starts and responds
- Error recovery: what happens when OpenCode fails mid-loop

**Example pattern**:
```python
@pytest.mark.e2e
class TestFullPipeline:
    def test_run_creates_pr(self, test_repo_url, test_issue_url):
        result = subprocess.run(
            ["komyt", "run", "--ticket", test_issue_url],
            capture_output=True, text=True, timeout=300,
        )
        assert result.returncode == 0
        assert "PR created" in result.stdout
```

### Test Fixtures

All shared fixtures are in `tests/conftest.py`. Available fixtures:
- `default_config` — default KomytConfig
- `custom_config` — customized config for edge case testing
- `sample_ticket` — well-formed ticket with @komyt trigger
- `vague_ticket` — underspecified ticket
- `ticket_without_trigger` — ticket without @komyt
- `ticket_with_trigger_in_comment` — @komyt in a comment only
- `complete_contract` — fully filled TicketContract
- `mock_dev_environment` — mock Docker environment
- `sample_dev_plan` — sample DevelopmentPlan with steps

### Running Tests

```bash
# Unit only (fast, always run these)
pytest -m unit

# Functional (moderate speed)
pytest -m functional

# E2E (slow, needs Docker + OpenCode)
pytest -m e2e

# All tests with coverage
pytest --cov=komyt --cov-report=html

# Parallel unit tests
pytest -m unit -n auto

# Specific module
pytest tests/unit/test_ingestion/
```

## Implementation Priority (MVP)

When implementing, follow this order:

### Phase 1 — Core + Ingestion
1. `core/models.py` — ✅ DONE (all dataclasses defined)
2. `core/config.py` — ✅ DONE (TOML load/save)
3. `ingestion/base.py` — ✅ DONE (TicketAdapter protocol + TicketFilter)
4. `ingestion/github.py` — Implement GitHubTicketAdapter (fetch issues, comments, add comments)
5. Unit tests for all above

### Phase 2 — Analysis
6. `analysis/contract.py` — Implement contract extraction + scoring via LLM
7. `analysis/clarity.py` — Implement feedback comment generation
8. `analysis/planner.py` — Implement DevelopmentPlan generation
9. `analysis/engine.py` — Wire everything together
10. Unit + functional tests

### Phase 3 — Environment
11. `environment/detection.py` — Stack detection (language, framework, test command)
12. `environment/docker.py` — Docker container lifecycle
13. `environment/git_ops.py` — Git clone, branch, commit, push
14. `environment/manager.py` — Wire everything together
15. Unit + functional tests

### Phase 4 — Dev Loop
16. `devloop/opencode.py` — OpenCode SDK client wrapper
17. `devloop/testing.py` — Test runner inside containers
18. `devloop/prompts.py` — Prompt templates
19. `devloop/loop.py` — Main iterative loop
20. Unit + functional tests

### Phase 5 — Finalization + Orchestrator
21. `finalization/pr_creator.py` — PR creation via GitHub adapter
22. `finalization/docs_updater.py` — Doc update via OpenCode
23. `finalization/reporter.py` — Run reports
24. `core/orchestrator.py` — Full pipeline coordinator
25. `cli.py` — Wire CLI commands to orchestrator
26. Full test suite (unit + functional + E2E)

### Phase 6 — GUI
27. `gui/app.py` — FastAPI application with routes
28. `gui/templates/` — Dashboard, ticket detail, config pages
29. SSE for real-time updates
30. E2E tests for GUI

## Key Design Decisions

### @komyt trigger
- Tickets MUST contain `@komyt` (configurable) to be processed
- Plain text matching, NOT a GitHub @mention — no bot account needed
- Searched in: title + description + all comments
- Case insensitive by default

### Contract validation
- Free-form tickets, no template required
- AI extracts a TicketContract and scores clarity (0-100)
- Score ≥ 80: proceed. Score 50-79: ask questions. Score < 50: reject with template
- AI NEVER modifies the ticket body — only adds comments

### Development loop
- Each step: code → test → lint → analyze results
- Success: commit + push immediately
- Failure: retry with error context (max 5 attempts per step)
- Token budget enforced to prevent infinite loops
- All commits go to a dedicated branch: `komyt/<type>/<short-desc>`

### Isolation
- Each ticket runs in its own Docker container
- Repo is cloned fresh inside the container
- Container is destroyed after completion (configurable)

## Common Patterns

### Adding a new ticket adapter (e.g., Jira)

1. Create `src/komyt/ingestion/jira.py`
2. Implement the `TicketAdapter` protocol from `ingestion/base.py`
3. Add config section in `core/config.py` (`JiraConfig`)
4. Register in orchestrator
5. Add unit tests in `tests/unit/test_ingestion/test_jira.py`
6. Add functional tests in `tests/functional/test_jira_integration.py`

### Adding a new git platform adapter (e.g., GitLab)

1. Create `src/komyt/adapters/git/gitlab.py`
2. Implement the `GitPlatformAdapter` protocol from `adapters/git/base.py`
3. Register in finalization module
4. Add tests

## Error Handling

- Use specific exception classes (create in `core/exceptions.py` if needed)
- Never silently swallow exceptions
- Log errors with structured context (ticket ID, step, attempt number)
- Failed pipelines should update the ticket with a clear error report
