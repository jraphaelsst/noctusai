"""
Meta Fechamentos Service — period closing + immutable history snapshots.

When a period closes, this service aggregates `meta_eventos` for each
corretor in the period window and writes one `meta_fechamentos` row per
agent. Closed rows are immutable by convention (no update endpoint; only
create + read).

See METAS-PLAN §6, §8.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)


def _get_periodo(db, periodo_id: str) -> dict:
    result = db.table("meta_periodos").select("*").eq("id", periodo_id).limit(1).execute()
    if not result.data:
        raise LookupError("Período não encontrado")
    return result.data[0]


def _get_config(db, org_id: str) -> dict:
    result = db.table("metas_configuracao").select("*").eq("org_id", org_id).limit(1).execute()
    if result.data:
        return result.data[0]
    return {"vgv_por_ponto": 10000, "peso_pontos": 1.0, "peso_vgv": 1.0}


def _score_unificado(pontos_atividade: float, vgv: float, config: dict) -> float:
    vgv_por_ponto = float(config.get("vgv_por_ponto") or 10000)
    peso_p = float(config.get("peso_pontos") or 1.0)
    peso_v = float(config.get("peso_vgv") or 1.0)
    pontos_vgv = (vgv / vgv_por_ponto) if vgv_por_ponto > 0 else 0.0
    return pontos_atividade * peso_p + pontos_vgv * peso_v


def close_periodo(db, *, periodo_id: str, fechado_por: str | None = None) -> dict:
    """Aggregate events within the period and snapshot per-agent rows.

    Idempotent: returns existing snapshots if the period is already closed.
    Also flips the period status to 'fechado'.
    """
    periodo = _get_periodo(db, periodo_id)

    # Short-circuit when already closed
    existing = (
        db.table("meta_fechamentos").select("*")
        .eq("periodo_id", periodo_id).execute()
    ).data or []
    if existing:
        return {"periodo_id": periodo_id, "snapshots": existing, "reused": True}

    # Aggregate per corretor within window
    events = (
        db.table("meta_eventos").select("*")
        .gte("data_evento", periodo["data_inicio"])
        .lte("data_evento", periodo["data_fim"])
        .execute()
    ).data or []

    per_corretor: dict[str, dict] = {}
    for ev in events:
        cid = ev["corretor_id"]
        bucket = per_corretor.setdefault(cid, {
            "corretor_id": cid,
            "equipe_id_snapshot": ev.get("equipe_id_snapshot"),
            "vgv_realizado": 0.0,
            "pontos_atividade": 0.0,
            "captacoes_count": 0,
            "visitas_count": 0,
            "vendas_count": 0,
            "locacoes_count": 0,
            "reunioes_count": 0,
            "org_id": ev.get("org_id"),
        })
        bucket["pontos_atividade"] += float(ev.get("pontos") or 0)
        bucket["vgv_realizado"]    += float(ev.get("valor_vgv") or 0)
        tipo = ev["evento_tipo"]
        if   tipo == "captacao": bucket["captacoes_count"] += 1
        elif tipo == "visita":   bucket["visitas_count"]   += 1
        elif tipo == "venda":    bucket["vendas_count"]    += 1
        elif tipo == "locacao":  bucket["locacoes_count"]  += 1
        elif tipo == "reuniao":  bucket["reunioes_count"]  += 1

    # Lookup individual VGV metas (stored on erp.metas with categoria='vgv' + periodo_id)
    metas_rows = (
        db.table("metas").select("usuario_id, meta_vgv")
        .eq("periodo_id", periodo_id).eq("categoria", "vgv").execute()
    ).data or []
    meta_by_user = {m["usuario_id"]: float(m["meta_vgv"] or 0) for m in metas_rows}

    snapshots_payload = []
    for cid, bucket in per_corretor.items():
        config = _get_config(db, bucket["org_id"]) if bucket.get("org_id") else {}
        vgv_por_ponto = float(config.get("vgv_por_ponto") or 10000)
        pontos_vgv = (bucket["vgv_realizado"] / vgv_por_ponto) if vgv_por_ponto > 0 else 0.0
        score = _score_unificado(bucket["pontos_atividade"], bucket["vgv_realizado"], config)

        snapshots_payload.append({
            "periodo_id": periodo_id,
            "corretor_id": cid,
            "equipe_id_snapshot": bucket["equipe_id_snapshot"],
            "vgv_realizado": bucket["vgv_realizado"],
            "vgv_meta": meta_by_user.get(cid, 0.0),
            "pontos_atividade": bucket["pontos_atividade"],
            "pontos_vgv": pontos_vgv,
            "score_unificado": score,
            "captacoes_count": bucket["captacoes_count"],
            "visitas_count": bucket["visitas_count"],
            "vendas_count": bucket["vendas_count"],
            "locacoes_count": bucket["locacoes_count"],
            "reunioes_count": bucket["reunioes_count"],
            "snapshot_json": bucket,
            "fechado_por": fechado_por,
        })

    if snapshots_payload:
        inserted = db.table("meta_fechamentos").insert(snapshots_payload).execute().data or []
    else:
        inserted = []

    # Flip period status
    db.table("meta_periodos").update({"status": "fechado"}).eq("id", periodo_id).execute()

    return {"periodo_id": periodo_id, "snapshots": inserted, "reused": False}


def listar_fechamentos(db, *, periodo_id: str | None = None,
                       corretor_id: str | None = None) -> list[dict]:
    query = db.table("meta_fechamentos").select("*")
    if periodo_id:
        query = query.eq("periodo_id", periodo_id)
    if corretor_id:
        query = query.eq("corretor_id", corretor_id)
    return query.order("fechado_em", desc=True).execute().data or []


def aggregate_trimestre(db, *, trimestre_id: str) -> dict:
    """Sum the monthly snapshots that roll up to a trimestre period.

    Uses parent-child linkage: meta_periodos with parent_periodo_id = trimestre_id.
    Returns a summary WITHOUT writing anything (read-only view).
    """
    meses = (
        db.table("meta_periodos").select("id")
        .eq("parent_periodo_id", trimestre_id).eq("tipo", "mensal").execute()
    ).data or []
    mes_ids = [m["id"] for m in meses]
    if not mes_ids:
        return {"trimestre_id": trimestre_id, "meses_count": 0, "agentes": []}

    snapshots = (
        db.table("meta_fechamentos").select("*")
        .in_("periodo_id", mes_ids).execute()
    ).data or []

    per_corretor: dict[str, dict] = {}
    for s in snapshots:
        cid = s["corretor_id"]
        bucket = per_corretor.setdefault(cid, {
            "corretor_id": cid,
            "vgv_realizado": 0.0, "pontos_atividade": 0.0,
            "score_unificado": 0.0,
            "captacoes_count": 0, "visitas_count": 0,
            "vendas_count": 0, "locacoes_count": 0, "reunioes_count": 0,
        })
        bucket["vgv_realizado"]    += float(s.get("vgv_realizado") or 0)
        bucket["pontos_atividade"] += float(s.get("pontos_atividade") or 0)
        bucket["score_unificado"]  += float(s.get("score_unificado") or 0)
        for k in ("captacoes_count", "visitas_count", "vendas_count", "locacoes_count", "reunioes_count"):
            bucket[k] += int(s.get(k) or 0)

    return {
        "trimestre_id": trimestre_id,
        "meses_count": len(mes_ids),
        "agentes": list(per_corretor.values()),
    }
