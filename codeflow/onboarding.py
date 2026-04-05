"""
Onboarding flow for CodeFlow Agent.

Interactive setup wizard that guides first-time users through:
1. Selecting an LLM provider
2. Entering their API key
3. Selecting a model
4. Testing the connection
5. Saving credentials to global config (~/.codeflow/config.json)

Can also be re-run anytime via /setup command.
"""

import getpass
import logging
import os
import sys
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .config.global_config import GlobalConfig

logger = logging.getLogger(__name__)

console = Console()

# Provider metadata
PROVIDERS = [
    {
        "id": "groq",
        "name": "Groq",
        "default_model": "llama-3.3-70b-versatile",
        "key_url": "https://console.groq.com/keys",
        "free": True,
        "langchain_pkg": "langchain_groq",
        "env_var": "GROQ_API_KEY",
    },
    {
        "id": "anthropic",
        "name": "Anthropic (Claude)",
        "default_model": "claude-sonnet-4-20250514",
        "key_url": "https://console.anthropic.com",
        "free": False,
        "langchain_pkg": "langchain_anthropic",
        "env_var": "ANTHROPIC_API_KEY",
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "default_model": "gpt-4o",
        "key_url": "https://platform.openai.com/api-keys",
        "free": False,
        "langchain_pkg": "langchain_openai",
        "env_var": "OPENAI_API_KEY",
    },
    {
        "id": "google",
        "name": "Google (Gemini)",
        "default_model": "gemini-2.0-flash",
        "key_url": "https://aistudio.google.com/apikey",
        "free": True,
        "langchain_pkg": "langchain_google_genai",
        "env_var": "GOOGLE_API_KEY",
    },
    {
        "id": "ollama",
        "name": "Ollama (local, no key)",
        "default_model": "llama3",
        "key_url": "https://ollama.com",
        "free": True,
        "langchain_pkg": "langchain_openai",
        "env_var": "",
    },
]

# Available models per provider
AVAILABLE_MODELS = {
    "groq": [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant",
        "mixtral-8x7b-32768",
        "gemma2-9b-it",
    ],
    "anthropic": [
        "claude-sonnet-4-20250514",
        "claude-opus-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-5-haiku-20241022",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
    ],
    "google": [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
    ],
    "ollama": [
        "llama3",
        "llama3.1",
        "mistral",
        "qwen2.5",
    ],
}


def _show_welcome() -> None:
    """Show welcome banner."""
    console.print()
    console.print(Panel.fit(
        "[bold cyan]Welcome to CodeFlow Agent v0.1.0[/]\n\n"
        "Let's set up your first LLM provider so you can start building.\n"
        "Your API key will be stored securely in ~/.codeflow/config.json",
        border_style="cyan",
    ))
    console.print()


def _show_providers_table() -> None:
    """Display available providers."""
    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=2)
    table.add_column("Provider", style="bold")
    table.add_column("Default Model", style="dim")
    table.add_column("Free Tier", width=10)

    for i, p in enumerate(PROVIDERS, 1):
        free_tag = "[green]Yes[/]" if p["free"] else "[yellow]Paid[/]"
        table.add_row(str(i), p["name"], p["default_model"], free_tag)

    console.print(table)
    console.print()


def _safe_input(prompt_text: str, password: bool = False) -> str:
    """
    Safe input that works alongside prompt_toolkit.
    Uses sys.stdin.readline() or getpass to avoid conflicts.
    """
    try:
        if password:
            console.print(prompt_text, end="", markup=False)
            return getpass.getpass("")
        else:
            console.print(prompt_text, end="", markup=False)
            return sys.stdin.readline().strip()
    except (EOFError, KeyboardInterrupt, OSError):
        return ""


def _confirm(prompt_text: str, default: bool = True) -> bool:
    """Safe yes/no confirmation."""
    suffix = "[Y/n]" if default else "[y/N]"
    resp = _safe_input(f"{prompt_text} {suffix}: ")
    if not resp:
        return default
    return resp.strip().lower() in ("y", "yes")


def _select_provider() -> Optional[dict]:
    """Let user select a provider using safe input."""
    while True:
        choice = _safe_input("Select a provider (number or name) [1]: ")
        if not choice:
            choice = "1"

        # Try number first
        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(PROVIDERS):
                return PROVIDERS[idx]
            console.print("[red]Invalid number. Try again.[/]\n")
            continue

        # Try name match
        for p in PROVIDERS:
            if choice.lower() in p["id"] or choice.lower() in p["name"].lower():
                return p
        console.print(f"[red]Unknown provider '{choice}'. Try again.[/]\n")


def _select_model(provider_id: str) -> str:
    """Let user select a model for the chosen provider."""
    models = AVAILABLE_MODELS.get(provider_id, [])
    if not models:
        return PROVIDERS[0]["default_model"]  # fallback

    console.print(f"\n[bold]Available models for {provider_id}:[/]\n")
    for i, m in enumerate(models, 1):
        default_tag = " [green](default)[/]" if i == 1 else ""
        console.print(f"  [bold cyan]{i}[/]. {m}{default_tag}")
    console.print(f"  [dim]{len(models) + 1}[/]. Enter custom model name")
    console.print()

    while True:
        choice = _safe_input(f"Select a model [{models[0]}]: ")
        if not choice:
            return models[0]

        if choice.isdigit():
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                return models[idx]
            elif idx == len(models):
                # Custom model
                custom = _safe_input("Enter model name: ")
                if custom.strip():
                    return custom.strip()
                console.print("[red]Model name cannot be empty. Try again.[/]\n")
                continue
            console.print("[red]Invalid number. Try again.[/]\n")
            continue

        # Treat as custom model name
        return choice.strip()


def _get_api_key(provider: dict) -> Optional[str]:
    """Prompt user for their API key using safe input."""
    if provider["id"] == "ollama":
        console.print(f"\n[dim]Ollama runs locally — no API key needed. Make sure Ollama is running (ollama serve).[/]")
        return ""

    console.print(f"\n[bold]Get your API key at:[/bold] {provider['key_url']}")
    console.print(f"[dim]After signing up, create an API key and paste it below.[/]\n")

    # Check env as fallback
    env_key = os.environ.get(provider["env_var"])
    if env_key:
        console.print(f"[green]✓[/] Found {provider['name']} key from environment")
        if _confirm("Use environment key?", default=True):
            return env_key

    key = _safe_input(f"Enter your {provider['name']} API key: ", password=True)

    if not key or not key.strip():
        if env_key:
            console.print(f"[dim]Using existing key from environment[/]")
            return env_key
        console.print("[red]No key provided. Setup cancelled.[/]")
        return None

    return key.strip()


def _test_api_key(provider: dict, api_key: str, model: str) -> tuple[bool, str]:
    """
    Test the API key using langchain.

    Returns:
        (success: bool, message: str)
    """
    pid = provider["id"]

    if pid == "ollama":
        # Test Ollama local server
        try:
            import httpx
            resp = httpx.get("http://localhost:11434/api/tags", timeout=5)
            if resp.status_code == 200:
                return True, "Ollama server is running"
            return False, f"Ollama returned {resp.status_code}"
        except Exception as e:
            return False, f"Cannot connect to Ollama: {e}"

    # Use langchain to test the key
    try:
        if pid == "groq":
            from langchain_groq import ChatGroq
            llm = ChatGroq(model=model, api_key=api_key, temperature=0.0, max_tokens=5)
        elif pid == "anthropic":
            from langchain_anthropic import ChatAnthropic
            llm = ChatAnthropic(model=model, api_key=api_key, temperature=0.0, max_tokens=5)
        elif pid == "openai":
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(model=model, api_key=api_key, temperature=0.0, max_tokens=5)
        elif pid == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            llm = ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=0.0, max_tokens=5)
        else:
            return False, f"Unknown provider: {pid}"

        # Make a minimal test call
        resp = llm.invoke("Reply with exactly: OK")
        return True, f"Connected to {provider['name']} — model: {model}"

    except ImportError:
        return False, f"{provider['langchain_pkg']} not installed. Run: pip install {provider['langchain_pkg']}"
    except Exception as e:
        msg = str(e).lower()
        if any(t in msg for t in ("api_key", "unauthorized", "401", "invalid")):
            return False, "Invalid API key"
        elif any(t in msg for t in ("429", "rate limit")):
            return True, f"Key is valid but rate limited"  # Key works, just limited
        elif any(t in msg for t in ("connection", "network", "timeout")):
            return False, "Cannot reach provider. Check internet."
        else:
            return False, str(e)[:300]


async def run_onboarding_flow(global_cfg: Optional[GlobalConfig] = None) -> bool:
    """
    Run the interactive onboarding flow.

    Args:
        global_cfg: Existing global config (will load if None)

    Returns:
        True if setup succeeded
    """
    if global_cfg is None:
        global_cfg = GlobalConfig.load()

    _show_welcome()

    while True:
        _show_providers_table()

        provider = _select_provider()
        if provider is None:
            return False

        api_key = _get_api_key(provider)
        if api_key is None:
            return False

        # Select model
        console.print()
        model = _select_model(provider["id"])

        # Test the connection
        if provider["id"] != "ollama":
            console.print(f"\n[dim]Testing connection to {provider['name']}...[/]")
            success, message = _test_api_key(provider, api_key, model)
        else:
            console.print(f"[dim]Skipping connection test (ensure Ollama is running locally)[/]")
            success, message = True, "Ollama configured (local)"

        if success:
            console.print(f"\n[green]✓ Connection successful — {message}[/]\n")

            # Save to global config
            global_cfg.set_provider(provider["id"], api_key, model=model)
            console.print(f"[dim]Credentials saved to {global_cfg.config_file}[/]\n")

            # Final summary
            providers = global_cfg.list_configured_providers()
            default = global_cfg.get_default_provider()

            console.print(Panel.fit(
                f"[bold green]✓ Setup Complete![/]\n\n"
                f"Configured: [cyan]{', '.join(providers)}[/]\n"
                f"Default: [bold]{default}[/]\n"
                f"Model: [bold]{model}[/]\n"
                f"Config: [dim]{global_cfg.config_file}[/]\n\n"
                f"You're ready to go! Type [bold]/help[/] for commands.",
                border_style="green",
            ))
            console.print()

            # Ask to add another provider
            if _confirm("Configure another provider?", default=False):
                continue

            return True
        else:
            console.print(f"\n[red]✗ Connection failed: {message}[/]\n")
            if not _confirm("Try again?", default=True):
                return False

    return False


# Alias for CLI compatibility
run_setup = run_onboarding_flow
