"""Lais > Conversas v2 (wave 7, contract section 9 + A7).

  GET    /api/lais/conversas?aba=todas|minhas|arquivadas&q&limit&offset
         list filters are COMMA-JOINED: operacao=a,b status_sw=a,b atendimento=julia,manual
         responsavel=<uuid>,sem (sem = unassigned) etiqueta=<id>,<id> (repeating etiqueta also works) equipe (ignored)
         ?view=kanban         -> {data:{colunas:[todas, <one per etiqueta>, arquivadas]}}
  PATCH  /api/lais/contatos/{id}                {responsavel_user_id?, arquivado?, bloqueado?, etiquetas?}
  GET|POST /api/lais/contatos/{id}/notas        DELETE /api/lais/contatos/{id}/notas/{nota_id} (soft)
  POST   /api/lais/contatos/{id}/feedback       {nota: like|dislike, comentario?, interacao_id?}
  GET|POST /api/lais/etiquetas   PATCH|DELETE /api/lais/etiquetas/{id} (admin)
  GET    /api/lais/historico/{contato_id}       -> {data:{contato, interacoes, mensagens}}

Access (A7, `lais_acesso`): every per-contato route -- and the history link -- is 401 without a session,
404 for a contato of another org, 403 `sem_acesso` for a same-org member who is neither its owner
(responsavel, else connection owner) nor an org owner/admin. Lists silently contain only what the caller may see.
`equipe` is accepted but ignored until the teams table lands (wave 11); `meta.equipe_ignorada` says so.

NB: registered BEFORE `lais_perguntas_router`, whose `GET /api/lais/contatos/{connection_id}/{chat_id}` would
otherwise swallow `GET /api/lais/contatos/{id}/notas`.
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
import logging
from typing import Any, Literal, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, Response
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import get_core_client, get_current_user_org, get_scoped_admin_client
from app.services import lais_acesso, lais_conversas_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/lais", tags=["lais-conversas"])


def get_conversas_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


class ContatoPatch(StrictHttpModel):
    responsavel_user_id: Optional[UUID] = None
    arquivado: Optional[bool] = None
    bloqueado: Optional[bool] = None
    etiquetas: Optional[list[UUID]] = Field(default=None, max_length=50)


class NotaIn(StrictHttpModel):
    texto: str = Field(min_length=1, max_length=4000)


class FeedbackIn(StrictHttpModel):
    nota: Literal["like", "dislike"]
    comentario: Optional[str] = Field(default=None, max_length=1000)
    interacao_id: Optional[UUID] = None


class EtiquetaIn(StrictHttpModel):
    nome: str = Field(min_length=1, max_length=40)
    cor: Optional[str] = Field(default=None, max_length=7)


class EtiquetaPatch(StrictHttpModel):
    nome: Optional[str] = Field(default=None, min_length=1, max_length=40)
    cor: Optional[str] = Field(default=None, max_length=7)


def _csv(valor: Optional[str]) -> list[str]:
    """Comma-joined query param -> list (`a,b`); blanks dropped."""
    return [p.strip() for p in (valor or "").split(",") if p.strip()]


def _ctx(auth: tuple, request: Optional[Request]) -> lais_acesso.AcessoCtx:
    return lais_acesso.contexto(auth, request)


# ── list / kanban ───────────────────────────────────────────────────────────
@router.get("/conversas")
def listar(
    request: Request = None,
    aba: str = "todas",
    view: str = "lista",
    operacao: Optional[str] = None,
    status_sw: Optional[str] = None,
    atendimento: Optional[str] = None,
    responsavel: Optional[str] = None,
    equipe: Optional[str] = None,
    etiqueta: Optional[list[str]] = Query(default=None),
    q: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_conversas_client),
) -> dict[str, Any]:
    if aba not in svc.ABAS:
        raise AppException("aba_invalida", "Use aba=todas, minhas ou arquivadas.", status_code=422)
    if view not in ("lista", "kanban"):
        raise AppException("view_invalida", "Use view=lista ou view=kanban.", status_code=422)
    atend = _csv(atendimento)
    if not set(atend) <= set(svc.ATENDIMENTOS):
        raise AppException("atendimento_invalido", "Use atendimento=julia e/ou manual.", status_code=422)
    resp = _csv(responsavel)
    for r in resp:
        if r != "sem":
            try:
                UUID(r)
            except ValueError:
                raise AppException("responsavel_invalido", "responsavel deve ser um uuid ou `sem`.", status_code=422)
    ctx = _ctx(auth, request)
    tags = [t for e in (etiqueta or []) for t in _csv(e)]
    ops, sts = _csv(operacao), _csv(status_sw)
    meta: dict[str, Any] = {"equipe_ignorada": equipe is not None}
    if view == "kanban":
        dados = svc.kanban(client, ctx, etiquetas=tags, operacao=ops, status_sw=sts, atendimento=atend, responsavel=resp)
        return {"data": dados, "meta": meta}
    itens, total = svc.listar(
        client, ctx, aba=aba, operacao=ops, status_sw=sts, atendimento=atend, responsavel=resp,
        etiquetas=tags, busca=q, limit=limit, offset=offset,
    )
    return {"data": itens, "meta": {**meta, "aba": aba, "total": total, "limit": limit, "offset": offset}}


# ── contato mutations ───────────────────────────────────────────────────────
@router.patch("/contatos/{contato_id}")
def patch_contato(
    contato_id: UUID,
    corpo: ContatoPatch,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_conversas_client),
) -> dict[str, Any]:
    ctx = _ctx(auth, request)
    contato = lais_acesso.exigir_contato(client, ctx, contato_id)
    campos = {k: getattr(corpo, k) for k in corpo.model_fields_set}
    return {"data": svc.atualizar_contato(client, get_core_client(), ctx, contato, campos)}


# ── notas ───────────────────────────────────────────────────────────────────
@router.get("/contatos/{contato_id}/notas")
def get_notas(
    contato_id: UUID,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_conversas_client),
) -> dict[str, Any]:
    ctx = _ctx(auth, request)
    lais_acesso.exigir_contato(client, ctx, contato_id)
    return {"data": svc.listar_notas(client, ctx.org_id, contato_id)}


@router.post("/contatos/{contato_id}/notas", status_code=201)
def post_nota(
    contato_id: UUID,
    corpo: NotaIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_conversas_client),
) -> dict[str, Any]:
    ctx = _ctx(auth, request)
    lais_acesso.exigir_contato(client, ctx, contato_id)
    return {"data": svc.criar_nota(client, ctx, contato_id, corpo.texto)}


@router.delete("/contatos/{contato_id}/notas/{nota_id}", status_code=204)
def delete_nota(
    contato_id: UUID,
    nota_id: UUID,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_conversas_client),
) -> Response:
    ctx = _ctx(auth, request)
    lais_acesso.exigir_contato(client, ctx, contato_id)
    svc.excluir_nota(client, ctx, contato_id, nota_id)
    return Response(status_code=204)


# ── feedback ────────────────────────────────────────────────────────────────
@router.post("/contatos/{contato_id}/feedback", status_code=201)
def post_feedback(
    contato_id: UUID,
    corpo: FeedbackIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_conversas_client),
) -> dict[str, Any]:
    ctx = _ctx(auth, request)
    contato = lais_acesso.exigir_contato(client, ctx, contato_id)
    return {"data": svc.registrar_feedback(
        client, ctx, contato, nota=corpo.nota, comentario=corpo.comentario,
        interacao_id=str(corpo.interacao_id) if corpo.interacao_id else None)}


# ── etiquetas ───────────────────────────────────────────────────────────────
@router.get("/etiquetas")
def get_etiquetas(
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_conversas_client),
) -> dict[str, Any]:
    return {"data": svc.listar_etiquetas(client, _ctx(auth, request).org_id)}


@router.post("/etiquetas", status_code=201)
def post_etiqueta(
    corpo: EtiquetaIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_conversas_client),
) -> dict[str, Any]:
    return {"data": svc.criar_etiqueta(client, _ctx(auth, request).org_id, corpo.nome, corpo.cor)}


@router.patch("/etiquetas/{etiqueta_id}")
def patch_etiqueta(
    etiqueta_id: UUID,
    corpo: EtiquetaPatch,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_conversas_client),
) -> dict[str, Any]:
    require_org_admin_for(get_core_client(), auth, request, "As etiquetas")
    return {"data": svc.atualizar_etiqueta(client, _ctx(auth, request).org_id, etiqueta_id, nome=corpo.nome, cor=corpo.cor)}


@router.delete("/etiquetas/{etiqueta_id}", status_code=204)
def delete_etiqueta(
    etiqueta_id: UUID,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_conversas_client),
) -> Response:
    require_org_admin_for(get_core_client(), auth, request, "As etiquetas")
    svc.excluir_etiqueta(client, _ctx(auth, request).org_id, etiqueta_id)
    return Response(status_code=204)


# ── history (the "Copiar link do histórico" target, A7) ─────────────────────
@router.get("/historico/{contato_id}")
def get_historico(
    contato_id: UUID,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_conversas_client),
) -> dict[str, Any]:
    ctx = _ctx(auth, request)
    contato = lais_acesso.exigir_contato(client, ctx, contato_id)
    return {"data": svc.historico(client, ctx, contato)}
