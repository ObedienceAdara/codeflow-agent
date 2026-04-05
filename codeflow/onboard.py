"""
Onboarding flow for CodeFlow Agent.

Interactive setup wizard that guides first-time users through:
1. Selecting an LLM provider
2. Entering their API key
3. Testing the connection
4. Saving credentials to global config (~/.codeflow/config.json)

Can also be re-run anytime via /setup command.
"""

import logging
import sys
import time
from typing import Optional

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.prompt import Prompt, Confirm
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

from .config.global_config import GlobalConfig

logger = logging.getLogger(__name__)

console = Console() if RICH_AVAILABLE else None


def _print(text: str, style: str = "") -> None:
    """Print with optional styling."""
    if RICH_AVAILABLE and console:
        console.print(text, style=style)
    else:
        print(text)


def _panel(title: str, body: str, style: str = "cyan") -> None:
    """Print a Rich panel."""
    if RICH_AVAILABLE and console:
        console.print(Panel(f"[bold]{title}[/]\n\n{body}", style=style))
    else:
        print(f"\n{'=' * 60}\n{title}\n{'=' * 60}\n{body}\n")


def _prompt_key(provider: str) -> str:
    """Prompt the user to enter their API key, with masking if possible."""
    _print(f"\nEnter your {provider.upper()} API key:", style="bold yellow")
    _print("(It won't be shown as you type)" if RICH_AVAILABLE else "(Input hidden)")

    try:
        if RICH_AVAILABLE:
            return Prompt.ask("API Key", password=True)
        else:
            import getpass
            return getpass.getpass("API Key: ")
    except (KeyboardInterrupt, EOFError):
        _print("\n\nSetup cancelled.", style="red")
        raise SystemExit(0)


def _test_api_key(provider: str, api_key: str) -> tuple[bool, str]:
    """
    Test the API key by making a minimal request.

    Returns:
        (success: bool, message: str)
    """
    _print(f"\nTesting connection to {provider}...", style="dim")

    try:
        if provider == "groq":
            return _test_groq(api_key)
        elif provider == "anthropic":
            return _test_anthropic(api_key)
        elif provider == "openai":
            return _test_openai(api_key)
        elif provider == "google":
            return _test_google(api_key)
        elif provider == "ollama":
            return _test_ollama()
        else:
            return False, f"Unknown provider: {provider}"
    except ImportError as e:
        return False, f"Missing dependency: {e}. Run: pip install langchain-{provider}"
    except Exception as e:
        return False, f"Connection failed: {e}"


def _test_groq(api_key: str) -> tuple[bool, str]:
    """Test Groq API key."""
    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[{"role": "user", "content": "Say 'connected' in exactly one word."}],
            max_tokens=5,
            temperature=0.0,
        )
        return True, f"Groq OK — model: llama-3.3-70b-versatile"
    except Exception as e:
        return False, str(e)


def _test_anthropic(api_key: str) -> tuple[bool, str]:
    """Test Anthropic API key."""
    try:
        import httpx
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-sonnet-4-20250514",
                "max_tokens": 5,
                "messages": [{"role": "user", "content": "Say 'connected' in one word."}],
            },
            timeout=30,
        )
        if response.status_code == 200:
            return True, "Anthropic OK"
        elif response.status_code == 401:
            return False, "Invalid API key (401 Unauthorized)"
        else:
            return False, f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, str(e)


def _test_openai(api_key: str) -> tuple[bool, str]:
    """Test OpenAI API key."""
    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "Say 'connected' in one word."}],
            max_tokens=5,
        )
        return True, f"OpenAI OK — model: gpt-4o-mini"
    except Exception as e:
        return False, str(e)


def _test_google(api_key: str) -> tuple[bool, str]:
    """Test Google (Gemini) API key."""
    try:
        import httpx
        response = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}",
            headers={"Content-Type": "application/json"},
            json={
                "contents": [{"parts": [{"text": "Say 'connected' in one word."}]}],
            },
            timeout=30,
        )
        if response.status_code == 200:
            return True, "Google OK"
        elif response.status_code == 400 or response.status_code == 403:
            return False, f"Invalid API key ({response.status_code})"
        else:
            return False, f"HTTP {response.status_code}: {response.text[:200]}"
    except Exception as e:
        return False, str(e)


def _test_ollama() -> tuple[bool, str]:
    """Test Ollama local server."""
    try:
        import httpx
        response = httpx.get("http://localhost:11434/api/tags", timeout=5)
        if response.status_code == 200:
            return True, "Ollama server running locally"
        return False, f"Ollama returned HTTP {response.status_code}"
    except Exception:
        return False, "Cannot connect to Ollama at localhost:11434. Is it running?"


def run_onboarding(
    global_cfg: Optional[GlobalConfig] = None,
    add_another: bool = False,
) -> GlobalConfig:
    """
    Run the interactive onboarding flow.

    Args:
        global_cfg: Existing global config, or None for fresh setup
        add_another: If True, skip welcome screen and go straight to provider add

    Returns:
        Updated GlobalConfig instance
    """
    if global_cfg is None:
        global_cfg = GlobalConfig.load()

    if not add_another:
        _panel(
            "🚀 Welcome to CodeFlow Agent v0.1.0",
            "Let's set up your LLM provider so you can start building.\n\n"
            "You'll need an API key from one of the supported providers.\n"
            "Don't have one? You can get free keys from:\n"
            "  • Groq:     https://console.groq.com/keys\n"
            "  • OpenAI:   https://platform.openai.com/api-keys\n"
            "  • Google:   https://aistudio.google.com/apikey\n"
            "  • Anthropic: https://console.anthropic.com/\n"
            "  • Ollama:   Runs locally, no key needed (install from ollama.com)",
            style="cyan",
        )

    while True:
        # Show provider list
        providers = list(GlobalConfig.SUPPORTED_PROVIDERS.keys())
        _print("\nAvailable providers:", style="bold")
        for i, p in enumerate(providers, 1):
            info = GlobalConfig.SUPPORTED_PROVIDERS[p]
            default_model = info.get("default_model", "N/A")
            needs_key = "No API key needed" if p == "ollama" else f"Requires API key"
            configured = " ✓ configured" if global_cfg.has_api_key(p) else ""
            _print(f"  {i}. {p:12s} ({default_model}) — {needs_key}{configured}")

        # Provider selection
        try:
            choice = Prompt.ask(
                "\nSelect a provider (number or name)",
                default=str(providers.index(global_cfg.get_default_provider()) + 1)
                if global_cfg.is_configured()
                else "1",
            )

            # Parse choice
            if choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(providers):
                    provider = providers[idx]
                else:
                    _print("Invalid number. Try again.", style="red")
                    continue
            else:
                provider = choice.lower().strip()
                if provider not in providers:
                    _print(f"Unknown provider: {provider}. Try again.", style="red")
                    continue
        except (KeyboardInterrupt, EOFError):
            _print("\n\nSetup cancelled.", style="yellow")
            return global_cfg

        # For non-Ollama providers, prompt for API key
        api_key = ""
        if provider != "ollama":
            api_key = _prompt_key(provider)
            if not api_key.strip():
                _print("Empty key entered. Try again or choose a different provider.", style="yellow")
                continue

        # Test the connection
        if provider == "ollama":
            success, message = _test_ollama()
        else:
            success, message = _test_api_key(provider, api_key)

        if success:
            _print(f"\n✓ Connection successful — {message}", style="bold green")

            # Save to global config
            model = GlobalConfig.SUPPORTED_PROVIDERS[provider].get("default_model", "")
            global_cfg.set_api_key(provider, api_key, model=model)
            global_cfg.save()

            _print(f"  Credentials saved to {global_cfg.config_path}", style="dim")

            # Ask if they want to add another provider
            try:
                if Confirm.ask("\nAdd another provider?", default=False):
                    continue
            except (KeyboardInterrupt, EOFError):
                pass

            break
        else:
            _print(f"\n✗ Connection failed: {message}", style="bold red")
            _print("Check your API key and try again, or choose a different provider.", style="dim")

            try:
                if not Confirm.ask("\nTry again with this provider?", default=True):
                    continue
            except (KeyboardInterrupt, EOFError):
                return global_cfg

    # Final summary
    _panel(
        "✅ Setup Complete",
        f"Default provider: {global_cfg.get_default_provider()}\n"
        f"Configured providers: {', '.join(global_cfg.list_configured_providers())}\n\n"
        f"Config stored at: {global_cfg.config_path}\n\n"
        f"You're ready to use CodeFlow! Type [bold]/help[/] for commands.",
        style="green",
    )

    return global_cfg


def run_setup(global_cfg: Optional[GlobalConfig] = None) -> GlobalConfig:
    """Re-run onboarding to modify existing configuration."""
    if global_cfg is None:
        global_cfg = GlobalConfig.load()

    _print("\nCurrent configuration:", style="bold")
    _print(f"  Default provider: {global_cfg.get_default_provider()}")
    for p in global_cfg.list_configured_providers():
        model = global_cfg.get_provider_model(p)
        key_preview = f"{global_cfg.get_api_key(p)[:8]}****"
        _print(f"  {p}: {key_preview} (model: {model})")

    return run_onboarding(global_cfg, add_another=True)
