"""Cliente endpoints — Módulo 1 (CRM).

The first surface wired end-to-end over the persistence seam, so it is the
reference for every IgIg router that follows:

* auth via ``Depends(get_current_user_org)`` — the factory-bound shape; never
  ``Depends(get_org_id)``, whose positional args become query params.
* data via ``Depends(get_repositorios)`` — repositories over the
  ``RecordStore`` seam, NOT a Supabase client. Auth still comes from Supabase;
  only domain data goes through the store.
* ``RecordNotFound`` → 404, in Portuguese, per the platform's language
  convention.
* explicit ``status_code=`` on every write so the status-assertion keeper has
  something to pin.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status
from noctusai_lib.integrations.persistence import Op, QuerySpec, RecordNotFound

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.repositories import Repositorios
from app.schemas.cliente import (
    ClienteCreate,
    ClienteListResponse,
    ClienteOut,
    ClienteUpdate,
)
from app.store import get_repositorios

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clientes", tags=["clientes"])


@router.get("", response_model=ClienteListResponse)
async def listar_clientes(
    busca: str | None = Query(default=None, description="Filtro por nome (contém)"),
    status_filtro: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> ClienteListResponse:
    """List the org's clients, optionally filtered by name and status."""
    _user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))

    spec = QuerySpec()
    if busca:
        spec = spec.with_filter("nome", Op.CONTAINS, busca)
    if status_filtro:
        spec = spec.with_filter("status", Op.EQ, status_filtro)

    itens = repos.cliente.listar(org_id, spec=spec, limit=limit, offset=offset)
    # Counted with the same filters but WITHOUT limit/offset, so the UI can
    # page correctly. Returning len(itens) would report the page size and make
    # every list look like it fit on one page.
    total = repos.cliente.contar(org_id, spec=spec)
    return ClienteListResponse(itens=[ClienteOut(**c) for c in itens], total=total)


@router.post("", response_model=ClienteOut, status_code=status.HTTP_201_CREATED)
async def criar_cliente(
    payload: ClienteCreate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> ClienteOut:
    """Create a client. Always enters the funnel as ``prospect``."""
    _user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))
    row = repos.cliente.criar(org_id, payload.model_dump(exclude_none=True))
    logger.info("cliente criado org=%s id=%s", org_id, row.get("id"))
    return ClienteOut(**row)


@router.get("/{cliente_id}", response_model=ClienteOut)
async def obter_cliente(
    cliente_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> ClienteOut:
    _user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))
    try:
        return ClienteOut(**repos.cliente.buscar(org_id, cliente_id))
    except RecordNotFound:
        # A row belonging to another org raises the same miss, so this can't
        # be used to probe for other tenants' ids.
        raise HTTPException(status_code=404, detail="Cliente não encontrado")


@router.patch("/{cliente_id}", response_model=ClienteOut)
async def atualizar_cliente(
    cliente_id: str,
    payload: ClienteUpdate,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> ClienteOut:
    _user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        return ClienteOut(**repos.cliente.atualizar(org_id, cliente_id, data))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")


@router.post("/{cliente_id}/ativar", response_model=ClienteOut)
async def ativar_cliente(
    cliente_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> ClienteOut:
    """Promote a prospect to ativo.

    Exposed as its own endpoint because Módulo 1's signature webhook calls
    exactly this transition — a generic PATCH would let any caller set any
    status and lose the intent.
    """
    _user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))
    try:
        return ClienteOut(**repos.cliente.ativar(org_id, cliente_id))
    except RecordNotFound:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")


@router.delete("/{cliente_id}", status_code=status.HTTP_200_OK)
async def remover_cliente(
    cliente_id: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> dict:
    """Delete a client.

    Hard delete — the schema cascades to marca / contrato / pauta / tarefa /
    apontamento. Módulo 6 will need a soft-delete for billing history; that
    is a deliberate follow-up, not an oversight.
    """
    _user, _token, raw_org = auth
    org_id = str(coerce_org_uuid(raw_org))
    if not repos.cliente.remover(org_id, cliente_id):
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return {"ok": True}
