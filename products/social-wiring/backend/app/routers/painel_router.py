"""Painel da imobiliária — the first screen after login, answering the only
question that screen should answer: *what needs me today?*

🔴 WHY THIS EXISTS RATHER THAN A FIX TO `/api/dashboard/*`
-----------------------------------------------------------
The Dashboard route lands on `app/modules/youtube/routers/dashboard.py`. That
is not an accident to be patched — the surface genuinely IS the YouTube
channel dashboard, and social-wiring inherited it. Measured in production on
2026-08-25: a real-estate agency logging in saw four empty channel metrics, an
empty trend chart, and "Nenhum canal conectado", after four requests taking
1,6–1,9 s each for a channel that does not exist.

So this is a new surface with its own vocabulary, not a rename of that one.
The YouTube dashboard stays exactly where it is for the orgs that use it.

WHAT IT ANSWERS, AND WHY THESE FIVE
------------------------------------
Each number is something a person can ACT on the same day, and each one is a
link to the screen where the acting happens. A metric nobody can act on is
decoration, and this product already had a screenful of that.

  novos          leads that arrived this week and are still in the first stage
  parados        open deals nobody has touched in two weeks
  agendamentos   what is booked for the next seven days
  revisao        duplicate-review groups waiting on a decision
  em_negociacao  money actually on the table right now

`em_negociacao` sums `atendimento_negociacao.valor_negociado` over OPEN deals,
which is the same source the funil columns now total. It is not a forecast
model — it is the sum of numbers people typed.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from noctusai_lib.primitives.responses import success_response

from app.dependencies import coerce_org_uuid, get_current_user_org, get_scoped_admin_client
from app.services import table_reads

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/painel", tags=["painel"])

#: A lead that arrived within this window is still "new" to the person working
#: it. Seven days is one working rhythm, not a tuned number.
JANELA_NOVOS_DIAS = 7

#: Untouched for this long and a deal has stopped being worked, whatever the
#: board says. Two weeks is long enough not to nag about a deal someone is
#: deliberately letting breathe, short enough that a forgotten one surfaces
#: while it is still recoverable.
PARADO_APOS_DIAS = 14

#: How far ahead the agenda looks.
AGENDA_DIAS = 7

#: Rows carried in each preview list. The counts above are the headline; these
#: exist so the panel is actionable without a second click.
PREVIEW = 5


class PainelItem(BaseModel):
    atendimento_id: str
    cliente_id: Optional[str] = None
    titulo: Optional[str] = None
    quando: Optional[str] = None
    tipo: Optional[str] = None


class PainelOut(BaseModel):
    novos: int
    parados: int
    agendamentos: int
    revisao: int
    em_negociacao: float
    proximos_agendamentos: list[PainelItem]
    atendimentos_parados: list[PainelItem]


def _agora() -> datetime:
    return datetime.now(timezone.utc)


@router.get("")
def obter_painel(
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    """The agency panel. One request, five numbers, two short lists."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_scoped_admin_client("social_wiring")

    agora = _agora()
    limite_novos = (agora - timedelta(days=JANELA_NOVOS_DIAS)).isoformat()
    limite_parado = (agora - timedelta(days=PARADO_APOS_DIAS)).isoformat()
    limite_agenda = (agora + timedelta(days=AGENDA_DIAS)).isoformat()

    abertos = table_reads.paged_rows(
        client,
        "atendimentos",
        org_id,
        eq_filters={"status": "aberta", "arquivado": False},
        refine=lambda q: q.is_("substituida_por", "null"),
        select="id,cliente_id,titulo,created_at,updated_at,etapa_id",
    )

    novos = [a for a in abertos if (a.get("created_at") or "") >= limite_novos]

    def _mexido_em(a: dict) -> str:
        # `updated_at` is null until something edits the row, so a deal nobody
        # has EVER touched is measured from when it arrived — which is the
        # honest reading of "untouched", and the one that surfaces the worst
        # cases instead of hiding them behind a null.
        return a.get("updated_at") or a.get("created_at") or ""

    parados = sorted(
        (a for a in abertos if _mexido_em(a) and _mexido_em(a) < limite_parado),
        key=_mexido_em,
    )

    agenda = [
        r
        for r in table_reads.paged_rows(
            client,
            "atendimento_agendamentos",
            org_id,
            refine=lambda q: q.is_("deleted_at", "null"),
            select="id,atendimento_id,quando,tipo",
        )
        if r.get("quando") and agora.isoformat() <= r["quando"] <= limite_agenda
    ]
    agenda.sort(key=lambda r: r["quando"])

    valores = _valor_em_negociacao(client, org_id, [str(a["id"]) for a in abertos])

    # `identidade_incerta` clientes sharing a contact key — the same population
    # the review queue lists. Counted here rather than re-derived: a number on
    # a panel that disagrees with the screen it links to is worse than no
    # number at all.
    revisao = _grupos_em_revisao(client, org_id)

    por_atendimento = {str(a["id"]): a for a in abertos}

    return success_response(
        PainelOut(
            novos=len(novos),
            parados=len(parados),
            agendamentos=len(agenda),
            revisao=revisao,
            em_negociacao=sum(valores.values()),
            proximos_agendamentos=[
                PainelItem(
                    atendimento_id=str(r["atendimento_id"]),
                    cliente_id=(
                        str(por_atendimento[str(r["atendimento_id"])]["cliente_id"])
                        if str(r["atendimento_id"]) in por_atendimento
                        and por_atendimento[str(r["atendimento_id"])].get("cliente_id")
                        else None
                    ),
                    titulo=(
                        por_atendimento.get(str(r["atendimento_id"]), {}).get("titulo")
                    ),
                    quando=r["quando"],
                    tipo=r.get("tipo"),
                )
                for r in agenda[:PREVIEW]
            ],
            atendimentos_parados=[
                PainelItem(
                    atendimento_id=str(a["id"]),
                    cliente_id=str(a["cliente_id"]) if a.get("cliente_id") else None,
                    titulo=a.get("titulo"),
                    quando=_mexido_em(a),
                )
                for a in parados[:PREVIEW]
            ],
        ).model_dump()
    )


def _valor_em_negociacao(
    client: Any, org_id: UUID, atendimento_ids: list[str]
) -> dict[str, float]:
    """Negotiated value per OPEN deal. One batched read, same source the funil
    columns total — the panel and the board must never disagree."""
    if not atendimento_ids:
        return {}
    out: dict[str, float] = {}
    for linha in table_reads.in_batched_rows(
        client,
        "atendimento_negociacao",
        org_id,
        "atendimento_id",
        atendimento_ids,
        select="atendimento_id,valor_negociado",
        order_col="atendimento_id",
    ):
        bruto = linha.get("valor_negociado")
        if bruto is None:
            continue
        try:
            out[str(linha["atendimento_id"])] = float(bruto)
        except (TypeError, ValueError):
            logger.warning(
                "painel: valor_negociado ilegível em %s: %r",
                linha.get("atendimento_id"), bruto,
            )
    return out


def _grupos_em_revisao(client: Any, org_id: UUID) -> int:
    """How many duplicate groups are waiting.

    Reuses `clientes_service.list_review_groups` rather than counting rows a
    second way — the panel links straight to that screen, and two counts that
    disagree would make both untrustworthy.
    """
    from app.services import clientes_service as svc

    try:
        return len(svc.list_review_groups(client, org_id))
    except Exception:
        # A panel is a summary. One slow or broken tile must not take the whole
        # first screen down — that is how a dashboard becomes the thing people
        # route around.
        logger.warning("painel: fila de revisão indisponível", exc_info=True)
        return 0


__all__ = ["router"]
