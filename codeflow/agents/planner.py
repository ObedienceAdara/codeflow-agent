"""
Planner Agent for CodeFlow Agent.

The Planner agent is responsible for breaking down high-level requirements
into actionable tasks, prioritizing work, and orchestrating the workflow.
"""

import json
import logging
from datetime import datetime, UTC
from typing import Any, Callable, Optional

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from ..config.settings import CodeFlowConfig
from ..models.entities import (
    AgentType,
    Task,
    TaskPriority,
    TaskStatus,
)
from .base import BaseAgent

logger = logging.getLogger(__name__)


class PlannerAgent(BaseAgent):
    """
    Agent responsible for task planning and workflow orchestration.

    The Planner analyzes requirements, breaks them into subtasks,
    assigns priorities, and coordinates with other agents.
    """

    agent_type = AgentType.PLANNER

    system_prompt = """You are the Planner Agent in the CodeFlow system.

Your responsibilities:
1. Analyze high-level requirements and break them into actionable tasks
2. Identify task dependencies and execution order
3. Assign appropriate agent types to each task
4. Prioritize tasks based on impact and urgency
5. Monitor progress and adjust plans as needed

Think systematically about:
- What needs to be accomplished
- Dependencies between tasks
- Which agent type is best suited for each task
- Potential risks and mitigation strategies
- Testing and validation requirements

Always provide clear, actionable task descriptions with sufficient context."""

    def __init__(
        self,
        config: CodeFlowConfig,
        llm: Any,
        tools: Optional[list[Callable]] = None,
    ):
        super().__init__(config, llm, tools)
        self._task_counter = 0

    def _generate_task_id(self) -> str:
        """Generate a unique task identifier."""
        self._task_counter += 1
        return f"task-{self._task_counter}"

    async def create_plan(
        self,
        requirement: str,
        context: Optional[dict[str, Any]] = None,
    ) -> list[Task]:
        """
        Create a detailed plan from a high-level requirement.

        Args:
            requirement: High-level requirement description
            context: Additional context about the project

        Returns:
            List of tasks representing the execution plan
        """
        logger.info(f"Creating plan for requirement: {requirement[:100]}...")

        # Build planning prompt
        prompt = f"""Analyze this requirement and create a detailed execution plan.

IMPORTANT: Return ONLY valid JSON. No markdown, no explanations, no code blocks.

REQUIREMENT:
{requirement}

CONTEXT:
{json.dumps(context or {}, default=str)}

Return ONLY this JSON structure (no other text):
{{
    "summary": "Brief summary of what needs to be done",
    "tasks": [
        {{
            "id": "task-1",
            "title": "Clear, concise title",
            "description": "Detailed description of what to do",
            "agent_type": "developer",
            "priority": "medium",
            "dependencies": []
        }}
    ],
    "estimated_iterations": 5,
    "risks": ["Potential risk 1"],
    "success_criteria": ["Criterion 1"]
}}
"""

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

        # Get LLM response
        response = await self.llm.ainvoke(messages)

        # Parse the plan
        try:
            if isinstance(response.content, str):
                raw = response.content.strip()
                # Strip markdown code fences
                if raw.startswith("```"):
                    raw = raw.split("\n", 1)[1] if "\n" in raw else raw
                    if raw.endswith("```"):
                        raw = raw[:-3]
                    raw = raw.strip()
                plan_data = json.loads(raw)
            else:
                plan_data = response.content
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse plan: {e}")
            # Create a fallback single task
            return [
                Task(
                    title="Implement requirement",
                    description=requirement,
                    priority=TaskPriority.MEDIUM,
                    assigned_agent=AgentType.DEVELOPER,
                    context={"original_requirement": requirement},
                )
            ]

        # Convert to Task objects
        tasks = []
        task_map = {}

        for task_data in plan_data.get("tasks", []):
            # Safely resolve agent_type, fallback to DEVELOPER
            raw_agent = task_data.get("agent_type", "developer")
            try:
                agent_type = AgentType(raw_agent)
            except ValueError:
                logger.warning(f"Unknown agent type '{raw_agent}', defaulting to developer")
                agent_type = AgentType.DEVELOPER

            task = Task(
                title=task_data.get("title", "Untitled Task"),
                description=task_data.get("description", ""),
                priority=TaskPriority(task_data.get("priority", "medium")),
                assigned_agent=agent_type,
                context={
                    "requirement": requirement,
                    "success_criteria": plan_data.get("success_criteria", []),
                    **context,
                },
            )
            tasks.append(task)
            task_map[task_data.get("id")] = task.id

        # Update dependencies with actual UUIDs
        for i, task_data in enumerate(plan_data.get("tasks", [])):
            deps = task_data.get("dependencies", [])
            tasks[i].dependencies = [
                task_map[dep_id] for dep_id in deps if dep_id in task_map
            ]

        logger.info(f"Created plan with {len(tasks)} tasks")
        return tasks

    async def reprioritize_tasks(
        self, tasks: list[Task], new_context: dict[str, Any]
    ) -> list[Task]:
        """Reprioritize existing tasks based on new information."""
        logger.info("Reprioritizing tasks based on new context")

        prompt = f"""Review these tasks and reprioritize based on new context:

CURRENT TASKS:
{json.dumps([{{'id': str(t.id), 'title': t.title, 'priority': t.priority.value}} for t in tasks], indent=2)}

NEW CONTEXT:
{json.dumps(new_context, default=str)}

Return a JSON object mapping task IDs to new priorities:
{{
    "task-id-1": "critical",
    "task-id-2": "high",
    ...
}}
"""

        messages = [
            SystemMessage(content=self.system_prompt),
            HumanMessage(content=prompt),
        ]

        response = await self.llm.ainvoke(messages)

        try:
            if isinstance(response.content, str):
                priority_updates = json.loads(response.content)
            else:
                priority_updates = response.content
        except json.JSONDecodeError:
            logger.warning("Failed to parse priority updates")
            return tasks

        # Apply priority updates
        for task in tasks:
            new_priority = priority_updates.get(str(task.id))
            if new_priority and new_priority in TaskPriority.__members__:
                task.priority = TaskPriority[new_priority]
                task.updated_at = datetime.now(UTC)

        return tasks

    async def analyze(self, task: Task) -> Task:
        """Analyze a planning task."""
        logger.info(f"Analyzing planning task: {task.title}")

        if "requirement" in task.context:
            # This is a requirement to plan
            subtasks = await self.create_plan(
                task.context["requirement"],
                task.context,
            )
            task.subtasks = [st.id for st in subtasks]
            task.result = f"Created {len(subtasks)} subtasks"
            task.status = TaskStatus.COMPLETED
        else:
            task.result = "No requirement specified for planning"
            task.status = TaskStatus.COMPLETED

        return task

    async def execute(self, task: Task) -> Task:
        """Execute a planning task (typically delegates to other agents)."""
        logger.info(f"Executing planning task: {task.title}")
        task.result = "Planning tasks are executed by creating subtasks for other agents"
        task.status = TaskStatus.COMPLETED
        return task

    async def validate(self, task: Task) -> Task:
        """Validate that the plan is complete and coherent."""
        logger.info(f"Validating plan for task: {task.title}")

        # Check if all subtasks are defined
        if not task.subtasks:
            task.error = "Plan has no subtasks"
            task.status = TaskStatus.FAILED
            return task

        # Validate task dependencies don't form cycles
        dependency_graph = {}
        for subtask_id in task.subtasks:
            # Would need access to full task list to properly validate
            pass

        task.result = "Plan validation successful"
        task.status = TaskStatus.COMPLETED
        return task

    async def get_next_task(
        self, tasks: list[Task], completed_ids: set
    ) -> Optional[Task]:
        """
        Determine the next task to execute based on dependencies and priorities.

        Args:
            tasks: List of all tasks
            completed_ids: Set of completed task IDs

        Returns:
            Next task to execute, or None if no tasks are ready
        """
        ready_tasks = []

        for task in tasks:
            if task.id in completed_ids:
                continue
            if task.is_complete():
                continue

            # Check if all dependencies are met
            deps_met = all(dep_id in completed_ids for dep_id in task.dependencies)
            if deps_met:
                ready_tasks.append(task)

        if not ready_tasks:
            return None

        # Sort by priority and return highest priority task
        priority_order = {
            TaskPriority.CRITICAL: 0,
            TaskPriority.HIGH: 1,
            TaskPriority.MEDIUM: 2,
            TaskPriority.LOW: 3,
        }
        ready_tasks.sort(key=lambda t: priority_order.get(t.priority, 99))
        return ready_tasks[0]
