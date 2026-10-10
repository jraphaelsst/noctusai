"""Accept a proposal into the Processos board — callable, client-injected.

The body of `POST /api/atendimentos-venda/{id}/aceitar-proposta`, extracted so
the funnel event `proposta_aceita` (`pipeline/funil_eventos`) and the button
share ONE implementation (CONTRACT §5.4). The route is a thin wrapper.

Raises the same `NotFoundError` / `ValidationError_` the route always raised.
`actor_id` is accepted for symmetry with the other callables (audit); the
Processos insert has never recorded one.
"""
from __future__ import annotations

from typing import Any, Optional

from noctusai_lib.domain.pipeline import (
    STAGE_ROLE_ACCEPT,
    resolve_initial_stage,
    stage_by_role,
)
from noctusai_lib.primitives.exceptions import NotFoundError, ValidationError_

from app.modules.pipeline.configs import (
    PIPELINE_FUNIL,
    PIPELINE_PROCESSOS,
    PROCESSO_SELECT,
    atendimento_to_dto,
    processo_to_dto,
)

STATUS_ABERTA = "aberta"


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

    try:
        created = (
            client.table("processos_venda")
            .insert({
                "org_id": org_id,
                "atendimento_id": atendimento_id,
                "etapa_id": etapa_inicial["id"],
                "valor": atendimento.get("valor_estimado") or 0,
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

    return {
        "atendimento": atendimento_to_dto(fechada[0] if fechada else atendimento),
        "processo": processo_to_dto(created[0]),
        "already_accepted": False,
    }
