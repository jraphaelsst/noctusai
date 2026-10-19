"""Lais > Analise de credito (wave 13, contract 15 / 17).

  GET  /api/lais/credito?status&page&page_size(5|10|15|20)   member   {data: {items, total}}
  GET  /api/lais/credito/config                              admin    {data: {ativo, provider, apenas_aluguel, providers}}
  PUT  /api/lais/credito/config   {ativo, provider, apenas_aluguel}    admin    {data: {...}}
  POST /api/lais/credito/{contato_id}/reprocessar            admin    {data: {analise_id, como}}

A7: the list is filtered to the contatos the caller owns (org admin: all). `reprocessar` needs a STORED consent
aceito=true (409 `consentimento_ausente`) and the analysis switched on (409 `credito_desativado`); it never
creates a consent. 422 `status_invalido` / `page_size_invalido` / `provider_invalido` / `provider_obrigatorio`.
The provider credential is NOT handled here: it lives in the per-org credentials store (`api_key:credito_provider`).
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
import logging
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.services import lais_acesso, lais_credito_service as svc
from app.services.lais_credito_provider import PROVIDERS_CONHECIDOS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lais/credito", tags=["lais-credito"])

svc.registrar()  # binds the `consentimento_credito` handler, the pedido_visita hook and the contexto providers


def get_credito_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


class ConfigIn(StrictHttpModel):
    ativo: bool
    provider: Optional[str] = None
    apenas_aluguel: bool = True


def _org(auth: tuple) -> UUID:
    return coerce_org_uuid(auth[2])


@router.get("")
def listar(
    request: Request = None,
    status: Optional[str] = None,
    page: int = Query(default=1, ge=1),
    page_size: int = 10,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_credito_client),
) -> dict[str, Any]:
    if page_size not in svc.PAGE_SIZES:
        raise AppException("page_size_invalido", "Use page_size 5, 10, 15 ou 20.", status_code=422)
    if status is not None and status not in svc.STATUS:
        raise AppException("status_invalido", "Status inválido.", status_code=422)
    return {"data": svc.listar(client, _org(auth), lais_acesso.contexto(auth, request), status=status, page=page, page_size=page_size)}


@router.get("/config")
def get_config(
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_credito_client),
) -> dict[str, Any]:
    require_org_admin_for(get_core_client(), auth, request, "A configuração da análise de crédito")
    return {"data": {**svc.ler_config(client, _org(auth)), "providers": list(PROVIDERS_CONHECIDOS)}}


@router.put("/config")
def put_config(
    corpo: ConfigIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_credito_client),
) -> dict[str, Any]:
    require_org_admin_for(get_core_client(), auth, request, "A configuração da análise de crédito")
    return {"data": svc.salvar_config(client, _org(auth), ativo=corpo.ativo, provider=corpo.provider, apenas_aluguel=corpo.apenas_aluguel)}


@router.post("/{contato_id}/reprocessar")
async def reprocessar(
    contato_id: UUID,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_credito_client),
) -> dict[str, Any]:
    require_org_admin_for(get_core_client(), auth, request, "O reprocessamento da análise de crédito")
    return {"data": await svc.reprocessar(client, _org(auth), contato_id)}
