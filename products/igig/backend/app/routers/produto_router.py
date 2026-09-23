"""Produtos e Serviços — the orçamento catalogue (roadmap R6, wave-2 slice A).

  GET    /api/produtos-servicos?secao=&ativo=   (seeds the owner's examples on
                                                  an org's first read)
  POST   /api/produtos-servicos                  201
  PATCH  /api/produtos-servicos/{id}
  DELETE /api/produtos-servicos/{id}             referenced by an orçamento item
                                                  ⇒ soft (ativo=false), else hard;
                                                  200 either way, says which

Rules live in `app/services/produtos.py`. Success = `{"data": ...}`.
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers; see esteira_router.py.
from typing import Any, Literal

from fastapi import APIRouter, Depends, status
from noctusai_lib.primitives.responses import success_response

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.pipelines import get_db
from app.schemas.orcamento import ProdutoServicoCreate, ProdutoServicoUpdate
from app.services import produtos as svc
from app.services.regras import RegraViolada, http_de

router = APIRouter(prefix="/api/produtos-servicos", tags=["produtos-servicos"])


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


@router.get("")
async def listar_produtos(
    secao: Literal["criacao_conteudo", "gestao_conta"] | None = None,
    ativo: bool | None = None,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    return success_response(svc.listar(db, _org(auth), secao=secao, ativo=ativo))


@router.post("", status_code=status.HTTP_201_CREATED)
async def criar_produto(
    payload: ProdutoServicoCreate,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    try:
        return success_response(svc.criar(db, _org(auth), payload.model_dump()))
    except RegraViolada as erro:
        raise http_de(erro) from erro


@router.patch("/{produto_id}")
async def atualizar_produto(
    produto_id: str,
    payload: ProdutoServicoUpdate,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    try:
        return success_response(
            svc.atualizar(db, _org(auth), produto_id, payload.model_dump(exclude_unset=True))
        )
    except RegraViolada as erro:
        raise http_de(erro) from erro


@router.delete("/{produto_id}")
async def remover_produto(
    produto_id: str,
    auth: tuple = Depends(get_current_user_org),
    db: Any = Depends(get_db),
) -> dict:
    return success_response(svc.remover(db, _org(auth), produto_id))
