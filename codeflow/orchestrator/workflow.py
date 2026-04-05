"""
CodeFlow Orchestrator - Main workflow engine.

Coordinates multiple agents to execute complex development workflows,
managing task distribution, state, and inter-agent communication.
"""

import asyncio
import logging
import os
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional
from uuid import UUID

from langchain_anthropic import ChatAnthropic
from langchain_groq import ChatGroq
from langchain_openai import ChatOpenAI
from langgraph.graph import END, StateGraph

from ..agents.developer import DeveloperAgent
from ..agents.planner import PlannerAgent
from ..config.settings import CodeFlowConfig, get_config
from ..core.diff_protocol import DiffProtocol
from ..core.knowledge_graph import KnowledgeGraph
from ..core.sandbox import DockerSandboxExecutor
from ..core.tree_sitter_parser import TreeSitterParser
from ..models.entities import (
    AgentType,
    CodeChange,
    CodeEntity,
    CodeEntityType,
    PullRequest,
    Relationship,
    RelationshipType,
    Task,
    TaskStatus,
    WorkflowState,
)
from .consensus_loop import ConsensusLoop, LoopConfig
from .debate_context import DebateContextManager

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
        self.sandbox = DockerSandboxExecutor(self.config)
        self.tree_sitter = TreeSitterParser()
        self.agents: dict[AgentType, Any] = {}
        self._llm: Optional[Any] = None
        self._initialized = False
        
        # Initialize consensus loop components
        self.debate_context_manager = DebateContextManager()
        self.consensus_loop = ConsensusLoop(self.debate_context_manager)

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
        elif llm_config.provider == "groq":
            return ChatGroq(
                model=llm_config.model,
                temperature=llm_config.temperature,
                max_tokens=llm_config.max_tokens,
                api_key=api_key,
            )
        elif llm_config.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model=llm_config.model,
                temperature=llm_config.temperature,
                max_output_tokens=llm_config.max_tokens,
                google_api_key=api_key,
            )
        elif llm_config.provider == "ollama":
            return ChatOpenAI(
                model=llm_config.model,
                temperature=llm_config.temperature,
                base_url=llm_config.base_url or "http://localhost:11434/v1",
                api_key="ollama",
            )
        else:
            raise ValueError(f"Unsupported LLM provider: {llm_config.provider}. "
                             f"Supported: anthropic, openai, groq, google, ollama")

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
        # Import additional agents for consensus loop
        from ..agents.reviewer import ReviewerAgent
        from ..agents.qa import QAAgent
        from ..agents.architect import ArchitectAgent
        from ..agents.devops import DevOpsAgent
        from ..agents.refactor import RefactorAgent
        from ..agents.monitor import MonitorAgent

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

        # Reviewer Agent (for consensus loop validation)
        reviewer = ReviewerAgent(
            config=self.config,
            llm=self._llm,
        )
        self.agents[AgentType.REVIEWER] = reviewer
        logger.info("Initialized Reviewer Agent")

        # QA Agent (for consensus loop validation)
        qa = QAAgent(
            config=self.config,
            llm=self._llm,
        )
        qa.set_sandbox(self.sandbox)
        self.agents[AgentType.QA] = qa
        logger.info("Initialized QA Agent with Docker sandbox")

        # Architect Agent (for system design tasks)
        architect = ArchitectAgent(
            config=self.config,
            llm=self._llm,
        )
        self.agents[AgentType.ARCHITECT] = architect
        logger.info("Initialized Architect Agent")

        # DevOps Agent (for CI/CD and deployment tasks)
        devops = DevOpsAgent(
            config=self.config,
            llm=self._llm,
        )
        self.agents[AgentType.DEVOPS] = devops
        logger.info("Initialized DevOps Agent")

        # Refactor Agent (for code refactoring and tech debt reduction)
        refactor = RefactorAgent(
            config=self.config,
            llm=self._llm,
        )
        self.agents[AgentType.REFACTOR] = refactor
        logger.info("Initialized Refactor Agent")

        # Monitor Agent (for system health and incident response)
        monitor = MonitorAgent(
            config=self.config,
            llm=self._llm,
        )
        self.agents[AgentType.MONITOR] = monitor
        logger.info("Initialized Monitor Agent")

        # Store agent states in workflow state
        for agent_type, agent in self.agents.items():
            self.state.agents[agent_type] = agent.get_state()

    async def analyze_project(self) -> dict[str, Any]:
        """
        Analyze the target project and build knowledge graph.

        Walks the project directory, parses code files to extract
        entities (classes, functions, imports), adds them to the
        knowledge graph with relationships, and computes metrics.

        Returns:
            Dictionary containing project analysis results
        """
        logger.info(f"Analyzing project at: {self.config.project_root}")

        from ..models.entities import ProjectMetrics

        stats = {
            "total_files": 0,
            "total_lines": 0,
            "languages": {},
            "files_by_type": {},
            "dependencies": {},
            "entities_added": 0,
            "relationships_added": 0,
        }

        project_root = Path(self.config.project_root)
        entity_map: dict[str, list[CodeEntity]] = {}  # file_path -> entities

        # File extensions to parse
        code_extensions = {
            ".py": CodeEntityType.FILE,
            ".js": CodeEntityType.FILE,
            ".ts": CodeEntityType.FILE,
            ".tsx": CodeEntityType.FILE,
            ".jsx": CodeEntityType.FILE,
        }

        for root, dirs, files in os.walk(project_root):
            # Skip hidden directories and common non-code directories
            dirs[:] = [
                d
                for d in dirs
                if not d.startswith(".") and d not in ("node_modules", "__pycache__", "venv", ".venv", "dist", "build")
            ]

            for file in files:
                file_path = Path(root) / file
                rel_path = str(file_path.relative_to(project_root))
                ext = file_path.suffix.lower()

                stats["total_files"] += 1

                # Count by language/extension
                lang = ext.lstrip(".") or "no_extension"
                stats["languages"][lang] = stats["languages"].get(lang, 0) + 1

                # Count lines
                try:
                    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                        lines = f.readlines()
                        stats["total_lines"] += len(lines)
                except Exception:
                    pass

                # Detect dependencies from requirements files
                if file in ("requirements.txt", "setup.py", "pyproject.toml", "package.json"):
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()
                            deps = self._parse_dependencies(content, file)
                            stats["dependencies"].update(deps)
                    except Exception:
                        pass

                # Parse code files and populate knowledge graph
                if ext in code_extensions:
                    try:
                        content = "".join(lines) if 'lines' in dir() else ""
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            content = f.read()

                        entities = self._parse_code_file(content, rel_path, ext.lstrip("."))
                        entity_map[rel_path] = entities

                        for entity in entities:
                            self.knowledge_graph.add_entity(entity)
                            stats["entities_added"] += 1

                        # Add CONTAINS relationships (file -> entities within it)
                        file_entity = CodeEntity(
                            entity_type=CodeEntityType.FILE,
                            name=file,
                            file_path=rel_path,
                            line_start=1,
                            line_end=len(content.splitlines()),
                            language=ext.lstrip(".").lstrip("."),
                            content=content[:5000],  # Truncate for storage
                        )
                        self.knowledge_graph.add_entity(file_entity)
                        stats["entities_added"] += 1

                        for entity in entities:
                            rel = Relationship(
                                source_id=file_entity.id,
                                target_id=entity.id,
                                relationship_type=RelationshipType.CONTAINS,
                            )
                            self.knowledge_graph.add_relationship(rel)
                            stats["relationships_added"] += 1

                    except Exception as e:
                        logger.warning(f"Failed to parse {rel_path}: {e}")

        # Add IMPORTS/DEPENDS_ON relationships between entities
        rel_count = self._build_inter_entity_relationships(entity_map)
        stats["relationships_added"] += rel_count

        # Create proper ProjectMetrics instance
        self.state.metrics = ProjectMetrics(
            total_files=stats["total_files"],
            total_lines=stats["total_lines"],
            languages=stats["languages"],
            dependencies=stats["dependencies"],
            last_analyzed=datetime.utcnow(),
        )

        # Sync knowledge graph to workflow state
        for eid, entity in self.knowledge_graph.entity_index.items():
            self.state.code_entities[eid] = entity

        logger.info(
            f"Analysis complete: {stats['total_files']} files, {stats['total_lines']} lines, "
            f"{stats['entities_added']} entities, {stats['relationships_added']} relationships"
        )
        return stats

    def _parse_code_file(self, content: str, file_path: str, language: str) -> list[CodeEntity]:
        """
        Parse a code file to extract entities (classes, functions, imports).

        Tries tree-sitter AST parsing first, falls back to regex.

        Args:
            content: File content
            file_path: Relative path to the file
            language: File extension/language

        Returns:
            List of CodeEntity objects extracted from the file
        """
        entities: list[CodeEntity] = []

        # Try tree-sitter AST parsing first
        if self.tree_sitter.is_available(language):
            entities = self.tree_sitter.parse_file(content, file_path, language)

        # Fall back to regex if tree-sitter returned empty or unavailable
        if not entities:
            lines = content.splitlines()
            if language == "py":
                entities = self._parse_python(content, file_path, lines)
            elif language in ("js", "ts", "tsx", "jsx"):
                entities = self._parse_javascript(content, file_path, lines)

        return entities

    def _parse_python(self, content: str, file_path: str, lines: list[str]) -> list[CodeEntity]:
        """Parse Python file to extract classes, functions, and imports."""
        import re
        entities: list[CodeEntity] = []

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Extract class definitions
            class_match = re.match(r'^class\s+(\w+)', stripped)
            if class_match:
                class_name = class_match.group(1)
                # Find class end (next class/def at same indent level or EOF)
                line_end = self._find_python_block_end(lines, i, 0)
                entities.append(CodeEntity(
                    entity_type=CodeEntityType.CLASS,
                    name=class_name,
                    file_path=file_path,
                    line_start=i + 1,
                    line_end=line_end,
                    content="\n".join(lines[i:line_end]),
                    language="python",
                ))

            # Extract function/method definitions
            func_match = re.match(r'^(async\s+)?def\s+(\w+)', stripped)
            if func_match:
                func_name = func_match.group(2)
                # Determine if it's a method (indented) or top-level function
                indent = len(line) - len(line.lstrip())
                entity_type = CodeEntityType.METHOD if indent > 0 else CodeEntityType.FUNCTION
                line_end = self._find_python_block_end(lines, i, indent)
                entities.append(CodeEntity(
                    entity_type=entity_type,
                    name=func_name,
                    file_path=file_path,
                    line_start=i + 1,
                    line_end=line_end,
                    content="\n".join(lines[i:line_end]),
                    language="python",
                ))

            # Extract imports
            import_match = re.match(r'^(from\s+[\w.]+\s+)?import\s+(.+)', stripped)
            if import_match:
                from_clause = import_match.group(1)
                import_names = import_match.group(2)
                # Create entity for each imported name
                for name in import_names.split(","):
                    name = name.strip().split(" as ")[-1].split(" ")[0]
                    if name and name != "*":
                        entities.append(CodeEntity(
                            entity_type=CodeEntityType.IMPORT,
                            name=name,
                            file_path=file_path,
                            line_start=i + 1,
                            line_end=i + 1,
                            content=stripped,
                            language="python",
                            metadata={"from_module": from_clause.strip() if from_clause else None},
                        ))

        return entities

    def _parse_javascript(self, content: str, file_path: str, lines: list[str]) -> list[CodeEntity]:
        """Parse JavaScript/TypeScript file to extract classes, functions, and imports."""
        import re
        entities: list[CodeEntity] = []

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Extract class definitions
            class_match = re.match(r'^(export\s+)?(default\s+)?class\s+(\w+)', stripped)
            if class_match:
                class_name = class_match.group(3)
                line_end = self._find_js_block_end(lines, i)
                entities.append(CodeEntity(
                    entity_type=CodeEntityType.CLASS,
                    name=class_name,
                    file_path=file_path,
                    line_start=i + 1,
                    line_end=line_end,
                    content="\n".join(lines[i:line_end]),
                    language="javascript",
                ))

            # Extract function definitions
            func_match = re.match(
                r'^(export\s+)?(default\s+)?(async\s+)?function\s+(\w+)', stripped
            )
            if func_match:
                func_name = func_match.group(4)
                line_end = self._find_js_block_end(lines, i)
                entities.append(CodeEntity(
                    entity_type=CodeEntityType.FUNCTION,
                    name=func_name,
                    file_path=file_path,
                    line_start=i + 1,
                    line_end=line_end,
                    content="\n".join(lines[i:line_end]),
                    language="javascript",
                ))

            # Extract const/let arrow functions
            arrow_match = re.match(
                r'^(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s+)?\(', stripped
            )
            if arrow_match:
                func_name = arrow_match.group(3)
                line_end = self._find_js_block_end(lines, i)
                entities.append(CodeEntity(
                    entity_type=CodeEntityType.FUNCTION,
                    name=func_name,
                    file_path=file_path,
                    line_start=i + 1,
                    line_end=line_end,
                    content="\n".join(lines[i:line_end]),
                    language="javascript",
                ))

            # Extract imports
            import_match = re.match(r'^import\s+(.+)', stripped)
            if import_match:
                entities.append(CodeEntity(
                    entity_type=CodeEntityType.IMPORT,
                    name=import_match.group(1)[:100],
                    file_path=file_path,
                    line_start=i + 1,
                    line_end=i + 1,
                    content=stripped,
                    language="javascript",
                ))

        return entities

    def _find_python_block_end(self, lines: list[str], start: int, base_indent: int) -> int:
        """Find the end line of a Python block (class/function)."""
        i = start + 1
        while i < len(lines):
            line = lines[i]
            # Skip blank lines and comments
            if line.strip() == "" or line.strip().startswith("#"):
                i += 1
                continue
            # Check if indent returns to or below base level
            current_indent = len(line) - len(line.lstrip())
            if current_indent <= base_indent and line.strip():
                break
            i += 1
        return i

    def _find_js_block_end(self, lines: list[str], start: int) -> int:
        """Find the end of a JavaScript block by brace matching."""
        brace_count = 0
        started = False
        for i in range(start, len(lines)):
            for ch in lines[i]:
                if ch == "{":
                    brace_count += 1
                    started = True
                elif ch == "}":
                    brace_count -= 1
                    if started and brace_count == 0:
                        return i + 1
        return len(lines)

    def _build_inter_entity_relationships(self, entity_map: dict[str, list[CodeEntity]]) -> int:
        """
        Build relationships between entities across files.

        Creates IMPORTS relationships when an entity references an import,
        and CALLS relationships based on function name references in code.

        Returns:
            Number of relationships added
        """
        relationships_added = 0
        all_entities: list[CodeEntity] = []
        for ents in entity_map.values():
            all_entities.extend(ents)

        # Build a name -> entity index for quick lookup
        name_to_entities: dict[str, list[CodeEntity]] = {}
        for entity in all_entities:
            if entity.name not in name_to_entities:
                name_to_entities[entity.name] = []
            name_to_entities[entity.name].append(entity)

        for entity in all_entities:
            if entity.content is None:
                continue
            content_lines = entity.content.splitlines()

            for line in content_lines:
                stripped = line.strip()

                # Skip comments
                if stripped.startswith("#") or stripped.startswith("//"):
                    continue

                # Check if this entity references/calls other entities
                for other_name, target_entities in name_to_entities.items():
                    if other_name == entity.name:
                        continue
                    if other_name in stripped and "(" in stripped:
                        # Likely a function call
                        for target in target_entities:
                            if target.id == entity.id:
                                continue
                            # Avoid duplicate relationships
                            existing = self.knowledge_graph.get_related_entities(
                                entity.id, RelationshipType.CALLS
                            )
                            if any(e.id == target.id for _, e in existing):
                                continue

                            rel = Relationship(
                                source_id=entity.id,
                                target_id=target.id,
                                relationship_type=RelationshipType.CALLS,
                            )
                            self.knowledge_graph.add_relationship(rel)
                            relationships_added += 1

        return relationships_added
    
    def _parse_dependencies(self, content: str, filename: str) -> dict[str, str]:
        """Parse dependencies from various dependency files."""
        deps = {}
        
        if filename == "requirements.txt":
            for line in content.split("\n"):
                line = line.strip()
                if line and not line.startswith("#"):
                    if "==" in line:
                        pkg, version = line.split("==", 1)
                        deps[pkg.strip()] = version.strip()
                    elif ">=" in line:
                        pkg, version = line.split(">=", 1)
                        deps[pkg.strip()] = f">={version.strip()}"
                    else:
                        deps[line] = "*"
        
        elif filename == "package.json":
            import json
            try:
                data = json.loads(content)
                for dep, version in data.get("dependencies", {}).items():
                    deps[dep] = version
                for dep, version in data.get("devDependencies", {}).items():
                    deps[dep] = version
            except json.JSONDecodeError:
                pass
        
        return deps

    async def execute_requirement(self, requirement: str) -> WorkflowState:
        """
        Execute a high-level requirement through the full workflow using LangGraph.

        Builds a state graph with nodes for each agent phase:
          PLAN -> [DEVELOP -> REVIEW -> QA] loop -> DONE

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

        # Step 2: Build and execute LangGraph state machine
        graph = self._build_workflow_graph()
        app = graph.compile()

        # Initial graph state
        initial_state = {
            "requirement": requirement,
            "tasks": {str(tid): t.model_dump(mode="json") for tid, t in self.state.tasks.items()},
            "completed_ids": [],
            "failed_ids": [],
            "current_task": None,
            "status": "running",
            "error": None,
        }

        # Execute the graph
        final_state = await app.ainvoke(initial_state)

        # Reconstruct workflow state from graph output
        self._reconstruct_state_from_graph(final_state)

        return self.state

    def _build_workflow_graph(self) -> StateGraph:
        """
        Build a LangGraph StateGraph for task execution.

        Graph structure:
          START -> select_task -> execute_task -> review_task -> qa_task -> should_continue
          should_continue -> select_task (more tasks) or END
        """
        from typing import TypedDict

        class WorkflowGraphState(TypedDict, total=False):
            requirement: str
            tasks: dict
            completed_ids: list
            failed_ids: list
            current_task: Optional[dict]
            status: str
            error: Optional[str]

        graph = StateGraph(WorkflowGraphState)

        # Add nodes
        graph.add_node("select_task", self._langgraph_select_task)
        graph.add_node("execute_task", self._langgraph_execute_task)
        graph.add_node("review_task", self._langgraph_review_task)
        graph.add_node("qa_task", self._langgraph_qa_task)
        graph.add_node("should_continue", self._langgraph_should_continue)

        # Define edges
        graph.set_entry_point("select_task")
        graph.add_edge("select_task", "execute_task")
        graph.add_edge("execute_task", "review_task")
        graph.add_edge("review_task", "qa_task")
        graph.add_edge("qa_task", "should_continue")

        # Conditional routing from should_continue
        graph.add_conditional_edges(
            "should_continue",
            self._langgraph_route_after_continue,
            {
                "continue": "select_task",
                "done": END,
            },
        )

        return graph

    async def _langgraph_select_task(self, state: dict) -> dict:
        """Select the next ready task based on dependencies."""
        planner = self.agents.get(AgentType.PLANNER)
        if not planner:
            return {"current_task": None, "error": "Planner not available"}

        # Reconstruct task objects
        all_tasks = self._reconstruct_tasks(state["tasks"])
        completed_ids = set(state.get("completed_ids", []))

        next_task = await planner.get_next_task(all_tasks, completed_ids)

        if next_task:
            return {
                "current_task": next_task.model_dump(mode="json"),
                "status": "running",
            }
        else:
            return {
                "current_task": None,
                "status": "completed",
            }

    async def _langgraph_execute_task(self, state: dict) -> dict:
        """Execute the current task with its assigned agent."""
        current_task_data = state.get("current_task")
        if not current_task_data:
            return {"status": "completed", "error": "No current task to execute"}

        task = Task(**current_task_data)
        agent_type = task.assigned_agent or AgentType.DEVELOPER
        agent = self.agents.get(agent_type)

        if not agent:
            task.status = TaskStatus.FAILED
            task.error = f"No agent available for {agent_type}"
            return {
                "tasks": {**state["tasks"], str(task.id): task.model_dump(mode="json")},
                "failed_ids": state.get("failed_ids", []) + [str(task.id)],
                "status": "running",
            }

        # Check if consensus loop is needed
        use_consensus = task.context.get("use_consensus_loop", False)

        if use_consensus and agent_type == AgentType.DEVELOPER:
            validator_agents = [
                self.agents.get(AgentType.REVIEWER),
                self.agents.get(AgentType.QA),
            ]
            validator_agents = [v for v in validator_agents if v is not None]

            if validator_agents:
                from .consensus_loop import ConsensusLoop, LoopConfig

                loop_config = LoopConfig(
                    max_iterations=3,
                    min_approvals_required=1,
                    require_unanimous_approval=False,
                )

                result = await self.consensus_loop.execute_loop(
                    task_id=str(task.id),
                    primary_agent=agent,
                    validator_agents=validator_agents,
                    initial_input=task,
                    config=loop_config,
                    topic=f"Review: {task.title}",
                )

                if result["success"]:
                    task.status = TaskStatus.COMPLETED
                else:
                    task.status = TaskStatus.FAILED
                    task.error = result.get("error", "Consensus loop failed")
            else:
                updated_task = await agent.process_task(task)
                task = updated_task
        else:
            updated_task = await agent.process_task(task)
            task = updated_task

        # Update task in state
        tasks_dict = dict(state.get("tasks", {}))
        tasks_dict[str(task.id)] = task.model_dump(mode="json")

        if task.status == TaskStatus.COMPLETED:
            completed = state.get("completed_ids", []) + [str(task.id)]
            return {
                "tasks": tasks_dict,
                "completed_ids": completed,
                "current_task": task.model_dump(mode="json"),
                "status": "running",
            }
        else:
            failed = state.get("failed_ids", []) + [str(task.id)]
            return {
                "tasks": tasks_dict,
                "failed_ids": failed,
                "current_task": task.model_dump(mode="json"),
                "status": "running",
            }

    async def _langgraph_review_task(self, state: dict) -> dict:
        """Run reviewer on the current task result."""
        current_task_data = state.get("current_task")
        if not current_task_data:
            return {"status": "running"}

        task = Task(**current_task_data)
        reviewer = self.agents.get(AgentType.REVIEWER)

        if reviewer and task.status == TaskStatus.COMPLETED:
            try:
                reviewed_task = await reviewer.process_task(task)
                tasks_dict = dict(state.get("tasks", {}))
                tasks_dict[str(reviewed_task.id)] = reviewed_task.model_dump(mode="json")
                return {
                    "tasks": tasks_dict,
                    "current_task": reviewed_task.model_dump(mode="json"),
                    "status": "running",
                }
            except Exception as e:
                logger.warning(f"Review task failed for {task.title}: {e}")

        return {"status": "running"}

    async def _langgraph_qa_task(self, state: dict) -> dict:
        """Run QA on the current task result."""
        current_task_data = state.get("current_task")
        if not current_task_data:
            return {"status": "running"}

        task = Task(**current_task_data)
        qa = self.agents.get(AgentType.QA)

        if qa and task.status == TaskStatus.COMPLETED:
            try:
                qa_task = await qa.process_task(task)
                tasks_dict = dict(state.get("tasks", {}))
                tasks_dict[str(qa_task.id)] = qa_task.model_dump(mode="json")
                return {
                    "tasks": tasks_dict,
                    "current_task": qa_task.model_dump(mode="json"),
                    "status": "running",
                }
            except Exception as e:
                logger.warning(f"QA task failed for {task.title}: {e}")

        return {"status": "running"}

    async def _langgraph_should_continue(self, state: dict) -> dict:
        """Check if there are more tasks to execute."""
        all_tasks = self._reconstruct_tasks(state["tasks"])
        completed_ids = set(state.get("completed_ids", []))
        failed_ids = set(state.get("failed_ids", []))

        remaining = [
            t for t in all_tasks
            if str(t.id) not in completed_ids and str(t.id) not in failed_ids
        ]

        has_more = len(remaining) > 0
        return {
            "status": "running" if has_more else "completed",
        }

    def _langgraph_route_after_continue(self, state: dict) -> Literal["continue", "done"]:
        """Route based on whether there are more tasks."""
        if state.get("status") == "completed":
            self.state.status = "completed"
            return "done"
        return "continue"

    def _reconstruct_tasks(self, tasks_dict: dict) -> list[Task]:
        """Reconstruct Task objects from serialized dict."""
        tasks = []
        for tid, tdata in tasks_dict.items():
            try:
                task = Task(**tdata)
                tasks.append(task)
            except Exception:
                pass
        return tasks

    def _reconstruct_state_from_graph(self, final_state: dict) -> None:
        """Reconstruct WorkflowState from LangGraph output."""
        tasks_data = final_state.get("tasks", {})
        for tid, tdata in tasks_data.items():
            try:
                task = Task(**tdata)
                self.state.tasks[task.id] = task
            except Exception:
                pass

        failed_ids = final_state.get("failed_ids", [])
        self.state.status = final_state.get("status", "completed")
        self.state.updated_at = datetime.utcnow()

        if failed_ids:
            logger.warning(f"{len(failed_ids)} tasks failed")

    async def create_pull_request(
        self,
        feature_description: str,
        branch_name: Optional[str] = None,
    ) -> PullRequest:
        """
        Create a pull request for a new feature.

        Executes the requirement through the workflow, applies code changes,
        creates a Git branch, commits changes, and returns PR metadata.

        Args:
            feature_description: Description of the feature to implement
            branch_name: Optional custom branch name

        Returns:
            PullRequest object with PR information
        """
        import subprocess

        # Execute the requirement through the full workflow
        state = await self.execute_requirement(feature_description)

        # Generate branch name
        if not branch_name:
            safe_name = (
                feature_description.lower()
                .replace(" ", "-")
                .replace("/", "-")
                .replace(".", "-")[:50]
            )
            branch_name = f"{self.config.git.branch_prefix}{safe_name}"

        project_root = Path(self.config.project_root)
        changes: list[CodeChange] = []

        # Collect all code changes from completed tasks
        for task_id, task in state.tasks.items():
            if task.status == TaskStatus.COMPLETED and task.context.get("changes"):
                for change_info in task.context["changes"]:
                    change = CodeChange(
                        file_path=change_info.get("file", ""),
                        old_content=change_info.get("old_content"),
                        new_content=change_info.get("new_content", ""),
                        change_type=change_info.get("type", "modify"),
                        description=task.title,
                        related_tasks=[task_id],
                    )
                    changes.append(change)

                    # Apply actual file changes if content is available
                    if change.new_content and change.file_path:
                        target_path = project_root / change.file_path
                        try:
                            target_path.parent.mkdir(parents=True, exist_ok=True)
                            target_path.write_text(change.new_content, encoding="utf-8")
                        except Exception as e:
                            logger.error(f"Failed to write {change.file_path}: {e}")

        # Git operations: create branch, stage, commit
        try:
            # Ensure we're in a git repo; initialize if needed
            self._run_git_command(project_root, ["git", "rev-parse", "--git-dir"], check=False)
        except (subprocess.CalledProcessError, FileNotFoundError):
            # Not a git repo, initialize
            self._run_git_command(project_root, ["git", "init"])

        # Get current branch
        current_branch = self._get_current_branch(project_root)

        # Create and checkout new branch
        self._run_git_command(
            project_root,
            ["git", "checkout", "-b", branch_name],
            check=False,  # May fail if branch exists
        )

        # Stage all changes
        self._run_git_command(project_root, ["git", "add", "-A"])

        # Commit changes
        commit_msg = f"feat: {feature_description}\n\nGenerated by CodeFlow Agent"
        self._run_git_command(
            project_root,
            [
                "git",
                "-c", f"user.name={self.config.git.author_name}",
                "-c", f"user.email={self.config.git.author_email}",
                "commit",
                "-m", commit_msg,
            ],
            check=False,  # May fail if nothing to commit
        )

        # Build PR description with task summary
        completed_count = sum(
            1 for t in state.tasks.values() if t.status == TaskStatus.COMPLETED
        )
        failed_count = sum(
            1 for t in state.tasks.values() if t.status == TaskStatus.FAILED
        )

        pr_description = f"""# {feature_description}

**Generated by CodeFlow Agent**

## Summary
- **Tasks completed:** {completed_count}
- **Tasks failed:** {failed_count}
- **Files changed:** {len(changes)}

## Tasks
"""
        for task in state.tasks.values():
            status_icon = "✅" if task.status == TaskStatus.COMPLETED else "❌"
            pr_description += f"- {status_icon} **{task.title}**: {task.status.value}\n"

        if changes:
            pr_description += "\n## Changes\n"
            for change in changes:
                pr_description += f"- `{change.file_path}` ({change.change_type})\n"

        # Create PullRequest object
        pr = PullRequest(
            title=feature_description[:100],
            description=pr_description,
            source_branch=branch_name,
            target_branch=current_branch,
            changes=changes,
            status="open",
            tests_passed=True,
            review_status="pending",
        )

        # Store PR in workflow state
        state.pull_requests.append(pr)
        state.status = "completed"

        logger.info(f"Created PR: {branch_name} -> {current_branch} with {len(changes)} changes")
        return pr

    def _run_git_command(
        self,
        project_root: Path,
        command: list[str],
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        """
        Run a Git command in the project root.

        Args:
            project_root: Path to the project root
            command: Git command and arguments
            check: Whether to raise on non-zero exit

        Returns:
            CompletedProcess result from subprocess
        """
        import subprocess

        result = subprocess.run(
            command,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=30,
        )

        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(
                result.returncode, command, result.stdout, result.stderr
            )

        return result

    def _get_current_branch(self, project_root: Path) -> str:
        """Get the current Git branch name."""
        result = self._run_git_command(
            project_root, ["git", "branch", "--show-current"]
        )
        return result.stdout.strip() or "main"

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

        # Cleanup sandbox
        try:
            await self.sandbox.cleanup()
        except Exception as e:
            logger.warning(f"Sandbox cleanup failed: {e}")

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
