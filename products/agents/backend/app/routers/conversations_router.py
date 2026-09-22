"""``/api/conversations`` — list/create/read + the turn loop + SSE stream
(contract §E.2, §E.3, §E.9, §E.11, ``projects/julia-agents-academia-CONTRACT.md``).

The turn loop (``_run_turn_background``) is the sole consumer of the E.9
runtime seam. It imports the STABLE, dependency-free ``TurnContext``
directly from ``app.runtime.types`` (G2's slice), but still obtains the
runtime/broker/spec-builder INSTANCES via the lazy dependency functions in
``app/dependencies.py`` — ``get_agent_runtime``'s real branch conditionally
imports ``claude_agent_sdk``, a cost worth deferring to the first request
that actually needs it. Drives exactly the sequence contract §E.9 "What
the routes must do with a turn" describes, per the §E.11 "Route order"
revision: reserve a slot, THEN acquire the turn lock, THEN persist the
user message, THEN start the task under a turn deadline.
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
    get_realtime_bus_dep,
    require_member,
)
from app.config import settings
from app.services.runtime_settings import get_runtime_settings_service
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
from app.runtime.types import AgentSpec, TurnContext
from app.routers.studio_agents_router import (
    get_knowledge_catalog_dep,
    get_studio_definition_store_dep,
    resolve_agent,
)
from app.studio.spec import StudioSpecError, build_studio_spec
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

_NOT_FOUND = {"detail": "Conversa não encontrada.", "code": "not_found"}

#: Agent Studio §D6 — the agent a request that names none addresses.
JULIA_KEY = "julia"


def _conversation_out(record: ConversationRecord, agent_key: str) -> ConversationOut:
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
        agent_key=agent_key,
        version_id=record.version_id,
        client_id=record.client_id,
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
        version_id=record.version_id,
        compiled_hash=record.compiled_hash,
    )


def _http(status_code: int, code: str, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"detail": detail, "code": code})


def _julia_agent(agent_store: Any, org_id: UUID) -> Any | None:
    """Julia's row, or ``None`` while it was never seeded for this org (an
    explicit "maybe" read — not an ``except NotFound`` fallback)."""
    return next((a for a in agent_store.list(org_id) if a.key == JULIA_KEY), None)


def _resolve_studio_agent(studio_store: Any, org_id: UUID, key: str) -> Any:
    """Agent Studio §D intro — the SAME resolver every studio route uses:
    unknown key → 404 ``agent_not_found``; legacy → 409 ``not_studio_agent``."""
    return resolve_agent(studio_store, org_id, key)


def _studio_agent_by_id(studio_store: Any, org_id: UUID, agent_id: UUID) -> Any | None:
    for agent in studio_store.list_agents(org_id):
        if agent.id == agent_id and agent.definition_mode == "studio":
            return agent
    return None


def _agent_key_for(org_id: UUID, agent_id: UUID, agent_store: Any, studio_store: Any) -> str:
    """The ``agent_key`` of a conversation's agent (§D6 ``ConversationOut``)."""
    for agent in agent_store.list(org_id):
        if agent.id == agent_id:
            return agent.key
    for agent in studio_store.list_agents(org_id):
        if agent.id == agent_id:
            return agent.key
    # A conversation whose agent row is gone is a data-integrity breach
    # (conversations.agent_id is a FK) — loud, never a guessed key.
    raise RuntimeError(f"agent {agent_id} of a conversation not found for org {org_id}")


def _conversation_payload(record: ConversationRecord) -> dict[str, Any]:
    """JSON-safe SSE payload for ``conversation.upsert`` (contract §E.3)."""

    def _iso(value: Any) -> Any:
        return value.isoformat() if hasattr(value, "isoformat") else value

    return {
        "id": str(record.id),
        "agent_id": str(record.agent_id),
        "owner_user_id": str(record.owner_user_id),
        "titulo": record.titulo,
        "sdk_session_id": record.sdk_session_id,
        "status": record.status,
        "last_message_at": _iso(record.last_message_at),
        "created_at": _iso(record.created_at),
        "updated_at": _iso(record.updated_at),
    }


def _message_payload(record: MessageRecord) -> dict[str, Any]:
    """JSON-safe SSE payload for ``message.new`` (contract §E.3).

    Agent Studio §A7: a stamped (studio assistant) message also carries
    ``version_id`` + ``compiled_hash``; an unstamped one (every Julia
    message) keeps the exact pre-studio payload."""
    payload = _message_payload_base(record)
    if record.version_id is not None:
        payload["version_id"] = str(record.version_id)
    if record.compiled_hash is not None:
        payload["compiled_hash"] = record.compiled_hash
    return payload


def _message_payload_base(record: MessageRecord) -> dict[str, Any]:
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
        # Not the owner (or absent) — fall through to the admin read below.
        logger.debug("agents.conversation.not_owned conversation_id=%s", conversation_id)
    role = resolve_org_role(get_core_client(), ctx.user_id)
    if role in ADMIN_ROLES:
        try:
            return conv_store.get(ctx.org_id, conversation_id)
        except NotFound:
            logger.debug("agents.conversation.not_found conversation_id=%s", conversation_id)
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)


@router.get("", response_model=ConversationListOut)
async def list_conversations(
    agent_key: str = Query(default=JULIA_KEY, min_length=1, max_length=64),
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_conversation_store_dep),
    agent_store=Depends(get_agent_store_dep),
    studio_store=Depends(get_studio_definition_store_dep),
) -> ConversationListOut:
    """Agent Studio §D6: filtered by agent, **default ``julia``** — Julia's
    page sends no filter and keeps seeing exactly her conversations."""
    if agent_key == JULIA_KEY:
        agent = _julia_agent(agent_store, ctx.org_id)
        if agent is None:  # never seeded for this org ⇒ she has no conversations
            return ConversationListOut(items=[], total=0)
    else:
        agent = _resolve_studio_agent(studio_store, ctx.org_id, agent_key)
    records = store.list_owned(ctx.org_id, ctx.user_id, agent_id=agent.id)
    items = [_conversation_out(r, agent.key) for r in records]
    return ConversationListOut(items=items, total=len(items))


@router.post("", response_model=ConversationOut, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreateRequest,
    ctx: AuthContext = Depends(require_member),
    agent_store=Depends(get_agent_store_dep),
    store=Depends(get_conversation_store_dep),
    studio_store=Depends(get_studio_definition_store_dep),
) -> ConversationOut:
    if payload.agent_key == JULIA_KEY:
        if payload.client_id is not None:
            raise _http(422, "invalid_client", "Clientes só existem para agentes do Studio.")
        agent_store.ensure_default_agents(ctx.org_id)
        agent = agent_store.get_by_key(ctx.org_id, JULIA_KEY)
        record = store.create(ctx.org_id, agent.id, ctx.user_id, titulo=payload.titulo)
        return _conversation_out(record, JULIA_KEY)

    # Agent Studio §D6: a studio conversation pins the ACTIVE version now (a
    # newer publish never moves it); with none yet, it pins at its first turn.
    agent = _resolve_studio_agent(studio_store, ctx.org_id, payload.agent_key)
    if payload.client_id is not None:
        # Scoped to THIS agent's clients: a foreign or unknown id is simply absent.
        client = next(
            (c for c in studio_store.list_clients(ctx.org_id, agent.id) if c.id == payload.client_id),
            None,
        )
        if client is None or not client.ativo:
            raise _http(422, "invalid_client", "Cliente inválido para este agente.")
    active = studio_store.get_active_version(ctx.org_id, agent.id)
    record = store.create(
        ctx.org_id, agent.id, ctx.user_id, titulo=payload.titulo,
        version_id=active.id if active is not None else None,
        client_id=payload.client_id,
    )
    return _conversation_out(record, agent.key)


@router.get("/{conversation_id}", response_model=ConversationOut)
async def get_conversation(
    conversation_id: UUID,
    ctx: AuthContext = Depends(require_member),
    store=Depends(get_conversation_store_dep),
    agent_store=Depends(get_agent_store_dep),
    studio_store=Depends(get_studio_definition_store_dep),
) -> ConversationOut:
    record = await _get_readable_conversation(ctx, conversation_id, store)
    return _conversation_out(
        record, _agent_key_for(ctx.org_id, record.agent_id, agent_store, studio_store)
    )


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
# Evaluated per request by slowapi — the admin override (Configurações do
# agente) applies without a restart; env `MESSAGES_RATE_LIMIT` is the default.
@limiter.limit(
    lambda: get_runtime_settings_service(settings).messages_rate_limit(), key_func=_caller_key
)
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
    bus=Depends(get_realtime_bus_dep),
    studio_store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> MessagePostResponse:
    try:
        conversation = conv_store.get_owned(ctx.org_id, conversation_id, ctx.user_id)
    except NotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND) from exc

    julia = _julia_agent(agent_store, ctx.org_id)
    studio_spec: AgentSpec | None = None
    if julia is not None and conversation.agent_id == julia.id:
        agent = julia
        if not agent.ativo:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"detail": "O agente Julia está desligado.", "code": "agent_off"},
            )
        capacity_text = (
            "A Julia está atendendo o número máximo de conversas "
            "agora. Tente novamente em instantes."
        )
    else:
        agent, studio_spec = _prepare_studio_turn(
            ctx.org_id, conversation, conv_store, studio_store, catalog
        )
        capacity_text = (
            f"O agente {agent.nome} está atendendo o número máximo de conversas "
            "agora. Tente novamente em instantes."
        )

    # Contract §E.11 "Route order", step 1: reserve a slot BEFORE the turn
    # lock and BEFORE persisting anything. A 429 here leaves zero trace —
    # no user message, no lock taken.
    slot = runtime.try_reserve()
    if slot is None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"detail": capacity_text, "code": "julia_capacidade"},
            headers={"Retry-After": "10"},
        )

    # Steps 2-4: acquire the turn lock, THEN persist the user message,
    # THEN start the task (fixes the orphan-message bug: the message used
    # to persist before the lock, so a 409 could leave an orphan user
    # message with no turn ever started for it). Any failure in this
    # block — including the 409 raised below — must release the slot;
    # once the lock is also held, it must be released too, since the
    # background task (the only OTHER thing that releases it) never got
    # to start.
    acquired = False
    try:
        acquired = conv_store.try_acquire_turn(
            ctx.org_id, conversation_id, INSTANCE_ID, settings.turn_lock_ttl_seconds
        )
        if not acquired:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={"detail": "Já existe um turno em andamento.", "code": "turn_in_progress"},
            )

        user_message = msg_store.add(ctx.org_id, conversation_id, "user", payload.texto)
        await publish_event(conversation_id, "message.new", _message_payload(user_message), bus=bus)

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
                bus=bus,
                slot=slot,
                spec=studio_spec,
            )
        )
        _track_background_task(request.app.state, task)
    except BaseException:
        # `BaseException`, not `Exception` — a cancelled request (the
        # client disconnecting mid-handler) must release the slot too;
        # cleanup-then-propagate is correct for a cancellation as well.
        if acquired:
            conv_store.release_turn(ctx.org_id, conversation_id, INSTANCE_ID)
        await slot.release()
        raise

    return MessagePostResponse(mensagem=_message_out(user_message), status="processando")


def _prepare_studio_turn(
    org_id: UUID, conversation: ConversationRecord, conv_store: Any, studio_store: Any, catalog: Any
) -> tuple[Any, AgentSpec]:
    """Agent Studio §D6/§E2: validate a studio turn and build its spec BEFORE
    the turn is accepted, so every refusal is a clean 409 with zero trace
    (no slot, no lock, no user message): ``agent_inactive``,
    ``no_active_version``, ``prompt_too_large``, ``client_inactive`` /
    ``invalid_client``. The spec (compiled once, stored once per hash) is
    what the background turn runs and stamps."""
    agent = _studio_agent_by_id(studio_store, org_id, conversation.agent_id)
    if agent is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    if not agent.ativo:
        raise _http(409, "agent_inactive", f"O agente {agent.nome} está desligado.")
    active = studio_store.get_active_version(org_id, agent.id)
    if active is None:
        raise _http(409, "no_active_version", f"O agente {agent.nome} não tem versão publicada.")
    if conversation.version_id is None:
        conversation = conv_store.pin_version(org_id, conversation.id, active.id)
    try:
        spec = build_studio_spec(agent, conversation, definitions=studio_store, catalog=catalog)
    except StudioSpecError as exc:
        raise _http(409, exc.code, exc.detail) from exc
    return agent, spec


def _apply_tool_event(
    blocks: list[dict[str, Any]], kind: str, payload: dict[str, Any]
) -> list[dict[str, Any]]:
    """Contract §E.7 ``ChatBlock`` (tool variant): ``{kind:"tool",
    toolUseId, name, status, resumo?}``.

    Every branch below builds a NEW block dict rather than mutating an
    existing one in place — an in-place ``block["status"] = ...`` would
    retroactively change every EARLIER published ``message.updated``
    payload too, since ``_message_payload``/``FakeMessageStore.
    update_blocks`` only ever shallow-copy the BLOCKS LIST, never the
    block dicts inside it, so an already-published snapshot would still
    hold a reference to the SAME dict object. (Found 2026-09-14, once
    ``message.updated`` was republished for the first time — the earlier
    revision never republished it, so the bug had no observable effect.)
    """
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
    # tool.finished — replace the matching block with a new dict; append
    # defensively if `tool.started` was somehow missed rather than
    # dropping the signal.
    resultado = payload.get("resultado", "ok")
    for i, block in enumerate(blocks):
        if block.get("kind") == "tool" and block.get("toolUseId") == tool_use_id:
            blocks[i] = {**block, "status": resultado}
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
    approvalId, resumo, diff?, decision}``.

    Revision 2026-09-14 (contract §E.3/§E.9): ``approval.requested`` now
    carries the real, persisted approval id (``payload["id"]`` — emitted
    from inside ``ApprovalBroker.request``'s ``on_created`` callback,
    AFTER the row is created). Correlation is therefore by ``approvalId``,
    NEVER by position — the earlier version had no id to correlate on and
    fell back to "the most recent pendente block", which silently mis-
    attributed a resolution whenever two escrita calls in the same message
    were ever concurrent rather than strictly sequential."""
    blocks = list(blocks)
    if kind == "approval.requested":
        blocks.append(
            {
                "kind": "approval",
                "approvalId": payload.get("id"),
                "resumo": payload.get("resumo"),
                "diff": payload.get("diff"),
                "decision": "pendente",
            }
        )
        return blocks
    # approval.resolved — replace with a new dict (see this module's other
    # mutation-safety note in `_apply_tool_event`).
    approval_id = payload.get("approval_id")
    decision = payload.get("decision", "pendente")
    for i, block in enumerate(blocks):
        if block.get("kind") == "approval" and block.get("approvalId") == approval_id:
            blocks[i] = {**block, "decision": decision}
            return blocks
    # Defensive: no matching block (should never happen given the fixed
    # §E.9 event order) — append rather than silently drop the signal.
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


async def _apply_and_publish_block_event(
    *,
    org_id: UUID,
    conversation_id: UUID,
    kind: str,
    evt_payload: dict[str, Any],
    current_message_id: UUID | None,
    current_blocks: list[dict[str, Any]],
    msg_store: Any,
    bus: Any,
    apply_fn: Any,
    stamp: dict[str, Any] | None = None,
) -> tuple[UUID, list[dict[str, Any]]]:
    """Contract §E.9 point 3 (revised): shared by ``tool.*`` and
    ``approval.*`` handling in ``_run_turn_background`` — both persist
    into the CURRENT assistant message's ``blocks`` (creating a placeholder
    ``message.new`` first if none exists yet), gain ``message_id`` on the
    published event, and are followed by a ``message.updated`` republish
    of the full row — in that fixture order: the granular event first,
    THEN ``message.updated``."""
    if current_message_id is None:
        record = msg_store.add(org_id, conversation_id, "assistant", "", blocks=[], **(stamp or {}))
        current_message_id = record.id
        current_blocks = []
        await publish_event(conversation_id, "message.new", _message_payload(record), bus=bus)

    evt_payload = {**evt_payload, "message_id": str(current_message_id)}
    current_blocks = apply_fn(current_blocks, kind, evt_payload)
    updated = msg_store.update_blocks(org_id, conversation_id, current_message_id, current_blocks)
    await publish_event(conversation_id, kind, evt_payload, bus=bus)
    await publish_event(conversation_id, "message.updated", _message_payload(updated), bus=bus)
    return current_message_id, current_blocks


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
    bus: Any,
    slot: Any,
    spec: AgentSpec | None = None,
) -> None:
    """Contract §E.9 "What the routes must do with a turn", points 2-6,
    wrapped per §E.11 "Route order" in a turn deadline
    (``asyncio.timeout(settings.turn_timeout_seconds)``).

    Every collaborator (``runtime`` / ``broker`` / ``build_spec`` / the
    three stores) is resolved by the caller (the route handler) via
    FastAPI ``Depends(...)`` and passed in explicitly — this function
    never calls a store factory itself, so it works identically against
    the real runtime (``app.runtime.claude_runtime.ClaudeAgentSdkRuntime``)
    and against G2's ``app.runtime.fake_runtime.FakeAgentRuntime`` over a
    test's own shared, stateful Fake store.

    ``slot`` is the :class:`~app.runtime.slots.TurnSlot` the route already
    reserved (contract §E.11) — this function's ``finally`` releases the
    turn lock FIRST, then the slot, on every exit path: normal
    completion, a runtime exception, the turn deadline, or task
    cancellation.

    Agent Studio §E2/§E4: ``spec`` is a studio agent's ALREADY-built spec
    (the route compiled it before accepting the turn); ``None`` keeps
    Julia's path — the active persona row through ``build_spec``. A studio
    spec's ``version_id`` + ``compiled_hash`` are stamped on every
    assistant message this turn persists."""
    current_message_id: UUID | None = None
    current_blocks: list[dict[str, Any]] = []
    stamp: dict[str, Any] = (
        {"version_id": spec.version_id, "compiled_hash": spec.compiled_hash}
        if spec is not None and spec.toolset == "studio"
        else {}
    )

    try:
        async with asyncio.timeout(settings.turn_timeout_seconds):
            conversation = conv_store.get_owned(org_id, conversation_id, owner_user_id)
            if spec is None:
                persona = persona_store.get_active(org_id, agent_id)
                spec = build_spec(persona)
            turn_ctx = TurnContext(
                org_id=org_id,
                conversation_id=conversation_id,
                requested_by=owner_user_id,
                instance_id=INSTANCE_ID,
                sdk_session_id=conversation.sdk_session_id,
            )

            # Contract §E.3 canonical fixture — bookends the turn's
            # `session.status` transitions the same way the failure branch
            # below bookends `erro`: the runtime only ever yields its OWN
            # final status (it has no reason to know the turn is starting
            # before it starts), so the route publishes the opening
            # "pensando" itself. Ephemeral — never persisted, same as
            # `message.delta`.
            await publish_event(conversation_id, "session.status", {"status": "pensando"}, bus=bus)

            async for event in runtime.run_turn(spec, turn_ctx, prompt, broker, slot=slot):
                kind = event["event"]
                evt_payload = event["payload"]

                if kind == "message.new":
                    record = msg_store.add(
                        org_id, conversation_id, "assistant", evt_payload.get("texto", ""),
                        blocks=[], **stamp,
                    )
                    current_message_id = record.id
                    current_blocks = []
                    await publish_event(
                        conversation_id, "message.new", _message_payload(record), bus=bus
                    )
                elif kind == "message.delta":
                    # Contract §E.9 point 4: published only, never persisted.
                    await publish_event(conversation_id, "message.delta", evt_payload, bus=bus)
                elif kind in ("tool.started", "tool.finished"):
                    current_message_id, current_blocks = await _apply_and_publish_block_event(
                        org_id=org_id,
                        conversation_id=conversation_id,
                        kind=kind,
                        evt_payload=evt_payload,
                        current_message_id=current_message_id,
                        current_blocks=current_blocks,
                        msg_store=msg_store,
                        bus=bus,
                        apply_fn=_apply_tool_event,
                        stamp=stamp,
                    )
                elif kind in ("approval.requested", "approval.resolved"):
                    current_message_id, current_blocks = await _apply_and_publish_block_event(
                        org_id=org_id,
                        conversation_id=conversation_id,
                        kind=kind,
                        evt_payload=evt_payload,
                        current_message_id=current_message_id,
                        current_blocks=current_blocks,
                        msg_store=msg_store,
                        bus=bus,
                        apply_fn=_apply_approval_event,
                        stamp=stamp,
                    )
                elif kind == "session.resume_fallback":
                    # Contract §E.9 "Resume after a restart" — a distinct
                    # `system` message, deliberately NOT threaded through the
                    # assistant-message block accumulator above (it isn't a
                    # tool/approval block, and it must render as its own
                    # message per the fixed PT-BR text).
                    system_record = msg_store.add(
                        org_id, conversation_id, "system", evt_payload.get("texto", "")
                    )
                    await publish_event(
                        conversation_id, "message.new", _message_payload(system_record), bus=bus
                    )
                elif kind == "session.status":
                    sdk_session_id = evt_payload.get("sdk_session_id")
                    await publish_event(conversation_id, "session.status", evt_payload, bus=bus)
                    if sdk_session_id:
                        # Canonical fixture: `conversation.upsert` follows the
                        # terminal `session.status` — the route re-publishes
                        # the conversation row it just persisted so list views
                        # pick up the new `sdk_session_id` live, without a
                        # refetch.
                        updated_conv = conv_store.set_sdk_session_id(
                            org_id, conversation_id, sdk_session_id
                        )
                        await publish_event(
                            conversation_id,
                            "conversation.upsert",
                            _conversation_payload(updated_conv),
                            bus=bus,
                        )
                elif kind == "conversation.upsert":
                    await publish_event(conversation_id, "conversation.upsert", evt_payload, bus=bus)
                else:
                    logger.warning(
                        "agents.turn.unknown_event org_id=%s conversation_id=%s kind=%s",
                        org_id, conversation_id, kind,
                    )
    except TimeoutError:
        # Contract §E.11 "Route order" — the turn exceeded
        # `settings.turn_timeout_seconds`. Generic PT-BR message, no
        # exception text (same posture as the generic-failure branch
        # below): `asyncio.timeout` cancels whatever the runtime was
        # awaiting and raises `TimeoutError` here, so this is reached for
        # a genuinely stuck turn regardless of where inside `run_turn`
        # it was stuck.
        logger.error(
            "agents.turn.deadline_exceeded org_id=%s conversation_id=%s timeout_s=%s",
            org_id, conversation_id, settings.turn_timeout_seconds,
        )
        try:
            msg_store.add(org_id, conversation_id, "system", "O turno excedeu o tempo limite.")
            await publish_event(
                conversation_id, "session.status", {"status": "erro"}, bus=bus
            )
        except Exception:
            logger.exception(
                "agents.turn.deadline_reporting_failed org_id=%s conversation_id=%s",
                org_id, conversation_id,
            )
    except Exception:
        # Contract §E.9 point 6 — generic message, NEVER exception text.
        logger.exception(
            "agents.turn.failed org_id=%s conversation_id=%s", org_id, conversation_id
        )
        try:
            msg_store.add(org_id, conversation_id, "system", "O turno falhou.")
            await publish_event(
                conversation_id, "session.status", {"status": "erro"}, bus=bus
            )
        except Exception:
            logger.exception(
                "agents.turn.failure_reporting_failed org_id=%s conversation_id=%s",
                org_id, conversation_id,
            )
    finally:
        # Contract §E.11 "Route order": the turn lock releases FIRST,
        # THEN the slot — on every exit path (this `finally` runs for
        # normal completion, the deadline branch above, the generic
        # failure branch above, AND a bare task cancellation that skips
        # both `except` clauses entirely).
        conv_store.release_turn(org_id, conversation_id, INSTANCE_ID)
        await slot.release()


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
