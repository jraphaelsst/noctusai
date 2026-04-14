"""
Tasks Service — Business logic for task management.

Handles stats aggregation and priority mapping, keeping routers thin.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

PRIORIDADE_MAP = {"alta": 3, "media": 2, "baixa": 1}


def get_prioridade_ordem(prioridade: str) -> int:
    """Map a priority label to its sort order value."""
    return PRIORIDADE_MAP.get(prioridade, 2)


def compute_task_stats(tasks: list[dict]) -> dict:
    """Aggregate task counts by status.

    Args:
        tasks: List of task dicts (must contain a ``status`` key).

    Returns:
        Dict with total and per-status counts.
    """
    stats = {"total": len(tasks), "pendente": 0, "em_progresso": 0, "concluida": 0, "cancelada": 0}
    for t in tasks:
        s = t.get("status", "pendente")
        if s in stats:
            stats[s] += 1
    return stats
