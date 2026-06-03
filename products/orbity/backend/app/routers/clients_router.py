"""
Clients router — CRUD for orbity.clients (the agency's customers).

Auth: every endpoint requires Depends(get_current_user_org).
Unauth'd requests → 401 (strict, not 404/422).

Endpoints:
  GET    /api/clients          list (page, page_size, active_only)
  POST   /api/clients          create → 201
  GET    /api/clients/{id}     detail
  PATCH  /api/clients/{id}     update
  POST   /api/clients/{id}/archive  soft-delete (active=False)
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    coerce_org_uuid,
    get_current_user_org,
    get_user_client,
)
from app.schemas.clients import ClientCreate, ClientOut, ClientUpdate
from app.services.clients_service import ClientsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/clients", tags=["Clients"])


@router.get("", status_code=status.HTTP_200_OK)
async def list_clients(
    active_only: bool = Query(default=True),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    svc = ClientsService(get_user_client(token), org_id=org_id)
    try:
        result = svc.list(active_only=active_only, page=page, page_size=page_size)
    except Exception:
        logger.exception("clients.list failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar clientes")
    return result


@router.post("", response_model=ClientOut, status_code=status.HTTP_201_CREATED)
async def create_client(
    payload: ClientCreate,
    auth: tuple = Depends(get_current_user_org),
) -> ClientOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    svc = ClientsService(get_user_client(token), org_id=org_id)
    try:
        row = svc.create(payload.model_dump(exclude_none=True))
    except Exception:
        logger.exception("clients.create failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar cliente")
    return ClientOut(**row)


@router.get("/{client_id}", response_model=ClientOut, status_code=status.HTTP_200_OK)
async def get_client(
    client_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> ClientOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    svc = ClientsService(get_user_client(token), org_id=org_id)
    try:
        row = svc.get(client_id)
    except Exception:
        logger.exception("clients.get failed org=%s id=%s", org_id, client_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar cliente")
    if not row:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return ClientOut(**row)


@router.patch("/{client_id}", response_model=ClientOut, status_code=status.HTTP_200_OK)
async def update_client(
    client_id: str,
    payload: ClientUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> ClientOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    svc = ClientsService(get_user_client(token), org_id=org_id)
    try:
        row = svc.update(client_id, data)
    except Exception:
        logger.exception("clients.update failed org=%s id=%s", org_id, client_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar cliente")
    if not row:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return ClientOut(**row)


@router.post(
    "/{client_id}/archive",
    status_code=status.HTTP_200_OK,
)
async def archive_client(
    client_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    """Soft-delete: sets active=False. Reversible via PATCH active=True."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    svc = ClientsService(get_user_client(token), org_id=org_id)
    try:
        ok = svc.archive(client_id)
    except Exception:
        logger.exception("clients.archive failed org=%s id=%s", org_id, client_id)
        raise HTTPException(status_code=502, detail="Falha ao arquivar cliente")
    if not ok:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return {"ok": True, "id": client_id}
