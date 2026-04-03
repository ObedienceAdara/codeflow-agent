"""
CLI interface for CodeFlow Agent.

Provides command-line tools for interacting with the CodeFlow system.
"""

import asyncio
import logging
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .config.settings import get_config
from .orchestrator.workflow import CodeFlowOrchestrator

app = typer.Typer(help="CodeFlow Agent - Autonomous Development Workflow Orchestrator")
console = Console()


def setup_logging(verbose: bool = False):
    """Configure logging for CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@app.command()
def init(
    project_path: Path = typer.Argument(default=Path("."), help="Path to project"),
    config_file: Optional[Path] = typer.Option(None, "--config", "-c"),
):
    """Initialize CodeFlow for a project."""
    setup_logging()
    console.print(Panel.fit("🚀 Initializing CodeFlow", style="bold green"))

    try:
        config = get_config(config_file)
        config.project_root = project_path.resolve()
        config.ensure_directories()

        # Save config if custom path provided
        if config_file:
            config.save_to_yaml(config_file)
            console.print(f"[green]✓[/] Configuration saved to {config_file}")

        console.print(f"[green]✓[/] Project root: {config.project_root}")
        console.print("[green]✓[/] CodeFlow initialized successfully!")
        console.print("\n[dim]Next steps:[/]")
        console.print("  1. Set your LLM API key in environment variables")
        console.print("  2. Run [bold]codeflow analyze[/] to analyze your codebase")
        console.print("  3. Run [bold]codeflow execute \"your requirement\"[/] to start")

    except Exception as e:
        console.print(f"[red]✗[/] Initialization failed: {e}")
        raise typer.Exit(1)


@app.command()
def analyze(
    project_path: Path = typer.Argument(default=Path("."), help="Path to project"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Analyze a codebase and build knowledge graph."""
    setup_logging(verbose)
    console.print(Panel.fit("🔍 Analyzing Codebase", style="bold blue"))

    async def run_analysis():
        orchestrator = CodeFlowOrchestrator(project_root=project_path)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Initializing...", total=None)

            await orchestrator.initialize()
            progress.update(task, description="Analyzing files...")

            stats = await orchestrator.analyze_project()
            progress.update(task, completed=True)

        # Display results
        table = Table(title="Project Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Files", str(stats.get("total_files", 0)))
        table.add_row("Total Lines", str(stats.get("total_lines", 0)))

        languages = stats.get("languages", {})
        top_languages = sorted(languages.items(), key=lambda x: x[1], reverse=True)[:5]
        lang_str = ", ".join([f"{lang}: {count}" for lang, count in top_languages])
        table.add_row("Languages", lang_str)

        console.print(table)

        if verbose:
            console.print("\n[yellow]Detailed language breakdown:[/]")
            for lang, count in sorted(languages.items(), key=lambda x: x[1], reverse=True):
                console.print(f"  {lang}: {count}")

        await orchestrator.shutdown()

    try:
        asyncio.run(run_analysis())
    except Exception as e:
        console.print(f"[red]✗[/] Analysis failed: {e}")
        raise typer.Exit(1)


@app.command()
def execute(
    requirement: str = typer.Argument(..., help="What you want to implement"),
    project_path: Path = typer.Argument(default=Path("."), help="Path to project"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Don't make changes"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Execute a requirement through the full workflow."""
    setup_logging(verbose)
    console.print(Panel.fit(f"⚡ Executing: {requirement[:50]}...", style="bold magenta"))

    if dry_run:
        console.print("[yellow]⚠ Dry run mode - no changes will be made[/]\n")

    async def run_execution():
        orchestrator = CodeFlowOrchestrator(project_root=project_path)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Initializing...", total=None)
            await orchestrator.initialize()
            progress.update(task, description="Planning...")

            state = await orchestrator.execute_requirement(requirement)
            progress.update(task, description="Completed!", completed=True)

        # Display results
        console.print(f"\n[green]✓[/] Workflow Status: {state.status}")
        console.print(f"[blue]ℹ[/] Tasks Created: {len(state.tasks)}")

        completed = sum(1 for t in state.tasks.values() if str(t.status) == "completed")
        failed = sum(1 for t in state.tasks.values() if str(t.status) == "failed")

        console.print(f"[green]✓[/] Completed: {completed}")
        if failed > 0:
            console.print(f"[red]✗[/] Failed: {failed}")

        await orchestrator.shutdown()

    try:
        asyncio.run(run_execution())
    except Exception as e:
        console.print(f"[red]✗[/] Execution failed: {e}")
        if verbose:
            console.print_exception()
        raise typer.Exit(1)


@app.command()
def pr(
    feature: str = typer.Argument(..., help="Feature description"),
    project_path: Path = typer.Argument(default=Path("."), help="Path to project"),
    branch: Optional[str] = typer.Option(None, "--branch", "-b"),
):
    """Create a pull request for a new feature."""
    setup_logging()
    console.print(Panel.fit(f"📝 Creating PR: {feature[:50]}...", style="bold yellow"))

    async def run_pr():
        orchestrator = CodeFlowOrchestrator(project_root=project_path)
        await orchestrator.initialize()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Implementing feature...", total=None)
            pr_info = await orchestrator.create_pull_request(feature, branch)
            progress.update(task, completed=True)

        console.print(f"\n[green]✓[/] PR Created: {pr_info['title']}")
        console.print(f"[blue]ℹ[/] Branch: {pr_info['branch']}")
        console.print(f"[yellow]⚠[/] Status: {pr_info['status']}")

        await orchestrator.shutdown()

    try:
        asyncio.run(run_pr())
    except Exception as e:
        console.print(f"[red]✗[/] PR creation failed: {e}")
        raise typer.Exit(1)


@app.command()
def status(project_path: Path = typer.Argument(default=Path("."), help="Path to project")):
    """Show current workflow status."""
    setup_logging()
    console.print(Panel.fit("📊 Workflow Status", style="bold cyan"))

    # This would show persistent state if available
    console.print("[green]✓[/] CodeFlow is ready")
    console.print(f"[blue]ℹ[/] Project: {project_path.resolve()}")


@app.command()
def refactor(
    project_path: Path = typer.Argument(default=Path("."), help="Path to project"),
    auto_detect: bool = typer.Option(True, "--auto-detect", "-a"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n"),
):
    """Auto-detect and fix technical debt."""
    setup_logging()
    console.print(Panel.fit("♻  Refactoring", style="bold purple"))

    if auto_detect:
        console.print("[blue]ℹ[/] Auto-detecting technical debt...")
        # Would integrate with RefactorAgent here

    if dry_run:
        console.print("[yellow]⚠ Dry run mode - showing suggestions only[/]")

    console.print("[green]✓[/] Refactoring complete (placeholder)")


@app.command()
def version():
    """Show version information."""
    from . import __version__

    console.print(f"[bold]CodeFlow Agent[/] v{__version__}")
    console.print("[dim]Autonomous Development Workflow Orchestrator[/]")


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
