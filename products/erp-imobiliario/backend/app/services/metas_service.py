"""
Metas Service — Business logic for goals/targets creation.

Handles batch creation of daily metas from active configurations.
All date math (period_end_date, calcular_meta_proporcional) delegates
to `noctusai_lib.domain.metas` (kept pure-Python in the seed to avoid
N+1 RPC round-trips against the database). The local helpers are thin
shims that map ERP `tipo` strings ↔ seed `PeriodKind` and preserve the
legacy "unknown tipo" fallback at the boundary.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import List

from noctusai_lib.domain.metas import (
    PeriodKind,
    count_business_days,
    period_bounds,
    proportional_target,
    working_days_remaining_in_month,
    working_days_remaining_in_week,
    working_days_remaining_in_year,
    working_days_total_in_month,
    working_days_total_in_year,
)

logger = logging.getLogger(__name__)

TIPOS = ["diaria", "semanal", "mensal", "anual"]
_TIPO_TO_PERIOD_KIND: dict[str, PeriodKind] = {
    "diaria": PeriodKind.DAILY,
    "semanal": PeriodKind.WEEKLY,
    "mensal": PeriodKind.MONTHLY,
    "anual": PeriodKind.YEARLY,
}


def _period_end_date(tipo: str, data_ref: date) -> date:
    """End-date of the period containing data_ref. Returns data_ref for
    unknown tipos (legacy fallback)."""
    kind = _TIPO_TO_PERIOD_KIND.get(tipo)
    if kind is None:
        return data_ref
    _, end = period_bounds(kind, data_ref)
    return end


def _count_weekdays(start: date, end: date) -> int:
    """Mon-Fri count, inclusive on both ends. Delegates to seed."""
    return count_business_days(start, end)


def _dias_uteis_totais_mes(data_ref: date) -> int:
    """Total Mon-Fri count in the month of data_ref."""
    return working_days_total_in_month(data_ref)


def _dias_uteis_restantes_semana(data_ref: date) -> int:
    """Mon-Fri count from data_ref through Sunday of the same ISO week."""
    return working_days_remaining_in_week(data_ref)


def _dias_uteis_restantes_mes(data_ref: date) -> int:
    """Mon-Fri count from data_ref through last day of the month."""
    return working_days_remaining_in_month(data_ref)


def _dias_uteis_totais_ano(data_ref: date) -> int:
    """Total Mon-Fri count in the year of data_ref."""
    return working_days_total_in_year(data_ref)


def _dias_uteis_restantes_ano(data_ref: date) -> int:
    """Mon-Fri count from data_ref through Dec 31 of the same year."""
    return working_days_remaining_in_year(data_ref)


def _calcular_meta_proporcional(meta_mensal: int, tipo: str, data_ref: date) -> int:
    """Per-tipo proportional target. Returns meta_mensal for unknown
    tipos (legacy fallback)."""
    kind = _TIPO_TO_PERIOD_KIND.get(tipo)
    if kind is None:
        return meta_mensal
    return proportional_target(meta_mensal, kind, data_ref)


# --------------- Main Logic ---------------


def criar_metas_hoje(user_id: str, data_hoje: str, db, admin) -> int:
    """
    Create today's metas from active metas_config entries.

    Uses 3 DB queries total regardless of config count:
    1. Fetch active configs
    2. Batch fetch existing metas for the user (replaces N×4 RPC calls)
    3. Batch insert new metas

    Args:
        user_id: The user's ID.
        data_hoje: Current date in São Paulo timezone (ISO string).
        db: Supabase user client (respects RLS).
        admin: Supabase admin client (unused after RPC removal, kept for signature compat).

    Returns:
        Number of metas created.
    """
    # data_hoje may come as str, date, or list (from RPC response wrapping)
    raw = data_hoje
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if raw is None:
        return 0
    ref = raw if isinstance(raw, date) else date.fromisoformat(str(raw))

    # 1. Fetch active configs
    configs_result = (
        db.table("metas_config")
        .select("*")
        .eq("usuario_id", user_id)
        .eq("ativo", True)
        .execute()
    )
    configs = configs_result.data or []
    if not configs:
        return 0

    # 2. Batch fetch all existing metas for this user — replaces N×4 ensure_scaffold_meta RPCs.
    # We need to know which (tipo, categoria, data_prazo) combos already exist.
    existing_result = db.table("metas").select(
        "tipo, categoria, data_prazo"
    ).eq("usuario_id", user_id).execute()
    existing_keys: set[tuple] = {
        (m["tipo"], m["categoria"], m["data_prazo"])
        for m in (existing_result.data or [])
    }

    # 3. Build list of metas to create (all date math in Python)
    metas_to_insert: List[dict] = []

    for cfg in configs:
        for tipo in TIPOS:
            data_prazo = _period_end_date(tipo, ref).isoformat()

            # Skip if already exists (replaces ensure_scaffold_meta RPC)
            if (tipo, cfg["categoria"], data_prazo) in existing_keys:
                continue

            meta_pretendida = _calcular_meta_proporcional(
                cfg["meta_pretendida"], tipo, ref,
            )

            metas_to_insert.append({
                "usuario_id": user_id,
                "tipo": tipo,
                "categoria": cfg["categoria"],
                "categoria_custom": cfg.get("categoria_custom"),
                "meta_pretendida": meta_pretendida,
                "meta_realizada": 0,
                "data_prazo": data_prazo,
                "status": "no_prazo",
                "criada_manualmente": False,
            })

    # 4. Batch insert
    if metas_to_insert:
        db.table("metas").insert(metas_to_insert).execute()

    return len(metas_to_insert)
