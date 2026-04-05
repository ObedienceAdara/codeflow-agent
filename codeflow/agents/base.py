"""
Base agent class for CodeFlow Agent.

Provides the foundation for all specialized agents with common functionality
for LLM interaction, tool execution, and state management.
"""

import asyncio
import inspect
import json
import logging
from abc import ABC
from datetime import datetime, UTC
from typing import Any, Callable, Optional, Union

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from ..config.settings import CodeFlowConfig
from ..models.entities import (
    AgentState,
    AgentType,
    ExecutionResult,
    Task,
    TaskStatus,
)

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Abstract base class for all CodeFlow agents.

    Each agent type implements specific capabilities while inheriting
    common functionality for LLM interaction, tool execution, and workflow integration.
    """

    agent_type: AgentType
    system_prompt: str = ""

    def __init__(
        self,
        config: CodeFlowConfig,
        llm: Any,
        tools: Optional[list[Callable]] = None,
    ):
        self.config = config
        self.llm = llm
        self.tools = tools or []
        self.state = AgentState(agent_type=self.agent_type)
        self._tool_registry: dict[str, Callable] = {}

        # Register tools
        for tool in self.tools:
            self.register_tool(tool)

        logger.info(f"Initialized {self.agent_type.value} agent")

    def register_tool(self, tool: Callable) -> None:
        """Register a tool function for use by the agent."""
        tool_name = getattr(tool, "__name__", str(tool))
        self._tool_registry[tool_name] = tool
        logger.debug(f"Registered tool: {tool_name}")

    def get_tools_schema(self) -> list[dict[str, Any]]:
        """Get the schema for all registered tools."""
        # Mapping from Python types to valid JSON Schema types
        JSON_TYPE_MAP = {
            "str": "string",
            "string": "string",
            "int": "integer",
            "integer": "integer",
            "float": "number",
            "number": "number",
            "bool": "boolean",
            "boolean": "boolean",
            "list": "array",
            "dict": "object",
            "object": "object",
            "NoneType": "null",
            "None": "null",
            "Path": "string",
            "Bytes": "string",
            "bytearray": "string",
            "datetime": "string",
            "date": "string",
        }

        schemas = []
        for name, tool in self._tool_registry.items():
            schema = {
                "name": name,
                "description": (getattr(tool, "__doc__", "No description available") or "").strip().split("\n")[0],
            }

            sig = inspect.signature(tool)
            properties = {}
            required = []

            for param_name, param in sig.parameters.items():
                if param_name == "self":
                    continue

                # Determine JSON type
                raw_type = getattr(param.annotation, "__name__", None)
                origin = getattr(param.annotation, "__origin__", None)

                if origin is not None:
                    # Handle Optional[X] -> use X's type
                    if origin is Union:
                        args = getattr(param.annotation, "__args__", [])
                        non_none = [a for a in args if a is not type(None)]
                        if non_none:
                            raw_type = getattr(non_none[0], "__name__", "string")
                        else:
                            raw_type = "string"
                    elif origin is list or origin is List:
                        raw_type = "array"
                    elif origin is dict or origin is Dict:
                        raw_type = "object"
                    else:
                        raw_type = "string"
                elif raw_type is not None:
                    pass  # Use as-is, mapped below
                else:
                    raw_type = "string"

                json_type = JSON_TYPE_MAP.get(raw_type, "string")

                prop_def: dict[str, Any] = {"type": json_type}

                # Add description from docstring if available
                prop_def["description"] = f"Parameter {param_name}"

                # Handle array items
                if json_type == "array":
                    prop_def["items"] = {"type": "string"}

                properties[param_name] = prop_def

                if param.default == inspect.Parameter.empty:
                    required.append(param_name)

            schema["parameters"] = {
                "type": "object",
                "properties": properties,
                "required": required,
            }
            schemas.append(schema)
        return schemas

    async def execute_tool(
        self, tool_name: str, **kwargs: Any
    ) -> ExecutionResult:
        """Execute a registered tool with the given arguments."""
        if tool_name not in self._tool_registry:
            return ExecutionResult(
                success=False,
                error=f"Unknown tool: {tool_name}",
            )

        start_time = datetime.now(UTC)
        try:
            tool_func = self._tool_registry[tool_name]
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(
                None, lambda: tool_func(**kwargs)
            )

            duration = (datetime.now(UTC) - start_time).total_seconds() * 1000

            if isinstance(result, ExecutionResult):
                result.duration_ms = duration
                return result

            return ExecutionResult(
                success=True,
                output=str(result),
                duration_ms=duration,
            )
        except Exception as e:
            duration = (datetime.now(UTC) - start_time).total_seconds() * 1000
            logger.exception(f"Tool execution failed: {tool_name}")
            return ExecutionResult(
                success=False,
                error=str(e),
                duration_ms=duration,
            )

    def _build_messages(
        self, task: Task, context: Optional[dict[str, Any]] = None
    ) -> list[BaseMessage]:
        """Build the message sequence for LLM interaction."""
        messages: list[BaseMessage] = []

        # System message with agent-specific prompt
        system_content = f"""{self.system_prompt}

You are a {self.agent_type.value} agent in the CodeFlow system.
Current task: {task.title}
Description: {task.description}

Available tools: {list(self._tool_registry.keys())}

IMPORTANT: Respond with ONLY valid JSON. No markdown, no code blocks, no explanations.

Your JSON response must have this structure:
{{
    "action": "use_tool" or "complete_task" or "request_help",
    "tool_name": "tool name here (only if action is use_tool)",
    "tool_args": {{"arg": "value"}},
    "reasoning": "brief explanation of your choice",
    "result": "final output (only if action is complete_task)"
}}
"""
        messages.append(SystemMessage(content=system_content))

        # Add conversation history
        messages.extend(self.state.messages)

        # Add current task context
        context_msg = f"Task context: {json.dumps(task.context, default=str)}\n"
        if context:
            context_msg += f"Additional context: {json.dumps(context, default=str)}\n"
        messages.append(HumanMessage(content=context_msg))

        return messages

    async def process_task(
        self,
        task: Task,
        context: Optional[dict[str, Any]] = None,
    ) -> Task:
        """
        Process a task through multiple iterations until completion.

        Args:
            task: The task to process
            context: Additional context for task execution

        Returns:
            Updated task with results or error information
        """
        task.status = TaskStatus.IN_PROGRESS
        task.started_at = datetime.now(UTC)
        task.assigned_agent = self.agent_type
        self.state.current_task = task

        logger.info(f"Starting task: {task.title} ({task.id})")

        for iteration in range(self.config.execution.max_iterations):
            task.iterations = iteration + 1
            self.state.iteration_count = iteration + 1

            try:
                # Build messages for LLM
                messages = self._build_messages(task, context)

                # Get LLM response
                response = await self._invoke_llm(messages)

                # Parse and execute action
                action_result = await self._execute_action(response, task)

                # Check if task is complete
                if task.is_complete():
                    break

            except Exception as e:
                logger.exception(f"Iteration {iteration + 1} failed")
                task.error = str(e)
                task.status = TaskStatus.FAILED
                break

        task.completed_at = datetime.now(UTC)
        task.updated_at = datetime.now(UTC)
        self.state.current_task = None

        logger.info(
            f"Task completed: {task.title} - Status: {task.status.value}"
        )
        return task

    async def _invoke_llm(self, messages: list[BaseMessage]) -> dict[str, Any]:
        """Invoke the LLM with the given messages and parse response."""
        # Use plain text invocation (no bind_tools) — LLM returns JSON in text
        # This works reliably across all providers (Groq/Llama, Anthropic, OpenAI, etc.)
        # Tool schemas are described in the system prompt
        response = await self.llm.ainvoke(messages)

        # Parse response content
        try:
            content = response.content
            if content is None:
                logger.warning("LLM returned None content")
                return {
                    "action": "complete_task",
                    "result": "",
                    "reasoning": "LLM returned empty response",
                }
            if isinstance(content, str):
                raw = content.strip()
                # Strip markdown code fences
                if raw.startswith("```"):
                    lines = raw.split("\n")
                    if lines[0].startswith("```"):
                        lines = lines[1:]
                    if lines and lines[-1].strip() == "```":
                        lines = lines[:-1]
                    raw = "\n".join(lines).strip()
                return json.loads(raw)
            return content
        except json.JSONDecodeError:
            # If parsing fails, create a default response
            logger.warning("Failed to parse LLM response as JSON")
            return {
                "action": "complete_task",
                "result": str(content),
                "reasoning": "Response parsing failed, returning raw output",
            }

    async def _execute_action(
        self, action: dict[str, Any], task: Task
    ) -> ExecutionResult:
        """Execute an action returned by the LLM."""
        action_type = action.get("action", "complete_task")
        reasoning = action.get("reasoning", "")

        logger.debug(f"Executing action: {action_type} - {reasoning}")

        if action_type == "use_tool":
            tool_name = action.get("tool_name")
            tool_args = action.get("tool_args", {})

            if not tool_name:
                task.error = "Tool name not specified"
                task.status = TaskStatus.FAILED
                return ExecutionResult(success=False, error=task.error)

            result = await self.execute_tool(tool_name, **tool_args)
            self.state.tool_outputs.append(
                {
                    "tool": tool_name,
                    "args": tool_args,
                    "result": result.output,
                    "error": result.error,
                    "success": result.success,
                }
            )

            # Add tool result to conversation history
            self.state.messages.append(
                AIMessage(
                    content=json.dumps(
                        {
                            "action": "used_tool",
                            "tool": tool_name,
                            "result": result.output or result.error,
                        }
                    )
                )
            )
            self.state.messages.append(
                HumanMessage(
                    content=f"Tool {tool_name} executed: {'Success' if result.success else 'Failed'}"
                )
            )

            return result

        elif action_type == "complete_task":
            result = action.get("result", "")
            task.result = result
            task.status = TaskStatus.COMPLETED
            return ExecutionResult(success=True, output=result)

        elif action_type == "request_help":
            # Task requires human intervention or another agent
            task.status = TaskStatus.WAITING_FOR_REVIEW
            task.result = action.get("reasoning", "Help requested")
            return ExecutionResult(
                success=True, output="Task paused for review"
            )

        else:
            task.error = f"Unknown action type: {action_type}"
            task.status = TaskStatus.FAILED
            return ExecutionResult(success=False, error=task.error)

    def analyze(self, task: Task) -> Task:
        """Analyze a task. Override in subclasses for domain-specific analysis."""
        logger.debug(f"{self.agent_type.value}: analyze() not implemented, returning task as-is")
        return task

    def execute(self, task: Task) -> Task:
        """Execute a task. Override in subclasses for domain-specific execution."""
        logger.debug(f"{self.agent_type.value}: execute() not implemented, returning task as-is")
        return task

    def validate(self, task: Task) -> Task:
        """Validate task results. Override in subclasses for domain-specific validation."""
        logger.debug(f"{self.agent_type.value}: validate() not implemented, returning task as-is")
        return task

    def get_state(self) -> AgentState:
        """Get the current agent state."""
        self.state.last_updated = datetime.now(UTC)
        return self.state

    def reset_state(self) -> None:
        """Reset the agent state for a new task."""
        self.state = AgentState(agent_type=self.agent_type)
        logger.debug(f"Reset state for {self.agent_type.value} agent")
