"""Komyt CLI — main entry point."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from komyt.core.config import DEFAULT_CONFIG_FILENAME, KomytConfig, load_config, save_config

app = typer.Typer(
    name="komyt",
    help="Komyt — Automated ticket-to-PR development pipeline.",
    no_args_is_help=True,
)
console = Console()

HISTORY_FILE = Path.home() / ".komyt" / "history.json"


@app.command()
def run(
    ticket: str = typer.Option(..., "--ticket", "-t", help="Ticket URL to process"),
    config_path: str = typer.Option("", "--config", "-c", help="Path to komyt.toml"),
) -> None:
    """Process a single ticket through the full pipeline."""
    console.print(f"[bold green]Processing ticket:[/] {ticket}")
    cfg = _load_cfg(config_path)
    asyncio.run(_run_ticket(ticket, cfg))


@app.command()
def analyze(
    ticket: str = typer.Option(..., "--ticket", "-t", help="Ticket URL to analyze"),
    config_path: str = typer.Option("", "--config", "-c", help="Path to komyt.toml"),
) -> None:
    """Analyze a ticket without running the dev loop (dry-run)."""
    console.print(f"[bold blue]Analyzing ticket:[/] {ticket}")
    cfg = _load_cfg(config_path)
    asyncio.run(_analyze_ticket(ticket, cfg))


@app.command()
def start(
    config_path: str = typer.Option("", "--config", "-c", help="Path to komyt.toml"),
) -> None:
    """Start the Komyt daemon (polling + automatic processing)."""
    cfg = _load_cfg(config_path)
    console.print(
        f"[bold yellow]Starting Komyt daemon...[/]\n"
        f"  Trigger: {cfg.trigger.keyword}\n"
        f"  Poll interval: {cfg.github.poll_interval_seconds}s\n"
        f"  Model: {cfg.opencode.default_model}"
    )
    asyncio.run(_daemon_loop(cfg))


@app.command()
def status(
    config_path: str = typer.Option("", "--config", "-c", help="Path to komyt.toml"),
) -> None:
    """Show the status of running and queued tasks."""
    history = _load_history()
    active = [r for r in history if r.get("status") in ("developing", "in_progress")]

    if not active:
        console.print("[dim]No active tasks.[/]")
        return

    table = Table(title="Active Tasks")
    table.add_column("Ticket", style="bold")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Started")

    for r in active:
        table.add_row(r["ticket_id"], r.get("title", ""), r["status"], r.get("started_at", ""))
    console.print(table)


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of entries to show"),
) -> None:
    """Show the history of processed tickets."""
    records = _load_history()

    if not records:
        console.print("[dim]No history yet.[/]")
        return

    table = Table(title="Processing History")
    table.add_column("Ticket", style="bold")
    table.add_column("Title")
    table.add_column("Status")
    table.add_column("Tokens", justify="right")
    table.add_column("Duration", justify="right")
    table.add_column("PR")
    table.add_column("Date")

    for r in records[-limit:]:
        color = {"completed": "green", "failed": "red", "waiting_clarification": "yellow"}.get(
            r.get("status", ""), "white"
        )
        table.add_row(
            r.get("ticket_id", ""),
            r.get("title", "")[:40],
            f"[{color}]{r.get('status', '')}[/{color}]",
            f"{r.get('tokens', 0):,}",
            f"{r.get('duration', 0):.0f}s",
            r.get("pr_url", "") or "-",
            r.get("completed_at", ""),
        )

    console.print(table)


@app.command()
def gui(
    config_path: str = typer.Option("", "--config", "-c", help="Path to komyt.toml"),
) -> None:
    """Launch the local web dashboard."""
    import uvicorn

    from komyt.gui.app import create_app

    cfg = _load_cfg(config_path)
    console.print(
        f"[bold cyan]Starting Komyt GUI on http://{cfg.gui.host}:{cfg.gui.port} ...[/]"
    )
    web_app = create_app(config=cfg)
    uvicorn.run(web_app, host=cfg.gui.host, port=cfg.gui.port, log_level="info")


@app.command("config")
def config_cmd(
    action: str = typer.Argument("show", help="Action: show | path"),
    config_path: str = typer.Option("", "--config", "-c", help="Path to komyt.toml"),
) -> None:
    """Manage Komyt configuration."""
    if action == "show":
        cfg = _load_cfg(config_path)
        table = Table(title="Komyt Configuration")
        table.add_column("Section", style="bold")
        table.add_column("Key")
        table.add_column("Value")

        table.add_row("general", "max_parallel_tasks", str(cfg.max_parallel_tasks))
        table.add_row("general", "log_level", cfg.log_level)
        table.add_row("trigger", "keyword", cfg.trigger.keyword)
        table.add_row("trigger", "case_sensitive", str(cfg.trigger.case_sensitive))
        table.add_row("opencode", "server_url", cfg.opencode.server_url)
        table.add_row("opencode", "default_model", cfg.opencode.default_model)
        table.add_row("opencode", "max_tokens_per_task", f"{cfg.opencode.max_tokens_per_task:,}")
        table.add_row("github", "default_org", cfg.github.default_org or "(not set)")
        table.add_row("github", "poll_interval_seconds", str(cfg.github.poll_interval_seconds))
        table.add_row("docker", "default_image", cfg.docker.default_image)
        table.add_row("docker", "memory_limit", cfg.docker.memory_limit)
        table.add_row("analysis", "clarity_threshold", str(cfg.analysis.clarity_threshold))
        table.add_row("gui", "host:port", f"{cfg.gui.host}:{cfg.gui.port}")

        console.print(table)

    elif action == "path":
        paths = [
            Path(DEFAULT_CONFIG_FILENAME),
            Path.home() / ".komyt" / DEFAULT_CONFIG_FILENAME,
        ]
        for p in paths:
            if p.exists():
                console.print(f"[bold green]Found:[/] {p.resolve()}")
                return
        console.print("[yellow]No config file found. Using defaults.[/]")

    else:
        console.print(f"[red]Unknown action: {action}[/]. Use 'show' or 'path'.")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Async helpers
# ---------------------------------------------------------------------------

def _create_docker_client(cfg: KomytConfig):  # type: ignore[no-untyped-def]
    if not cfg.docker.enabled:
        from komyt.environment.local import LocalDockerClient
        return LocalDockerClient()
    try:
        from komyt.environment.docker_impl import RealDockerClient
        return RealDockerClient()
    except Exception as exc:
        console.print(f"[red]Docker unavailable:[/] {exc}")
        console.print("[dim]Set docker.enabled = false in komyt.toml to run without Docker.[/]")
        raise typer.Exit(code=1)


def _resolve_github_token(cfg: KomytConfig) -> str:
    token = cfg.github.token or os.environ.get("GITHUB_TOKEN", "")
    if not token:
        console.print("[red]Error:[/] GITHUB_TOKEN is not set. Set it via env or komyt.toml.")
        raise typer.Exit(code=1)
    cfg.github.token = token
    return token


async def _fetch_ticket(cfg: KomytConfig, ticket_url: str):  # type: ignore[no-untyped-def]
    from komyt.ingestion.github import GitHubTicketAdapter
    from komyt.utils.github_url import parse_github_issue_url

    parsed = parse_github_issue_url(ticket_url)
    console.print(f"  Repository: [bold]{parsed.owner}/{parsed.repo}[/]")
    console.print(f"  Issue: [bold]#{parsed.issue_number}[/]")

    _resolve_github_token(cfg)

    console.print("\n[dim]Fetching ticket...[/]")
    async with GitHubTicketAdapter(cfg.github, parsed.owner, parsed.repo) as adapter:
        ticket = await adapter.fetch_ticket(parsed.issue_number)

    console.print(f"  Title: [bold]{ticket.title}[/]")
    console.print(f"  Labels: {', '.join(ticket.labels) or '(none)'}")
    console.print(f"  Comments: {len(ticket.comments)}")
    return ticket, parsed


async def _analyze_ticket(ticket_url: str, cfg: KomytConfig) -> None:
    from rich.panel import Panel

    from komyt.analysis.engine import AnalysisEngine
    from komyt.llm.anthropic import create_llm_client

    ticket, _ = await _fetch_ticket(cfg, ticket_url)

    llm = create_llm_client(cfg.opencode)
    console.print(f"  LLM: [dim]{cfg.opencode.default_model} @ {cfg.opencode.server_url}[/]")
    engine = AnalysisEngine(config=cfg.analysis, llm=llm)

    console.print("\n[dim]Running analysis (LLM call)...[/]")
    try:
        result = await engine.analyze(ticket)
    finally:
        await llm.close()

    v = result.validation
    color = {"ready": "green", "needs_clarification": "yellow", "rejected": "red"}.get(
        v.status.value, "white"
    )
    console.print(f"\n  Score: [bold]{v.score}[/]/100")
    console.print(f"  Status: [bold {color}]{v.status.value.upper()}[/]")

    if result.plan:
        console.print(f"\n  Branch: [bold]{result.plan.branch_name}[/]")
        console.print(f"  Steps: {len(result.plan.steps)}")
        for i, step in enumerate(result.plan.steps, 1):
            console.print(f"    {i}. {step.description}")

    if result.feedback_comment:
        console.print()
        console.print(Panel(result.feedback_comment, title="Feedback", border_style="yellow"))


async def _run_ticket(ticket_url: str, cfg: KomytConfig) -> None:
    from komyt.adapters.git.github import GitHubPlatformAdapter
    from komyt.core.orchestrator import Orchestrator
    from komyt.ingestion.github import GitHubTicketAdapter
    from komyt.llm.anthropic import create_llm_client
    from komyt.llm.opencode_backend import LLMOpenCodeBackend
    from komyt.utils.github_url import parse_github_issue_url

    ticket, parsed = await _fetch_ticket(cfg, ticket_url)

    token = cfg.github.token
    llm = create_llm_client(cfg.opencode)
    opencode_backend = LLMOpenCodeBackend(cfg.opencode)
    git_platform = GitHubPlatformAdapter(token)

    docker_client = _create_docker_client(cfg)

    console.print(f"  LLM: [dim]{cfg.opencode.default_model} @ {cfg.opencode.server_url}[/]")
    if not cfg.docker.enabled:
        console.print("  Mode: [bold yellow]local[/] (no Docker)")
    console.print()

    async with GitHubTicketAdapter(cfg.github, parsed.owner, parsed.repo) as adapter:
        orchestrator = Orchestrator(
            config=cfg,
            ticket_adapter=adapter,
            git_platform=git_platform,
            docker_client=docker_client,
            opencode_backend=opencode_backend,
            llm_client=llm,
        )

        try:
            with console.status("[bold green]Pipeline running..."):
                result = await orchestrator.process_ticket(ticket)
        except Exception as exc:
            console.print(f"\n[red]Pipeline error:[/] {exc}")
            await llm.close()
            await opencode_backend.close()
            await git_platform.close()
            raise typer.Exit(code=1)

    await llm.close()
    await opencode_backend.close()
    await git_platform.close()

    color = {"completed": "green", "failed": "red", "waiting_clarification": "yellow"}.get(
        result.status.value, "white"
    )
    console.print(f"\n  Status: [{color}]{result.status.value.upper()}[/{color}]")
    console.print(f"  Tokens: {result.total_tokens:,}")
    console.print(f"  Cost: ${result.estimated_cost:.4f}")
    console.print(f"  Duration: {result.duration_seconds:.0f}s")
    if result.pr_url:
        console.print(f"  PR: [bold]{result.pr_url}[/]")
    if result.error_summary:
        console.print(f"  Error: [red]{result.error_summary}[/]")

    _save_history_entry({
        "ticket_id": ticket.id,
        "title": ticket.title,
        "status": result.status.value,
        "tokens": result.total_tokens,
        "cost": result.estimated_cost,
        "duration": result.duration_seconds,
        "pr_url": result.pr_url or "",
        "completed_at": datetime.now().isoformat(timespec="seconds"),
    })


async def _daemon_loop(cfg: KomytConfig) -> None:
    import signal

    from komyt.adapters.git.github import GitHubPlatformAdapter
    from komyt.core.orchestrator import Orchestrator
    from komyt.ingestion.github import GitHubTicketAdapter
    from komyt.llm.anthropic import create_llm_client
    from komyt.llm.opencode_backend import LLMOpenCodeBackend

    _resolve_github_token(cfg)

    if not cfg.github.default_org:
        console.print("[red]Error:[/] github.default_org is required for daemon mode.")
        raise typer.Exit(code=1)

    running = True

    def _stop(signum: int, frame: object) -> None:
        nonlocal running
        console.print("\n[yellow]Shutting down...[/]")
        running = False

    signal.signal(signal.SIGINT, _stop)

    llm = create_llm_client(cfg.opencode)
    opencode_backend = LLMOpenCodeBackend(cfg.opencode)
    git_platform = GitHubPlatformAdapter(cfg.github.token)
    docker_client = _create_docker_client(cfg)

    org = cfg.github.default_org
    console.print(f"\n[dim]Polling {org} every {cfg.github.poll_interval_seconds}s...[/]")
    console.print("[dim]Press Ctrl+C to stop.[/]\n")

    while running:
        repos = await _list_org_repos(cfg.github.token, org)
        total_results = []

        for repo_name in repos:
            async with GitHubTicketAdapter(cfg.github, org, repo_name) as adapter:
                orchestrator = Orchestrator(
                    config=cfg, ticket_adapter=adapter, git_platform=git_platform,
                    docker_client=docker_client, opencode_backend=opencode_backend,
                    llm_client=llm,
                )
                results = await orchestrator.poll_and_process()
                total_results.extend(results)

        if total_results:
            console.print(f"[green]Processed {len(total_results)} ticket(s)[/]")
            for r in total_results:
                _save_history_entry({
                    "ticket_id": r.ticket.id,
                    "title": r.ticket.title,
                    "status": r.status.value,
                    "tokens": r.total_tokens,
                    "cost": r.estimated_cost,
                    "duration": r.duration_seconds,
                    "pr_url": r.pr_url or "",
                    "completed_at": datetime.now().isoformat(timespec="seconds"),
                })
        else:
            console.print("[dim]No triggerable tickets found.[/]")

        for _ in range(cfg.github.poll_interval_seconds):
            if not running:
                break
            await asyncio.sleep(1)

    await llm.close()
    await opencode_backend.close()
    await git_platform.close()
    console.print("[bold]Daemon stopped.[/]")


async def _list_org_repos(token: str, org: str) -> list[str]:
    import httpx

    async with httpx.AsyncClient(
        base_url="https://api.github.com",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
        },
        timeout=30.0,
    ) as client:
        resp = await client.get(f"/orgs/{org}/repos", params={"per_page": "100"})
        if resp.status_code == 404:
            resp = await client.get(f"/users/{org}/repos", params={"per_page": "100"})
        resp.raise_for_status()
        return [r["name"] for r in resp.json()]


# ---------------------------------------------------------------------------
# History persistence (simple JSON file)
# ---------------------------------------------------------------------------

def _load_history() -> list[dict[str, object]]:
    if not HISTORY_FILE.exists():
        return []
    try:
        return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []


def _save_history_entry(entry: dict[str, object]) -> None:
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    records = _load_history()
    records.append(entry)
    HISTORY_FILE.write_text(json.dumps(records, indent=2, default=str), encoding="utf-8")


def _load_cfg(config_path: str) -> KomytConfig:
    path = Path(config_path) if config_path else None
    return load_config(path)
