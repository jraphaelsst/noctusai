"""Aplicações router — manager-defined application questions + public
submissions + review — contract §Aplicações.

Two routes are PUBLIC (`GET /formulario`, `POST ""`) — genuinely
unauthenticated, rate-limited via the product limiter, and org-scoped
via `resolve_public_org_id()` (this product is single-tenant; see that
function's docstring in `app/dependencies.py`). Every other route
requires `Depends(get_current_user_org)`; writes are `admin`-only.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    get_admin_client,
    get_community_role,
    get_current_user_org,
    get_user_client,
    require_admin,
    resolve_public_org_id,
)
from app.rate_limit import limiter
from app.schemas.aplicacoes import (
    Aplicacao,
    AplicacaoAprovarRequest,
    AplicacaoAprovarResponse,
    AplicacaoListResponse,
    AplicacaoPublicaCreate,
    AplicacaoPublicaOut,
    AplicacaoRejeitarRequest,
    Pergunta,
    PerguntaCreate,
    PerguntaListResponse,
    PerguntaUpdate,
)
from app.schemas.membros import Membro
from app.services.aplicacoes_service import (
    AplicacoesService,
    AplicacoesServiceError,
    PublicAplicacoesService,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/aplicacoes", tags=["aplicacoes"])


# ── perguntas (authenticated) ────────────────────────────────────────


@router.get("/perguntas", response_model=PerguntaListResponse)
async def list_perguntas(
    auth: tuple = Depends(get_current_user_org),
) -> PerguntaListResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = AplicacoesService(client, org_id=org_id)
    result = await service.list_perguntas()
    return PerguntaListResponse(**result)


@router.post("/perguntas", response_model=Pergunta, status_code=status.HTTP_201_CREATED)
async def create_pergunta(
    payload: PerguntaCreate,
    auth: tuple = Depends(get_current_user_org),
) -> Pergunta:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="gerenciar as perguntas do formulário")
    client = get_user_client(token)
    service = AplicacoesService(client, org_id=org_id)
    try:
        row = await service.create_pergunta(payload=payload.model_dump())
    except AplicacoesServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return Pergunta(**row)


@router.patch("/perguntas/{pergunta_id}", response_model=Pergunta)
async def update_pergunta(
    pergunta_id: str,
    payload: PerguntaUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> Pergunta:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="gerenciar as perguntas do formulário")
    client = get_user_client(token)
    service = AplicacoesService(client, org_id=org_id)
    data = payload.model_dump(exclude_none=True)
    try:
        row = await service.update_pergunta(pergunta_id=pergunta_id, payload=data)
    except AplicacoesServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if not row:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada.")
    return Pergunta(**row)


@router.delete("/perguntas/{pergunta_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pergunta(
    pergunta_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> None:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="gerenciar as perguntas do formulário")
    client = get_user_client(token)
    service = AplicacoesService(client, org_id=org_id)
    ok = await service.soft_delete_pergunta(pergunta_id=pergunta_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Pergunta não encontrada.")
    return None


# ── PUBLIC (no auth) ─────────────────────────────────────────────────


@router.get("/formulario", response_model=PerguntaListResponse)
@limiter.limit(settings.aplicacoes_rate_limit)
async def get_formulario(request: Request) -> PerguntaListResponse:
    org_id = resolve_public_org_id()
    client = get_admin_client()
    service = PublicAplicacoesService(client, org_id=org_id)
    result = await service.list_formulario()
    return PerguntaListResponse(**result)


@router.post("", response_model=AplicacaoPublicaOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.aplicacoes_rate_limit)
async def submit_aplicacao(
    request: Request,
    payload: AplicacaoPublicaCreate,
) -> AplicacaoPublicaOut:
    org_id = resolve_public_org_id()
    client = get_admin_client()
    service = PublicAplicacoesService(client, org_id=org_id)
    try:
        row = await service.submit(payload=payload.model_dump())
    except AplicacoesServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return AplicacaoPublicaOut(**row)


# ── aplicacoes (authenticated review) ────────────────────────────────


@router.get("", response_model=AplicacaoListResponse)
async def list_aplicacoes(
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> AplicacaoListResponse:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = AplicacoesService(client, org_id=org_id)
    result = await service.list_aplicacoes(status=status, page=page, page_size=page_size)
    return AplicacaoListResponse(**result)


@router.post("/{aplicacao_id}/aprovar", response_model=AplicacaoAprovarResponse)
async def aprovar_aplicacao(
    aplicacao_id: str,
    payload: AplicacaoAprovarRequest,
    auth: tuple = Depends(get_current_user_org),
) -> AplicacaoAprovarResponse:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="aprovar inscrições")
    client = get_user_client(token)
    service = AplicacoesService(client, org_id=org_id)
    plano_id = str(payload.plano_id) if payload.plano_id else None
    try:
        result = await service.aprovar(
            aplicacao_id=aplicacao_id,
            plano_id=plano_id,
            ativar=payload.ativar,
            revisor_id=str(getattr(user, "id", "")),
        )
    except AplicacoesServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    return AplicacaoAprovarResponse(
        aplicacao=Aplicacao(**result["aplicacao"]),
        membro=Membro(**result["membro"]),
    )


@router.post("/{aplicacao_id}/rejeitar", response_model=Aplicacao)
async def rejeitar_aplicacao(
    aplicacao_id: str,
    payload: AplicacaoRejeitarRequest,
    auth: tuple = Depends(get_current_user_org),
) -> Aplicacao:
    user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    require_admin(get_community_role(user), action="rejeitar inscrições")
    client = get_user_client(token)
    service = AplicacoesService(client, org_id=org_id)
    try:
        row = await service.rejeitar(
            aplicacao_id=aplicacao_id,
            motivo=payload.motivo,
            revisor_id=str(getattr(user, "id", "")),
        )
    except AplicacoesServiceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
    if not row:
        raise HTTPException(status_code=404, detail="Inscrição não encontrada.")
    return Aplicacao(**row)
