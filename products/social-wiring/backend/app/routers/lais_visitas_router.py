"""Lais > Visitas (wave 5, contract section 7).

  GET  /api/lais/visitas/config                  org member
  PUT  /api/lais/visitas/config                  org admin (the drawer's Salvar)
  GET  /api/lais/visitas?view=semana|dia&data=YYYY-MM-DD[&operacao&status&responsavel]
                                                 org member; any other view -> 422 `view_invalida`
  POST /api/lais/visitas/{id}/confirmar          -> 200 {data: visita}
  POST /api/lais/visitas/{id}/remarcar {inicio, fim}
  POST /api/lais/visitas/{id}/cancelar {motivo?}
                                                 an illegal transition -> 409 `transicao_invalida`

Confirm / reschedule / cancel send the lead a WAHA text over the contato's own line; `data` carries
`mensagem_enviada` (false when it could not leave -- the state change stands) and, on Confirmar,
`aviso` when no `atendimento_agendamentos` row was created because the contato has no lead/card yet.
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
import logging
from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.routers.whatsapp_connections_router import get_connection_store, get_waha_client_factory
from app.services import lais_acesso, lais_visitas_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lais/visitas", tags=["lais-visitas"])

svc.registrar()  # binds the `pedido_visita` action handler

VIEWS = ("semana", "dia")


def get_visitas_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


class RemarcarIn(StrictHttpModel):
    inicio: datetime
    fim: datetime


class CancelarIn(StrictHttpModel):
    motivo: Optional[str] = Field(default=None, max_length=300)


def _org(auth: tuple) -> UUID:
    return coerce_org_uuid(auth[2])


def _aware(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=svc.TZ)


@router.get("/config")
def get_config(auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_visitas_client)) -> dict[str, Any]:
    return {"data": svc.ler_config(client, _org(auth))}


@router.put("/config")
def put_config(
    corpo: svc.ConfigVisitas,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_visitas_client),
) -> dict[str, Any]:
    require_org_admin_for(get_core_client(), auth, request, "A configuração de visitas")
    return {"data": svc.salvar_config(client, _org(auth), corpo)}


@router.get("")
def listar(
    view: str = "semana",
    data: Optional[str] = None,
    operacao: Optional[str] = None,
    status: Optional[str] = None,
    responsavel: Optional[UUID] = None,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_visitas_client),
) -> dict[str, Any]:
    if view not in VIEWS:
        raise AppException("view_invalida", "Use view=semana ou view=dia.", status_code=422)
    if status is not None and status not in svc.STATUS:
        raise AppException("status_invalido", "Status inválido.", status_code=422)
    try:
        dia = date.fromisoformat(data) if data else datetime.now(svc.TZ).date()
    except ValueError:
        raise AppException("data_invalida", "Use data=YYYY-MM-DD.", status_code=422)
    itens = svc.listar(client, _org(auth), view=view, data=dia, operacao=operacao, status=status,
                       responsavel_user_id=str(responsavel) if responsavel else None)
    # A7: members only see the visits of the contatos they own; admins/owners see all
    return {"data": lais_acesso.filtrar_por_contato(client, lais_acesso.contexto(auth, request), itens)}


def _guardar(client: Any, auth: tuple, request: Any, org: UUID, visita_id: UUID) -> None:
    """A7: a visit hangs off a contato -- only that contato's owner or an org admin may act on it."""
    v = svc.obter(client, org, visita_id)  # 404 when missing / another org
    lais_acesso.exigir_contato(client, lais_acesso.contexto(auth, request), v["contato_id"])


async def _responder(client: Any, org_id: UUID, visita: dict[str, Any], acao: str, store: Any, waha_factory: Any) -> dict[str, Any]:
    enviada = await svc.avisar_lead(client, org_id, visita, svc.mensagem_lead(acao, visita), store=store, waha_factory=waha_factory)
    return {"data": {**visita, "mensagem_enviada": enviada}}


@router.post("/{visita_id}/confirmar")
async def confirmar(
    visita_id: UUID,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_visitas_client),
    store: Any = Depends(get_connection_store),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> dict[str, Any]:
    org = _org(auth)
    _guardar(client, auth, request, org, visita_id)
    return await _responder(client, org, svc.confirmar(client, org, visita_id), "confirmar", store, waha_factory)


@router.post("/{visita_id}/remarcar")
async def remarcar(
    visita_id: UUID,
    corpo: RemarcarIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_visitas_client),
    store: Any = Depends(get_connection_store),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> dict[str, Any]:
    org = _org(auth)
    _guardar(client, auth, request, org, visita_id)
    v = svc.remarcar(client, org, visita_id, _aware(corpo.inicio), _aware(corpo.fim))
    return await _responder(client, org, v, "remarcar", store, waha_factory)


@router.post("/{visita_id}/cancelar")
async def cancelar(
    visita_id: UUID,
    corpo: CancelarIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_visitas_client),
    store: Any = Depends(get_connection_store),
    waha_factory: Any = Depends(get_waha_client_factory),
) -> dict[str, Any]:
    org = _org(auth)
    _guardar(client, auth, request, org, visita_id)
    return await _responder(client, org, svc.cancelar(client, org, visita_id, corpo.motivo), "cancelar", store, waha_factory)
