"""
Meta Rankings Service — live leaderboards computed from meta_eventos.

Returns three views (pontos, VGV, unificado). Scored using the org's
metas_configuracao (vgv_por_ponto + weights) — the same formula used by
meta_fechamentos_service.close_periodo so current leaderboards match
historical snapshots.

See METAS-PLAN §5.4, §9.
"""
from __future__ import annotations

from typing import Literal


RankType = Literal["pontos", "vgv", "unificado"]


def _get_config(db, org_id: str | None) -> dict:
    if not org_id:
        return {"vgv_por_ponto": 10000, "peso_pontos": 1.0, "peso_vgv": 1.0}
    result = db.table("metas_configuracao").select("*").eq("org_id", org_id).limit(1).execute()
    if result.data:
        return result.data[0]
    return {"vgv_por_ponto": 10000, "peso_pontos": 1.0, "peso_vgv": 1.0}


def compute_rankings(db, *, org_id: str | None = None,
                     equipe_id: str | None = None,
                     data_inicio: str | None = None,
                     data_fim: str | None = None) -> dict:
    """Return {pontos: [...], vgv: [...], unificado: [...]} ranked desc.

    Each list item: {corretor_id, equipe_id_snapshot, pontos_atividade, vgv, score_unificado, rank}
    """
    query = db.table("meta_eventos").select("*")
    if org_id:
        query = query.eq("org_id", org_id)
    if equipe_id:
        query = query.eq("equipe_id_snapshot", equipe_id)
    if data_inicio:
        query = query.gte("data_evento", data_inicio)
    if data_fim:
        query = query.lte("data_evento", data_fim)
    events = query.execute().data or []

    per_corretor: dict[str, dict] = {}
    for ev in events:
        cid = ev["corretor_id"]
        bucket = per_corretor.setdefault(cid, {
            "corretor_id": cid,
            "equipe_id_snapshot": ev.get("equipe_id_snapshot"),
            "pontos_atividade": 0.0,
            "vgv": 0.0,
        })
        bucket["pontos_atividade"] += float(ev.get("pontos") or 0)
        bucket["vgv"]              += float(ev.get("valor_vgv") or 0)

    config = _get_config(db, org_id)
    vgv_por_ponto = float(config.get("vgv_por_ponto") or 10000)
    peso_p = float(config.get("peso_pontos") or 1.0)
    peso_v = float(config.get("peso_vgv") or 1.0)

    for b in per_corretor.values():
        pontos_vgv = (b["vgv"] / vgv_por_ponto) if vgv_por_ponto > 0 else 0
        b["pontos_vgv"] = pontos_vgv
        b["score_unificado"] = b["pontos_atividade"] * peso_p + pontos_vgv * peso_v

    all_rows = list(per_corretor.values())

    def _rank(key: str) -> list[dict]:
        s = sorted(all_rows, key=lambda r: r[key], reverse=True)
        return [{**r, "rank": i + 1, "metric": r[key]} for i, r in enumerate(s)]

    return {
        "pontos": _rank("pontos_atividade"),
        "vgv": _rank("vgv"),
        "unificado": _rank("score_unificado"),
        "config": {
            "vgv_por_ponto": vgv_por_ponto,
            "peso_pontos": peso_p,
            "peso_vgv": peso_v,
        },
    }
