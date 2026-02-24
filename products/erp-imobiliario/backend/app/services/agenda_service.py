"""
Agenda service — scheduling conflict detection and helpers.
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def check_conflict(
    corretor_id: str,
    data_inicio: str,
    data_fim: str,
    supabase,
    exclude_id: Optional[str] = None,
) -> Optional[dict]:
    """
    Check if a corretor already has an event overlapping the given time range.

    Two events overlap when:
      existing.data_inicio < new.data_fim AND existing.data_fim > new.data_inicio

    Returns the conflicting event dict or None if no conflict.
    """
    query = (
        supabase.table("eventos")
        .select("id, titulo, data_inicio, data_fim")
        .eq("corretor_id", corretor_id)
        .neq("status", "cancelado")
        .lt("data_inicio", data_fim)
        .gt("data_fim", data_inicio)
    )

    if exclude_id:
        query = query.neq("id", exclude_id)

    result = query.execute()
    conflitos = result.data or []

    if conflitos:
        return conflitos[0]
    return None
