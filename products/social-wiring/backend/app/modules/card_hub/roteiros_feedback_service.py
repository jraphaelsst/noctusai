"""Roteiro feedback — "a visita aconteceu?" (CONTRACT sw-lead-to-contract §3.2–3.4).

The roteiro is DUE once `data_visita` (plus `hora_visita` when set) has passed
and nobody answered. Answering fills the per-visita outcome and the structured
`nao_realizada_motivo` the funnel metric groups by (`metricas_service`).

Kept apart from `roteiros_service` (which owns create/patch/proposta toggles) so
the prompt, its answer and its scheduler read as one unit.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timezone
from typing import Any, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from noctusai_lib.primitives.exceptions import (
    AppException,
    NotFoundError,
    ValidationError_,
)

from app.modules.card_hub import roteiros_service as roteiros_svc
from app.modules.card_hub.services import _t
from app.modules.imovel_hub.busca_service import enriquecer
from app.services import table_reads

logger = logging.getLogger(__name__)

TZ = ZoneInfo("America/Sao_Paulo")
PROPOSTAS_TABLE = "atendimento_propostas"

#: Mirrors the DB CHECK in migration 219.
MOTIVOS = (
    "cliente_desistiu",
    "cliente_nao_compareceu",
    "imovel_indisponivel",
    "reagendada",
    "outro",
)
MOTIVO_PADRAO = "outro"


def agora_local() -> datetime:
    return datetime.now(TZ)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class RoteiroJaRespondido(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="roteiro_ja_respondido",
            message="Este roteiro já foi respondido; corrija cada visita individualmente.",
            status_code=409,
        )


def _parse_hora(valor: Any) -> Optional[time]:
    if not valor:
        return None
    if isinstance(valor, time):
        return valor
    return time.fromisoformat(str(valor))


def vencido(roteiro: dict, agora: datetime) -> bool:
    """Is `roteiro` due for feedback at `agora` (local time)?"""
    if roteiro.get("feedback_status") != "pendente" or not roteiro.get("data_visita"):
        return False
    dia = date.fromisoformat(str(roteiro["data_visita"])[:10])
    if dia < agora.date():
        return True
    if dia > agora.date():
        return False
    hora = _parse_hora(roteiro.get("hora_visita"))
    # No hora_visita: due from the start of the day.
    return hora is None or hora <= agora.time().replace(tzinfo=None)


# ── 3.2 — the prompt ────────────────────────────────────────────────────────

def pendentes(
    client: Any, org_id: UUID, *, agora: Optional[datetime] = None
) -> list[dict]:
    """Every due roteiro of the org, oldest visit first."""
    agora = agora or agora_local()
    roteiros = table_reads.paged_rows(
        client,
        roteiros_svc.TABLE,
        org_id,
        eq_filters={"feedback_status": "pendente"},
        refine=lambda q: q.is_("deleted_at", "null").lte("data_visita", agora.date().isoformat()),
    )
    roteiros = [r for r in roteiros if vencido(r, agora)]
    if not roteiros:
        return []

    atendimentos = {
        str(a["id"]): a
        for a in table_reads.in_batched_rows(
            client, "atendimentos", org_id, "id", [str(r["atendimento_id"]) for r in roteiros]
        )
    }
    clientes = {
        str(c["id"]): c
        for c in table_reads.in_batched_rows(
            client, "clientes", org_id, "id",
            [str(a["cliente_id"]) for a in atendimentos.values() if a.get("cliente_id")],
        )
    }
    visitas = roteiros_svc._visitas_de(client, org_id, [str(r["id"]) for r in roteiros])
    imoveis = enriquecer(client, org_id, [v["codigo"] for v in visitas])
    por_roteiro: dict[str, list[dict]] = {}
    for v in sorted(visitas, key=lambda v: (v.get("ordem") or 0)):
        por_roteiro.setdefault(str(v["roteiro_id"]), []).append(v)

    saida = []
    for r in sorted(roteiros, key=lambda r: (str(r["data_visita"]), str(r.get("hora_visita") or ""))):
        atendimento = atendimentos.get(str(r["atendimento_id"]))
        if not atendimento:  # orphan roteiro: nothing to answer on
            continue
        cliente = clientes.get(str(atendimento.get("cliente_id")), {})
        saida.append(
            {
                "roteiro_id": r["id"],
                "cliente_id": atendimento.get("cliente_id"),
                "atendimento_id": r["atendimento_id"],
                "cliente_nome": cliente.get("nome"),
                "data_visita": r["data_visita"],
                "visitas": [
                    {
                        "visita_id": v["id"],
                        "imovel_codigo": v["codigo"],
                        "titulo": (imoveis.get(roteiros_svc.canonical(str(v["codigo"]))) or {}).get("titulo"),
                    }
                    for v in por_roteiro.get(str(r["id"]), [])
                ],
            }
        )
    return saida


# ── 3.3 — answering ─────────────────────────────────────────────────────────

def _motivo_valido(motivo: Optional[str]) -> Optional[str]:
    if motivo is not None and motivo not in MOTIVOS:
        raise ValidationError_(
            f"motivo deve ser um de {list(MOTIVOS)}, recebido {motivo!r}", field="motivo"
        )
    return motivo


def responder(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    roteiro_id: UUID,
    *,
    aconteceu: bool,
    visitas: list[dict],
) -> dict:
    """Record "a visita aconteceu?" for a roteiro and return the updated Roteiro.

    ALL validation happens before the first write (card_hub has no
    transactions): a 400 never leaves a half-answered roteiro.
    """
    roteiro = roteiros_svc._obter(client, org_id, cliente_id, roteiro_id)
    if roteiro.get("feedback_status") == "respondido":
        raise RoteiroJaRespondido()
    existentes = {
        str(v["id"]): v for v in roteiros_svc._visitas_de(client, org_id, [str(roteiro_id)])
    }

    dadas: dict[str, dict] = {}
    for entrada in visitas:
        vid = str(entrada["visita_id"])
        if vid not in existentes:
            raise NotFoundError("Visita", vid)
        if vid in dadas:
            raise ValidationError_(f"visita {vid} aparece mais de uma vez.", field="visitas")
        dadas[vid] = entrada

    if aconteceu:
        faltando = sorted(set(existentes) - set(dadas))
        if faltando:
            raise ValidationError_(
                "Informe o resultado de todas as visitas do roteiro; faltando: "
                + ", ".join(faltando),
                field="visitas",
            )
    plano: dict[str, dict] = {}
    for vid in existentes:
        entrada = dadas.get(vid)
        if aconteceu:
            realizada = bool(entrada["realizada"])
        else:
            if entrada is not None and entrada.get("realizada"):
                raise ValidationError_(
                    "aconteceu=false não admite visita realizada.", field="visitas"
                )
            realizada = False
        motivo = _motivo_valido((entrada or {}).get("motivo"))
        if not realizada:
            if aconteceu and motivo is None:
                raise ValidationError_(
                    f"Informe o motivo da visita {vid} não realizada.", field="motivo"
                )
            motivo = motivo or MOTIVO_PADRAO
        else:
            motivo = None
        plano[vid] = {
            "realizada": realizada,
            "motivo": motivo,
            "observacao": ((entrada or {}).get("observacao") or "").strip() or None,
        }

    agora = _now()
    for vid, p in plano.items():
        atual = existentes[vid]
        updates: dict = {
            "status": "realizada" if p["realizada"] else "nao_realizada",
            "nao_realizada_motivo": p["motivo"],
            "realizada_em": (atual.get("realizada_em") or agora) if p["realizada"] else None,
            "feedback_em": atual.get("feedback_em") or agora,
        }
        if p["observacao"] is not None:
            updates["observacao"] = p["observacao"]
        _t(client, roteiros_svc.VISITAS_TABLE).update(updates).eq("id", vid).eq(
            "org_id", str(org_id)
        ).execute()

    _t(client, roteiros_svc.TABLE).update(
        {"feedback_status": "respondido", "feedback_em": agora}
    ).eq("id", str(roteiro_id)).eq("org_id", str(org_id)).execute()
    return roteiros_svc.obter(client, org_id, cliente_id, roteiro_id)


# ── 3.4 — the visited list ──────────────────────────────────────────────────

def visitadas(client: Any, org_id: UUID, cliente_id: UUID, roteiro_id: UUID) -> list[dict]:
    """Visitas that happened, with the proposta already generated for each."""
    roteiros_svc._obter(client, org_id, cliente_id, roteiro_id)
    reais = [
        v
        for v in roteiros_svc._visitas_de(client, org_id, [str(roteiro_id)])
        if v.get("status") == "realizada"
    ]
    if not reais:
        return []
    reais.sort(key=lambda v: (v.get("ordem") or 0))
    imoveis = enriquecer(client, org_id, [v["codigo"] for v in reais])
    propostas = table_reads.in_batched_rows(
        client, PROPOSTAS_TABLE, org_id, "visita_id", [str(v["id"]) for v in reais]
    )
    # A cancelled proposta frees the button; the newest live one blocks it.
    vivas = sorted(
        (p for p in propostas if p.get("status") != "cancelada"),
        key=lambda p: str(p.get("created_at") or ""),
        reverse=True,
    )
    por_visita: dict[str, dict] = {}
    for p in vivas:
        por_visita.setdefault(str(p["visita_id"]), p)

    return [
        {
            "visita_id": v["id"],
            "imovel_codigo": v["codigo"],
            "titulo": (imoveis.get(roteiros_svc.canonical(str(v["codigo"]))) or {}).get("titulo"),
            "realizada_em": v.get("realizada_em") or v.get("feedback_em"),
            "proposta": (
                {"id": por_visita[str(v["id"])]["id"], "status": por_visita[str(v["id"])]["status"]}
                if str(v["id"]) in por_visita
                else None
            ),
        }
        for v in reais
    ]
