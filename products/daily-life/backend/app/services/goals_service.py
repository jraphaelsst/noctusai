"""
Goals Service — Business logic for goals, habits, and check-ins.

Handles check-in registration with valor_atual accumulation.
"""
from __future__ import annotations

import logging
from fastapi import HTTPException
from noctusai_lib.auth import first_or_none

logger = logging.getLogger(__name__)


def register_checkin(db, goal_id: str, user_id: str, data: str, valor: float | None, nota: str | None) -> dict:
    """Register a habit check-in and update the goal's valor_atual.

    Steps:
        1. Verify the goal exists and belongs to the user.
        2. Insert the check-in record.
        3. Sum all check-in values for this goal and update valor_atual.

    Returns:
        The newly created check-in row.

    Raises:
        HTTPException 404 if goal not found.
        HTTPException 500 if insert fails.
    """
    # 1. Verify goal exists and belongs to user
    goal_result = (
        db.table("metas")
        .select("id, tipo")
        .eq("id", goal_id)
        .eq("user_id", user_id)
        .execute()
    )
    if not first_or_none(goal_result):
        raise HTTPException(status_code=404, detail="Meta nao encontrada")

    # 2. Insert check-in
    checkin_result = db.table("checkins").insert({
        "meta_id": goal_id,
        "user_id": user_id,
        "data": data,
        "valor": valor,
        "nota": nota,
    }).execute()

    row = first_or_none(checkin_result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao registrar checkin")

    # 3. Accumulate valor_atual from all check-ins
    all_checkins = (
        db.table("checkins")
        .select("valor")
        .eq("meta_id", goal_id)
        .execute()
    )
    total_valor = sum(c.get("valor", 0) or 0 for c in (all_checkins.data or []))

    db.table("metas").update({
        "valor_atual": total_valor,
    }).eq("id", goal_id).execute()

    return row
