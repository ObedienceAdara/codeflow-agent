"""Developer Agent for CodeFlow Agent.

The Developer agent is responsible for implementing code changes,
writing new features, and fixing bugs.
"""

import json
import logging
from pathlib import Path
from typing import Any, Callable, Optional

from langchain_core.messages import HumanMessage, SystemMessage

from ..config.settings import CodeFlowConfig
from ..core.diff_protocol import DiffProtocol
from ..models.entities import (
    AgentType,
    CodeChange,
    Task,
    TaskStatus,
)
from .base import BaseAgent

logger = logging.getLogger(__name__)


class DeveloperAgent(BaseAgent):
    """
    Agent responsible for code implementation and development tasks.

    The Developer writes new code, modifies existing code, and implements
    features based on specifications from the Planner.
    """

    agent_type = AgentType.DEVELOPER

    system_prompt = """You are the Developer Agent in the CodeFlow system.

Your responsibilities:
1. Implement code changes based on task specifications
2. Write clean, maintainable, and well-documented code
3. Follow best practices and coding standards
4. Ensure backward compatibility when modifying existing code
5. Add appropriate error handling and logging

When writing code:
- Use clear, descriptive variable and function names
- Add docstrings and comments where helpful
- Follow the existing code style in the project
- Consider edge cases and error conditions
- Write testable code with clear interfaces

Always think through your changes before implementing them."""

    def __init__(
        self,
        config: CodeFlowConfig,
        llm: Any,
        tools: Optional[list[Callable]] = None,
    ):
        # Add developer-specific tools
        developer_tools = [
            self.read_file,
            self.write_file,
            self.create_file,
            self.delete_file,
            self.search_code,
        ]
        all_tools = (tools or []) + developer_tools
        super().__init__(config, llm, all_tools)
        self.project_root: Optional[Path] = None
        self.diff_protocol = DiffProtocol()

    def set_project_root(self, path: Path) -> None:
        """Set the project root directory for file operations."""
        self.project_root = path
        logger.info(f"Developer project root set to: {path}")

    def _safe_path(self, file_path: str) -> Path:
        """Ensure file path is within project root for security."""
        if self.project_root is None:
            raise ValueError("Project root not set")

        full_path = (self.project_root / file_path).resolve()
        try:
            full_path.relative_to(self.project_root.resolve())
        except ValueError:
            raise ValueError(
                f"File path '{file_path}' is outside project root"
            )
        return full_path

    def read_file(self, file_path: str) -> str:
        """Read contents of a file.

        Args:
            file_path: Relative path to the file

        Returns:
            File contents as string
        """
        try:
            safe_path = self._safe_path(file_path)
            if not safe_path.exists():
                return f"Error: File not found: {file_path}"
            with open(safe_path, "r", encoding="utf-8") as f:
                return f.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

    def write_file(self, file_path: str, content: str) -> str:
        """Write content to an existing file.

        Args:
            file_path: Relative path to the file
            content: Content to write

        Returns:
            Success message or error
        """
        try:
            safe_path = self._safe_path(file_path)
            if not safe_path.exists():
                return f"Error: File does not exist: {file_path}"
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully wrote to {file_path}"
        except Exception as e:
            return f"Error writing file: {str(e)}"

    def create_file(self, file_path: str, content: str) -> str:
        """Create a new file with content.

        Args:
            file_path: Relative path to the new file
            content: Initial content

        Returns:
            Success message or error
        """
        try:
            safe_path = self._safe_path(file_path)
            if safe_path.exists():
                return f"Error: File already exists: {file_path}"
            safe_path.parent.mkdir(parents=True, exist_ok=True)
            with open(safe_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Successfully created {file_path}"
        except Exception as e:
            return f"Error creating file: {str(e)}"

    def delete_file(self, file_path: str) -> str:
        """Delete a file.

        Args:
            file_path: Relative path to the file

        Returns:
            Success message or error
        """
        try:
            safe_path = self._safe_path(file_path)
            if not safe_path.exists():
                return f"Error: File not found: {file_path}"
            safe_path.unlink()
            return f"Successfully deleted {file_path}"
        except Exception as e:
            return f"Error deleting file: {str(e)}"

    def search_code(self, pattern: str, file_pattern: str = "*.py") -> str:
        """Search for a pattern in code files.

        Args:
            pattern: Text or regex pattern to search for
            file_pattern: Glob pattern for files to search

        Returns:
            Matching lines with file paths
        """
        try:
            if self.project_root is None:
                return "Error: Project root not set"

            import glob
            import re

            results = []
            files = glob.glob(
                str(self.project_root / "**" / file_pattern), recursive=True
            )

            compiled_pattern = re.compile(pattern)

            for file_path in files[:100]:  # Limit to 100 files
                try:
                    path = Path(file_path)
                    if path.is_file():
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            for line_num, line in enumerate(f, 1):
                                if compiled_pattern.search(line):
                                    rel_path = path.relative_to(self.project_root)
                                    results.append(
                                        f"{rel_path}:{line_num}: {line.rstrip()}"
                                    )
                except Exception:
                    continue

            if not results:
                return f"No matches found for pattern: {pattern}"

            return "\n".join(results[:50])  # Limit output
        except Exception as e:
            return f"Error searching code: {str(e)}"

    async def implement_change(
        self,
        file_path: str,
        description: str,
        current_content: Optional[str] = None,
    ) -> CodeChange:
        """Generate code changes using LLM.

        Args:
            file_path: Path to the file to modify
            description: Description of the change to make
            current_content: Current file content (optional)

        Returns:
            CodeChange object with the proposed changes
        """
        if current_content is None:
            current_content = self.read_file(file_path)

        prompt = f"""Implement the following change to this file:

FILE: {file_path}
CHANGE DESCRIPTION: {description}

CURRENT CONTENT:
{current_content}

Provide the complete new content for the file. Include all necessary imports,
functions, classes, etc. The entire file content should be valid and complete.

Return ONLY the new file content, no explanations or markdown formatting."""

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

        response = await self.llm.ainvoke(messages)
        new_content = response.content.strip()

        # Generate unified diff via DiffProtocol (token-efficient)
        diff_result = self.diff_protocol.generate_diff(
            original_text=current_content,
            modified_text=new_content,
            filename=file_path,
        )

        if not diff_result.success:
            logger.warning(f"Diff generation failed for {file_path}: {diff_result.error}")

        return CodeChange(
            file_path=file_path,
            old_content=current_content,
            new_content=new_content,
            change_type="modify" if current_content else "create",
            diff=diff_result.diff_text,
            description=description,
        )

    async def analyze(self, task: Task) -> Task:
        """Analyze a development task."""
        logger.info(f"Analyzing development task: {task.title}")

        # Review task requirements and plan approach
        prompt = f"""Analyze this development task and plan your approach:

TASK: {task.title}
DESCRIPTION: {task.description}
CONTEXT: {json.dumps(task.context, default=str)}

Provide a brief analysis including:
1. What files need to be created or modified
2. Key implementation considerations
3. Potential challenges
4. Testing requirements

Respond in JSON format:
{{
    "files_to_modify": ["file1.py", "file2.py"],
    "files_to_create": ["new_file.py"],
    "considerations": ["Consideration 1"],
    "challenges": ["Challenge 1"],
    "testing_needed": true
}}
"""

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

        response = await self.llm.ainvoke(messages)

        try:
            if isinstance(response.content, str):
                analysis = json.loads(response.content)
            else:
                analysis = response.content

            task.context["analysis"] = analysis
            task.result = f"Analysis complete: {len(analysis.get('files_to_modify', []))} files to modify"
        except json.JSONDecodeError:
            task.context["analysis"] = {"raw_analysis": response.content}
            task.result = "Analysis complete (parsing failed)"

        task.status = TaskStatus.COMPLETED
        return task

    async def execute(self, task: Task) -> Task:
        """Execute a development task by implementing code changes."""
        logger.info(f"Executing development task: {task.title}")

        analysis = task.context.get("analysis", {})
        changes_made = []

        # Process files to modify
        for file_path in analysis.get("files_to_modify", []):
            try:
                change = await self.implement_change(
                    file_path=file_path,
                    description=f"{task.title}: {task.description}",
                )
                changes_made.append(change)

                # Apply the change
                if change.change_type == "create":
                    result = self.create_file(file_path, change.new_content)
                else:
                    result = self.write_file(file_path, change.new_content)

                logger.info(f"Applied change to {file_path}: {result}")
            except Exception as e:
                logger.error(f"Failed to modify {file_path}: {e}")
                task.error = f"Failed to modify {file_path}: {str(e)}"
                task.status = TaskStatus.FAILED
                return task

        # Process files to create
        for file_path in analysis.get("files_to_create", []):
            try:
                change = await self.implement_change(
                    file_path=file_path,
                    description=f"{task.title}: Create new file",
                    current_content=None,
                )
                changes_made.append(change)

                result = self.create_file(file_path, change.new_content)
                logger.info(f"Created {file_path}: {result}")
            except Exception as e:
                logger.error(f"Failed to create {file_path}: {e}")
                task.error = f"Failed to create {file_path}: {str(e)}"
                task.status = TaskStatus.FAILED
                return task

        task.context["changes"] = [
            {"file": c.file_path, "type": c.change_type} for c in changes_made
        ]
        task.result = f"Implemented {len(changes_made)} code changes"
        task.status = TaskStatus.COMPLETED
        return task

    async def validate(self, task: Task) -> Task:
        """Validate that code changes are syntactically correct."""
        logger.info(f"Validating development task: {task.title}")

        changes = task.context.get("changes", [])
        validation_errors = []

        for change_info in changes:
            file_path = change_info.get("file")
            if not file_path:
                continue

            # Check syntax for Python files
            if file_path.endswith(".py"):
                try:
                    content = self.read_file(file_path)
                    compile(content, file_path, "exec")
                    logger.debug(f"Syntax OK: {file_path}")
                except SyntaxError as e:
                    validation_errors.append(
                        f"Syntax error in {file_path}: {str(e)}"
                    )

        if validation_errors:
            task.error = "; ".join(validation_errors)
            task.status = TaskStatus.FAILED
        else:
            task.result = "Code validation passed"
            task.status = TaskStatus.COMPLETED

        return task
