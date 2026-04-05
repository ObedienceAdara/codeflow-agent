"""Tests for data models (entities.py)."""

import pytest
from datetime import datetime
from uuid import UUID

from codeflow.models.entities import (
    Task,
    TaskStatus,
    TaskPriority,
    AgentType,
    CodeEntity,
    CodeEntityType,
    Relationship,
    RelationshipType,
    ExecutionResult,
    CodeChange,
    PullRequest,
    TechDebtItem,
    ProjectMetrics,
    WorkflowState,
    AgentState,
)


class TestTask:
    """Test Task model."""

    def test_create_task_defaults(self, sample_task):
        """Test creating a task with default values."""
        assert sample_task.status == TaskStatus.PENDING
        assert sample_task.priority == TaskPriority.MEDIUM
        assert sample_task.assigned_agent is None
        assert sample_task.result is None
        assert sample_task.error is None
        assert sample_task.iterations == 0
        assert sample_task.max_iterations == 10
        assert isinstance(sample_task.id, UUID)

    def test_task_is_complete_completed(self):
        """Test is_complete for completed task."""
        task = Task(
            title="Done",
            description="A completed task",
            status=TaskStatus.COMPLETED,
        )
        assert task.is_complete() is True

    def test_task_is_complete_failed(self):
        """Test is_complete for failed task."""
        task = Task(
            title="Failed",
            description="A failed task",
            status=TaskStatus.FAILED,
        )
        assert task.is_complete() is True

    def test_task_is_complete_pending(self):
        """Test is_complete for pending task."""
        task = Task(
            title="Pending",
            description="A pending task",
            status=TaskStatus.PENDING,
        )
        assert task.is_complete() is False

    def test_task_can_execute(self):
        """Test can_execute for a pending task."""
        task = Task(
            title="Ready",
            description="A ready task",
            status=TaskStatus.PENDING,
            iterations=0,
            max_iterations=10,
        )
        assert task.can_execute() is True

    def test_task_cannot_execute_completed(self):
        """Test can_execute for completed task."""
        task = Task(
            title="Done",
            description="Completed task",
            status=TaskStatus.COMPLETED,
        )
        assert task.can_execute() is False

    def test_task_cannot_execute_max_iterations(self):
        """Test can_execute when max iterations reached."""
        task = Task(
            title="Exhausted",
            description="Max iterations reached",
            status=TaskStatus.PENDING,
            iterations=10,
            max_iterations=10,
        )
        assert task.can_execute() is False

    def test_task_with_dependencies(self):
        """Test task with dependencies."""
        dep_id = UUID("00000000-0000-0000-0000-000000000001")
        task = Task(
            title="Dependent task",
            description="Depends on another task",
            dependencies=[dep_id],
        )
        assert len(task.dependencies) == 1
        assert task.dependencies[0] == dep_id


class TestCodeEntity:
    """Test CodeEntity model."""

    def test_create_entity(self, sample_code_entity):
        """Test creating a code entity."""
        assert sample_code_entity.entity_type == CodeEntityType.FUNCTION
        assert sample_code_entity.name == "calculate_sum"
        assert sample_code_entity.file_path == "test.py"
        assert sample_code_entity.language == "python"
        assert isinstance(sample_code_entity.id, UUID)


class TestRelationship:
    """Test Relationship model."""

    def test_create_relationship(self):
        """Test creating a relationship."""
        source_id = UUID("00000000-0000-0000-0000-000000000001")
        target_id = UUID("00000000-0000-0000-0000-000000000002")

        rel = Relationship(
            source_id=source_id,
            target_id=target_id,
            relationship_type=RelationshipType.CALLS,
        )

        assert rel.source_id == source_id
        assert rel.target_id == target_id
        assert rel.relationship_type == RelationshipType.CALLS


class TestExecutionResult:
    """Test ExecutionResult model."""

    def test_successful_result(self):
        """Test creating a successful result."""
        result = ExecutionResult(
            success=True,
            output="Hello, world!",
            exit_code=0,
        )

        assert result.success is True
        assert result.output == "Hello, world!"
        assert result.error is None

    def test_failed_result(self):
        """Test creating a failed result."""
        result = ExecutionResult(
            success=False,
            error="Something went wrong",
            exit_code=1,
        )

        assert result.success is False
        assert result.error == "Something went wrong"


class TestCodeChange:
    """Test CodeChange model."""

    def test_create_code_change(self):
        """Test creating a code change."""
        change = CodeChange(
            file_path="test.py",
            old_content="old",
            new_content="new",
            change_type="modify",
            description="Updated test",
        )

        assert change.file_path == "test.py"
        assert change.change_type == "modify"
        assert change.risk_level == "medium"
        assert change.requires_test is True


class TestPullRequest:
    """Test PullRequest model."""

    def test_create_pull_request(self):
        """Test creating a pull request."""
        pr = PullRequest(
            title="Add feature",
            description="A new feature",
            source_branch="codeflow/add-feature",
            target_branch="main",
        )

        assert pr.status == "draft"
        assert pr.created_by == "CodeFlow Agent"
        assert isinstance(pr.id, UUID)


class TestTechDebtItem:
    """Test TechDebtItem model."""

    def test_create_tech_debt(self):
        """Test creating a tech debt item."""
        debt = TechDebtItem(
            title="Long method",
            description="Method has 200 lines",
            severity="high",
            category="code_smell",
            file_path="app.py",
            line_number=42,
            suggestion="Extract into smaller methods",
        )

        assert debt.severity == "high"
        assert debt.estimated_effort == "medium"


class TestProjectMetrics:
    """Test ProjectMetrics model."""

    def test_create_project_metrics(self):
        """Test creating project metrics."""
        metrics = ProjectMetrics(
            total_files=50,
            total_lines=10000,
            languages={"python": 40, "javascript": 10},
            dependencies={"requests": "2.31.0"},
        )

        assert metrics.total_files == 50
        assert metrics.total_lines == 10000
        assert "python" in metrics.languages


class TestWorkflowState:
    """Test WorkflowState model."""

    def test_create_workflow_state(self):
        """Test creating a workflow state."""
        state = WorkflowState(
            project_root="/path/to/project",
        )

        assert state.status == "initializing"
        assert state.tasks == {}
        assert state.agents == {}
        assert state.code_entities == {}
        assert state.pull_requests == []


class TestAgentState:
    """Test AgentState model."""

    def test_create_agent_state(self):
        """Test creating an agent state."""
        state = AgentState(
            agent_type=AgentType.DEVELOPER,
        )

        assert state.agent_type == AgentType.DEVELOPER
        assert state.current_task is None
        assert state.iteration_count == 0


class TestEnums:
    """Test enum values."""

    def test_task_status_values(self):
        """Test all task status values exist."""
        assert TaskStatus.PENDING.value == "pending"
        assert TaskStatus.IN_PROGRESS.value == "in_progress"
        assert TaskStatus.WAITING_FOR_REVIEW.value == "waiting_for_review"
        assert TaskStatus.COMPLETED.value == "completed"
        assert TaskStatus.FAILED.value == "failed"
        assert TaskStatus.CANCELLED.value == "cancelled"

    def test_agent_type_values(self):
        """Test all agent type values exist."""
        assert AgentType.ARCHITECT.value == "architect"
        assert AgentType.DEVELOPER.value == "developer"
        assert AgentType.QA.value == "qa"
        assert AgentType.DEVOPS.value == "devops"
        assert AgentType.REVIEWER.value == "reviewer"
        assert AgentType.REFACTOR.value == "refactor"
        assert AgentType.PLANNER.value == "planner"
        assert AgentType.MONITOR.value == "monitor"
