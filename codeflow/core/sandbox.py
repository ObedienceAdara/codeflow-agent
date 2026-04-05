"""
Docker Sandbox Executor for CodeFlow Agent.

Provides isolated execution of user code using Docker containers
with configurable resource limits, network isolation, and timeout enforcement.
"""

import asyncio
import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from ..config.settings import CodeFlowConfig

logger = logging.getLogger(__name__)


@dataclass
class SandboxResult:
    """Result from sandbox execution."""
    success: bool
    stdout: str = ""
    stderr: str = ""
    exit_code: int = -1
    execution_time_ms: float = 0.0
    error: str = ""
    container_id: str = ""
    resource_usage: dict[str, Any] = field(default_factory=dict)


class DockerSandboxExecutor:
    """
    Executes code in isolated Docker containers.

    Uses the Docker SDK for Python to create, run, and destroy
    ephemeral containers with configurable resource limits.

    Features:
    - Memory and CPU limits from DockerConfig
    - Network isolation (optional)
    - Execution timeout enforcement
    - Automatic container cleanup
    - Volume mounting for project code
    """

    def __init__(self, config: CodeFlowConfig):
        self.config = config.docker
        self._client: Any = None
        self._active_containers: list[str] = []

    def _get_client(self) -> Any:
        """Lazy-initialize Docker client."""
        if self._client is None:
            try:
                import docker
                self._client = docker.from_env()
            except ImportError:
                raise RuntimeError(
                    "Docker SDK not installed. Run: pip install docker"
                )
            except docker.errors.DockerException as e:
                raise RuntimeError(
                    f"Docker daemon not available: {e}. "
                    "Ensure Docker Desktop is running."
                )
        return self._client

    async def execute(
        self,
        code: str,
        language: str = "python",
        working_dir: str = "/workspace",
        extra_env: Optional[dict[str, str]] = None,
        command_override: Optional[str] = None,
    ) -> SandboxResult:
        """
        Execute code in an isolated Docker container.

        Args:
            code: Source code to execute
            language: Programming language (python, node, etc.)
            working_dir: Working directory inside container
            extra_env: Additional environment variables
            command_override: Override default command

        Returns:
            SandboxResult with execution output
        """
        import docker
        import time

        client = self._get_client()

        # Select image based on language
        image = self._get_image_for_language(language)

        # Ensure image is available
        try:
            client.images.get(image)
        except docker.errors.ImageNotFound:
            logger.info(f"Pulling image: {image}")
            try:
                client.images.pull(image)
            except docker.errors.APIError as e:
                return SandboxResult(
                    success=False,
                    error=f"Failed to pull image {image}: {e}",
                )

        # Generate unique container name
        container_name = f"codeflow-{uuid.uuid4().hex[:12]}"

        # Prepare environment
        env = extra_env or {}
        env["CODEFLOW_SANDBOX"] = "1"

        # Parse resource limits
        mem_limit = self._parse_memory_limit(self.config.memory_limit)
        nano_cpus = int(self.config.cpu_limit * 1e9)  # Convert to nano-CPUs

        # Prepare volumes
        volumes = {}
        if working_dir and Path(working_dir).exists():
            volumes[str(Path(working_dir).resolve())] = {
                "bind": "/workspace",
                "mode": "ro",
            }

        # Create temporary file for code
        code_path = await self._write_code_to_temp(code, language)

        # Build command
        if command_override:
            cmd = command_override
        else:
            cmd = self._get_command_for_language(language, code_path)

        container_kwargs = {
            "image": image,
            "command": cmd,
            "name": container_name,
            "environment": env,
            "mem_limit": mem_limit,
            "nano_cpus": nano_cpus if not self.config.cpu_limit == 0 else None,
            "network_disabled": self.config.network_disabled,
            "detach": True,
            "stdout": True,
            "stderr": True,
        }

        if volumes:
            container_kwargs["volumes"] = volumes

        start_time = time.monotonic()

        try:
            container = client.containers.run(**container_kwargs)
            self._active_containers.append(container.id)

            # Wait for completion with timeout
            timeout = self.config.timeout
            try:
                result = container.wait(timeout=timeout)
            except Exception:
                # Timeout or error - kill container
                container.kill()
                elapsed = (time.monotonic() - start_time) * 1000
                return SandboxResult(
                    success=False,
                    error=f"Container execution timed out after {timeout}s",
                    container_id=container.id,
                    execution_time_ms=elapsed,
                )

            # Collect output
            try:
                stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace")
            except Exception:
                stdout = ""

            try:
                stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace")
            except Exception:
                stderr = ""

            exit_code = result.get("StatusCode", -1) if isinstance(result, dict) else -1

            elapsed = (time.monotonic() - start_time) * 1000

            # Collect resource usage
            resource_usage = {}
            try:
                stats = container.stats(stream=False)
                if "memory_stats" in stats:
                    resource_usage["memory"] = {
                        "usage": stats["memory_stats"].get("usage", 0),
                        "limit": stats["memory_stats"].get("limit", 0),
                    }
                if "cpu_stats" in stats:
                    resource_usage["cpu"] = stats["cpu_stats"].get(
                        "cpu_usage", {}
                    ).get("total_usage", 0)
            except Exception:
                pass

            return SandboxResult(
                success=exit_code == 0,
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                execution_time_ms=elapsed,
                container_id=container.id,
                resource_usage=resource_usage,
            )

        except docker.errors.ContainerError as e:
            elapsed = (time.monotonic() - start_time) * 1000
            return SandboxResult(
                success=False,
                error=str(e),
                execution_time_ms=elapsed,
            )
        except docker.errors.APIError as e:
            elapsed = (time.monotonic() - start_time) * 1000
            return SandboxResult(
                success=False,
                error=f"Docker API error: {e}",
                execution_time_ms=elapsed,
            )
        finally:
            # Cleanup container
            await self._cleanup_container(container_name)

    async def execute_file(
        self,
        file_path: str,
        language: str = "python",
        extra_env: Optional[dict[str, str]] = None,
    ) -> SandboxResult:
        """
        Execute a file in an isolated Docker container.

        Args:
            file_path: Path to the file to execute
            language: Programming language
            extra_env: Additional environment variables

        Returns:
            SandboxResult with execution output
        """
        path = Path(file_path)
        if not path.exists():
            return SandboxResult(
                success=False,
                error=f"File not found: {file_path}",
            )

        code = path.read_text(encoding="utf-8", errors="replace")
        project_root = str(path.parent)

        return await self.execute(
            code=code,
            language=language,
            working_dir=project_root,
            extra_env=extra_env,
        )

    async def execute_tests(
        self,
        test_path: str,
        project_root: str,
        framework: str = "pytest",
    ) -> SandboxResult:
        """
        Run tests in an isolated Docker container.

        Args:
            test_path: Path to test file or directory
            project_root: Root of the project
            framework: Test framework (pytest, unittest)

        Returns:
            SandboxResult with test execution output
        """
        if framework == "pytest":
            command = f"python -m pytest {test_path} -v --tb=short"
        elif framework == "unittest":
            command = f"python -m unittest discover -s {test_path}"
        else:
            return SandboxResult(
                success=False,
                error=f"Unsupported test framework: {framework}",
            )

        return await self.execute(
            code="",
            language="python",
            working_dir=project_root,
            command_override=command,
        )

    async def cleanup(self) -> None:
        """Clean up all active containers and Docker client."""
        for container_id in list(self._active_containers):
            await self._cleanup_container(container_id)
        self._active_containers.clear()

        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def is_available(self) -> bool:
        """Check if Docker is available."""
        try:
            client = self._get_client()
            client.ping()
            return True
        except Exception:
            return False

    async def _write_code_to_temp(self, code: str, language: str) -> str:
        """Write code to a temporary file for volume mounting."""
        import tempfile

        ext_map = {
            "python": ".py",
            "node": ".js",
            "javascript": ".js",
        }
        ext = ext_map.get(language, ".txt")

        with tempfile.NamedTemporaryFile(
            suffix=ext,
            delete=False,
            mode="w",
            encoding="utf-8",
        ) as f:
            f.write(code)
            return f.name

    def _get_image_for_language(self, language: str) -> str:
        """Get Docker image for a language."""
        image_map = {
            "python": "python:3.12-slim",
            "node": "node:20-slim",
            "javascript": "node:20-slim",
        }
        return image_map.get(language, self.config.sandbox_image)

    def _get_command_for_language(self, language: str, code_path: str) -> str:
        """Get command to execute code for a language."""
        if language == "python":
            return f"python {code_path}"
        elif language in ("node", "javascript"):
            return f"node {code_path}"
        else:
            return f"cat {code_path}"

    def _parse_memory_limit(self, limit: str) -> str:
        """Parse memory limit string for Docker."""
        return limit  # Docker SDK accepts strings like "2g" directly

    async def _cleanup_container(self, container_name_or_id: str) -> None:
        """Remove a container by name or ID."""
        try:
            client = self._get_client()
            container = client.containers.get(container_name_or_id)
            container.remove(force=True)
            if container_name_or_id in self._active_containers:
                self._active_containers.remove(container_name_or_id)
        except Exception:
            pass  # Container may already be gone
