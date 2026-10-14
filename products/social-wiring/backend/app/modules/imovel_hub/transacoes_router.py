"""`/api/imovel-transacoes` -- admin review of ground-truth closing prices.

    GET   /api/imovel-transacoes?vinculo_status=&limit=&offset=
    POST  /api/imovel-transacoes/{transacao_id}/confirmar   {codigo}
    POST  /api/imovel-transacoes/{transacao_id}/rejeitar

Admin/owner only on every route (the TRUSTED `noctus_users` role, never
`user_metadata`): these are the agency's real sale prices. Rows are written by
the importer (service side); this router only lists and resolves the link.
"""
from __future__ import annotations

from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org
from app.modules.imovel_hub import transacoes_service as svc
from app.modules.imovel_hub.deps import get_imovel_hub_client

router = APIRouter(prefix="/api/imovel-transacoes", tags=["imovel-transacoes"])


class ConfirmarBody(StrictHttpModel):
    codigo: str = Field(min_length=1, max_length=64)


def _admin(auth, request: Optional[Request], context: str):
    user, _token, raw_org = auth
    require_org_admin_for(get_core_client(), auth, request, context)
    return user, coerce_org_uuid(raw_org)


@router.get("")
async def listar_route(
    vinculo_status: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
    request: Request = None,
) -> dict:
    _user, org_id = _admin(auth, request, "Transações de imóveis")
    return svc.listar(client, org_id, vinculo_status=vinculo_status, limit=limit, offset=offset)


@router.post("/{transacao_id}/confirmar")
async def confirmar_route(
    transacao_id: UUID,
    body: ConfirmarBody,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
    request: Request = None,
) -> dict:
    """Link to `codigo` (a proposed candidate or a typed code; it must exist in
    the registry -> 404). `409 transacao_ja_resolvida` unless `pendente`."""
    user, org_id = _admin(auth, request, "Confirmar transação")
    return svc.confirmar(client, org_id, transacao_id, body.codigo, getattr(user, "id", None))


@router.post("/{transacao_id}/rejeitar")
async def rejeitar_route(
    transacao_id: UUID,
    auth=Depends(get_current_user_org),
    client=Depends(get_imovel_hub_client),
    request: Request = None,
) -> dict:
    user, org_id = _admin(auth, request, "Rejeitar transação")
    return svc.rejeitar(client, org_id, transacao_id, getattr(user, "id", None))
