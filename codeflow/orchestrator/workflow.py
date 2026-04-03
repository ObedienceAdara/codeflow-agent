"""
CodeFlow Orchestrator - Main workflow engine.

Coordinates multiple agents to execute complex development workflows,
managing task distribution, state, and inter-agent communication.
"""

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional
from uuid import UUID

from langchain_anthropic import ChatAnthropic
from langchain_openai import ChatOpenAI

from ..agents.developer import DeveloperAgent
from ..agents.planner import PlannerAgent
from ..config.settings import CodeFlowConfig, get_config
from ..core.knowledge_graph import KnowledgeGraph
from ..models.entities import (
    AgentType,
    Task,
    TaskStatus,
    WorkflowState,
)

logger = logging.getLogger(__name__)


class CodeFlowOrchestrator:
    """
    Main orchestrator for CodeFlow Agent workflows.

    The orchestrator manages the lifecycle of workflows, coordinates
    multiple specialized agents, and maintains global state.
    """

    def __init__(
        self,
        config: Optional[CodeFlowConfig] = None,
        project_root: Optional[Path] = None,
    ):
        self.config = config or get_config()
        if project_root:
            self.config.project_root = project_root

        self.state = WorkflowState(
            project_root=str(self.config.project_root)
        )
        self.knowledge_graph = KnowledgeGraph()
        self.agents: dict[AgentType, Any] = {}
        self._llm: Optional[Any] = None
        self._initialized = False

        logger.info("CodeFlow Orchestrator initialized")

    def _initialize_llm(self) -> Any:
        """Initialize the LLM based on configuration."""
        llm_config = self.config.llm
        
        # Get API key from environment if not in config
        import os
        api_key = llm_config.api_key or os.environ.get(f"{llm_config.provider.upper()}_API_KEY")

        if llm_config.provider == "anthropic":
            return ChatAnthropic(
                model=llm_config.model,
                temperature=llm_config.temperature,
                max_tokens=llm_config.max_tokens,
                api_key=api_key,
            )
        elif llm_config.provider == "openai":
            return ChatOpenAI(
                model=llm_config.model,
                temperature=llm_config.temperature,
                max_tokens=llm_config.max_tokens,
                api_key=api_key,
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_config.provider}")

    async def initialize(self) -> None:
        """Initialize the orchestrator and all agents."""
        if self._initialized:
            logger.warning("Orchestrator already initialized")
            return

        logger.info("Initializing CodeFlow Orchestrator...")

        # Initialize LLM
        self._llm = self._initialize_llm()
        logger.info(f"Initialized LLM: {self.config.llm.provider}/{self.config.llm.model}")

        # Initialize agents
        await self._initialize_agents()

        # Ensure directories exist
        self.config.ensure_directories()

        self._initialized = True
        self.state.status = "running"
        logger.info("CodeFlow Orchestrator ready")

    async def _initialize_agents(self) -> None:
        """Initialize all enabled agents."""
        # Planner Agent
        self.agents[AgentType.PLANNER] = PlannerAgent(
            config=self.config,
            llm=self._llm,
        )
        logger.info("Initialized Planner Agent")

        # Developer Agent
        developer = DeveloperAgent(
            config=self.config,
            llm=self._llm,
        )
        developer.set_project_root(self.config.project_root)
        self.agents[AgentType.DEVELOPER] = developer
        logger.info("Initialized Developer Agent")

        # Store agent states in workflow state
        for agent_type, agent in self.agents.items():
            self.state.agents[agent_type] = agent.get_state()

    async def analyze_project(self) -> dict[str, Any]:
        """
        Analyze the target project and build knowledge graph.

        Returns:
            Dictionary containing project analysis results
        """
        logger.info(f"Analyzing project at: {self.config.project_root}")

        # This would integrate with code parsers (tree-sitter, etc.)
        # For now, return basic file statistics
        import os

        stats = {
            "total_files": 0,
            "total_lines": 0,
            "languages": {},
            "files_by_type": {},
        }

        for root, dirs, files in os.walk(self.config.project_root):
            # Skip hidden directories and common non-code directories
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv")
            ]

            for file in files:
                file_path = Path(root) / file
                rel_path = file_path.relative_to(self.config.project_root)
                ext = file_path.suffix.lower()

                stats["total_files"] += 1

                # Count by language/extension
                lang = ext.lstrip(".") or "no_extension"
                stats["languages"][lang] = stats["languages"].get(lang, 0) + 1

                # Count lines
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = len(f.readlines())
                        stats["total_lines"] += lines
                except Exception:
                    pass

        self.state.metrics = {
            "total_files": stats["total_files"],
            "total_lines": stats["total_lines"],
            "languages": stats["languages"],
            "last_analyzed": datetime.utcnow(),
        }

        logger.info(
            f"Analysis complete: {stats['total_files']} files, {stats['total_lines']} lines"
        )
        return stats

    async def execute_requirement(self, requirement: str) -> WorkflowState:
        """
        Execute a high-level requirement through the full workflow.

        Args:
            requirement: Natural language description of what needs to be done

        Returns:
            Updated workflow state
        """
        if not self._initialized:
            await self.initialize()

        logger.info(f"Executing requirement: {requirement[:100]}...")

        # Step 1: Create plan using Planner agent
        planner = self.agents.get(AgentType.PLANNER)
        if not planner:
            raise RuntimeError("Planner agent not initialized")

        planning_task = Task(
            title="Plan requirement implementation",
            description=f"Create detailed plan for: {requirement}",
            context={"requirement": requirement},
        )

        tasks = await planner.create_plan(requirement, {})
        logger.info(f"Created plan with {len(tasks)} tasks")

        # Add tasks to workflow state
        for task in tasks:
            self.state.tasks[task.id] = task

        # Step 2: Execute tasks in dependency order
        completed_ids = set()
        failed_tasks = []

        while len(completed_ids) < len(tasks):
            # Get next ready task
            next_task = await planner.get_next_task(tasks, completed_ids)

            if not next_task:
                if len(completed_ids) < len(tasks):
                    logger.warning("No more tasks ready but some incomplete")
                    break
                break

            # Get appropriate agent for task
            agent_type = next_task.assigned_agent or AgentType.DEVELOPER
            agent = self.agents.get(agent_type)

            if not agent:
                logger.error(f"Agent not available: {agent_type}")
                next_task.status = TaskStatus.FAILED
                next_task.error = f"No agent available for {agent_type}"
                failed_tasks.append(next_task)
                completed_ids.add(next_task.id)
                continue

            # Execute task
            logger.info(
                f"Executing task '{next_task.title}' with {agent_type.value} agent"
            )

            try:
                # Run the full task processing pipeline
                updated_task = await agent.process_task(next_task)
                self.state.tasks[updated_task.id] = updated_task

                if updated_task.status == TaskStatus.COMPLETED:
                    completed_ids.add(updated_task.id)
                    logger.info(f"Task completed: {updated_task.title}")
                else:
                    failed_tasks.append(updated_task)
                    completed_ids.add(updated_task.id)

            except Exception as e:
                logger.exception(f"Task execution failed: {next_task.title}")
                next_task.status = TaskStatus.FAILED
                next_task.error = str(e)
                self.state.tasks[next_task.id] = next_task
                failed_tasks.append(next_task)
                completed_ids.add(next_task.id)

        # Update workflow state
        self.state.updated_at = datetime.utcnow()
        self.state.status = "completed" if not failed_tasks else "failed"

        if failed_tasks:
            logger.warning(f"{len(failed_tasks)} tasks failed")

        return self.state

    async def create_pull_request(
        self,
        feature_description: str,
        branch_name: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        Create a pull request for a new feature.

        Args:
            feature_description: Description of the feature to implement
            branch_name: Optional custom branch name

        Returns:
            Pull request information
        """
        # Execute the requirement
        await self.execute_requirement(feature_description)

        # Generate branch name
        if not branch_name:
            safe_name = feature_description.lower().replace(" ", "-")[:50]
            branch_name = f"{self.config.git.branch_prefix}{safe_name}"

        # This would integrate with Git operations
        pr_info = {
            "title": feature_description[:100],
            "branch": branch_name,
            "status": "draft",
            "changes": [],
        }

        logger.info(f"Created PR draft: {branch_name}")
        return pr_info

    def get_workflow_state(self) -> WorkflowState:
        """Get current workflow state."""
        self.state.updated_at = datetime.utcnow()
        return self.state

    async def shutdown(self) -> None:
        """Gracefully shutdown the orchestrator."""
        logger.info("Shutting down CodeFlow Orchestrator...")
        self.state.status = "stopped"

        # Reset agent states
        for agent in self.agents.values():
            agent.reset_state()

        self._initialized = False
        logger.info("CodeFlow Orchestrator stopped")


async def main():
    """Example usage of the orchestrator."""
    # Initialize orchestrator
    orchestrator = CodeFlowOrchestrator(
        project_root=Path("/workspace")
    )

    try:
        # Initialize
        await orchestrator.initialize()

        # Analyze project
        stats = await orchestrator.analyze_project()
        print(f"Project stats: {stats}")

        # Execute a requirement
        requirement = "Add a utility function to calculate fibonacci numbers"
        state = await orchestrator.execute_requirement(requirement)
        print(f"Workflow completed: {state.status}")

    finally:
        await orchestrator.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
