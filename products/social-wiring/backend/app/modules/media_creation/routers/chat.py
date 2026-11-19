# NOTE: no `from __future__ import annotations` here -- slowapi's @limiter.limit wrapper
# breaks FastAPI's annotation resolution (the body model becomes a query param -> 422).
"""Chat endpoints (``specs/geracao-contract.md`` section 4.6, endpoints 41-48).

``POST /chat/conversas/{id}/mensagens`` answers ``text/event-stream``; every refusal that can be
decided before the first byte is a plain HTTP status (404 foreign id/reference, 409
``stream_em_andamento``, 429 caps, 503 ``ia_nao_configurada`` / ``orcamento_ia_excedido``). SSE frames:
``{"meta"}`` -> ``{"delta"}``... -> [``{"truncated"}``] -> ``{"done": {mensagem_id, propostas}}`` | ``{"error"}``.

ONE unified chat (``specs/estruturas-contract.md`` 6.5): ``agente`` is accepted and ignored; ``POST
/conversas/{id}/escolher`` saves the clicked headline and starts the headline -> roteiro -> card flow (section 9.2).
"""
import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask

from noctusai_lib.api.rate_limit_policies import DEFAULT_AI_RL
from noctusai_lib.primitives.responses import success_response

from noctusai_lib.domain.approvals import ApprovalService
from noctusai_lib.domain.jobs import JobRepository

from app.dependencies import get_admin_client, get_current_user_org
from app.modules.media_creation.schemas.chat import (
    Agente,
    ConversaCreate,
    ConversaRename,
    EscolherIn,
    MemoriaCreate,
    MencaoTipo,
    MensagemCreate,
)
from app.modules.media_creation.services.chat_service import (
    ChatError,
    ChatService,
    ChatStreamFn,
    ExtrairFn,
    get_chat_stream_fn,
    get_extrair_propostas,
    liberar_stream,
)
from app.modules.media_creation.services.fluxo_service import (
    FluxoService,
    Orcamento,
    get_fluxo_orcamento,
    get_fluxo_settings,
)
from app.modules.media_creation.services.fluxo_continuacao import FluxoContinuacao
from app.modules.media_creation.services.geracao_jobs import make_jobs_repository
from app.modules.media_creation.services.roteiro_aprovacao import make_approvals
from app.modules.media_creation.services.roteiro_service import IaCheck, RoteiroService, get_roteiro_ia_check
from app.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/media-creation/chat", tags=["Media Creation — Chat"])


def _svc(auth) -> ChatService:
    user, _, org_id = auth
    return ChatService(get_admin_client(), str(org_id), str(user.id))


def get_fluxo_jobs() -> JobRepository:
    """DI seam for the saga's queue (roteiro job, finalizer, roteiro-first headline). Tests override with a Fake."""
    return make_jobs_repository(get_admin_client())


def get_fluxo_approvals() -> ApprovalService:
    """DI seam for the approvals organ ``RoteiroService`` presents with. Tests override with the Fake ledger."""
    return make_approvals(get_admin_client())


def _fluxo_svc(
    auth, cfg, ia_check: IaCheck, orcamento: Orcamento, jobs: Optional[JobRepository] = None,
    approvals: Optional[ApprovalService] = None,
) -> ChatService:
    user, _, org_id = auth
    db = get_admin_client()
    continuacao = None
    if jobs is not None:
        def roteiros(db_: Any, org: str, usuario: str) -> RoteiroService:
            return RoteiroService(db_, org, usuario, cfg=cfg, jobs=jobs, ia_check=ia_check, approvals=approvals)

        continuacao = FluxoContinuacao(db, str(org_id), str(user.id), jobs=jobs, roteiros=roteiros)
    fluxo = FluxoService(
        db, str(org_id), str(user.id), cfg=cfg, ia_check=ia_check, orcamento=orcamento, continuacao=continuacao,
    )
    return ChatService(db, str(org_id), str(user.id), fluxo=fluxo)


def _raise(exc: ChatError):
    detail = {"detail": exc.detail, "code": exc.code} if exc.code else exc.detail
    raise HTTPException(status_code=exc.status, detail=detail, headers=exc.headers or None) from exc


@router.get("/conversas")
def list_conversas(
    marca_id: uuid.UUID,
    agente: Optional[Agente] = None,  # DEPRECATED: accepted and ignored (one unified chat)
    limit: int = Query(15, ge=1, le=15),
    offset: int = Query(0, ge=0),
    auth=Depends(get_current_user_org),
):
    try:
        return success_response(_svc(auth).list_conversas(str(marca_id), limit, offset))
    except ChatError as exc:
        _raise(exc)


@router.post("/conversas", status_code=201)
def create_conversa(body: ConversaCreate, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).create_conversa(str(body.marca_id), body.titulo))
    except ChatError as exc:
        _raise(exc)


@router.patch("/conversas/{conversa_id}")
def rename_conversa(conversa_id: uuid.UUID, body: ConversaRename, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).rename_conversa(str(conversa_id), body.titulo))
    except ChatError as exc:
        _raise(exc)


@router.delete("/conversas/{conversa_id}", status_code=204)
def delete_conversa(conversa_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        _svc(auth).delete_conversa(str(conversa_id))
    except ChatError as exc:
        _raise(exc)
    return Response(status_code=204)


@router.get("/conversas/{conversa_id}/mensagens")
def list_mensagens(
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
    extrair: ExtrairFn = Depends(get_extrair_propostas),
):
    svc = _svc(auth)
    try:
        envio = await svc.preparar_envio(str(conversa_id), body.conteudo, body.referencias, stream_fn, extrair)
    except ChatError as exc:
        _raise(exc)
    return StreamingResponse(
        svc.eventos(envio, body.conteudo),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        # the generator's `finally` releases the lock; this covers a response that never started it
        background=BackgroundTask(liberar_stream, svc.user_id),
    )


@router.post("/conversas/{conversa_id}/escolher", status_code=202)
@limiter.limit(DEFAULT_AI_RL)
async def escolher(
    request: Request,
    response: Response,
    conversa_id: uuid.UUID,
    body: EscolherIn,
    auth=Depends(get_current_user_org),
    cfg=Depends(get_fluxo_settings),
    ia_check: IaCheck = Depends(get_roteiro_ia_check),
    orcamento: Orcamento = Depends(get_fluxo_orcamento),
    jobs: JobRepository = Depends(get_fluxo_jobs),
    approvals: ApprovalService = Depends(get_fluxo_approvals),
):
    """The click on a proposta (9.2 / 16.6): 202 the first time, 200 + ``ja_existia`` when the flow already exists."""
    svc = _fluxo_svc(auth, cfg, ia_check, orcamento, jobs, approvals)
    try:
        resultado = await svc.fluxo.escolher(
            str(conversa_id),
            proposta_id=str(body.proposta_id) if body.proposta_id else None,
            headline_id=str(body.headline_id) if body.headline_id else None,
        )
    except ChatError as exc:
        _raise(exc)
    if resultado.ja_existia:
        response.status_code = 200
    return success_response(resultado.como_dict())


@router.get("/mencoes")
def listar_mencoes(
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
def list_memorias(marca_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).list_memorias(str(marca_id)))
    except ChatError as exc:
        _raise(exc)


@router.post("/memorias", status_code=201)
def create_memoria(body: MemoriaCreate, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).create_memoria(str(body.marca_id), body.texto))
    except ChatError as exc:
        _raise(exc)


@router.delete("/memorias/{memoria_id}", status_code=204)
def delete_memoria(memoria_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        _svc(auth).delete_memoria(str(memoria_id))
    except ChatError as exc:
        _raise(exc)
    return Response(status_code=204)


@router.get("/contexto")
def medir_contexto(conversa_id: uuid.UUID, auth=Depends(get_current_user_org)):
    try:
        return success_response(_svc(auth).medir_contexto(str(conversa_id)))
    except ChatError as exc:
        _raise(exc)
