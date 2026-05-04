"""
Goals Service — Business logic for goals, habits, and check-ins.

Handles check-in registration with valor_atual accumulation.
Wired to noctusai_lib.domain.metas.accumulate_contribution per
KB § PATTERNS/metas-seed.md § 4 (canonical wiring recipe).
"""
from __future__ import annotations

import logging
from fastapi import HTTPException
from noctusai_lib.api.auth import first_or_none
from noctusai_lib.domain.metas import accumulate_contribution

logger = logging.getLogger(__name__)


def register_checkin(db, goal_id: str, user_id: str, data: str, valor: float | None, nota: str | None) -> dict:
    """Register a habit check-in and update the goal's valor_atual.

    Steps:
        1. Verify the goal exists and belongs to the user; read current state.
        2. Insert the check-in record.
        3. Compute new valor_atual via seed accumulate_contribution.
        4. Persist new valor_atual; log milestone crossings.

    The math layer is the seed (`noctusai_lib.domain.metas.accumulate_contribution`).
    Persistence + RLS + schema-naming stay product-side per the wiring recipe.

    Returns:
        The newly created check-in row.

    Raises:
        HTTPException 404 if goal not found.
        HTTPException 500 if insert fails.
    """
    # 1. Verify goal exists and read state needed for seed math.
    goal_result = (
        db.table("metas")
        .select("id, tipo, meta_valor, valor_atual")
        .eq("id", goal_id)
        .eq("user_id", user_id)
        .execute()
    )
    goal_row = first_or_none(goal_result)
    if not goal_row:
        raise HTTPException(status_code=404, detail="Meta nao encontrada")

    # 2. Insert check-in.
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

    # 3. Delegate accumulation math to the seed.
    #
    # Habit goals may have meta_valor=None (no numeric target — pure check-yes/no
    # cadence). The seed Target validator allows zero (boundary case for
    # habit-check-yes/no goals); substitute 0.0 when the column is None.
    target = float(goal_row.get("meta_valor") or 0)
    current = float(goal_row.get("valor_atual") or 0)
    increment = float(valor or 0)
    transition = accumulate_contribution(target, current, increment)

    # 4. Persist new valor_atual.
    db.table("metas").update({
        "valor_atual": transition.new_current,
    }).eq("id", goal_id).execute()

    # 5. Surface milestone crossings for future gamification + notification
    # consumers. Engineer 3 shipped crossed_threshold_pct ahead of consumer
    # (metas-domain-seed-absorption proposal § 2.3); logging today preserves
    # the audit trail without committing to a UI surface.
    if transition.crossed_threshold_pct is not None:
        logger.info(
            "goal_milestone_crossed goal_id=%s user_id=%s pct=%.0f completed=%s",
            goal_id, user_id, transition.crossed_threshold_pct, transition.completed,
        )

    return row
