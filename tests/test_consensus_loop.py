"""Tests for ConsensusLoop."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from codeflow.orchestrator.consensus_loop import ConsensusLoop, LoopConfig, LoopState
from codeflow.orchestrator.debate_context import DebateContextManager
from codeflow.models.entities import Task, AgentType, TaskStatus


class TestLoopConfig:
    """Test LoopConfig dataclass."""

    def test_defaults(self):
        """Test default configuration."""
        config = LoopConfig()

        assert config.enabled is True
        assert config.max_iterations == 5
        assert config.min_approvals_required == 2
        assert config.auto_resolve_on_timeout is True
        assert config.require_unanimous_approval is False
        assert config.escalation_threshold == 3

    def test_should_continue_disabled(self):
        """Test loop stops when disabled."""
        config = LoopConfig(enabled=False)
        assert config.should_continue(0, 0, False) is False

    def test_should_continue_max_iterations(self):
        """Test loop stops at max iterations."""
        config = LoopConfig(max_iterations=3)
        assert config.should_continue(3, 0, False) is False

    def test_should_continue_blocking_issues(self):
        """Test loop continues when there are blocking issues."""
        config = LoopConfig(max_iterations=5)
        assert config.should_continue(1, 0, True) is True

    def test_should_continue_approved(self):
        """Test loop stops when enough approvals."""
        config = LoopConfig(max_iterations=5, min_approvals_required=2)
        assert config.should_continue(1, 2, False) is False

    def test_should_continue_unanimous(self):
        """Test unanimous approval requirement."""
        config = LoopConfig(max_iterations=5, min_approvals_required=1, require_unanimous_approval=True)
        # With unanimous approval required and min 1, need at least 1 approval
        # should_continue returns False when approval_count >= min_approvals_required
        assert config.should_continue(1, 1, False) is False
        assert config.should_continue(1, 0, False) is True


class TestLoopState:
    """Test LoopState dataclass."""

    def test_defaults(self):
        """Test default state values."""
        state = LoopState(task_id="task-1")

        assert state.task_id == "task-1"
        assert state.iteration == 0
        assert state.artifact is None
        assert state.critiques == []
        assert state.approvals == []
        assert state.rejections == []
        assert state.responses == {}
        assert state.consensus_reached is False
        assert state.final_decision is None
        assert state.escalated is False


class TestConsensusLoop:
    """Test ConsensusLoop class."""

    def test_init(self):
        """Test initialization."""
        loop = ConsensusLoop()

        assert loop.context_manager is not None
        assert isinstance(loop.context_manager, DebateContextManager)
        assert loop.active_loops == {}

    def test_create_critique_report_approval(self):
        """Test creating a critique report with approval."""
        loop = ConsensusLoop()

        reviewer = MagicMock()
        reviewer.agent_type = AgentType.REVIEWER

        target = MagicMock()
        target.agent_type = AgentType.DEVELOPER

        report = loop._create_critique_report(
            task_id="task-1",
            reviewer=reviewer,
            target=target,
            artifact="some code",
            validation_result={"valid": True, "summary": "Looks good", "confidence": 0.95},
        )

        assert report.overall_status == "approved"
        assert report.reviewer_agent_id == reviewer.agent_type.value
        assert report.target_agent_id == target.agent_type.value

    def test_create_critique_report_rejection(self):
        """Test creating a critique report with rejection."""
        loop = ConsensusLoop()

        reviewer = MagicMock()
        reviewer.agent_type = AgentType.REVIEWER

        target = MagicMock()
        target.agent_type = AgentType.DEVELOPER

        report = loop._create_critique_report(
            task_id="task-1",
            reviewer=reviewer,
            target=target,
            artifact="some code",
            validation_result={
                "valid": False,
                "issues": [
                    {
                        "description": "Security issue found",
                        "blocking": True,
                        "suggestion": "Fix the vulnerability",
                    }
                ],
            },
        )

        assert report.overall_status in ("needs_revision", "rejected")
        assert report.has_blocking_issues is True

    def test_format_fix_request(self):
        """Test formatting fix request from critiques."""
        loop = ConsensusLoop()

        # Create mock critiques
        from codeflow.protocols.critique import (
            CritiqueReport,
            CritiqueType,
            SeverityLevel,
            CritiquePoint,
        )

        report = CritiqueReport(
            task_id="task-1",
            reviewer_agent_id="reviewer",
            target_agent_id="developer",
            artifact_type="code",
            artifact_id="123",
            overall_status="needs_revision",
        )
        report.add_critique(
            critique_type=CritiqueType.ERROR,
            severity=SeverityLevel.CRITICAL,
            description="Critical bug found",
            suggestion="Fix immediately",
        )

        formatted = loop._format_fix_request([report])

        assert "BLOCKING" in formatted
        assert "Critical bug found" in formatted
        assert "Fix immediately" in formatted

    @pytest.mark.asyncio
    async def test_execute_loop_first_iteration(self):
        """Test first iteration of consensus loop."""
        context_manager = DebateContextManager()
        loop = ConsensusLoop(context_manager)

        # Mock primary agent
        primary_agent = AsyncMock()
        primary_agent.agent_type = AgentType.DEVELOPER
        primary_agent.process_task = AsyncMock(
            return_value=Task(
                title="Test task",
                description="A task",
                status=TaskStatus.COMPLETED,
                result="Completed successfully",
            )
        )

        # Mock validator that approves
        validator = AsyncMock()
        validator.agent_type = AgentType.REVIEWER
        validator.validate = AsyncMock(
            return_value=Task(
                title="Validate",
                description="Validation",
                status=TaskStatus.COMPLETED,
            )
        )

        # Create a task as initial input
        initial_task = Task(
            title="Initial task",
            description="Do something",
        )

        config = LoopConfig(
            max_iterations=3,
            min_approvals_required=1,
        )

        result = await loop.execute_loop(
            task_id="test-task-1",
            primary_agent=primary_agent,
            validator_agents=[validator],
            initial_input=initial_task,
            config=config,
        )

        assert result["success"] is True
        assert result["task_id"] == "test-task-1"
        # Primary agent should have been called at least once
        assert primary_agent.process_task.call_count >= 1

    def test_create_success_result(self):
        """Test creating a success result."""
        loop = ConsensusLoop()
        state = LoopState(
            task_id="task-1",
            iteration=2,
            artifact="final artifact",
            consensus_reached=True,
            final_decision="approved",
            approvals=["reviewer", "qa"],
            rejections=[],
        )

        result = loop._create_success_result(state)

        assert result["success"] is True
        assert result["task_id"] == "task-1"
        assert result["artifact"] == "final artifact"
        assert result["iterations"] == 2
        assert result["approvals"] == 2
        assert result["rejections"] == 0
        assert result["consensus_reached"] is True

    def test_create_failure_result(self):
        """Test creating a failure result."""
        loop = ConsensusLoop()
        state = LoopState(task_id="task-1", iteration=0)

        result = loop._create_failure_result(state, "Test error")

        assert result["success"] is False
        assert result["error"] == "Test error"
        assert result["consensus_reached"] is False
