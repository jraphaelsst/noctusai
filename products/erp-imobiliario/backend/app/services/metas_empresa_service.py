"""
Metas Empresa Service — business logic for company-level VGV targets.

The owner sets `metas_empresa.valor_meta` per period. Leaders then
distribute that envelope across teams via `metas_equipe`. This service
exposes CRUD + the invariant check that guards the cascade:

    sum(metas_equipe.valor_meta where periodo=P) <= metas_empresa.valor_meta for P

See products/erp-imobiliario/METAS-PLAN.md §2 (VGV cascade) and §5.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_CATEGORIA = "vgv"


# ── CRUD ─────────────────────────────────────────────────────────────

def listar_metas_empresa(db, *, periodo_id: str | None = None,
                          categoria: str | None = None) -> list[dict]:
    query = db.table("metas_empresa").select("*")
    if periodo_id:
        query = query.eq("periodo_id", periodo_id)
    if categoria:
        query = query.eq("categoria", categoria)
    result = query.order("definida_em", desc=True).execute()
    return result.data or []


def obter_meta_empresa(db, meta_id: str) -> dict | None:
    result = db.table("metas_empresa").select("*").eq("id", meta_id).limit(1).execute()
    return (result.data or [None])[0]


def upsert_meta_empresa(db, *, periodo_id: str, valor_meta: float,
                        categoria: str = DEFAULT_CATEGORIA,
                        definida_por: str | None = None,
                        observacoes: str | None = None) -> dict:
    """Insert or update the company meta for (periodo, categoria).

    The schema has `UNIQUE (periodo_id, categoria)`, so one row per
    (period, category). This helper upserts.
    """
    if valor_meta < 0:
        raise ValueError("valor_meta deve ser >= 0")

    # Look for existing
    existing = (
        db.table("metas_empresa").select("*")
        .eq("periodo_id", periodo_id)
        .eq("categoria", categoria)
        .limit(1)
        .execute()
    )
    payload: dict[str, Any] = {
        "periodo_id": periodo_id,
        "categoria": categoria,
        "valor_meta": valor_meta,
        "definida_por": definida_por,
        "observacoes": observacoes,
    }
    if existing.data:
        result = db.table("metas_empresa").update(payload).eq("id", existing.data[0]["id"]).execute()
    else:
        result = db.table("metas_empresa").insert(payload).execute()
    if not result.data:
        raise RuntimeError("Falha ao salvar meta de empresa")
    return result.data[0]


def atualizar_meta_empresa(db, meta_id: str, patch: dict) -> dict:
    clean = {k: v for k, v in patch.items() if v is not None}
    if not clean:
        existing = obter_meta_empresa(db, meta_id)
        if existing is None:
            raise LookupError("Meta de empresa não encontrada")
        return existing
    if "valor_meta" in clean and clean["valor_meta"] < 0:
        raise ValueError("valor_meta deve ser >= 0")
    result = db.table("metas_empresa").update(clean).eq("id", meta_id).execute()
    if not result.data:
        raise LookupError("Meta de empresa não encontrada")
    return result.data[0]


def deletar_meta_empresa(db, meta_id: str) -> None:
    result = db.table("metas_empresa").delete().eq("id", meta_id).execute()
    if not result.data:
        raise LookupError("Meta de empresa não encontrada")


# ── Cascade invariant ───────────────────────────────────────────────

def resumo_cascata(db, *, periodo_id: str, categoria: str = DEFAULT_CATEGORIA) -> dict:
    """Return the cascade state for a period: company meta + sum of team allocations.

    Use case: owner UI shows "R$ 30M target, R$ 22M allocated, R$ 8M unassigned".
    """
    empresa = (
        db.table("metas_empresa").select("*")
        .eq("periodo_id", periodo_id)
        .eq("categoria", categoria)
        .limit(1)
        .execute()
    )
    empresa_row = (empresa.data or [None])[0]

    equipes_rows = (
        db.table("metas_equipe").select("equipe_id, valor_meta")
        .eq("periodo_id", periodo_id)
        .eq("categoria", categoria)
        .execute()
    ).data or []

    meta_total = float(empresa_row["valor_meta"]) if empresa_row else 0.0
    alocado = sum(float(r["valor_meta"]) for r in equipes_rows)
    return {
        "periodo_id": periodo_id,
        "categoria": categoria,
        "meta_empresa": meta_total,
        "alocado_em_equipes": alocado,
        "saldo_a_alocar": max(0.0, meta_total - alocado),
        "estouro": max(0.0, alocado - meta_total),
        "equipes_count": len(equipes_rows),
    }
