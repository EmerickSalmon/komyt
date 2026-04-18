# Komyt

**Automated ticket-to-PR development pipeline powered by OpenCode.**

Komyt picks up tickets from your issue tracker, analyzes them, clones your repo into an isolated Docker environment, uses an AI coding agent (OpenCode) to implement the changes in an iterative code/test/commit loop, and delivers a ready-to-review pull request — fully autonomous.

## Features

- **Ticket to PR** — from issue to pull request, hands-free
- **Smart ticket analysis** — AI validates ticket clarity, asks for clarification when needed
- **Iterative dev loop** — code → test → lint → fix → commit → push, until it works
- **Isolated environments** — each ticket runs in its own Docker container
- **Provider agnostic** — works with any LLM (Anthropic, OpenAI, Google, local models via OpenCode)
- **Platform agnostic** — GitHub, GitLab, Bitbucket, Jira, Linear (GitHub first, more coming)
- **`@komyt` trigger** — only processes tickets explicitly tagged with `@komyt` in the text
- **Local web dashboard** — real-time progress tracking via FastAPI + HTMX

## Status

> **Pre-alpha** — under active development. Not yet ready for production use.

## Quick Start

### Prerequisites

- Python 3.12+
- Docker
- [OpenCode](https://opencode.ai) installed and configured
- A GitHub personal access token

### Installation

#### Bash (Linux / macOS / Git Bash)

```bash
git clone https://github.com/EmerickSalmon/komyt.git
cd komyt
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

cp komyt.example.toml komyt.toml
# Edit komyt.toml with your settings
```

#### PowerShell (Windows)

```powershell
git clone https://github.com/EmerickSalmon/komyt.git
cd komyt
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

Copy-Item komyt.example.toml komyt.toml
# Edit komyt.toml with your settings
```

### Configuration

#### Bash

```bash
export GITHUB_TOKEN="ghp_your_token_here"
opencode serve
```

#### PowerShell

```powershell
$env:GITHUB_TOKEN = "ghp_your_token_here"
opencode serve
```

### Usage

#### Bash

```bash
# Process a single ticket
komyt run --ticket https://github.com/your-org/your-repo/issues/42

# Analyze a ticket without developing (dry-run)
komyt analyze --ticket https://github.com/your-org/your-repo/issues/42

# Start the daemon (automatic polling)
komyt start

# Check task status
komyt status

# Launch the web dashboard
komyt gui

# Show configuration
komyt config
```

#### PowerShell

```powershell
# Process a single ticket
python -m komyt run --ticket https://github.com/your-org/your-repo/issues/42

# Analyze a ticket without developing (dry-run)
python -m komyt analyze --ticket https://github.com/your-org/your-repo/issues/42

# Start the daemon (automatic polling)
python -m komyt start

# Check task status
python -m komyt status

# Launch the web dashboard
python -m komyt gui

# Show configuration
python -m komyt config
```

### How the `@komyt` trigger works

Komyt only processes tickets that contain `@komyt` somewhere in the title, description, or comments. This is plain text matching — no bot account required.

```markdown
<!-- In a GitHub issue description -->
@komyt Add a GET /api/users endpoint with pagination.

Acceptance criteria:
- Pagination via offset/limit
- Filter by name
- Unit tests required
```

```markdown
<!-- Or in a comment on an existing issue -->
@komyt This ticket is ready for automated processing.
```

## Architecture

```
Ticket Source (GitHub Issues, Jira, ...)
        │
        ▼
  ┌─────────────┐
  │  Ingestion   │ ← Fetch & filter tickets (@komyt trigger)
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Analysis    │ ← Validate contract, build dev plan
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │ Environment  │ ← Clone repo, Docker container, health check
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │  Dev Loop    │ ← OpenCode: code → test → fix → commit (iterative)
  └──────┬──────┘
         ▼
  ┌─────────────┐
  │ Finalization │ ← Create PR, update docs, report results
  └─────────────┘
```

## Development

#### Bash

```bash
pip install -e ".[dev]"
pytest -m unit           # unit tests
pytest -m functional     # functional tests
pytest -m e2e            # E2E tests (requires Docker + OpenCode)
pytest                   # all tests
ruff check .             # linter
mypy src/                # type checker
```

#### PowerShell

```powershell
pip install -e ".[dev]"
python -m pytest -m unit           # unit tests
python -m pytest -m functional     # functional tests
python -m pytest -m e2e            # E2E tests (requires Docker + OpenCode)
python -m pytest                   # all tests
ruff check .                       # linter
mypy src/                          # type checker
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for more details.

## Tech Stack

- **Python 3.12+** with asyncio
- **OpenCode SDK** (`opencode-agent-sdk`) for AI coding
- **FastAPI + HTMX** for the web dashboard
- **SQLAlchemy + SQLite** for persistence
- **Docker** for isolated dev environments
- **Typer + Rich** for the CLI
- **pytest** for testing (unit, functional, E2E)

## License

MIT — see [LICENSE](LICENSE) for details.
