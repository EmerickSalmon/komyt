"""Komyt CLI — main entry point."""

import typer
from rich.console import Console

app = typer.Typer(
    name="komyt",
    help="Komyt — Automated ticket-to-PR development pipeline.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def run(
    ticket: str = typer.Option(..., "--ticket", "-t", help="Ticket URL to process"),
) -> None:
    """Process a single ticket through the full pipeline."""
    console.print(f"[bold green]Processing ticket:[/] {ticket}")
    # TODO: Implement full pipeline
    raise NotImplementedError("Pipeline not yet implemented")


@app.command()
def analyze(
    ticket: str = typer.Option(..., "--ticket", "-t", help="Ticket URL to analyze"),
) -> None:
    """Analyze a ticket without running the dev loop (dry-run)."""
    console.print(f"[bold blue]Analyzing ticket:[/] {ticket}")
    # TODO: Implement analysis only
    raise NotImplementedError("Analysis not yet implemented")


@app.command()
def start() -> None:
    """Start the Komyt daemon (polling + automatic processing)."""
    console.print("[bold yellow]Starting Komyt daemon...[/]")
    # TODO: Implement daemon mode
    raise NotImplementedError("Daemon not yet implemented")


@app.command()
def status() -> None:
    """Show the status of running and queued tasks."""
    console.print("[bold]Task status:[/]")
    # TODO: Implement status display
    raise NotImplementedError("Status not yet implemented")


@app.command()
def history() -> None:
    """Show the history of processed tickets."""
    console.print("[bold]Processing history:[/]")
    # TODO: Implement history display
    raise NotImplementedError("History not yet implemented")


@app.command()
def gui() -> None:
    """Launch the local web dashboard."""
    console.print("[bold cyan]Starting Komyt GUI on http://127.0.0.1:8420 ...[/]")
    # TODO: Implement GUI launch
    raise NotImplementedError("GUI not yet implemented")


@app.command()
def config(
    action: str = typer.Argument(help="Action: show | set | path"),
    key: str = typer.Argument(default="", help="Config key (for set)"),
    value: str = typer.Argument(default="", help="Config value (for set)"),
) -> None:
    """Manage Komyt configuration."""
    if action == "show":
        console.print("[bold]Current configuration:[/]")
        # TODO: Show config
    elif action == "set":
        console.print(f"[bold]Setting[/] {key} = {value}")
        # TODO: Set config value
    elif action == "path":
        console.print("[bold]Config file path:[/]")
        # TODO: Show config path
    else:
        console.print(f"[red]Unknown action: {action}[/]")
    raise NotImplementedError("Config management not yet implemented")
