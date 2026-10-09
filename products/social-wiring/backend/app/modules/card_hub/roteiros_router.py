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
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import Field

from noctusai_lib.api import StrictHttpModel

from app.dependencies import get_current_user_org
from app.modules.card_hub import metricas_service
from app.modules.card_hub import roteiros_feedback_service as svc
from app.modules.card_hub.auth import auth_parts
from app.modules.card_hub.deps import get_card_hub_client

router = APIRouter()
pendentes_router = APIRouter(prefix="/api/roteiros", tags=["card_hub"])
metricas_router = APIRouter(prefix="/api/metricas", tags=["card_hub"])


class VisitaFeedbackItem(StrictHttpModel):
    visita_id: UUID
    realizada: bool
    #: Closed enum, validated in the service so a bad value is the contract's 400.
    motivo: Optional[str] = None
    observacao: Optional[str] = Field(default=None, max_length=2000)


class RoteiroFeedbackBody(StrictHttpModel):
    aconteceu: bool
    visitas: list[VisitaFeedbackItem] = Field(default_factory=list, max_length=100)


@router.post("/{cliente_id}/roteiros/{roteiro_id}/feedback")
async def feedback_route(
    cliente_id: UUID,
    roteiro_id: UUID,
    body: RoteiroFeedbackBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return svc.responder(
        client, org_id, cliente_id, roteiro_id,
        aconteceu=body.aconteceu,
        visitas=[v.model_dump() for v in body.visitas],
    )


@router.get("/{cliente_id}/roteiros/{roteiro_id}/visitadas")
async def visitadas_route(
    cliente_id: UUID,
    roteiro_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> list[dict]:
    _user, org_id = auth_parts(auth)
    return svc.visitadas(client, org_id, cliente_id, roteiro_id)


@pendentes_router.get("/pendentes-feedback")
async def pendentes_feedback_route(
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> list[dict]:
    _user, org_id = auth_parts(auth)
    return svc.pendentes(client, org_id)


@metricas_router.get("/atendimentos")
async def metricas_atendimentos_route(
    de: Optional[date] = None,
    ate: Optional[date] = None,
    corretor_id: Optional[UUID] = None,
    auth=Depends(get_current_user_org),
    client=Depends(get_card_hub_client),
) -> dict:
    _user, org_id = auth_parts(auth)
    return metricas_service.funil(client, org_id, de=de, ate=ate, corretor_id=corretor_id)
