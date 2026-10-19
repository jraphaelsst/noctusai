"""Accept a proposal into the Processos board — callable, client-injected.

The body of `POST /api/atendimentos-venda/{id}/aceitar-proposta`, extracted so
the funnel event `proposta_aceita` (`pipeline/funil_eventos`) and the button
share ONE implementation (CONTRACT §5.4). The route is a thin wrapper.

Raises the same `NotFoundError` / `ValidationError_` the route always raised.

The accept is the funil -> processos boundary, and it now leaves a
`pipeline_movimentos` row like every other stage entry (maya-blocks CONTRACT
§2.2: `pipeline='processos_venda'`, `de_etapa_id=NULL`, `para_etapa_id` = the
initial stage, `motivo='aceite_proposta'`), followed by the block-boundary
hook. `responsavel_id` is NOT NULL, so `actor_id` -- the user from the route,
or the actor the `proposta_aceita` funnel event carries -- is required for it;
an accept without an actor is still an accept (recording never blocks the flow
it observes) but the missing movement raises a visible `aceite_sem_ator` alert
(julia-v2 G4), never a silent skip. The funil -> processos HANDOFF no longer
depends on the actor: `handoffs.ao_aceite` (T3, julia-v2 G3) records it from the
processo itself, so an actor-less accept keeps its juridico handoff.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.domain.pipeline import (
    STAGE_ROLE_ACCEPT,
    resolve_initial_stage,
    stage_by_role,
)
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.atendimento_blocos import handoffs as atendimento_handoffs
from app.modules.supervisao.alertas import alertar
from app.modules.pipeline.configs import (
    PIPELINE_FUNIL,
    PIPELINE_PROCESSOS,
    PROCESSO_SELECT,
    atendimento_to_dto,
    processo_to_dto,
)

logger = logging.getLogger(__name__)

STATUS_ABERTA = "aberta"
MOTIVO_ACEITE = atendimento_handoffs.MOTIVO_ACEITE


def _valor_negociado(client: Any, org_id: str, atendimento_id: str) -> Any:
    """The deal's agreed price (`atendimento_negociacao.valor_negociado`), or None.

    The processo's `valor` is the closed deal's value — the negotiated price,
    not the lead's early `valor_estimado` guess.
    """
    rows = (
        client.table("atendimento_negociacao")
        .select("valor_negociado")
        .eq("org_id", org_id)
        .eq("atendimento_id", atendimento_id)
        .execute()
        .data
        or []
    )
    valor = rows[0].get("valor_negociado") if rows else None
    return valor if valor not in (None, "") and float(valor) > 0 else None


def aceitar_proposta(
    client: Any, org_id: Any, atendimento_id: Any, actor_id: Optional[Any] = None
) -> dict:
    """Close the negociação and open its processo (idempotent).

    Returns `{"processo": dto, "already_accepted": bool, "atendimento": dto}`.
    Gated on the stage ROLE (`proposta_aceite`), never its name.
    """
    org_id = str(org_id)
    atendimento_id = str(atendimento_id)
    current = (
        client.table("atendimentos")
        .select("id, etapa_id, status, valor_estimado")
        .eq("id", atendimento_id)
        .eq("org_id", org_id)
        .execute()
        .data
        or []
    )
    if not current:
        raise NotFoundError("Atendimento", atendimento_id)
    atendimento = current[0]

    existing = (
        client.table("processos_venda")
        .select(PROCESSO_SELECT)
        .eq("atendimento_id", atendimento_id)
        .execute()
        .data
        or []
    )
    if existing:
        return {
            "atendimento": atendimento_to_dto(atendimento),
            "processo": processo_to_dto(existing[0]),
            "already_accepted": True,
        }

    if atendimento["status"] != STATUS_ABERTA:
        raise ValidationError_(
            f"Atendimento não está aberta (status: {atendimento['status']})."
        )

    stage_aceite = stage_by_role(client, PIPELINE_FUNIL, STAGE_ROLE_ACCEPT, org_id=org_id)
    if not stage_aceite:
        raise ValidationError_(
            "Nenhuma etapa do funil está marcada como etapa de aceite de proposta. "
            "Defina o papel 'proposta_aceite' em uma etapa nas configurações do funil."
        )
    if atendimento.get("etapa_id") != stage_aceite["id"]:
        raise ValidationError_(
            f"Só é possível aceitar a proposta de uma negociação na etapa "
            f"'{stage_aceite['label']}'."
        )

    etapa_inicial = resolve_initial_stage(client, PIPELINE_PROCESSOS, org_id=org_id)
    valor = _valor_negociado(client, org_id, atendimento_id) or (
        atendimento.get("valor_estimado") or 0
    )

    try:
        created = (
            client.table("processos_venda")
            .insert({
                "org_id": org_id,
                "atendimento_id": atendimento_id,
                "etapa_id": etapa_inicial["id"],
                "valor": valor,
            })
            .execute()
            .data
            or []
        )
    except Exception:
        # Lost the race against a concurrent accept — the UNIQUE constraint is
        # the real guarantee; re-read and return the winner's row rather than
        # surfacing a 500 for a request whose intent was already satisfied.
        existing = (
            client.table("processos_venda")
            .select(PROCESSO_SELECT)
            .eq("atendimento_id", atendimento_id)
            .execute()
            .data
            or []
        )
        if not existing:
            raise
        return {
            "atendimento": atendimento_to_dto(atendimento),
            "processo": processo_to_dto(existing[0]),
            "already_accepted": True,
        }

    # The deal leaves the Funil entirely. `closed_at` is what makes cycle-time
    # measurable — the CHECK in 034 refuses a closed status without it.
    fechada = (
        client.table("atendimentos")
        .update({"status": "aceita", "closed_at": "now()"})
        .eq("id", atendimento_id)
        .eq("org_id", org_id)
        .execute()
        .data
        or []
    )

    _registrar_movimento_do_aceite(client, org_id, created[0], etapa_inicial, actor_id)

    return {
        "atendimento": atendimento_to_dto(fechada[0] if fechada else atendimento),
        "processo": processo_to_dto(created[0]),
        "already_accepted": False,
    }


def _registrar_movimento_do_aceite(
    client: Any, org_id: str, processo: dict, etapa_inicial: dict, actor_id: Optional[Any]
) -> None:
    """T3 (the accept's handoff, actor-independent) + the processo's entry movement + the block-boundary hook.
    Never raises: the accept already happened."""
    atendimento_handoffs.ao_aceite(client, org_id, processo)
    if not actor_id:
        logger.error(
            "aceite: processo %s opened without an actor -- its pipeline_movimentos row (responsavel_id NOT NULL) "
            "is NOT written (the juridico handoff IS recorded by T3) (org=%s)", processo.get("id"), org_id,
        )
        alertar(client, org_id, "aceite_sem_ator", {"processo_id": processo.get("id"), "atendimento_id": processo.get("atendimento_id")})
        return
    try:
        movimento = (
            client.table("pipeline_movimentos")
            .insert({
                "org_id": org_id,
                "pipeline": PIPELINE_PROCESSOS.pipeline,
                "entidade_id": str(processo["id"]),
                "de_etapa_id": None,
                "para_etapa_id": str(etapa_inicial["id"]),
                "responsavel_id": str(actor_id),
                "motivo": MOTIVO_ACEITE,
            })
            .execute()
            .data
            or []
        )
    except Exception:
        logger.exception("aceite: could not write the entry movement of processo %s (org=%s) -- the accept stands", processo.get("id"), org_id)
        alertar(client, org_id, "aceite_movimento", {"processo_id": processo.get("id")})
        return
    if movimento:
        atendimento_handoffs.ao_movimento(client, org_id, movimento[0])
