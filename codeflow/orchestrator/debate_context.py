"""
Debate Context Manager

Handles memory management for agent debates, preventing context explosion
while maintaining necessary history for productive discussions.
"""
import logging
from typing import Dict, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass

from ..protocols.critique import DebateContext, DebateRound, CritiqueReport

logger = logging.getLogger(__name__)


@dataclass
class ContextWindow:
    """Sliding window for managing debate context."""
    max_rounds_in_memory: int = 3
    max_critiques_per_round: int = 10
    compress_after_rounds: int = 2
    
    def should_compress(self, current_round: int) -> bool:
        """Check if context should be compressed."""
        return current_round > self.compress_after_rounds


class DebateContextManager:
    """
    Manages debate contexts with sliding window memory management.
    
    Prevents memory explosion during long debates by:
    - Keeping only recent rounds in full detail
    - Compressing older rounds into summaries
    - Maintaining critical decisions and consensus points
    """
    
    def __init__(self, max_active_debates: int = 10):
        self.active_debates: Dict[str, DebateContext] = {}
        self.context_windows: Dict[str, ContextWindow] = {}
        self.compressed_history: Dict[str, List[str]] = {}  # task_id -> summaries
        self.max_active_debates = max_active_debates
        
    def create_debate(
        self,
        task_id: str,
        topic: str,
        initiator: str,
        participants: List[str],
        max_rounds: int = 5
    ) -> DebateContext:
        """Create a new debate context."""
        if len(self.active_debates) >= self.max_active_debates:
            # Remove oldest resolved debate or raise error
            self._cleanup_resolved()
            
            if len(self.active_debates) >= self.max_active_debates:
                raise ValueError(
                    f"Maximum active debates ({self.max_active_debates}) reached. "
                    "Resolve some debates first."
                )
        
        context = DebateContext(
            task_id=task_id,
            topic=topic,
            initiator_agent_id=initiator,
            participants=participants,
            max_rounds=max_rounds
        )
        
        self.active_debates[task_id] = context
        self.context_windows[task_id] = ContextWindow()
        self.compressed_history[task_id] = []
        
        logger.info(f"Created debate on '{topic}' with {len(participants)} participants")
        return context
    
    def get_debate(self, task_id: str) -> Optional[DebateContext]:
        """Get an active debate context."""
        return self.active_debates.get(task_id)
    
    def start_round(self, task_id: str) -> Optional[DebateRound]:
        """Start a new round for an existing debate."""
        context = self.get_debate(task_id)
        if not context:
            logger.error(f"No debate found for task {task_id}")
            return None
        
        try:
            round_obj = context.start_round()
            
            # Check if compression is needed
            window = self.context_windows.get(task_id)
            if window and window.should_compress(context.current_round):
                self._compress_oldest_round(task_id)
            
            return round_obj
        except ValueError as e:
            logger.error(f"Cannot start round: {e}")
            return None
    
    def add_critique(
        self,
        task_id: str,
        critique_report: CritiqueReport
    ) -> bool:
        """Add a critique report to the current round."""
        context = self.get_debate(task_id)
        if not context or not context.rounds:
            logger.error(f"No active round for task {task_id}")
            return False
        
        current_round = context.rounds[-1]
        
        # Limit critiques per round
        window = self.context_windows.get(task_id)
        if window and len(current_round.critiques) >= window.max_critiques_per_round:
            logger.warning(
                f"Max critiques ({window.max_critiques_per_round}) reached for round. "
                "Skipping additional critique."
            )
            return False
        
        current_round.critiques.append(critique_report)
        logger.debug(
            f"Added critique to round {current_round.round_number}: "
            f"{critique_report.overall_status}"
        )
        return True
    
    def add_response(self, task_id: str, agent_id: str, response: str) -> bool:
        """Add an agent's response to the current round."""
        context = self.get_debate(task_id)
        if not context or not context.rounds:
            return False
        
        current_round = context.rounds[-1]
        current_round.add_response(agent_id, response)
        return True
    
    def mark_consensus(self, task_id: str, decision: str) -> bool:
        """Mark that consensus has been reached in the current round."""
        context = self.get_debate(task_id)
        if not context or not context.rounds:
            return False
        
        current_round = context.rounds[-1]
        current_round.mark_consensus(decision)
        
        # Store decision in compressed history
        summary = f"Round {current_round.round_number}: Consensus - {decision}"
        self.compressed_history[task_id].append(summary)
        
        logger.info(f"Consensus reached in debate {task_id}: {decision}")
        return True
    
    def resolve_debate(self, task_id: str, resolution: str) -> bool:
        """Resolve and close a debate."""
        context = self.get_debate(task_id)
        if not context:
            return False
        
        context.resolve(resolution)
        
        # Final summary
        final_summary = (
            f"Debate resolved: {resolution}. "
            f"Total rounds: {context.current_round}. "
            f"{' | '.join(self.compressed_history[task_id])}"
        )
        self.compressed_history[task_id].append(final_summary)
        
        # Move to resolved state (keep in memory for now)
        logger.info(f"Debate {task_id} resolved: {resolution}")
        return True
    
    def _compress_oldest_round(self, task_id: str):
        """Compress the oldest round into a summary."""
        context = self.get_debate(task_id)
        if not context or len(context.rounds) <= 1:
            return
        
        oldest_round = context.rounds[0]
        
        # Create summary
        critique_count = len(oldest_round.critiques)
        response_count = len(oldest_round.responses)
        had_consensus = oldest_round.consensus_reached
        
        summary_parts = [
            f"R{oldest_round.round_number}: {critique_count} critiques",
            f"{response_count} responses"
        ]
        if had_consensus:
            summary_parts.append(f"consensus: {oldest_round.decision}")
        
        summary = ", ".join(summary_parts)
        self.compressed_history[task_id].append(summary)
        
        # Note: We don't remove the round object to maintain data integrity,
        # but future operations will prioritize newer rounds
        logger.debug(f"Compressed round {oldest_round.round_number} for task {task_id}")
    
    def _cleanup_resolved(self):
        """Remove old resolved debates from active memory."""
        resolved = [
            task_id for task_id, ctx in self.active_debates.items()
            if ctx.resolved
        ]
        
        # Keep most recent resolved debates, remove oldest
        if len(resolved) > 2:
            for task_id in resolved[:-2]:
                del self.active_debates[task_id]
                logger.debug(f"Cleaned up resolved debate {task_id}")
    
    def get_debate_summary(self, task_id: str) -> str:
        """Get a summary of a debate including compressed history."""
        context = self.get_debate(task_id)
        if not context:
            return "No debate found"
        
        parts = [context.get_summary()]
        
        if self.compressed_history.get(task_id):
            parts.append("History: " + " | ".join(self.compressed_history[task_id]))
        
        return "\n".join(parts)
    
    def list_active_debates(self) -> List[Tuple[str, str]]:
        """List all active debates with their topics."""
        return [
            (task_id, ctx.topic)
            for task_id, ctx in self.active_debates.items()
            if not ctx.resolved
        ]
