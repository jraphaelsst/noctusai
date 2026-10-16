"""Lais > Notificações (wave 6, contract 8).

  GET  /api/lais/notificacoes?tipo&operacao&de&ate&page[&page_size]  -> {data:{items,total,nao_lidas}}
  POST /api/lais/notificacoes/lidas {ids | todas}                    -> 204
  GET  /api/lais/notificacoes/preferencias                           -> {data:{tipos:[{tipo,in_app}], lead_pronto}}
  PUT  /api/lais/notificacoes/preferencias {tipos:{<tipo>: bool}}    -> same shape

Every route is the caller's OWN notifications / preferences (any org member), scoped by org.
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.services import lais_notificacoes_service as svc

router = APIRouter(prefix="/api/lais/notificacoes", tags=["lais-notificacoes"])

svc.registrar()  # binds the lais_eventos -> in-app fan-out sink


def get_notificacoes_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


class LidasIn(StrictHttpModel):
    ids: Optional[list[UUID]] = Field(default=None, max_length=500)
    todas: bool = False


class PreferenciasIn(StrictHttpModel):
    tipos: dict[str, bool] = Field(default_factory=dict)


def _uid(auth: tuple) -> str:
    return str(auth[0].id)


@router.get("")
def listar(
    tipo: Optional[str] = None,
    operacao: Optional[str] = None,
    de: Optional[date] = None,
    ate: Optional[date] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=svc.PAGE_SIZE_MAX),
    auth: tuple = Depends(get_current_user_org),
) -> dict[str, Any]:
    return {"data": svc.listar(get_core_client(), coerce_org_uuid(auth[2]), _uid(auth), tipo=tipo, operacao=operacao,
                               de=de, ate=ate, page=page, page_size=page_size)}


@router.post("/lidas", status_code=204, response_class=Response, response_model=None)
def lidas(corpo: LidasIn, auth: tuple = Depends(get_current_user_org)):
    if not corpo.todas and not corpo.ids:
        raise AppException("alvo_obrigatorio", "Informe `ids` ou `todas: true`.", status_code=422)
    svc.marcar_lidas(get_core_client(), coerce_org_uuid(auth[2]), _uid(auth), ids=corpo.ids, todas=corpo.todas)
    return Response(status_code=204)


@router.get("/preferencias")
def get_preferencias(auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_notificacoes_client)) -> dict[str, Any]:
    return {"data": svc.ler_preferencias(client, coerce_org_uuid(auth[2]), auth[0])}


@router.put("/preferencias")
def put_preferencias(
    corpo: PreferenciasIn, auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_notificacoes_client)
) -> dict[str, Any]:
    return {"data": svc.salvar_preferencias(client, coerce_org_uuid(auth[2]), _uid(auth), corpo.tipos)}
