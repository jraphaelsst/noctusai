"""Lancamentos (cashflow) router — CONTRACT.md §Cashflow + dashboard,
slice BE-C.

Auth: `Depends(get_current_user_org)` on every route (401 boundary).
`GET` allows both community roles; writes (`POST`/`PATCH`/`DELETE`) are
`admin`-only via `require_admin`.
"""
from __future__ import annotations

import calendar
import logging
from datetime import date

from fastapi import APIRouter, Depends, Query, status
from noctusai_lib.primitives.timeutil import today_utc

from app.dependencies import (
    coerce_org_uuid,
    http_error,
    get_community_role,
    get_current_user_org,
    get_user_client,
    require_admin,
)
from app.schemas.lancamentos import (
    CategoriasResponse,
    Lancamento,
    LancamentoCreate,
    LancamentoListResponse,
    LancamentoUpdate,
)
from app.services.lancamentos_service import LancamentosService, LancamentosServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lancamentos", tags=["lancamentos"])


def _mes_atual() -> tuple[date, date]:
    """(first day, last day) of the current UTC calendar month — the
    query's default window when `de`/`ate` are omitted."""
    hoje = today_utc()
    ultimo_dia = calendar.monthrange(hoje.year, hoje.month)[1]
    return date(hoje.year, hoje.month, 1), date(hoje.year, hoje.month, ultimo_dia)


@router.get("", response_model=LancamentoListResponse)
async def list_lancamentos(
    de: date | None = Query(default=None),
    ate: date | None = Query(default=None),
    tipo: str | None = Query(default=None),
    categoria: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> LancamentoListResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    inicio_mes, fim_mes = _mes_atual()
    client = get_user_client(token)
    service = LancamentosService(client, org_id=org_id)
    result = await service.list(
        de=de or inicio_mes, ate=ate or fim_mes,
        tipo=tipo, categoria=categoria, page=page, page_size=page_size,
    )
    return LancamentoListResponse(**result)


@router.get("/categorias", response_model=CategoriasResponse)
async def list_categorias(
    auth: tuple = Depends(get_current_user_org),
) -> CategoriasResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = LancamentosService(client, org_id=org_id)
    items = await service.categorias()
    return CategoriasResponse(items=items)


@router.post("", response_model=Lancamento, status_code=status.HTTP_201_CREATED)
async def create_lancamento(
    payload: LancamentoCreate,
    auth: tuple = Depends(get_current_user_org),
) -> Lancamento:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="lançar movimentações de caixa")
    client = get_user_client(token)
    service = LancamentosService(client, org_id=org_id)
    try:
        row = await service.create(payload=payload.model_dump())
    except LancamentosServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return Lancamento(**row)


@router.patch("/{lancamento_id}", response_model=Lancamento)
async def update_lancamento(
    lancamento_id: str,
    payload: LancamentoUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> Lancamento:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="editar lançamentos")
    client = get_user_client(token)
    service = LancamentosService(client, org_id=org_id)
    data = payload.model_dump(exclude_none=True)
    try:
        row = await service.update(lancamento_id=lancamento_id, payload=data)
    except LancamentosServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    if not row:
        raise http_error(404, "Lançamento não encontrado.")
    return Lancamento(**row)


@router.delete("/{lancamento_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lancamento(
    lancamento_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> None:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="excluir lançamentos")
    client = get_user_client(token)
    service = LancamentosService(client, org_id=org_id)
    try:
        ok = await service.delete(lancamento_id=lancamento_id)
    except LancamentosServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    if not ok:
        raise http_error(404, "Lançamento não encontrado.")
    return None
