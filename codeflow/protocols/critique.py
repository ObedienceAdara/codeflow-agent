"""
Critique Protocol for Agent Communication

Defines structured feedback mechanisms for agent collaboration,
debate, and iterative refinement.
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, UTC


class CritiqueType(Enum):
    """Types of critique feedback."""
    ERROR = "error"           # Blocking issue that must be fixed
    WARNING = "warning"       # Non-blocking but should be addressed
    SUGGESTION = "suggestion" # Optional improvement
    QUESTION = "question"     # Clarification needed
    APPROVAL = "approval"     # Explicit approval


class SeverityLevel(Enum):
    """Severity levels for critiques."""
    CRITICAL = 1
    HIGH = 2
    MEDIUM = 3
    LOW = 4
    INFO = 5


@dataclass
class CritiquePoint:
    """A single point of critique or feedback."""
    critique_type: CritiqueType
    severity: SeverityLevel
    agent_id: str
    target_agent_id: str
    description: str
    location: Optional[str] = None  # File:line or component name
    suggestion: Optional[str] = None
    evidence: Optional[str] = None  # Code snippet, log, etc.
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.critique_type.value,
            "severity": self.severity.value,
            "agent": self.agent_id,
            "target": self.target_agent_id,
            "description": self.description,
            "location": self.location,
            "suggestion": self.suggestion,
            "evidence": self.evidence,
            "timestamp": self.timestamp.isoformat()
        }


@dataclass
class CritiqueReport:
    """
    Structured report containing multiple critique points
    for a specific task or artifact.
    """
    task_id: str
    reviewer_agent_id: str
    target_agent_id: str
    artifact_type: str  # code, design, test, config, etc.
    artifact_id: str
    overall_status: str  # approved, needs_revision, rejected
    critique_points: List[CritiquePoint] = field(default_factory=list)
    summary: str = ""
    confidence_score: float = 0.0  # 0.0 to 1.0
    
    @property
    def has_blocking_issues(self) -> bool:
        """Check if there are any blocking (ERROR) issues."""
        return any(
            cp.critique_type == CritiqueType.ERROR 
            for cp in self.critique_points
        )
    
    @property
    def critical_count(self) -> int:
        """Count of critical severity issues."""
        return sum(
            1 for cp in self.critique_points 
            if cp.severity == SeverityLevel.CRITICAL
        )
    
    @property
    def total_issues(self) -> int:
        """Total number of issues (excluding approvals)."""
        return sum(
            1 for cp in self.critique_points 
            if cp.critique_type != CritiqueType.APPROVAL
        )
    
    def add_critique(
        self,
        critique_type: CritiqueType,
        severity: SeverityLevel,
        description: str,
        location: Optional[str] = None,
        suggestion: Optional[str] = None,
        evidence: Optional[str] = None
    ):
        """Add a critique point to the report."""
        point = CritiquePoint(
            critique_type=critique_type,
            severity=severity,
            agent_id=self.reviewer_agent_id,
            target_agent_id=self.target_agent_id,
            description=description,
            location=location,
            suggestion=suggestion,
            evidence=evidence
        )
        self.critique_points.append(point)
        
        # Update overall status based on new critique
        if critique_type == CritiqueType.ERROR:
            self.overall_status = "rejected"
        elif critique_type == CritiqueType.WARNING and self.overall_status == "approved":
            self.overall_status = "needs_revision"
    
    def approve(self, summary: str = "", confidence: float = 1.0):
        """Mark the report as approved."""
        self.overall_status = "approved"
        self.summary = summary or "No issues found. Approved."
        self.confidence_score = confidence
        
        # Add approval point
        self.add_critique(
            critique_type=CritiqueType.APPROVAL,
            severity=SeverityLevel.INFO,
            description="Artifact approved without issues"
        )
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "task_id": self.task_id,
            "reviewer": self.reviewer_agent_id,
            "target": self.target_agent_id,
            "artifact_type": self.artifact_type,
            "artifact_id": self.artifact_id,
            "status": self.overall_status,
            "summary": self.summary,
            "confidence": self.confidence_score,
            "blocking": self.has_blocking_issues,
            "critical_count": self.critical_count,
            "total_issues": self.total_issues,
            "critiques": [cp.to_dict() for cp in self.critique_points],
            "timestamp": datetime.now(UTC).isoformat()
        }


@dataclass
class DebateRound:
    """Represents a single round of debate between agents."""
    round_number: int
    participants: List[str]
    critiques: List[CritiqueReport] = field(default_factory=list)
    responses: Dict[str, str] = field(default_factory=dict)  # agent_id -> response
    consensus_reached: bool = False
    decision: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def add_response(self, agent_id: str, response: str):
        """Add a response from an agent."""
        self.responses[agent_id] = response
    
    def mark_consensus(self, decision: str):
        """Mark that consensus has been reached."""
        self.consensus_reached = True
        self.decision = decision


@dataclass
class DebateContext:
    """
    Full context for an ongoing debate or discussion.
    Tracks all rounds, participants, and current state.
    """
    task_id: str
    topic: str
    initiator_agent_id: str
    participants: List[str]
    rounds: List[DebateRound] = field(default_factory=list)
    max_rounds: int = 5
    current_round: int = 0
    resolved: bool = False
    resolution: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_active(self) -> bool:
        """Check if debate is still active."""
        return not self.resolved and self.current_round < self.max_rounds
    
    @property
    def can_continue(self) -> bool:
        """Check if another round can be conducted."""
        return self.is_active and not any(
            r.consensus_reached for r in self.rounds
        )
    
    def start_round(self) -> DebateRound:
        """Start a new debate round."""
        if not self.can_continue:
            raise ValueError("Cannot start new round: debate ended or max rounds reached")
        
        self.current_round += 1
        round_obj = DebateRound(
            round_number=self.current_round,
            participants=self.participants
        )
        self.rounds.append(round_obj)
        return round_obj
    
    def resolve(self, resolution: str):
        """Mark the debate as resolved."""
        self.resolved = True
        self.resolution = resolution
    
    def get_summary(self) -> str:
        """Get a summary of the debate."""
        if self.resolved:
            return f"Debate resolved: {self.resolution}"
        
        return (
            f"Active debate on '{self.topic}' - "
            f"Round {self.current_round}/{self.max_rounds}, "
            f"{len(self.participants)} participants"
        )
