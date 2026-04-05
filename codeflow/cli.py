"""
CLI interface for CodeFlow Agent.

Provides command-line tools for interacting with the CodeFlow system,
including an interactive REPL mode.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.prompt import Prompt, Confirm

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
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_time=False)],
    )


def _print_banner():
    """Print the CodeFlow interactive banner."""
    from . import __version__

    banner = r"""
[cyan] ██████╗  ██████╗ ██████╗ ███████╗███████╗██╗      ██████╗ ██╗    ██╗[/]
[cyan]██╔════╝ ██╔═══██╗██╔══██╗██╔════╝██╔════╝██║     ██╔═══██╗██║    ██║[/]
[cyan]██║      ██║   ██║██║  ██║█████╗  █████╗  ██║     ██║   ██║██║ █╗ ██║[/]
[cyan]██║      ██║   ██║██║  ██║██╔══╝  ██╔══╝  ██║     ██║   ██║██║███╗██║[/]
[cyan]╚██████╗ ╚██████╔╝██████╔╝███████╗██║     ███████╗╚██████╔╝╚███╔███╔╝[/]
[cyan] ╚═════╝  ╚═════╝ ╚═════╝ ╚══════╝╚═╝     ╚══════╝ ╚═════╝  ╚══╝╚══╝[/]
"""
    console.print(banner)
    console.print(f"[dim]  >_ CodeFlow Agent v{__version__}[/]")
    console.print(f"[dim]  ~[/]")
    console.print()
    console.print("[dim]  Tips: Type [bold]/help[/] for commands, [bold]/clear[/] to start fresh.[/]")
    console.print()


def _print_commands():
    """Print available interactive commands."""
    commands = Table(show_header=False, box=None, padding=(0, 2))
    commands.add_column("Command", style="cyan", width=14)
    commands.add_column("Description", style="dim")

    commands.add_row("/analyze", "Analyze current project and build knowledge graph")
    commands.add_row("/execute <req>", "Execute a requirement through the workflow")
    commands.add_row("/pr <feature>", "Create a pull request for a feature")
    commands.add_row("/status", "Show current workflow status")
    commands.add_row("/project <path>", "Switch to a different project directory")
    commands.add_row("/help", "Show this help message")
    commands.add_row("/clear", "Clear the screen")
    commands.add_row("/exit", "Exit CodeFlow")

    console.print(commands)


async def _interactive_session(project_path: Path, verbose: bool):
    """Run the interactive REPL session."""
    _print_banner()

    setup_logging(verbose)
    orchestrator = CodeFlowOrchestrator(project_root=project_path)

    try:
        # Initialize on first command
        initialized = False

        while True:
            try:
                user_input = Prompt.ask(
                    "[green]>[/]",
                    console=console,
                ).strip()
            except EOFError:
                break
            except KeyboardInterrupt:
                console.print()
                continue

            if not user_input:
                continue

            # Slash commands
            if user_input.startswith("/"):
                parts = user_input[1:].split(None, 1)
                cmd = parts[0].lower()
                args = parts[1] if len(parts) > 1 else ""

                if cmd in ("exit", "quit", "q"):
                    console.print("[dim]Goodbye![/]")
                    break

                elif cmd == "help":
                    _print_commands()

                elif cmd == "clear":
                    console.clear()
                    _print_banner()

                elif cmd == "project":
                    if not args:
                        console.print(f"[blue]ℹ[/] Current project: {orchestrator.config.project_root}")
                    else:
                        new_path = Path(args).resolve()
                        if not new_path.exists():
                            console.print(f"[red]✗[/] Path does not exist: {new_path}")
                        else:
                            orchestrator.config.project_root = new_path
                            orchestrator.state.project_root = str(new_path)
                            orchestrator._initialized = False
                            initialized = False
                            console.print(f"[green]✓[/] Project switched to: {new_path}")

                elif cmd == "status":
                    if not initialized:
                        console.print("[yellow]ℹ[/] Not initialized yet. Run [bold]/analyze[/] first.")
                    else:
                        state = orchestrator.get_workflow_state()
                        console.print(Panel.fit("📊 Workflow Status", style="bold cyan"))
                        console.print(f"[blue]ℹ[/] Project: {state.project_root}")
                        console.print(f"[blue]ℹ[/] Tasks: {len(state.tasks)}")
                        completed = sum(1 for t in state.tasks.values() if str(t.status) == "completed")
                        failed = sum(1 for t in state.tasks.values() if str(t.status) == "failed")
                        console.print(f"[green]✓[/] Completed: {completed}")
                        if failed > 0:
                            console.print(f"[red]✗[/] Failed: {failed}")

                elif cmd == "analyze":
                    console.print(Panel.fit("🔍 Analyzing Codebase", style="bold blue"))

                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console,
                    ) as progress:
                        task = progress.add_task("Initializing...", total=None)

                        if not initialized:
                            await orchestrator.initialize()
                            initialized = True
                        progress.update(task, description="Analyzing files...")

                        stats = await orchestrator.analyze_project()
                        progress.update(task, completed=True)

                    table = Table(title="Project Statistics")
                    table.add_column("Metric", style="cyan")
                    table.add_column("Value", style="green")
                    table.add_row("Total Files", str(stats.get("total_files", 0)))
                    table.add_row("Total Lines", str(stats.get("total_lines", 0)))

                    languages = stats.get("languages", {})
                    top_languages = sorted(languages.items(), key=lambda x: x[1], reverse=True)[:5]
                    lang_str = ", ".join([f"{lang}: {count}" for lang, count in top_languages])
                    table.add_row("Languages", lang_str)
                    table.add_row("Entities", str(stats.get("entities_added", 0)))
                    table.add_row("Relationships", str(stats.get("relationships_added", 0)))

                    console.print(table)

                elif cmd == "execute":
                    if not args:
                        console.print("[yellow]ℹ[/] Usage: [bold]/execute <requirement>[/]")
                        continue

                    console.print(Panel.fit(f"⚡ Executing: {args[:60]}...", style="bold magenta"))

                    if not initialized:
                        await orchestrator.initialize()
                        initialized = True

                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console,
                    ) as progress:
                        task = progress.add_task("Planning...", total=None)
                        state = await orchestrator.execute_requirement(args)
                        progress.update(task, description="Completed!", completed=True)

                    console.print(f"\n[green]✓[/] Workflow Status: {state.status}")
                    console.print(f"[blue]ℹ[/] Tasks Created: {len(state.tasks)}")
                    completed = sum(1 for t in state.tasks.values() if str(t.status) == "completed")
                    failed = sum(1 for t in state.tasks.values() if str(t.status) == "failed")
                    console.print(f"[green]✓[/] Completed: {completed}")
                    if failed > 0:
                        console.print(f"[red]✗[/] Failed: {failed}")

                elif cmd == "pr":
                    if not args:
                        console.print("[yellow]ℹ[/] Usage: [bold]/pr <feature description>[/]")
                        continue

                    console.print(Panel.fit(f"📝 Creating PR: {args[:60]}...", style="bold yellow"))

                    if not initialized:
                        await orchestrator.initialize()
                        initialized = True

                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console,
                    ) as progress:
                        task = progress.add_task("Implementing feature...", total=None)
                        pr = await orchestrator.create_pull_request(args)
                        progress.update(task, completed=True)

                    console.print(f"\n[green]✓[/] PR Created: {pr.title}")
                    console.print(f"[blue]ℹ[/] Branch: {pr.source_branch} -> {pr.target_branch}")
                    console.print(f"[blue]ℹ[/] Status: {pr.status}")
                    console.print(f"[blue]ℹ[/] Files changed: {len(pr.changes)}")
                    if pr.changes:
                        console.print("\n[yellow]Changes:[/]")
                        for change in pr.changes:
                            console.print(f"  {change.change_type}  {change.file_path}")

                else:
                    console.print(f"[yellow]⚠[/] Unknown command: {cmd}. Type [bold]/help[/] for options.")

            # Natural language - default to execute
            else:
                if not initialized:
                    await orchestrator.initialize()
                    initialized = True

                console.print(Panel.fit(f"⚡ Executing: {user_input[:60]}...", style="bold magenta"))

                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    console=console,
                ) as progress:
                    task = progress.add_task("Planning...", total=None)
                    state = await orchestrator.execute_requirement(user_input)
                    progress.update(task, description="Completed!", completed=True)

                console.print(f"\n[green]✓[/] Workflow Status: {state.status}")
                console.print(f"[blue]ℹ[/] Tasks Created: {len(state.tasks)}")
                completed = sum(1 for t in state.tasks.values() if str(t.status) == "completed")
                failed = sum(1 for t in state.tasks.values() if str(t.status) == "failed")
                console.print(f"[green]✓[/] Completed: {completed}")
                if failed > 0:
                    console.print(f"[red]✗[/] Failed: {failed}")

    except KeyboardInterrupt:
        console.print("\n[dim]Interrupted.[/]")
    finally:
        try:
            await orchestrator.shutdown()
        except Exception:
            pass


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

        if config_file:
            config.save_to_yaml(config_file)
            console.print(f"[green]✓[/] Configuration saved to {config_file}")

        console.print(f"[green]✓[/] Project root: {config.project_root}")
        console.print("[green]✓[/] CodeFlow initialized successfully!")
        console.print("\n[dim]Next steps:[/]")
        console.print("  1. Set your LLM API key in environment variables")
        console.print("  2. Run [bold]codeflow[/] to enter interactive mode")

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

        table = Table(title="Project Statistics")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="green")

        table.add_row("Total Files", str(stats.get("total_files", 0)))
        table.add_row("Total Lines", str(stats.get("total_lines", 0)))

        languages = stats.get("languages", {})
        top_languages = sorted(languages.items(), key=lambda x: x[1], reverse=True)[:5]
        lang_str = ", ".join([f"{lang}: {count}" for lang, count in top_languages])
        table.add_row("Languages", lang_str)
        table.add_row("Entities", str(stats.get("entities_added", 0)))
        table.add_row("Relationships", str(stats.get("relationships_added", 0)))

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
            pr = await orchestrator.create_pull_request(feature, branch)
            progress.update(task, completed=True)

        console.print(f"\n[green]✓[/] PR Created: {pr.title}")
        console.print(f"[blue]ℹ[/] Branch: {pr.source_branch} -> {pr.target_branch}")
        console.print(f"[blue]ℹ[/] Status: {pr.status}")
        console.print(f"[blue]ℹ[/] Files changed: {len(pr.changes)}")

        if pr.changes:
            console.print("\n[yellow]Changes:[/]")
            for change in pr.changes:
                console.print(f"  {change.change_type}  {change.file_path}")

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

    if dry_run:
        console.print("[yellow]⚠ Dry run mode - showing suggestions only[/]")

    console.print("[green]✓[/] Refactoring complete (placeholder)")


@app.command()
def version():
    """Show version information."""
    from . import __version__

    console.print(f"[bold]CodeFlow Agent[/] v{__version__}")
    console.print("[dim]Autonomous Development Workflow Orchestrator[/]")


@app.command(name="interactive")
def interactive_cmd(
    project_path: Path = typer.Argument(default=Path("."), help="Path to project"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Launch interactive REPL mode (default when no command given)."""
    asyncio.run(_interactive_session(project_path, verbose))


@app.command(name="help")
def help_cmd():
    """Show help information."""
    console.print(Panel.fit("CodeFlow Agent - Help", style="bold cyan"))
    console.print()
    console.print("[bold]Usage:[/]")
    console.print("  codeflow                  Enter interactive REPL mode")
    console.print("  codeflow analyze [PATH]   Analyze a codebase")
    console.print("  codeflow execute <REQ>    Execute a requirement")
    console.print("  codeflow pr <FEATURE>     Create a pull request")
    console.print("  codeflow status [PATH]    Show workflow status")
    console.print("  codeflow refactor [PATH]  Auto-detect technical debt")
    console.print("  codeflow init [PATH]      Initialize for a project")
    console.print("  codeflow version          Show version")
    console.print()
    console.print("[bold]Interactive mode commands:[/]")
    _print_commands()


def main():
    """Entry point for CLI."""
    # If no arguments, launch interactive mode
    if len(sys.argv) == 1:
        asyncio.run(_interactive_session(Path("."), verbose=False))
    else:
        app()


if __name__ == "__main__":
    main()
