# Contributing to Komyt

Thank you for your interest in contributing to Komyt! This document provides guidelines and instructions for contributing.

## Development Setup

### Prerequisites

- Python 3.12 or higher
- Docker (for running isolated dev environments)
- [OpenCode](https://opencode.ai) (for the AI coding agent)
- Git

### Getting Started

```bash
# Fork and clone the repository
git clone https://github.com/<your-username>/komyt.git
cd komyt

# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Verify installation
komyt --help
pytest -m unit
```

## Code Style

- **Formatter & Linter**: [Ruff](https://docs.astral.sh/ruff/) — configured in `pyproject.toml`
- **Type Checker**: [mypy](https://mypy.readthedocs.io/) with strict mode
- **Line length**: 100 characters
- **Code language**: English (variable names, functions, comments, docstrings)
- **Docstrings**: Google style

Run before committing:

```bash
ruff check .
ruff format .
mypy src/
```

## Testing

Komyt uses three levels of testing:

### Unit Tests (`pytest -m unit`)

Fast, isolated tests with no external dependencies. Mock all I/O.

- Located in `tests/unit/`
- Run in milliseconds
- Required for all new code
- Target: >80% coverage on new modules

### Functional Tests (`pytest -m functional`)

Tests that verify module integration with real (local) resources.

- Located in `tests/functional/`
- May read/write files, use SQLite, parse real configs
- No network calls, no Docker required

### E2E Tests (`pytest -m e2e`)

Full pipeline tests that exercise the real system.

- Located in `tests/e2e/`
- Require Docker and OpenCode server running
- Slower, run less frequently
- Test actual CLI commands via subprocess

### Running Tests

```bash
# All tests
pytest

# By level
pytest -m unit
pytest -m functional
pytest -m e2e

# With coverage
pytest -m unit --cov=komyt --cov-report=html

# Parallel execution
pytest -m unit -n auto
```

## Branch Naming

- `feature/<short-description>` — new features
- `fix/<short-description>` — bug fixes
- `refactor/<short-description>` — code refactoring
- `docs/<short-description>` — documentation updates

## Commit Messages

Use clear, imperative commit messages:

```
Add ticket contract validation engine

Implement the TicketContract extraction and scoring system.
The engine evaluates ticket clarity on a 0-100 scale and generates
feedback comments for unclear tickets.
```

## Pull Requests

- Keep PRs focused on a single concern
- Include tests for new functionality
- Update documentation if relevant
- Ensure all CI checks pass
- Reference the related issue if applicable

## Architecture

See [AGENTS.md](AGENTS.md) for a detailed guide to the codebase architecture and development instructions.

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
