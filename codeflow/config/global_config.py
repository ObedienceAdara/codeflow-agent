"""
Global Configuration for CodeFlow.

Manages user-wide settings stored in ~/.codeflow/config.json,
including API keys, default provider, and onboarding state.
"""

import json
import logging
import os
import platform
import stat
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Platform-aware config directory
if platform.system() == "Windows":
    _HOME_DIR = Path(os.environ.get("USERPROFILE", Path.home()))
else:
    _HOME_DIR = Path.home()

_CODEFLOW_DIR = _HOME_DIR / ".codeflow"
_CONFIG_FILE = _CODEFLOW_DIR / "config.json"


class GlobalConfig:
    """
    Manages global user configuration for CodeFlow.

    Handles:
    - Default LLM provider
    - API keys per provider
    - Onboarding completion state
    - User preferences
    """

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._loaded = False

    @property
    def config_dir(self) -> Path:
        """Path to the .codeflow directory."""
        return _CODEFLOW_DIR

    @property
    def config_file(self) -> Path:
        """Path to the config.json file."""
        return _CONFIG_FILE

    @property
    def is_configured(self) -> bool:
        """Whether the user has completed onboarding (has at least one API key)."""
        self._ensure_loaded()
        return bool(self._data.get("providers"))

    @property
    def default_provider(self) -> Optional[str]:
        """The user's default LLM provider."""
        self._ensure_loaded()
        return self._data.get("default_provider")

    @property
    def providers(self) -> dict[str, dict[str, str]]:
        """All configured providers with their API keys."""
        self._ensure_loaded()
        return self._data.get("providers", {})

    def get_api_key(self, provider: str) -> Optional[str]:
        """Get API key for a specific provider."""
        self._ensure_loaded()
        providers = self._data.get("providers", {})
        if provider.lower() in providers:
            return providers[provider.lower()].get("api_key")
        return None

    def get_provider_model(self, provider: str) -> str:
        """Get the configured model for a provider."""
        self._ensure_loaded()
        providers = self._data.get("providers", {})
        if provider.lower() in providers:
            return providers[provider.lower()].get("model", "")
        return ""

    def has_provider(self, provider: str) -> bool:
        """Check if a provider is configured."""
        self._ensure_loaded()
        return provider.lower() in self._data.get("providers", {})

    def set_provider(self, provider: str, api_key: str, model: str = "") -> None:
        """Add or update a provider's API key and optionally model."""
        self._ensure_loaded()
        if "providers" not in self._data:
            self._data["providers"] = {}
        self._data["providers"][provider.lower()] = {"api_key": api_key}
        if model:
            self._data["providers"][provider.lower()]["model"] = model
        # Auto-set default if first provider
        if not self._data.get("default_provider"):
            self._data["default_provider"] = provider.lower()
        self._save()

    def remove_provider(self, provider: str) -> None:
        """Remove a provider."""
        self._ensure_loaded()
        self._data.get("providers", {}).pop(provider.lower(), None)
        # Clear default if it was removed
        if self._data.get("default_provider") == provider.lower():
            remaining = list(self._data.get("providers", {}).keys())
            self._data["default_provider"] = remaining[0] if remaining else None
        self._save()

    def set_default_provider(self, provider: str) -> None:
        """Set the default LLM provider."""
        self._ensure_loaded()
        if not self.has_provider(provider):
            raise ValueError(f"Provider '{provider}' is not configured. Run /setup first.")
        self._data["default_provider"] = provider.lower()
        self._save()

    def get_llm_config(self) -> dict[str, Any]:
        """Get merged L config from global settings."""
        self._ensure_loaded()
        provider = self._data.get("default_provider", "groq")
        api_key = self.get_api_key(provider)
        return {
            "provider": provider,
            "api_key": api_key,
        }

    def _ensure_loaded(self) -> None:
        """Load config if not already loaded."""
        if not self._loaded:
            self._load()

    def _load(self) -> None:
        """Load config from disk."""
        if _CONFIG_FILE.exists():
            try:
                with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
                logger.debug(f"Loaded global config from {_CONFIG_FILE}")
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load global config: {e}")
                self._data = {}
        else:
            self._data = {}
        self._loaded = True

    def _save(self) -> None:
        """Save config to disk with secure permissions."""
        _CODEFLOW_DIR.mkdir(parents=True, exist_ok=True)

        with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

        # Set owner-only permissions (read/write for owner, nothing for others)
        try:
            if platform.system() == "Windows":
                # Windows: use icacls equivalent via os module
                os.chmod(_CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)
            else:
                os.chmod(_CONFIG_FILE, stat.S_IRUSR | stat.S_IWUSR)  # 600
            logger.debug(f"Saved global config to {_CONFIG_FILE}")
        except OSError:
            logger.warning("Could not set secure permissions on config file")

    def reload(self) -> None:
        """Force reload from disk."""
        self._loaded = False
        self._load()


# Module-level singleton
_global_config: Optional[GlobalConfig] = None


def get_global_config() -> GlobalConfig:
    """Get the global configuration singleton."""
    global _global_config
    if _global_config is None:
        _global_config = GlobalConfig()
    return _global_config
