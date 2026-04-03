"""
Consensus Loop Engine

Implements iterative feedback loops where agents debate, critique, and refine
work until validation passes or consensus is reached.
"""
import logging
from typing import Any, Dict, List, Optional, Type
from dataclasses import dataclass, field

from ..protocols.critique import (
    CritiqueReport,
    CritiqueType,
    SeverityLevel,
    DebateContext
)
from .debate_context import DebateContextManager
from ..agents.base import BaseAgent

logger = logging.getLogger(__name__)


@dataclass
class LoopConfig:
    """Configuration for consensus loop behavior."""
    enabled: bool = True
    max_iterations: int = 5
    min_approvals_required: int = 2
    auto_resolve_on_timeout: bool = True
    require_unanimous_approval: bool = False
    escalation_threshold: int = 3  # Iterations before escalating
    
    def should_continue(
        self,
        current_iteration: int,
        approval_count: int,
        has_blocking_issues: bool
    ) -> bool:
        """Determine if the loop should continue."""
        if not self.enabled:
            return False
        
        if current_iteration >= self.max_iterations:
            return False
        
        if has_blocking_issues:
            return True
        
        if self.require_unanimous_approval:
            return approval_count < self.min_approvals_required
        
        return approval_count < self.min_approvals_required


@dataclass
class LoopState:
    """Current state of a consensus loop."""
    task_id: str
    iteration: int = 0
    artifact: Any = None
    critiques: List[CritiqueReport] = field(default_factory=list)
    approvals: List[str] = field(default_factory=list)  # agent_ids
    rejections: List[str] = field(default_factory=list)  # agent_ids
    responses: Dict[str, str] = field(default_factory=dict)
    consensus_reached: bool = False
    final_decision: Optional[str] = None
    escalated: bool = False


class ConsensusLoop:
    """
    Orchestrates iterative feedback loops between agents.
    
    Workflow:
    1. Primary agent produces artifact
    2. Validator agents review and critique
    3. If issues found, primary agent responds/fixes
    4. Repeat until consensus or max iterations
    5. Escalate if no resolution
    """
    
    def __init__(self, context_manager: Optional[DebateContextManager] = None):
        self.context_manager = context_manager or DebateContextManager()
        self.active_loops: Dict[str, LoopState] = {}
        
    def execute_loop(
        self,
        task_id: str,
        primary_agent: BaseAgent,
        validator_agents: List[BaseAgent],
        initial_input: Any,
        config: LoopConfig = None,
        topic: str = "Artifact Review"
    ) -> Dict[str, Any]:
        """
        Execute a consensus loop for a task.
        
        Args:
            task_id: Unique identifier for the task
            primary_agent: Agent producing the artifact
            validator_agents: Agents reviewing the artifact
            initial_input: Input for the primary agent
            config: Loop configuration
            topic: Topic for debate context
            
        Returns:
            Dictionary with final artifact, status, and loop metadata
        """
        config = config or LoopConfig()
        
        logger.info(
            f"Starting consensus loop for task {task_id} with "
            f"{len(validator_agents)} validators"
        )
        
        # Initialize loop state
        state = LoopState(task_id=task_id)
        self.active_loops[task_id] = state
        
        # Create debate context
        participants = [primary_agent.agent_id] + [
            agent.agent_id for agent in validator_agents
        ]
        
        try:
            debate_ctx = self.context_manager.create_debate(
                task_id=task_id,
                topic=topic,
                initiator=primary_agent.agent_id,
                participants=participants,
                max_rounds=config.max_iterations
            )
        except ValueError as e:
            logger.error(f"Failed to create debate context: {e}")
            return self._create_failure_result(state, str(e))
        
        # Main loop
        while config.should_continue(
            state.iteration,
            len(state.approvals),
            any(r.has_blocking_issues for r in state.critiques[-len(validator_agents):])
            if state.critiques else False
        ):
            state.iteration += 1
            logger.info(f"Iteration {state.iteration}/{config.max_iterations}")
            
            # Start new debate round
            round_obj = self.context_manager.start_round(task_id)
            if not round_obj:
                logger.error("Failed to start debate round")
                break
            
            # Primary agent produces/updates artifact
            try:
                if state.iteration == 1:
                    # First iteration: generate initial artifact
                    result = primary_agent.execute(initial_input)
                else:
                    # Subsequent iterations: fix based on critiques
                    latest_critiques = state.critiques[-len(validator_agents):]
                    fix_request = self._format_fix_request(latest_critiques)
                    result = primary_agent.execute({
                        "original_input": initial_input,
                        "previous_artifact": state.artifact,
                        "critiques": fix_request
                    })
                
                state.artifact = result.get("artifact") if isinstance(result, dict) else result
                
                # Record primary agent's response
                self.context_manager.add_response(
                    task_id,
                    primary_agent.agent_id,
                    f"Produced artifact (iteration {state.iteration})"
                )
                
            except Exception as e:
                logger.error(f"Primary agent failed: {e}")
                state.rejections.append(primary_agent.agent_id)
                state.responses[primary_agent.agent_id] = f"Error: {e}"
                continue
            
            # Validators review
            all_approved = True
            has_blocking = False
            
            for validator in validator_agents:
                try:
                    # Validate the artifact
                    validation = validator.validate(state.artifact)
                    
                    # Convert validation to critique report
                    critique = self._create_critique_report(
                        task_id=task_id,
                        reviewer=validator,
                        target=primary_agent,
                        artifact=state.artifact,
                        validation_result=validation
                    )
                    
                    state.critiques.append(critique)
                    self.context_manager.add_critique(task_id, critique)
                    
                    # Track approval/rejection
                    if critique.overall_status == "approved":
                        state.approvals.append(validator.agent_id)
                        self.context_manager.add_response(
                            task_id,
                            validator.agent_id,
                            "Approved"
                        )
                    else:
                        state.rejections.append(validator.agent_id)
                        all_approved = False
                        
                        if critique.has_blocking_issues:
                            has_blocking = True
                            
                        self.context_manager.add_response(
                            task_id,
                            validator.agent_id,
                            f"Rejected: {critique.summary}"
                        )
                    
                except Exception as e:
                    logger.error(f"Validator {validator.agent_id} failed: {e}")
                    state.rejections.append(validator.agent_id)
                    all_approved = False
            
            # Check for consensus
            approval_count = len(state.approvals)
            required = config.min_approvals_required
            
            if config.require_unanimous_approval:
                required = len(validator_agents)
            
            if approval_count >= required and not has_blocking:
                state.consensus_reached = True
                state.final_decision = "approved"
                
                self.context_manager.mark_consensus(
                    task_id,
                    f"Approved with {approval_count}/{len(validator_agents)} validations"
                )
                break
            
            # Check if we've hit max iterations
            if state.iteration >= config.max_iterations:
                logger.warning("Max iterations reached without consensus")
                
                if config.auto_resolve_on_timeout:
                    # Auto-resolve based on majority
                    if len(state.approvals) > len(state.rejections):
                        state.final_decision = "approved_with_warnings"
                    else:
                        state.final_decision = "rejected"
                        state.escalated = True
                    
                    self.context_manager.resolve_debate(
                        task_id,
                        f"Timeout resolution: {state.final_decision}"
                    )
                else:
                    state.escalated = True
                    state.final_decision = "escalated"
                
                break
        
        # Cleanup
        if state.final_decision and not state.consensus_reached:
            self.context_manager.resolve_debate(
                task_id,
                state.final_decision
            )
        
        del self.active_loops[task_id]
        
        return self._create_success_result(state)
    
    def _create_critique_report(
        self,
        task_id: str,
        reviewer: BaseAgent,
        target: BaseAgent,
        artifact: Any,
        validation_result: Dict[str, Any]
    ) -> CritiqueReport:
        """Convert validation result to critique report."""
        is_valid = validation_result.get("valid", False)
        issues = validation_result.get("issues", [])
        summary = validation_result.get("summary", "")
        
        report = CritiqueReport(
            task_id=task_id,
            reviewer_agent_id=reviewer.agent_id,
            target_agent_id=target.agent_id,
            artifact_type="code",  # Could be parameterized
            artifact_id=str(hash(str(artifact))),
            overall_status="approved" if is_valid else "needs_revision"
        )
        
        if is_valid:
            report.approve(summary=summary, confidence=validation_result.get("confidence", 0.9))
        else:
            for issue in issues:
                severity = SeverityLevel.MEDIUM
                if issue.get("blocking", False):
                    severity = SeverityLevel.CRITICAL
                    critique_type = CritiqueType.ERROR
                elif issue.get("severity", "").lower() == "high":
                    severity = SeverityLevel.HIGH
                    critique_type = CritiqueType.WARNING
                else:
                    critique_type = CritiqueType.SUGGESTION
                
                report.add_critique(
                    critique_type=critique_type,
                    severity=severity,
                    description=issue.get("description", "Issue found"),
                    location=issue.get("location"),
                    suggestion=issue.get("suggestion"),
                    evidence=issue.get("evidence")
                )
        
        return report
    
    def _format_fix_request(self, critiques: List[CritiqueReport]) -> str:
        """Format critiques into a fix request for the primary agent."""
        parts = ["Please address the following issues:"]
        
        for i, critique in enumerate(critiques, 1):
            if critique.has_blocking_issues:
                parts.append(f"\n{i}. [BLOCKING] {critique.summary}")
            else:
                parts.append(f"\n{i}. {critique.summary}")
            
            for point in critique.critique_points:
                if point.critique_type != CritiqueType.APPROVAL:
                    parts.append(f"   - {point.description}")
                    if point.suggestion:
                        parts.append(f"     Suggestion: {point.suggestion}")
        
        return "\n".join(parts)
    
    def _create_success_result(self, state: LoopState) -> Dict[str, Any]:
        """Create successful loop result."""
        return {
            "success": True,
            "task_id": state.task_id,
            "artifact": state.artifact,
            "status": state.final_decision or "completed",
            "iterations": state.iteration,
            "approvals": len(state.approvals),
            "rejections": len(state.rejections),
            "consensus_reached": state.consensus_reached,
            "escalated": state.escalated,
            "total_critiques": len(state.critiques)
        }
    
    def _create_failure_result(self, state: LoopState, error: str) -> Dict[str, Any]:
        """Create failure result."""
        return {
            "success": False,
            "task_id": state.task_id,
            "artifact": None,
            "status": "failed",
            "error": error,
            "iterations": state.iteration,
            "consensus_reached": False,
            "escalated": False
        }
