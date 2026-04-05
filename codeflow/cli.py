"""
CLI interface for CodeFlow Agent.

Provides command-line tools for interacting with the CodeFlow system,
including an interactive REPL mode.
"""

import asyncio
import json
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

logger = logging.getLogger(__name__)
from rich.table import Table

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

from .config.settings import get_config
from .orchestrator.workflow import CodeFlowOrchestrator

app = typer.Typer(help="CodeFlow Agent - Autonomous Development Workflow Orchestrator")
console = Console()


def setup_logging(verbose: bool = False):
    """Configure logging for CLI."""
    # Default: only show WARNING+ to console (clean output)
    # With --verbose: show INFO messages too
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_time=False, show_path=False)],
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
    commands.add_row("/setup", "Configure or change LLM provider")
    commands.add_row("/model", "Switch the model for current provider")
    commands.add_row("/status", "Show current workflow status")
    commands.add_row("/project <path>", "Switch to a different project directory")
    commands.add_row("/help", "Show this help message")
    commands.add_row("/clear", "Clear the screen")
    commands.add_row("/exit", "Exit CodeFlow")

    console.print(commands)


# Command definitions for autocomplete
COMMANDS = {
    "/analyze": "Analyze current project",
    "/execute": "Execute a requirement",
    "/pr": "Create a pull request",
    "/setup": "Configure or change LLM provider",
    "/model": "Switch the model for current provider",
    "/status": "Show workflow status",
    "/project": "Switch project directory",
    "/help": "Show help",
    "/clear": "Clear screen",
    "/exit": "Exit CodeFlow",
}


class CodeFlowCompleter(Completer):
    """Custom autocompleter for slash commands."""

    def get_completions(self, document, complete_event):
        word = document.text_before_cursor.strip()

        if word.startswith("/"):
            cmd_prefix = word.split()[0].lower()

            for full_cmd, description in COMMANDS.items():
                if full_cmd.startswith(cmd_prefix):
                    yield Completion(
                        full_cmd,
                        start_position=-len(word),
                        display=HTML(f'<cyan>{full_cmd}</cyan>'),
                        display_meta=HTML(f'<grey>- {description}</grey>'),
                    )


async def _interactive_session(project_path: Path, verbose: bool):
    """Run the interactive REPL session."""
    _print_banner()

    setup_logging(verbose)

    # Onboarding already ran synchronously before asyncio.start
    orchestrator = CodeFlowOrchestrator(project_root=project_path)

    # Set up prompt_toolkit session with autocomplete
    session = PromptSession(
        completer=CodeFlowCompleter(),
        complete_while_typing=True,
        style=Style.from_dict({
            'completion-menu.completion': 'fg:#00aaaa',
            'completion-menu.completion.current': 'bg:#00aaaa #000000',
            'completion-menu.meta.completion': 'fg:gray',
            'completion-menu.meta.completion.current': 'bg:#00aaaa #000000',
        }),
        message=HTML('<green>&gt;</green> '),
    )

    try:
        # Initialize on first command
        initialized = False

        while True:
            try:
                user_input = await session.prompt_async()
                user_input = user_input.strip()
            except EOFError:
                console.print("\n[dim]Goodbye![/]")
                return
            except KeyboardInterrupt:
                console.print("\n[dim]Goodbye![/]")
                return

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

                elif cmd == "setup":
                    console.print(Panel.fit("🔑 LLM Provider Setup", style="bold cyan"))
                    from .config.global_config import get_global_config
                    from .onboarding import PROVIDERS, _test_api_key, AVAILABLE_MODELS

                    gcfg = get_global_config()
                    if gcfg.is_configured:
                        console.print(f"Current provider: [cyan]{gcfg.default_provider}[/]")
                        for p in gcfg.list_configured_providers():
                            key_preview = f"{gcfg.get_api_key(p)[:8]}****"
                            console.print(f"  • {p}: {key_preview}")
                        console.print()

                    # Show provider list
                    console.print("[bold]Available providers:[/]")
                    for i, p in enumerate(PROVIDERS, 1):
                        free_tag = " [green](free)[/]" if p["free"] else ""
                        console.print(f"  [bold cyan]{i}[/]. {p['name']}{free_tag}")
                    console.print()

                    # Use session.prompt_async() for REPL-compatible input
                    choice = await session.prompt_async("Select provider [1]: ")
                    choice = (choice or "1").strip()
                    if choice.isdigit():
                        idx = int(choice) - 1
                        provider = PROVIDERS[idx] if 0 <= idx < len(PROVIDERS) else None
                    else:
                        provider = next((p for p in PROVIDERS if choice.lower() in p["id"]), None)

                    if not provider:
                        console.print("[red]Invalid selection.[/]")
                    elif provider["id"] == "ollama":
                        gcfg.set_provider("ollama", "", model="llama3")
                        console.print("[green]✓[/] Ollama configured (no key needed)")
                        initialized = False
                        orchestrator._initialized = False
                    else:
                        api_key = await session.prompt_async(f"Enter {provider['name']} API key: ")
                        api_key = (api_key or "").strip()
                        if not api_key:
                            console.print("[red]No key provided.[/]")
                        else:
                            models = AVAILABLE_MODELS.get(provider["id"], [])
                            model = models[0] if models else provider.get("default_model", "")
                            console.print(f"[dim]Testing connection...[/]")
                            try:
                                success, message = _test_api_key(provider, api_key, model)
                                if success:
                                    gcfg.set_provider(provider["id"], api_key, model=model)
                                    console.print(f"[green]✓ {message}[/]")
                                    console.print(f"[dim]Saved to {gcfg.config_file}[/]")
                                    initialized = False
                                    orchestrator._initialized = False
                                else:
                                    console.print(f"[red]✗ {message}[/]")
                            except Exception as e:
                                console.print(f"[red]✗ Test failed: {e}[/]")

                elif cmd == "model":
                    console.print(Panel.fit("🤖 Model Selection", style="bold cyan"))
                    from .config.global_config import get_global_config
                    from .onboarding import AVAILABLE_MODELS

                    gcfg = get_global_config()
                    if not gcfg.is_configured:
                        console.print("[yellow]No provider configured. Run /setup first.[/]")
                    else:
                        provider = gcfg.default_provider
                        current_model = gcfg.get_provider_model(provider)
                        console.print(f"Current provider: [bold]{provider}[/] — model: [bold cyan]{current_model}[/]\n")

                        models = AVAILABLE_MODELS.get(provider, [])
                        if models:
                            console.print("[bold]Available models:[/]")
                            for i, m in enumerate(models, 1):
                                tag = " [green](current)[/]" if m == current_model else ""
                                console.print(f"  [bold cyan]{i}[/]. {m}{tag}")
                            console.print(f"  [dim]{len(models) + 1}[/]. Enter custom model name")
                            console.print()

                            choice = await session.prompt_async(f"Select a model [{current_model}]: ")
                            choice = (choice or "1").strip()

                            if choice.isdigit():
                                idx = int(choice) - 1
                                if 0 <= idx < len(models):
                                    new_model = models[idx]
                                elif idx == len(models):
                                    new_model = await session.prompt_async("Enter model name: ")
                                else:
                                    console.print("[red]Invalid selection.[/]")
                                    new_model = None
                            else:
                                new_model = choice.strip()

                            if new_model and new_model.strip():
                                gcfg.set_provider(provider, gcfg.get_api_key(provider), model=new_model)
                                console.print(f"\n[green]✓[/] Model changed to: [bold]{new_model}[/]")
                                # Re-initialize orchestrator
                                initialized = False
                                orchestrator._initialized = False
                        else:
                            new_model = await session.prompt_async(f"Enter model name for {provider}: ")
                            if new_model and new_model.strip():
                                gcfg.set_provider(provider, gcfg.get_api_key(provider), model=new_model)
                                console.print(f"\n[green]✓[/] Model changed to: [bold]{new_model}[/]")

                elif cmd == "analyze":
                    console.print(Panel.fit("🔍 Analyzing Codebase", style="bold blue"))

                    if not initialized:
                        with console.status("[dim]Initializing CodeFlow...[/]"):
                            await orchestrator.initialize()
                        initialized = True

                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        console=console,
                    ) as progress:
                        task = progress.add_task("Analyzing files...", total=None)
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

                    if not initialized:
                        with console.status("[dim]Initializing CodeFlow...[/]"):
                            await orchestrator.initialize()
                        initialized = True

                    console.print(Panel.fit(f"⚡ Executing: {args[:60]}...", style="bold magenta"))

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

                    if not initialized:
                        with console.status("[dim]Initializing CodeFlow...[/]"):
                            await orchestrator.initialize()
                        initialized = True

                    console.print(Panel.fit(f"📝 Creating PR: {args[:60]}...", style="bold yellow"))

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
                # Reserved words that look like commands
                reserved = {"help", "exit", "quit", "status", "clear", "cls", "version"}
                if user_input.lower() in reserved:
                    console.print(f"[yellow]ℹ[/] Type [bold]/{user_input}[/] for commands.")
                    continue

                if not initialized:
                    with console.status("[dim]Initializing CodeFlow...[/]"):
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
    console.print(f"[blue]ℹ[/] Project: {project_path.resolve()}")
    console.print("[green]✓[/] CodeFlow Agent ready")

    # Check for LLM configuration
    import os
    provider = os.environ.get("LLM_PROVIDER", "not configured")
    api_key_set = bool(os.environ.get(f"{provider.upper()}_API_KEY"))
    if api_key_set:
        console.print(f"[green]✓[/] LLM: {provider} (API key configured)")
    else:
        console.print(f"[yellow]⚠[/] LLM: {provider} (no API key found)")


@app.command()
def refactor(
    project_path: Path = typer.Argument(default=Path("."), help="Path to project"),
    auto_detect: bool = typer.Option(True, "--auto-detect", "-a"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n"),
):
    """Auto-detect and fix technical debt."""
    setup_logging()
    console.print(Panel.fit("♻  Refactoring", style="bold purple"))

    from .core.code_smell_detector import CodeSmellDetector, SmellConfig

    detector = CodeSmellDetector(SmellConfig())
    smells_found = 0
    files_scanned = 0

    if auto_detect:
        console.print("[blue]ℹ[/] Auto-detecting technical debt...")

        # Scan Python files
        for py_file in project_path.rglob("*.py"):
            if any(part.startswith(".") for part in py_file.parts):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                smells = detector.detect_all(str(py_file.relative_to(project_path)), content)
                smells_found += len(smells)
                files_scanned += 1

                if dry_run and smells:
                    for smell in smells:
                        console.print(
                            f"[yellow]{smell.severity.value.upper()}[/] "
                            f"[bold]{smell.name}[/] in {smell.file_path}:{smell.line_start} — "
                            f"{smell.description}"
                        )
            except Exception as e:
                logger.debug(f"Failed to scan {py_file}: {e}")

    console.print(f"[green]✓[/] Scanned {files_scanned} files, found {smells_found} code smell(s)")

    if dry_run and smells_found > 0:
        console.print("[yellow]⚠ Dry run mode — run without --dry-run to apply fixes[/]")


@app.command()
def version():
    """Show version information."""
    from . import __version__

    console.print(f"[bold]CodeFlow Agent[/] v{__version__}")
    console.print("[dim]Autonomous Development Workflow Orchestrator[/]")


def _run_pre_repl_onboarding() -> None:
    """
    Run onboarding synchronously BEFORE the async REPL starts.
    input() and getpass() are blocking and incompatible with asyncio.run().
    """
    try:
        from .config.global_config import get_global_config
        gcfg = get_global_config()
        if gcfg.is_configured:
            return  # Already configured, skip
    except Exception:
        return  # Can't check config, skip

    # Run onboarding synchronously
    console.print("[yellow]No LLM provider configured. Let's set that up.[/]\n")

    try:
        import getpass
        from .onboarding import (
            _show_welcome, _show_providers_table, _select_model,
            _test_api_key, AVAILABLE_MODELS, PROVIDERS,
        )
        from .config.global_config import get_global_config

        gcfg = get_global_config()
        _show_welcome()

        while True:
            _show_providers_table()
            choice = input("Select a provider (number or name) [1]: ").strip() or "1"

            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(PROVIDERS):
                    provider = PROVIDERS[idx]
                else:
                    console.print("[red]Invalid number. Try again.[/]\n")
                    continue
            else:
                found = None
                for p in PROVIDERS:
                    if choice.lower() in p["id"] or choice.lower() in p["name"].lower():
                        found = p
                        break
                if found:
                    provider = found
                else:
                    console.print(f"[red]Unknown provider '{choice}'. Try again.[/]\n")
                    continue

            if provider["id"] == "ollama":
                api_key = ""
                console.print("[dim]Ollama runs locally — no API key needed.[/]")
            else:
                console.print(f"\n[bold]Get your API key at: {provider['key_url']}[/bold]")
                api_key = getpass.getpass(f"Enter your {provider['name']} API key: ").strip()

            if not api_key and provider["id"] != "ollama":
                console.print("[red]No key provided. Try again.[/]\n")
                continue

            model = _select_model(provider["id"])
            console.print(f"\n[dim]Testing connection to {provider['name']}...[/]")
            success, message = _test_api_key(provider, api_key, model)

            if success:
                console.print(f"\n[green]✓ Connection successful — {message}[/]\n")
                gcfg.set_provider(provider["id"], api_key, model=model)
                console.print(f"[dim]Credentials saved to {gcfg.config_file}[/]\n")

                providers = gcfg.list_configured_providers()
                default = gcfg.get_default_provider()
                console.print(Panel.fit(
                    f"[bold green]✓ Setup Complete![/]\n\n"
                    f"Configured: [cyan]{', '.join(providers)}[/]\n"
                    f"Default: [bold]{default}[/]\n"
                    f"Model: [bold]{model}[/]\n"
                    f"You're ready to go!",
                    border_style="green",
                ))
                console.print()
                break
            else:
                console.print(f"\n[red]✗ Connection failed: {message}[/]\n")
                retry = input("Try again? [Y/n]: ").strip().lower()
                if retry not in ("", "y", "yes"):
                    console.print("[yellow]Continuing without API key. Use /setup to configure later.[/]\n")
                    break

    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Setup cancelled.[/]\n")
    except Exception as e:
        console.print(f"[dim]Onboarding skipped: {e}[/]\n", markup=False)


@app.command(name="interactive")
def interactive_cmd(
    project_path: Path = typer.Argument(default=".", help="Path to project"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Launch interactive REPL mode (default when no command given)."""
    _run_pre_repl_onboarding()
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
    # Run onboarding BEFORE asyncio (input()/getpass block inside async)
    _run_pre_repl_onboarding()

    # If no arguments, launch interactive mode
    if len(sys.argv) == 1:
        try:
            asyncio.run(_interactive_session(Path("."), verbose=False))
        except (KeyboardInterrupt, EOFError, SystemExit):
            console.print("\n[dim]Goodbye![/]")
        except asyncio.CancelledError:
            pass  # Asyncio cancellation during shutdown
        except Exception as e:
            console.print(f"\n[red]Fatal error:[/] {e}")
            sys.exit(1)
    else:
        app()


if __name__ == "__main__":
    main()
