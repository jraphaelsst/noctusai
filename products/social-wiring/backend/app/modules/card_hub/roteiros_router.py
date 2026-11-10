"""Roteiro feedback + funnel metrics routes (CONTRACT sw-lead-to-contract §3).

Three routers, because the contract's paths live under three prefixes:

* `router` (`/api/clientes`): `POST …/roteiros/{id}/feedback`, `GET …/roteiros/{id}/visitadas`
  — included once into `card_hub.router`.
* `pendentes_router` (`/api/roteiros`): `GET /pendentes-feedback`.
* `metricas_router` (`/api/metricas`): `GET /atendimentos`.

The last two are registered by `card_hub.register()`.
"""
from __future__ import annotations

from datetime import date
from typing import Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field, model_validator

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import access_tier

from app.dependencies import get_core_client, get_current_user_org
from app.modules.card_hub import metricas_service
from app.modules.card_hub import roteiros_feedback_service as svc
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.deps import get_card_hub_client
from app.modules.card_hub.roteiros_papeis import ator_da_requisicao

router = APIRouter()
pendentes_router = APIRouter(prefix="/api/roteiros", tags=["card_hub"])
metricas_router = APIRouter(prefix="/api/metricas", tags=["card_hub"])


class VisitaFeedbackItem(StrictHttpModel):
    visita_id: UUID
    #: LEGACY answer (`realizada` + `motivo`), still accepted and mapped as the migration-338 backfill maps it.
    realizada: Optional[bool] = None
    #: Closed enum, validated in the service so a bad value is the contract's 400.
    motivo: Optional[str] = None
    #: The new answer (migration 338): the visita's outcome. `cancelada` needs `cancelada_por` + `cancelada_motivo`.
    resultado: Optional[Literal["realizada", "cancelada", "nao_compareceu", "reagendada"]] = None
    cancelada_por: Optional[Literal["cliente", "proprietario", "corretor"]] = None
    cancelada_motivo: Optional[Literal["cliente_desistiu", "imovel_indisponivel", "outro"]] = None
    observacao: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def _uma_resposta(self) -> "VisitaFeedbackItem":
        if self.resultado is None and self.realizada is None:
            raise ValueError("informe `resultado` (ou o legado `realizada`) para cada visita")
        return self


class RoteiroFeedbackBody(StrictHttpModel):
    aconteceu: bool
    visitas: list[VisitaFeedbackItem] = Field(default_factory=list, max_length=100)


@router.post("/{cliente_id}/roteiros/{roteiro_id}/feedback")
@access_tier("org", reason="org-scoped via get_current_user_org; cliente ownership proven in the service")
def feedback_route(
    cliente_id: UUID,
    roteiro_id: UUID,
    body: RoteiroFeedbackBody,
    request: Request,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    user, org_id = auth_parts(auth)
    return svc.responder(
        client, org_id, cliente_id, roteiro_id,
        aconteceu=body.aconteceu,
        visitas=[v.model_dump(mode="json") for v in body.visitas],
        usuario_id=getattr(user, "id", None),
        ator=ator_da_requisicao(client, get_core_client(), auth, org_id, request),
    )


@router.get("/{cliente_id}/roteiros/{roteiro_id}/visitadas")
@access_tier("org", reason="org-scoped via get_current_user_org; cliente ownership proven in the service")
def visitadas_route(
    cliente_id: UUID,
    roteiro_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> list[dict]:
    _user, org_id = auth_parts(auth)
    return svc.visitadas(client, org_id, cliente_id, roteiro_id)


@pendentes_router.get("/pendentes-feedback")
@access_tier("org", reason="org-scoped via get_current_user_org")
def pendentes_feedback_route(
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> list[dict]:
    _user, org_id = auth_parts(auth)
    return svc.pendentes(client, org_id)


@metricas_router.get("/atendimentos")
@access_tier("org", reason="org-scoped via get_current_user_org")
def metricas_atendimentos_route(
    de: Optional[date] = None,
    ate: Optional[date] = None,
    corretor_id: Optional[UUID] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return metricas_service.funil(client, org_id, de=de, ate=ate, corretor_id=corretor_id)
