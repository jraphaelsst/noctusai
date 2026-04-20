"""
Metas Equipe Service — team-level VGV quotas allocated from the company meta.

Invariant: SUM(metas_equipe where periodo=P) <= metas_empresa where periodo=P.
The upsert validates this; the resumo endpoint exposes remaining allocation.

See METAS-PLAN §5, §6 (cascade enforcement).
"""
from __future__ import annotations

from typing import Any

DEFAULT_CATEGORIA = "vgv"


def listar_metas_equipe(db, *, periodo_id: str | None = None,
                         equipe_id: str | None = None,
                         categoria: str | None = None) -> list[dict]:
    query = db.table("metas_equipe").select("*")
    if periodo_id:
        query = query.eq("periodo_id", periodo_id)
    if equipe_id:
        query = query.eq("equipe_id", equipe_id)
    if categoria:
        query = query.eq("categoria", categoria)
    return query.order("definida_em", desc=True).execute().data or []


def obter_meta_equipe(db, meta_id: str) -> dict | None:
    result = db.table("metas_equipe").select("*").eq("id", meta_id).limit(1).execute()
    return (result.data or [None])[0]


def upsert_meta_equipe(db, *, periodo_id: str, equipe_id: str, valor_meta: float,
                        categoria: str = DEFAULT_CATEGORIA,
                        definida_por: str | None = None,
                        enforce_cascade: bool = True) -> dict:
    """Insert/update team meta. Optionally enforces company-meta cap."""
    if valor_meta < 0:
        raise ValueError("valor_meta deve ser >= 0")

    if enforce_cascade:
        company = (
            db.table("metas_empresa").select("valor_meta")
            .eq("periodo_id", periodo_id).eq("categoria", categoria).limit(1).execute()
        ).data
        if company:
            siblings = (
                db.table("metas_equipe").select("id, valor_meta")
                .eq("periodo_id", periodo_id).eq("categoria", categoria).execute()
            ).data or []
            existing_id = next(
                (s["id"] for s in siblings if s.get("equipe_id") == equipe_id), None
            )
            others_sum = sum(float(s["valor_meta"]) for s in siblings if s["id"] != existing_id)
            cap = float(company[0]["valor_meta"])
            if others_sum + valor_meta > cap:
                raise ValueError(
                    f"Alocação estoura a meta da empresa: "
                    f"outras equipes já somam R$ {others_sum:,.2f}; "
                    f"cabe mais R$ {max(0.0, cap - others_sum):,.2f} (tentativa: R$ {valor_meta:,.2f})"
                )

    existing = (
        db.table("metas_equipe").select("*")
        .eq("periodo_id", periodo_id).eq("equipe_id", equipe_id)
        .eq("categoria", categoria).limit(1).execute()
    )
    payload: dict[str, Any] = {
        "periodo_id": periodo_id,
        "equipe_id": equipe_id,
        "categoria": categoria,
        "valor_meta": valor_meta,
        "definida_por": definida_por,
    }
    if existing.data:
        result = db.table("metas_equipe").update(payload).eq("id", existing.data[0]["id"]).execute()
    else:
        result = db.table("metas_equipe").insert(payload).execute()
    if not result.data:
        raise RuntimeError("Falha ao salvar meta de equipe")
    return result.data[0]


def deletar_meta_equipe(db, meta_id: str) -> None:
    result = db.table("metas_equipe").delete().eq("id", meta_id).execute()
    if not result.data:
        raise LookupError("Meta de equipe não encontrada")


def resumo_cascata_equipe(db, *, equipe_id: str, periodo_id: str,
                           categoria: str = DEFAULT_CATEGORIA) -> dict:
    """Team meta vs sum of individual agent quotas (stored in erp.metas with categoria='vgv')."""
    equipe = (
        db.table("metas_equipe").select("*")
        .eq("periodo_id", periodo_id).eq("equipe_id", equipe_id)
        .eq("categoria", categoria).limit(1).execute()
    ).data
    equipe_meta = float(equipe[0]["valor_meta"]) if equipe else 0.0

    agentes = (
        db.table("metas").select("usuario_id, meta_vgv")
        .eq("equipe_id", equipe_id).eq("periodo_id", periodo_id).eq("categoria", "vgv")
        .execute()
    ).data or []
    alocado = sum(float(a["meta_vgv"] or 0) for a in agentes)

    return {
        "equipe_id": equipe_id,
        "periodo_id": periodo_id,
        "categoria": categoria,
        "meta_equipe": equipe_meta,
        "alocado_em_agentes": alocado,
        "saldo_a_alocar": max(0.0, equipe_meta - alocado),
        "estouro": max(0.0, alocado - equipe_meta),
        "agentes_count": len(agentes),
    }
