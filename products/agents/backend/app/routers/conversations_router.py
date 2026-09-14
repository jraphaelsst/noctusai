"""``/api/conversations`` — list/create/read + the turn loop + SSE stream
(contract §E.2, §E.3, §E.9, ``projects/julia-agents-academia-CONTRACT.md``).

The turn loop (``_run_turn_background``) is the sole consumer of the E.9
runtime seam. It obtains the runtime + broker via the lazy dependency
functions in ``app/dependencies.py`` (never importing ``app.runtime`` at
THIS module's top level — that package is G2's slice and does not exist on
this branch's base) and drives exactly the sequence contract §E.9 "What the
routes must do with a turn" describes.
"""
# NOTE: deliberately NO `from __future__ import annotations` here — this
# router has `@limiter.limit(...)`-decorated routes, and with postponed
# annotations FastAPI cannot resolve types through the slowapi wrapper (it
# degrades a `UUID` path param into an unresolvable `ForwardRef`, and the
# whole app fails to build at import / first request). Same fix as
# `products/igig/backend/app/routers/esteira_router.py`'s documented NOTE.
# Eager `X | None` union syntax still works unchanged (Python 3.10+).

import asyncio
import logging
from typing import Any
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from slowapi.util import get_remote_address

from app.dependencies import (
    ADMIN_ROLES,
    get_agent_runtime_dep,
    get_agent_store_dep,
    get_approval_broker_dep,
    get_build_julia_spec_dep,
    get_conversation_store_dep,
    get_core_client,
    get_message_store_dep,
    get_persona_store_dep,
    require_member,
)
from app.config import settings
from app.rate_limit import limiter
from app.realtime import conversation_scope, get_bus, publish_event
from app.schemas.agents import (
    ConversationCreateRequest,
    ConversationListOut,
    ConversationOut,
    MessageCreateRequest,
    MessageListOut,
    MessageOut,
    MessagePostResponse,
)
from app.stores.conversations import ConversationRecord
from app.stores.errors import NotFound
from app.stores.messages import MessageRecord
from app.turn_context import TurnContext
from noctusai_lib.api.auth.session import AuthContext, resolve_org_role
from noctusai_lib.realtime import create_sse_router

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

#: This process's turn-lock holder id (contract §E.1 migration header /
#: §E.2 "one in-flight turn per conversation, DB lock"). Stable for the
#: life of the process — same value the approvals-startup-expiry sweep
#: (G2, contract §E.2 "Startup") must key off of, so BOTH halves agree on
#: what "this instance" means. A module-level constant (not per-request)
#: because the lock/expiry semantics are process-scoped, not request-scoped.
INSTANCE_ID = f"agents-{uuid4().hex[:12]}"

#: Generous upper bound on how long a turn may hold the lock before another
#: request is allowed to reclaim it (crash recovery — see migration header).
_TURN_LOCK_TTL_SECONDS = 15 * 60

_NOT_FOUND = {"detail": "Conversa não encontrada.", "code": "not_found"}


def _conversation_out(record: ConversationRecord) -> ConversationOut:
    return ConversationOut(
        id=record.id,
        agent_id=record.agent_id,
        owner_user_id=record.owner_user_id,
        titulo=record.titulo,
        sdk_session_id=record.sdk_session_id,
        status=record.status,
        last_message_at=record.last_message_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _message_out(record: MessageRecord) -> MessageOut:
    return MessageOut(
        id=record.id,
        conversation_id=record.conversation_id,
        role=record.role,
        texto=record.texto,
        blocks=list(record.blocks),
        token_usage=record.token_usage,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _message_payload(record: MessageRecord) -> dict[str, Any]:
    """JSON-safe SSE payload for ``message.new`` (contract §E.3)."""
    return {
        "id": str(record.id),
        "conversation_id": str(record.conversation_id),
        "role": record.role,
        "texto": record.texto,
        "blocks": list(record.blocks),
        "token_usage": record.token_usage,
        "created_at": record.created_at.isoformat()
        if hasattr(record.created_at, "isoformat")
        else record.created_at,
        "updated_at": record.updated_at.isoformat()
        if hasattr(record.updated_at, "isoformat")
        else record.updated_at,
    }


def _caller_key(request: Request) -> str:
    """Rate-limit key for ``POST .../messages`` — "per user" (contract
    §E.2). Keyed off the raw credential (session cookie / bearer secret)
    rather than a resolved user id, so the limiter never needs its own DB
    round-trip; same caller always yields the same key."""
    cookie = request.cookies.get("nai_session")
    if cookie:
        return f"session:{cookie}"
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        return f"bearer:{authorization[7:]}"
    return get_remote_address(request)


async def _get_readable_conversation(
    ctx: AuthContext, conversation_id: UUID, conv_store: Any
) -> ConversationRecord:
    """Owner OR admin (contract §E.2 "404 unless the caller owns the
    conversation; admins may read")."""
    try:
        return conv_store.get_owned(ctx.org_id, conversation_id, ctx.user_id)
    except NotFound:
        pass
    role = resolve_org_role(get_core_client(), ctx.user_id)
    if role in ADMIN_ROLES:
        try:
            return conv_store.get(ctx.org_id, conversation_id)
        except NotFound:
            pass
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


@router.get("", response_model=ConversationListOut)
async def list_conversations(
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_conversation_store_dep),
) -> ConversationListOut:
    records = store.list_owned(ctx.org_id, ctx.user_id)
    items = [_conversation_out(r) for r in records]
    return ConversationListOut(items=items, total=len(items))


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreateRequest,
    ctx: AuthContext = Depends(require_member),
    agent_store=Depends(get_agent_store_dep),
    store=Depends(get_conversation_store_dep),
) -> ConversationOut:
    agent_store.ensure_default_agents(ctx.org_id)
    agent = agent_store.get_by_key(ctx.org_id, "julia")
    record = store.create(ctx.org_id, agent.id, ctx.user_id, titulo=payload.titulo)
    return _conversation_out(record)


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: UUID,
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_conversation_store_dep),
) -> ConversationOut:
    record = await _get_readable_conversation(ctx, conversation_id, store)
    return _conversation_out(record)


@router.get("/{conversation_id}/messages", response_model=MessageListOut)
async def list_messages(
    conversation_id: UUID,
    before: UUID | None = Query(default=None),
    limite: int = Query(default=50, ge=1, le=200),
    ctx: AuthContext = Depends(require_member),
    conv_store=Depends(get_conversation_store_dep),
    msg_store=Depends(get_message_store_dep),
) -> MessageListOut:
    await _get_readable_conversation(ctx, conversation_id, conv_store)
    records = msg_store.list(ctx.org_id, conversation_id, before=before, limite=limite)
    items = [_message_out(r) for r in records]
    return MessageListOut(items=items, total=len(items))


def _track_background_task(app_state: Any, task: "asyncio.Task") -> None:
    """Keeps a strong reference on ``app.state`` so the event loop never
    garbage-collects the running turn (a bare fire-and-forget
    ``asyncio.create_task`` is only weakly referenced by the loop)."""
    tasks = getattr(app_state, "agents_background_tasks", None)
    if tasks is None:
        tasks = set()
        app_state.agents_background_tasks = tasks
    tasks.add(task)
    task.add_done_callback(tasks.discard)


@router.post(
    "/{conversation_id}/messages",
    response_model=MessagePostResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
@limiter.limit(lambda: settings.messages_rate_limit, key_func=_caller_key)
async def post_message(
    request: Request,
    conversation_id: UUID,
    payload: MessageCreateRequest,
    ctx: AuthContext = Depends(require_member),
    runtime: Any = Depends(get_agent_runtime_dep),
    broker: Any = Depends(get_approval_broker_dep),
    build_spec: Any = Depends(get_build_julia_spec_dep),
    conv_store=Depends(get_conversation_store_dep),
    agent_store=Depends(get_agent_store_dep),
    msg_store=Depends(get_message_store_dep),
    persona_store=Depends(get_persona_store_dep),
) -> MessagePostResponse:
    try:
        conv_store.get_owned(ctx.org_id, conversation_id, ctx.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc

    try:
        agent = agent_store.get_by_key(ctx.org_id, "julia")
    except NotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc
    if not agent.ativo:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "O agente Julia está desligado.", "code": "agent_off"},
        )

    # Contract §E.9 point 1: persist the user message, THEN try_acquire_turn.
    user_message = msg_store.add(ctx.org_id, conversation_id, "user", payload.texto)
    await publish_event(conversation_id, "message.new", _message_payload(user_message))

    acquired = conv_store.try_acquire_turn(
        ctx.org_id, conversation_id, INSTANCE_ID, _TURN_LOCK_TTL_SECONDS
    )
    if not acquired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"detail": "Já existe um turno em andamento.", "code": "turn_in_progress"},
        )

    task = asyncio.create_task(
        _run_turn_background(
            org_id=ctx.org_id,
            conversation_id=conversation_id,
            agent_id=agent.id,
            owner_user_id=ctx.user_id,
            prompt=payload.texto,
            runtime=runtime,
            broker=broker,
            build_spec=build_spec,
            conv_store=conv_store,
            msg_store=msg_store,
            persona_store=persona_store,
        )
    )
    _track_background_task(request.app.state, task)

    return MessagePostResponse(mensagem=_message_out(user_message), status="processando")


def _apply_tool_event(
    blocks: list[dict[str, Any]], kind: str, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """Contract §E.7 ``ChatBlock`` (tool variant): ``{kind:"tool",
    toolUseId, name, status, resumo?}``."""
    blocks = list(blocks)
    tool_use_id = payload.get("tool_use_id")
    if kind == "tool.started":
        blocks.append(
            {
                "kind": "tool",
                "toolUseId": tool_use_id,
                "name": payload.get("tool_name"),
                "status": "running",
                "resumo": payload.get("resumo"),
            }
        )
        return blocks
    # tool.finished — update the matching block in place; append defensively
    # if `tool.started` was somehow missed rather than dropping the signal.
    resultado = payload.get("resultado", "ok")
    for block in blocks:
        if block.get("kind") == "tool" and block.get("toolUseId") == tool_use_id:
            block["status"] = resultado
            return blocks
    blocks.append(
        {
            "kind": "tool",
            "toolUseId": tool_use_id,
            "name": payload.get("tool_name"),
            "status": resultado,
            "resumo": None,
        }
    )
    return blocks


def _apply_approval_event(
    blocks: list[dict[str, Any]], kind: str, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """Contract §E.7 ``ChatBlock`` (approval variant): ``{kind:"approval",
    approvalId, resumo, diff?, decision}``."""
    blocks = list(blocks)
    approval_id = payload.get("id") or payload.get("approval_id")
    if kind == "approval.requested":
        blocks.append(
            {
                "kind": "approval",
                "approvalId": approval_id,
                "resumo": payload.get("resumo"),
                "diff": payload.get("diff"),
                "decision": "pendente",
            }
        )
        return blocks
    decision = payload.get("decision", "pendente")
    for block in blocks:
        if block.get("kind") == "approval" and block.get("approvalId") == approval_id:
            block["decision"] = decision
            return blocks
    blocks.append(
        {
            "kind": "approval",
            "approvalId": approval_id,
            "resumo": None,
            "diff": None,
            "decision": decision,
        }
    )
    return blocks


async def _run_turn_background(
    *,
    org_id: UUID,
    conversation_id: UUID,
    agent_id: UUID,
    owner_user_id: UUID,
    prompt: str,
    runtime: Any,
    broker: Any,
    build_spec: Any,
    conv_store: Any,
    msg_store: Any,
    persona_store: Any,
) -> None:
    """Contract §E.9 "What the routes must do with a turn", points 2-6.

    Every collaborator (``runtime`` / ``broker`` / ``build_spec`` / the
    three stores) is resolved by the caller (the route handler) via
    FastAPI ``Depends(...)`` and passed in explicitly — this function
    never calls a store factory or imports ``app.runtime`` itself, so it
    works identically against the real runtime (once G2 lands) and
    against the ``tests/_runtime_standin.py`` stand-in with a shared,
    stateful Fake store."""
    current_message_id: UUID | None = None
    current_blocks: list[dict[str, Any]] = []

    try:
        persona = persona_store.get_active(org_id, agent_id)
        conversation = conv_store.get_owned(org_id, conversation_id, owner_user_id)

        spec = build_spec(persona)
        turn_ctx = TurnContext(
            org_id=org_id,
            conversation_id=conversation_id,
            requested_by=owner_user_id,
            instance_id=INSTANCE_ID,
            sdk_session_id=conversation.sdk_session_id,
        )

        async for event in runtime.run_turn(spec, turn_ctx, prompt, broker):
            kind = event["event"]
            evt_payload = event["payload"]

            if kind == "message.new":
                record = msg_store.add(
                    org_id, conversation_id, "assistant", evt_payload.get("texto", ""),
                    blocks=[],
                )
                current_message_id = record.id
                current_blocks = []
                await publish_event(conversation_id, "message.new", _message_payload(record))
            elif kind == "message.delta":
                # Contract §E.9 point 4: published only, never persisted.
                await publish_event(conversation_id, "message.delta", evt_payload)
            elif kind in ("tool.started", "tool.finished"):
                if current_message_id is None:
                    record = msg_store.add(org_id, conversation_id, "assistant", "", blocks=[])
                    current_message_id = record.id
                    current_blocks = []
                current_blocks = _apply_tool_event(current_blocks, kind, evt_payload)
                msg_store.update_blocks(org_id, conversation_id, current_message_id, current_blocks)
                await publish_event(conversation_id, kind, evt_payload)
            elif kind in ("approval.requested", "approval.resolved"):
                if current_message_id is None:
                    record = msg_store.add(org_id, conversation_id, "assistant", "", blocks=[])
                    current_message_id = record.id
                    current_blocks = []
                current_blocks = _apply_approval_event(current_blocks, kind, evt_payload)
                msg_store.update_blocks(org_id, conversation_id, current_message_id, current_blocks)
                await publish_event(conversation_id, kind, evt_payload)
            elif kind == "session.status":
                sdk_session_id = evt_payload.get("sdk_session_id")
                if sdk_session_id:
                    conv_store.set_sdk_session_id(org_id, conversation_id, sdk_session_id)
                await publish_event(conversation_id, "session.status", evt_payload)
            elif kind == "conversation.upsert":
                await publish_event(conversation_id, "conversation.upsert", evt_payload)
            else:
                logger.warning(
                    "agents.turn.unknown_event org_id=%s conversation_id=%s kind=%s",
                    org_id, conversation_id, kind,
                )
    except Exception:
        # Contract §E.9 point 6 — generic message, NEVER exception text.
        logger.exception(
            "agents.turn.failed org_id=%s conversation_id=%s", org_id, conversation_id
        )
        try:
            msg_store.add(org_id, conversation_id, "system", "O turno falhou.")
            await publish_event(conversation_id, "session.status", {"status": "erro"})
        except Exception:
            logger.exception(
                "agents.turn.failure_reporting_failed org_id=%s conversation_id=%s",
                org_id, conversation_id,
            )
    finally:
        conv_store.release_turn(org_id, conversation_id, INSTANCE_ID)


# ── SSE stream (contract §E.3) ──────────────────────────────────────────────


async def _resolve_stream_auth(
    request: Request,
    ctx: AuthContext = Depends(require_member),
    conv_store=Depends(get_conversation_store_dep),
) -> UUID:
    """Auth dependency for the SSE stream — resolves AND verifies
    ownership/admin access (same shape as social-wiring's
    ``_resolve_stream_auth``; see that module for the pattern's origin)."""
    conversation_id = UUID(request.path_params["conversation_id"])
    await _get_readable_conversation(ctx, conversation_id, conv_store)
    return conversation_id


def _stream_scope(request: Request, conversation_id: UUID) -> str:
    return conversation_scope(conversation_id)


router.include_router(
    create_sse_router(
        get_bus(),
        scope_resolver=_stream_scope,
        auth_dependency=_resolve_stream_auth,
        path="/{conversation_id}/stream",
    )
)


__all__ = ["router", "INSTANCE_ID"]
