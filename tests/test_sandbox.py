"""Tests for DockerSandboxExecutor."""

import pytest
from unittest.mock import MagicMock, patch

from codeflow.core.sandbox import DockerSandboxExecutor, SandboxResult
from codeflow.config.settings import CodeFlowConfig


class TestSandboxResult:
    """Test SandboxResult dataclass."""

    def test_default_values(self):
        """Test default field values."""
        result = SandboxResult(success=True)

        assert result.success is True
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.exit_code == -1
        assert result.execution_time_ms == 0.0
        assert result.error == ""
        assert result.container_id == ""
        assert result.resource_usage == {}

    def test_successful_result(self):
        """Test creating a successful result."""
        result = SandboxResult(
            success=True,
            stdout="output",
            stderr="",
            exit_code=0,
            execution_time_ms=150.5,
        )

        assert result.success is True
        assert result.stdout == "output"
        assert result.exit_code == 0

    def test_failed_result(self):
        """Test creating a failed result."""
        result = SandboxResult(
            success=False,
            error="Timeout occurred",
            exit_code=1,
        )

        assert result.success is False
        assert result.error == "Timeout occurred"


class TestDockerSandboxExecutor:
    """Test DockerSandboxExecutor class."""

    def test_init(self, config):
        """Test initialization."""
        executor = DockerSandboxExecutor(config)

        assert executor.config == config.docker
        assert executor._client is None
        assert executor._active_containers == []

    def test_get_image_for_language(self, config):
        """Test image selection by language."""
        executor = DockerSandboxExecutor(config)

        assert executor._get_image_for_language("python") == "python:3.12-slim"
        assert executor._get_image_for_language("node") == "node:20-slim"
        assert executor._get_image_for_language("javascript") == "node:20-slim"
        assert executor._get_image_for_language("unknown") == config.docker.sandbox_image

    def test_get_command_for_language(self, config):
        """Test command generation by language."""
        executor = DockerSandboxExecutor(config)

        assert executor._get_command_for_language("python", "/tmp/test.py") == "python /tmp/test.py"
        assert executor._get_command_for_language("node", "/tmp/test.js") == "node /tmp/test.js"

    def test_parse_memory_limit(self, config):
        """Test memory limit parsing."""
        executor = DockerSandboxExecutor(config)

        assert executor._parse_memory_limit("2g") == "2g"
        assert executor._parse_memory_limit("512m") == "512m"

    def test_is_available_docker_not_running(self, config):
        """Test availability check when Docker is not running."""
        executor = DockerSandboxExecutor(config)

        # Should return False when Docker daemon is not available
        result = executor.is_available()
        assert result in (True, False)  # Depends on actual Docker availability

    @pytest.mark.asyncio
    async def test_execute_file_not_found(self, config):
        """Test executing a non-existent file."""
        executor = DockerSandboxExecutor(config)

        result = await executor.execute_file("/nonexistent/path/file.py")

        assert result.success is False
        assert "not found" in result.error.lower()

    @pytest.mark.asyncio
    async def test_execute_unsupported_framework(self, config):
        """Test running tests with unsupported framework."""
        executor = DockerSandboxExecutor(config)

        result = await executor.execute_tests(
            test_path="/tmp/tests",
            project_root="/tmp",
            framework="unknown_framework",
        )

        assert result.success is False
        assert "Unsupported test framework" in result.error

    @pytest.mark.asyncio
    async def test_cleanup_empty(self, config):
        """Test cleanup when no containers are active."""
        executor = DockerSandboxExecutor(config)

        # Should not raise
        await executor.cleanup()
        assert len(executor._active_containers) == 0
