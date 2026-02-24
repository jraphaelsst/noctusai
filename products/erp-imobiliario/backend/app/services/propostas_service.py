"""
Propostas Service — Business logic for proposal and negotiation workflows.

Handles status transitions, history tracking, and statistics.
"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Valid status transitions for proposals
VALID_TRANSITIONS = {
    "enviada": {"em_analise", "recusada", "expirada"},
    "em_analise": {"contraproposta", "aceita", "recusada", "expirada"},
    "contraproposta": {"em_analise", "aceita", "recusada", "expirada"},
    "aceita": set(),  # Terminal state
    "recusada": set(),  # Terminal state
    "expirada": set(),  # Terminal state
}

ALL_STATUSES = {"enviada", "em_analise", "contraproposta", "aceita", "recusada", "expirada"}


class PropostasService:
    """Service for proposal business logic."""

    def __init__(self, db_client, user_id: str):
        self.db = db_client
        self.user_id = user_id

    @staticmethod
    def validate_status_transition(current_status: str, new_status: str) -> bool:
        """
        Check if the status transition is valid.

        Args:
            current_status: Current proposal status
            new_status: Target proposal status

        Returns:
            True if transition is valid
        """
        if current_status not in VALID_TRANSITIONS:
            return False
        return new_status in VALID_TRANSITIONS[current_status]

    @staticmethod
    def get_valid_transitions(current_status: str) -> set:
        """Get the set of valid next statuses from the current status."""
        return VALID_TRANSITIONS.get(current_status, set())

    @staticmethod
    def build_history_entry(action: str, details: Optional[Dict] = None, user_id: Optional[str] = None) -> Dict:
        """
        Build a history entry for the proposal timeline.

        Args:
            action: Description of the action taken
            details: Optional additional details
            user_id: ID of the user performing the action

        Returns:
            History entry dict
        """
        entry = {
            "action": action,
            "timestamp": datetime.utcnow().isoformat(),
        }
        if user_id:
            entry["user_id"] = user_id
        if details:
            entry["details"] = details
        return entry

    def get_stats(self, propostas: List[Dict]) -> Dict[str, int]:
        """
        Calculate proposal statistics by status.

        Args:
            propostas: List of proposal records

        Returns:
            Dict with count per status
        """
        stats = {status: 0 for status in ALL_STATUSES}
        stats["total"] = len(propostas)

        for p in propostas:
            status = p.get("status", "")
            if status in stats:
                stats[status] += 1

        return stats
