"""
Metas Service — Business logic for goals/targets creation.

Handles batch creation of daily metas from active configurations.
All date math (period_end_date, calcular_meta_proporcional) is computed
in Python to avoid N+1 RPC round-trips to the database.
"""
from __future__ import annotations

import logging
import math
from datetime import date, timedelta
from typing import List

logger = logging.getLogger(__name__)

TIPOS = ["diaria", "semanal", "mensal", "anual"]


# --------------- Date Math (replaces DB RPCs) ---------------


def _period_end_date(tipo: str, data_ref: date) -> date:
    """Calculate the end date of the period for a given tipo.

    Replaces the DB function erp.period_end_date().
    """
    if tipo == "diaria":
        return data_ref
    if tipo == "semanal":
        # Sunday of the same ISO week
        return data_ref + timedelta(days=7 - data_ref.isoweekday())
    if tipo == "mensal":
        # Last day of the month
        if data_ref.month == 12:
            return date(data_ref.year + 1, 1, 1) - timedelta(days=1)
        return date(data_ref.year, data_ref.month + 1, 1) - timedelta(days=1)
    if tipo == "anual":
        return date(data_ref.year, 12, 31)
    return data_ref


def _count_weekdays(start: date, end: date) -> int:
    """Count weekdays (Mon–Fri) between start and end (inclusive)."""
    count = 0
    d = start
    while d <= end:
        if d.isoweekday() <= 5:
            count += 1
        d += timedelta(days=1)
    return count


def _dias_uteis_totais_mes(data_ref: date) -> int:
    """Total working days in the month of data_ref."""
    first = data_ref.replace(day=1)
    if data_ref.month == 12:
        last = date(data_ref.year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(data_ref.year, data_ref.month + 1, 1) - timedelta(days=1)
    return _count_weekdays(first, last)


def _dias_uteis_restantes_semana(data_ref: date) -> int:
    """Working days remaining in the ISO week (including today)."""
    sunday = data_ref + timedelta(days=7 - data_ref.isoweekday())
    return _count_weekdays(data_ref, sunday)


def _dias_uteis_restantes_mes(data_ref: date) -> int:
    """Working days remaining in the month (including today)."""
    if data_ref.month == 12:
        last = date(data_ref.year + 1, 1, 1) - timedelta(days=1)
    else:
        last = date(data_ref.year, data_ref.month + 1, 1) - timedelta(days=1)
    return _count_weekdays(data_ref, last)


def _dias_uteis_totais_ano(data_ref: date) -> int:
    """Total working days in the year of data_ref."""
    return _count_weekdays(date(data_ref.year, 1, 1), date(data_ref.year, 12, 31))


def _dias_uteis_restantes_ano(data_ref: date) -> int:
    """Working days remaining in the year (including today)."""
    return _count_weekdays(data_ref, date(data_ref.year, 12, 31))


def _calcular_meta_proporcional(meta_mensal: int, tipo: str, data_ref: date) -> int:
    """Calculate proportional target for a given period type.

    Replaces the DB function erp.calcular_meta_proporcional().
    """
    if tipo == "diaria":
        total = _dias_uteis_totais_mes(data_ref)
        return math.ceil(meta_mensal / max(total, 1))
    if tipo == "semanal":
        total = _dias_uteis_totais_mes(data_ref)
        restantes = _dias_uteis_restantes_semana(data_ref)
        diaria = meta_mensal / max(total, 1)
        return math.ceil(diaria * restantes)
    if tipo == "mensal":
        total = _dias_uteis_totais_mes(data_ref)
        restantes = _dias_uteis_restantes_mes(data_ref)
        return math.ceil(meta_mensal * restantes / max(total, 1))
    if tipo == "anual":
        total = _dias_uteis_totais_ano(data_ref)
        restantes = _dias_uteis_restantes_ano(data_ref)
        return math.ceil(meta_mensal * 12 * restantes / max(total, 1))
    return meta_mensal


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
