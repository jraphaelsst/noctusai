"""Julia > Captacao (wave 8, contract section 10).

  GET  /api/julia/captacoes?status&de&ate&page&page_size(5|10|15|20)   member   {data: {items, total}}
  POST /api/julia/captacoes/{id}/registrar  [{titulo?, endereco?}]      member   {data: {imovel_id, imovel_codigo}}
  POST /api/julia/captacoes/{id}/descartar                              member   204

A7: a captacao hangs off a contato -- a member sees/acts on the captacoes of THEIR contatos, an org admin
on all (403 `sem_acesso` for a same-org stranger, 404 for another org's id). 404 `captacao_nao_encontrada`;
409 `captacao_ja_tratada` (registrar/descartar on a row that is no longer `nova`); 422 `page_size_invalido`
/ `status_invalido` / `filtro_invalido`. The registrar body is optional: it overrides the prefill taken from
the row (a structured `endereco` replaces the free-text one).
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
import logging
from datetime import date
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Body, Depends, Query, Request, Response

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.primitives.exceptions import AppException
from pydantic import Field

from app.dependencies import coerce_org_uuid, get_current_user_org, get_scoped_admin_client
from app.modules.imovel_hub.schemas import EnderecoManualIn
from app.services import julia_acesso, julia_captacao_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/julia/captacoes", tags=["julia-captacao"])

svc.registrar()  # binds the real `captacao` action handler (composes the wave-3 policy)


def get_captacao_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


class RegistrarIn(StrictHttpModel):
    titulo: Optional[str] = Field(default=None, min_length=1, max_length=200)
    endereco: Optional[EnderecoManualIn] = None


def _org(auth: tuple) -> UUID:
    return coerce_org_uuid(auth[2])


def _guardar(client: Any, auth: tuple, request: Any, captacao_id: UUID) -> dict[str, Any]:
    captacao = svc.obter(client, _org(auth), captacao_id)  # 404 when missing / another org
    julia_acesso.exigir_contato(client, julia_acesso.contexto(auth, request), captacao["contato_id"])
    return captacao


@router.get("")
def listar(
    request: Request = None,
    status: Optional[str] = None,
    de: Optional[date] = None,
    ate: Optional[date] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = 10,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_captacao_client),
) -> dict[str, Any]:
    if page_size not in svc.PAGE_SIZES:
        raise AppException("page_size_invalido", "Use page_size 5, 10, 15 ou 20.", status_code=422)
    if status is not None and status not in svc.STATUS:
        raise AppException("status_invalido", "Status inválido.", status_code=422)
    if de and ate and de > ate:
        raise AppException("filtro_invalido", "O período está invertido.", status_code=422)
    out = svc.listar(client, _org(auth), julia_acesso.contexto(auth, request), status=status, de=de, ate=ate, page=page, page_size=page_size)
    return {"data": out}


@router.post("/{captacao_id}/registrar")
def registrar(
    captacao_id: UUID,
    corpo: Optional[RegistrarIn] = Body(default=None),
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_captacao_client),
) -> dict[str, Any]:
    _guardar(client, auth, request, captacao_id)
    valores = corpo.model_dump(mode="json", exclude_unset=True) if corpo else {}
    usuario = getattr(auth[0], "id", None)
    return {"data": svc.registrar_captacao(client, _org(auth), captacao_id, valores, usuario_id=usuario)}


@router.post("/{captacao_id}/descartar", status_code=204)
def descartar(
    captacao_id: UUID,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_captacao_client),
) -> Response:
    _guardar(client, auth, request, captacao_id)
    svc.descartar(client, _org(auth), captacao_id)
    return Response(status_code=204)
