"""
Core data models for CodeFlow Agent.

Defines the fundamental data structures used throughout the system,
including tasks, agents, code entities, and execution results.
"""

from datetime import datetime, UTC
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class TaskStatus(str, Enum):
    """Status of a task in the workflow."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_REVIEW = "waiting_for_review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(str, Enum):
    """Priority levels for tasks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AgentType(str, Enum):
    """Types of agents in the system."""

    ARCHITECT = "architect"
    DEVELOPER = "developer"
    QA = "qa"
    DEVOPS = "devops"
    REVIEWER = "reviewer"
    REFACTOR = "refactor"
    PLANNER = "planner"
    MONITOR = "monitor"


class CodeEntityType(str, Enum):
    """Types of code entities in the knowledge graph."""

    FILE = "file"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    VARIABLE = "variable"
    IMPORT = "import"
    DEPENDENCY = "dependency"
    TEST = "test"
    CONFIG = "config"


class RelationshipType(str, Enum):
    """Types of relationships between code entities."""

    CALLS = "calls"
    IMPORTS = "imports"
    EXTENDS = "extends"
    IMPLEMENTS = "implements"
    CONTAINS = "contains"
    DEPENDS_ON = "depends_on"
    OVERRIDES = "overrides"
    REFERENCES = "references"
    TESTS = "tests"


class CodeEntity(BaseModel):
    """Represents a code entity in the knowledge graph."""

    id: UUID = Field(default_factory=uuid4)
    entity_type: CodeEntityType
    name: str
    file_path: str
    line_start: int
    line_end: Optional[int] = None
    content: Optional[str] = None
    language: str = "python"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(json_encoders={UUID: str, datetime: lambda v: v.isoformat()})


class Relationship(BaseModel):
    """Represents a relationship between two code entities."""

    id: UUID = Field(default_factory=uuid4)
    source_id: UUID
    target_id: UUID
    relationship_type: RelationshipType
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Task(BaseModel):
    """Represents a task to be executed by agents."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.MEDIUM
    assigned_agent: Optional[AgentType] = None
    parent_task_id: Optional[UUID] = None
    subtasks: list[UUID] = Field(default_factory=list)
    dependencies: list[UUID] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    result: Optional[str] = None
    error: Optional[str] = None
    iterations: int = 0
    max_iterations: int = 10
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def is_complete(self) -> bool:
        """Check if task is in a terminal state."""
        return self.status in {TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED}

    def can_execute(self) -> bool:
        """Check if task can be executed (all dependencies met)."""
        return self.status == TaskStatus.PENDING and self.iterations < self.max_iterations

    model_config = ConfigDict(json_encoders={UUID: str, datetime: lambda v: v.isoformat()})


class AgentState(BaseModel):
    """Represents the state of an agent during execution."""

    agent_type: AgentType
    current_task: Optional[Task] = None
    working_memory: dict[str, Any] = Field(default_factory=dict)
    tool_outputs: list[dict[str, Any]] = Field(default_factory=list)
    messages: list[Any] = Field(default_factory=list)  # Can hold dict or BaseMessage
    iteration_count: int = 0
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class ExecutionResult(BaseModel):
    """Result of executing a tool or command."""

    success: bool
    output: Optional[str] = None
    error: Optional[str] = None
    exit_code: Optional[int] = None
    duration_ms: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


class CodeChange(BaseModel):
    """Represents a code change to be applied."""

    file_path: str
    old_content: Optional[str] = None
    new_content: str
    change_type: str = "modify"  # create, modify, delete, rename
    diff: Optional[str] = None
    description: str
    risk_level: str = "medium"  # low, medium, high
    requires_test: bool = True
    related_tasks: list[UUID] = Field(default_factory=list)


class PullRequest(BaseModel):
    """Represents a pull request generated by CodeFlow."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str
    source_branch: str
    target_branch: str = "main"
    changes: list[CodeChange] = Field(default_factory=list)
    status: str = "draft"  # draft, open, merged, closed
    created_by: str = "CodeFlow Agent"
    tests_passed: Optional[bool] = None
    review_status: Optional[str] = None
    url: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(json_encoders={UUID: str, datetime: lambda v: v.isoformat()})


class TechDebtItem(BaseModel):
    """Represents a technical debt item detected in the codebase."""

    id: UUID = Field(default_factory=uuid4)
    title: str
    description: str
    severity: str = "medium"  # low, medium, high, critical
    category: str  # code_smell, bug, vulnerability, performance, security
    file_path: str
    line_number: Optional[int] = None
    suggestion: Optional[str] = None
    estimated_effort: str = "medium"  # low, medium, high
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(json_encoders={UUID: str})


class ProjectMetrics(BaseModel):
    """Metrics about the analyzed project."""

    total_files: int = 0
    total_lines: int = 0
    languages: dict[str, int] = Field(default_factory=dict)
    dependencies: dict[str, str] = Field(default_factory=dict)
    test_coverage: Optional[float] = None
    complexity_score: Optional[float] = None
    tech_debt_count: int = 0
    last_analyzed: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class DependencyInfo(BaseModel):
    """Information about a project dependency."""
    
    name: str
    version: str
    type: str = "runtime"  # runtime, dev, optional


class WorkflowState(BaseModel):
    """Overall state of a CodeFlow workflow execution."""

    workflow_id: UUID = Field(default_factory=uuid4)
    project_root: str
    tasks: dict[UUID, Task] = Field(default_factory=dict)
    agents: dict[AgentType, AgentState] = Field(default_factory=dict)
    code_entities: dict[UUID, CodeEntity] = Field(default_factory=dict)
    relationships: list[Relationship] = Field(default_factory=list)
    pull_requests: list[PullRequest] = Field(default_factory=list)
    metrics: Optional[ProjectMetrics] = None
    status: str = "initializing"  # initializing, running, paused, completed, failed
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    model_config = ConfigDict(json_encoders={UUID: str, datetime: lambda v: v.isoformat()})
