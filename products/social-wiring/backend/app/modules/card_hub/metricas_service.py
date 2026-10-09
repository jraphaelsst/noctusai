"""Funil de atendimento metrics (CONTRACT sw-lead-to-contract §3.5).

Computed from rows on every call: no stored counters, so there is nothing to
drift. The cohort is the atendimentos CREATED in `[de, ate]` (and, when asked,
whose lead belongs to `corretor_id`); every other number follows that cohort
down the funnel, which is what makes the ratios between steps meaningful.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from app.modules.card_hub.roteiros_feedback_service import MOTIVO_PADRAO
from app.services import table_reads

PROPOSTAS_TABLE = "atendimento_propostas"


def _ts(valor: Any) -> Optional[datetime]:
    if not valor:
        return None
    return datetime.fromisoformat(str(valor).replace("Z", "+00:00"))


def _media_dias(pares: list[tuple[Optional[datetime], Optional[datetime]]]) -> Optional[float]:
    dias = [
        (fim - ini).total_seconds() / 86400
        for ini, fim in pares
        if ini is not None and fim is not None and fim >= ini
    ]
    return round(sum(dias) / len(dias), 2) if dias else None


def _coorte(
    client: Any, org_id: UUID, de: Optional[date], ate: Optional[date], corretor_id: Optional[UUID]
) -> list[dict]:
    def refine(q):
        q = q.is_("substituida_por", "null")
        if de:
            q = q.gte("created_at", de.isoformat())
        if ate:
            # inclusive end day
            q = q.lt("created_at", (ate.fromordinal(ate.toordinal() + 1)).isoformat())
        return q

    atendimentos = table_reads.paged_rows(client, "atendimentos", org_id, refine=refine)
    if corretor_id is None:
        return atendimentos
    leads = table_reads.in_batched_rows(
        client, "leads", org_id, "id",
        [str(a["lead_id"]) for a in atendimentos if a.get("lead_id")],
    )
    do_corretor = {str(l["id"]) for l in leads if str(l.get("corretor_id")) == str(corretor_id)}
    return [a for a in atendimentos if str(a.get("lead_id")) in do_corretor]


def funil(
    client: Any,
    org_id: UUID,
    *,
    de: Optional[date] = None,
    ate: Optional[date] = None,
    corretor_id: Optional[UUID] = None,
) -> dict:
    atendimentos = _coorte(client, org_id, de, ate, corretor_id)
    ids = [str(a["id"]) for a in atendimentos]
    criado_em = {str(a["id"]): _ts(a.get("created_at")) for a in atendimentos}

    roteiros = [
        r
        for r in table_reads.in_batched_rows(client, "roteiros", org_id, "atendimento_id", ids)
        if r.get("deleted_at") is None
    ]
    visitas = [
        v
        for v in table_reads.in_batched_rows(
            client, "visitas", org_id, "roteiro_id", [str(r["id"]) for r in roteiros]
        )
        if v.get("deleted_at") is None
    ]
    propostas = table_reads.in_batched_rows(client, PROPOSTAS_TABLE, org_id, "atendimento_id", ids)

    nao_realizadas: dict[str, int] = {}
    for v in visitas:
        if v.get("status") == "nao_realizada":
            motivo = v.get("nao_realizada_motivo") or MOTIVO_PADRAO
            nao_realizadas[motivo] = nao_realizadas.get(motivo, 0) + 1

    # lead -> first roteiro
    primeiro_roteiro: dict[str, datetime] = {}
    roteiro_criado: dict[str, Optional[datetime]] = {}
    for r in roteiros:
        t = _ts(r.get("created_at"))
        roteiro_criado[str(r["id"])] = t
        aid = str(r["atendimento_id"])
        if t is not None and (aid not in primeiro_roteiro or t < primeiro_roteiro[aid]):
            primeiro_roteiro[aid] = t
    realizada_em = {str(v["id"]): _ts(v.get("realizada_em")) for v in visitas}

    return {
        "leads": len(atendimentos),
        "com_roteiro": len({str(r["atendimento_id"]) for r in roteiros}),
        "visitas_agendadas": len(visitas),
        "visitas_realizadas": sum(1 for v in visitas if v.get("status") == "realizada"),
        "visitas_nao_realizadas": nao_realizadas,
        "propostas_criadas": len(propostas),
        "propostas_aceitas": sum(1 for p in propostas if p.get("status") == "aceita"),
        "propostas_recusadas": sum(1 for p in propostas if p.get("status") == "recusada"),
        "tempo_medio_dias": {
            "lead_a_roteiro": _media_dias([(criado_em.get(a), t) for a, t in primeiro_roteiro.items()]),
            "roteiro_a_visita": _media_dias(
                [
                    (roteiro_criado.get(str(v["roteiro_id"])), realizada_em[str(v["id"])])
                    for v in visitas
                    if v.get("status") == "realizada"
                ]
            ),
            "visita_a_proposta": _media_dias(
                [
                    (realizada_em.get(str(p["visita_id"])), _ts(p.get("created_at")))
                    for p in propostas
                    if p.get("visita_id")
                ]
            ),
            "proposta_a_aceite": _media_dias(
                [(_ts(p.get("created_at")), _ts(p.get("aceita_em"))) for p in propostas if p.get("status") == "aceita"]
            ),
        },
    }
