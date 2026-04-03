"""
Configuration management for CodeFlow Agent.

Handles loading and validation of configuration from environment variables,
YAML files, and default values.
"""

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class LLMConfig(BaseSettings):
    """LLM provider configuration."""

    provider: str = Field(default="anthropic", description="LLM provider: anthropic, openai, google, ollama")
    model: str = Field(default="claude-sonnet-4-5-20250929", description="Model name to use")
    temperature: float = Field(default=0.7, ge=0.0, le=2.0, description="Sampling temperature")
    max_tokens: int = Field(default=4096, gt=0, description="Maximum tokens per call")
    api_key: Optional[str] = Field(default=None, description="API key (loaded from env)")
    base_url: Optional[str] = Field(default=None, description="Custom API base URL")

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        valid_providers = {"anthropic", "openai", "google", "ollama"}
        if v.lower() not in valid_providers:
            raise ValueError(f"Provider must be one of: {valid_providers}")
        return v.lower()

    model_config = SettingsConfigDict(env_prefix="LLM_", extra="ignore")


class DatabaseConfig(BaseSettings):
    """Vector and graph database configuration."""

    # ChromaDB for embeddings
    chroma_path: str = Field(default="./.codeflow/chroma_db", description="Path to ChromaDB storage")
    chroma_collection: str = Field(default="codeflow_embeddings", description="ChromaDB collection name")

    # Neo4j for code relationships (optional)
    neo4j_uri: Optional[str] = Field(default=None, description="Neo4j connection URI")
    neo4j_username: Optional[str] = Field(default=None, description="Neo4j username")
    neo4j_password: Optional[str] = Field(default=None, description="Neo4j password")

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class DockerConfig(BaseSettings):
    """Docker sandbox configuration."""

    host: str = Field(default="unix:///var/run/docker.sock", description="Docker socket path")
    sandbox_image: str = Field(default="codeflow-sandbox:latest", description="Sandbox container image")
    timeout: int = Field(default=300, gt=0, description="Container execution timeout in seconds")
    memory_limit: str = Field(default="2g", description="Memory limit for containers")
    cpu_limit: float = Field(default=2.0, gt=0, description="CPU limit for containers")
    network_disabled: bool = Field(default=True, description="Disable network access in sandbox")

    model_config = SettingsConfigDict(env_prefix="DOCKER_", extra="ignore")


class GitConfig(BaseSettings):
    """Git operations configuration."""

    author_name: str = Field(default="CodeFlow Agent", description="Git author name")
    author_email: str = Field(default="codeflow@localhost", description="Git author email")
    auto_branch: bool = Field(default=True, description="Automatically create branches")
    auto_commit: bool = Field(default=False, description="Automatically commit changes")
    require_review: bool = Field(default=True, description="Require review before merging")
    branch_prefix: str = Field(default="codeflow/", description="Prefix for auto-generated branches")

    model_config = SettingsConfigDict(env_prefix="GIT_", extra="ignore")


class ExecutionConfig(BaseSettings):
    """Task execution limits and timeouts."""

    max_iterations: int = Field(default=10, gt=0, description="Maximum agent iterations per task")
    concurrent_agents: int = Field(default=3, gt=0, description="Maximum concurrent agents")
    task_timeout: int = Field(default=600, gt=0, description="Task timeout in seconds")
    retry_attempts: int = Field(default=3, ge=0, description="Number of retry attempts")
    retry_delay: float = Field(default=1.0, gt=0, description="Delay between retries in seconds")

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class LoggingConfig(BaseSettings):
    """Logging configuration."""

    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="json", description="Log format: json, text")
    file: str = Field(default="./.codeflow/codeflow.log", description="Log file path")
    enable_audit: bool = Field(default=True, description="Enable audit logging")
    max_size_mb: int = Field(default=100, gt=0, description="Max log file size in MB")
    backup_count: int = Field(default=5, ge=0, description="Number of backup log files")

    @field_validator("level")
    @classmethod
    def validate_level(cls, v: str) -> str:
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid_levels:
            raise ValueError(f"Log level must be one of: {valid_levels}")
        return v.upper()

    model_config = SettingsConfigDict(env_prefix="LOG_", extra="ignore")


class APIConfig(BaseSettings):
    """API server configuration."""

    host: str = Field(default="127.0.0.1", description="API server host")
    port: int = Field(default=8000, gt=0, lt=65536, description="API server port")
    debug: bool = Field(default=False, description="Enable debug mode")
    cors_origins: list[str] = Field(default=["http://localhost:3000"], description="CORS allowed origins")
    api_key: Optional[str] = Field(default=None, description="API authentication key")

    model_config = SettingsConfigDict(env_prefix="API_", extra="ignore")


class SecurityConfig(BaseSettings):
    """Security configuration."""

    encryption_key: Optional[str] = Field(default=None, description="Encryption key for sensitive data")
    session_timeout: int = Field(default=3600, gt=0, description="Session timeout in seconds")
    max_failed_auth: int = Field(default=5, gt=0, description="Max failed auth attempts before lockout")

    @field_validator("encryption_key")
    @classmethod
    def validate_encryption_key(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and len(v) < 32:
            raise ValueError("Encryption key must be at least 32 characters")
        return v

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class FeatureFlags(BaseSettings):
    """Feature flags for enabling/disabling capabilities."""

    enable_auto_refactor: bool = Field(default=True, description="Enable automatic refactoring")
    enable_auto_deploy: bool = Field(default=False, description="Enable automatic deployment")
    enable_incident_response: bool = Field(default=True, description="Enable incident response")
    enable_dependency_updates: bool = Field(default=True, description="Enable dependency updates")
    enable_telemetry: bool = Field(default=False, description="Enable telemetry collection")

    model_config = SettingsConfigDict(env_prefix="ENABLE_", extra="ignore")


class CodeFlowConfig(BaseSettings):
    """Main configuration class for CodeFlow Agent."""

    # Sub-configurations
    llm: LLMConfig = Field(default_factory=LLMConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)
    git: GitConfig = Field(default_factory=GitConfig)
    execution: ExecutionConfig = Field(default_factory=ExecutionConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    api: APIConfig = Field(default_factory=APIConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    features: FeatureFlags = Field(default_factory=FeatureFlags)

    # Project-specific settings
    project_root: Path = Field(default=Path("."), description="Root directory of the target project")
    config_file: Optional[Path] = Field(default=None, description="Path to YAML config file")

    model_config = SettingsConfigDict(env_nested_delimiter="_", extra="ignore")

    @classmethod
    def load_from_yaml(cls, config_path: Path) -> "CodeFlowConfig":
        """Load configuration from a YAML file."""
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")

        with open(config_path, "r") as f:
            yaml_data = yaml.safe_load(f)

        # Merge YAML data with environment variables
        # Environment variables take precedence
        return cls(**yaml_data)

    def save_to_yaml(self, config_path: Path) -> None:
        """Save current configuration to a YAML file."""
        config_path.parent.mkdir(parents=True, exist_ok=True)

        yaml_data = self.model_dump(mode="json", exclude_none=True)
        with open(config_path, "w") as f:
            yaml.dump(yaml_data, f, default_flow_style=False, sort_keys=False)

    def ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        dirs = [
            self.project_root / ".codeflow",
            Path(self.database.chroma_path).parent,
            Path(self.logging.file).parent,
        ]
        for dir_path in dirs:
            dir_path.mkdir(parents=True, exist_ok=True)


def get_config(config_file: Optional[Path] = None) -> CodeFlowConfig:
    """
    Load configuration from environment and optional YAML file.

    Args:
        config_file: Optional path to YAML configuration file

    Returns:
        CodeFlowConfig instance
    """
    if config_file and config_file.exists():
        return CodeFlowConfig.load_from_yaml(config_file)
    return CodeFlowConfig()
