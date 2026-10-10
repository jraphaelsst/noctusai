# NOTE: no `from __future__ import annotations` here -- slowapi's @limiter.limit wrapper
# breaks FastAPI's annotation resolution (the body model becomes a query param -> 422).
"""Chat endpoints (``specs/geracao-contract.md`` section 4.6, endpoints 41-48).

``POST /chat/conversas/{id}/mensagens`` answers ``text/event-stream``; every refusal that can be
decided before the first byte is a plain HTTP status (404 foreign id/reference, 409
``stream_em_andamento``, 429 caps, 503 ``ia_nao_configurada`` / ``orcamento_ia_excedido``). SSE frames:
``{"meta"}`` -> ``{"delta"}``... -> [``{"truncated"}``] -> ``{"done"}`` | ``{"error"}``.
"""
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.schemas.chat import (
    Agente,
    ConversaCreate,
    ConversaRename,
    MemoriaCreate,
    MencaoTipo,
    MensagemCreate,
)
from app.modules.media_creation.services.chat_service import (
    ChatError,
    ChatService,
    ChatStreamFn,
    get_chat_stream_fn,
    liberar_stream,
)
from app.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media-creation/chat", tags=["Media Creation — Chat"])


def _svc(auth) -> ChatService:
    user, _, org_id = auth
    return ChatService(get_admin_client(), str(org_id), str(user.id))


def _raise(exc: ChatError):
    detail = {"detail": exc.detail, "code": exc.code} if exc.code else exc.detail
    raise HTTPException(status_code=exc.status, detail=detail, headers=exc.headers or None) from exc


@router.get("/conversas")
async def list_conversas(
    marca_id: uuid.UUID,
    agente: Agente,
    limit: int = Query(15, ge=1, le=15),
    offset: int = Query(0, ge=0),
    auth=Depends(get_current_user_org),
):
    try:
        return success_response(_svc(auth).list_conversas(str(marca_id), agente, limit, offset))
    except ChatError as exc:
        _raise(exc)


@router.post("/conversas", status_code=201)
async def create_conversa(body: ConversaCreate, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).create_conversa(str(body.marca_id), body.agente, body.titulo))
    except ChatError as exc:
        _raise(exc)


@router.patch("/conversas/{conversa_id}")
async def rename_conversa(conversa_id: uuid.UUID, body: ConversaRename, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).rename_conversa(str(conversa_id), body.titulo))
    except ChatError as exc:
        _raise(exc)


@router.delete("/conversas/{conversa_id}", status_code=204)
async def delete_conversa(conversa_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        _svc(auth).delete_conversa(str(conversa_id))
    except ChatError as exc:
        _raise(exc)
    return Response(status_code=204)


@router.get("/conversas/{conversa_id}/mensagens")
async def list_mensagens(
    conversa_id: uuid.UUID,
    antes: Optional[str] = None,
    limit: int = Query(50, ge=1, le=100),
    auth=Depends(get_current_user_org),
):
    try:
        return success_response(_svc(auth).list_mensagens(str(conversa_id), antes, limit))
    except ChatError as exc:
        _raise(exc)


@router.post("/conversas/{conversa_id}/mensagens")
@limiter.limit(DEFAULT_AI_RL)
async def enviar_mensagem(
    request: Request,
    conversa_id: uuid.UUID,
    body: MensagemCreate,
    auth=Depends(get_current_user_org),
    stream_fn: ChatStreamFn = Depends(get_chat_stream_fn),
):
    svc = _svc(auth)
    try:
        envio = await svc.preparar_envio(str(conversa_id), body.conteudo, body.referencias, stream_fn)
    except ChatError as exc:
        _raise(exc)
    return StreamingResponse(
        svc.eventos(envio, body.conteudo),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        # the generator's `finally` releases the lock; this covers a response that never started it
        background=BackgroundTask(liberar_stream, svc.user_id),
    )


@router.get("/mencoes")
async def listar_mencoes(
    marca_id: uuid.UUID,
    tipo: MencaoTipo,
    q: Optional[str] = Query(None, max_length=100),
    variavel: Optional[str] = Query(None, max_length=120),
    page: int = Query(0, ge=0, le=1000),
    auth=Depends(get_current_user_org),
):
    svc = _svc(auth)
    try:
        svc.assert_marca(str(marca_id))
        return success_response(svc.contexto.mencoes(str(marca_id), tipo, q, variavel, page))
    except ChatError as exc:
        _raise(exc)


@router.get("/memorias")
async def list_memorias(marca_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).list_memorias(str(marca_id)))
    except ChatError as exc:
        _raise(exc)


@router.post("/memorias", status_code=201)
async def create_memoria(body: MemoriaCreate, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).create_memoria(str(body.marca_id), body.texto))
    except ChatError as exc:
        _raise(exc)


@router.delete("/memorias/{memoria_id}", status_code=204)
async def delete_memoria(memoria_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        _svc(auth).delete_memoria(str(memoria_id))
    except ChatError as exc:
        _raise(exc)
    return Response(status_code=204)


@router.get("/contexto")
async def medir_contexto(conversa_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).medir_contexto(str(conversa_id)))
    except ChatError as exc:
        _raise(exc)
