"""``/api/channels`` — the product-to-product turn API (Lais contract §3).

A CHANNEL TRANSPORT (social-wiring, over WhatsApp) drives an ``llm`` studio
agent with a minted ``pk_*`` product token:

* ``POST /api/channels/turns`` (``agents:channel-turn``) — run one turn for a
  channel conversation (a debounced batch of the lead's messages in, the reply
  bubbles + actions out);
* ``GET /api/channels/agents/{agent_key}/status`` (``agents:channel-status``) —
  link health;
* ``DELETE /api/channels/conversations`` (``agents:channel-turn``) — deletion on
  request (LGPD, §10.1 M5).

Trust model (§10.1 M1): ``org_id`` comes ONLY from the token; ``agent_key`` is
resolved INSIDE that org and the token must be bound to that very agent
(``principal_agent_id``); the issuer is read from the STORED token row. Errors
are ``HTTPException(detail={"detail", "code"})`` (agents' flat shape; the seed
passes it through). A lead never sees error details (L2): messages here are
fixed strings, provider text is never echoed.

The turn is a SYNCHRONOUS hop (one inbound batch → one turn, bounded by
``channel_turn_timeout_seconds``). Order of refusals — every one BEFORE the
lead's text is persisted: agent resolution (404/403) → idempotency replay /
conflict (409) → ``agent_inactive`` / ``no_active_version`` / ``prompt_too_large``
(409) → org key + budget preflight (424 / 429) → capacity slot (429) → turn lock
(409 ``turn_in_progress``).
"""
# NOTE: deliberately NO `from __future__ import annotations` (same reason as
# conversations_router): FastAPI must resolve the body/dependency types eagerly.

import asyncio
import hashlib
import logging
from typing import Any, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.channels.bubbles import split_into_bubbles
from app.channels.retention import ChannelRetention
from app.channels.tools import HandoffCollector
from app.config import settings
from app.dependencies import (
    get_channel_inbound_store_dep,
    get_channel_llm_runtime_dep,
    get_channel_retention_dep,
    get_conversation_store_dep,
    get_handoff_collector_dep,
    get_message_store_dep,
    get_org_llm_key_resolver_dep,
    get_realtime_bus_dep,
    require_channel_status,
    require_channel_turn,
)
from app.realtime import publish_event
from app.routers.conversations_router import (
    INSTANCE_ID,
    _apply_and_publish_block_event,
    _apply_tool_event,
    _conversation_payload,
    _llm_http,
    _message_payload,
)
from app.routers.studio_agents_router import (
    get_knowledge_catalog_dep,
    get_studio_definition_store_dep,
)
from app.runtime.errors import LlmRuntimeError
from app.runtime.llm_runtime import service_principal_id
from app.runtime.types import TurnContext
from app.schemas.channels import (
    ChannelAgentStatusOut,
    ChannelDeleteRequest,
    ChannelTurnRequest,
    ChannelTurnResponse,
)
from app.stores.channel_inbound import ChannelInboundRecord
from app.stores.errors import Conflict, NotFound
from app.studio.spec import StudioSpecError, StudioTurnTarget, build_studio_spec
from noctusai_lib.api.auth.session import AuthContext

logger = logging.getLogger(__name__)

__all__ = ["router", "CHANNEL_STUDIO_RUNTIME"]

#: Only an agent on the provider-neutral runtime is reachable from a channel.
CHANNEL_STUDIO_RUNTIME = "llm"

_UPSTREAM_DETAIL = "O assistente não conseguiu responder agora."


class _ChannelRoute(APIRoute):
    """422 in agents' error shape: a body that fails validation answers
    ``{"detail", "code": "invalid_field"}`` (contract §3.1), not the seed's
    generic envelope. Auth dependencies still win (they raise first)."""

    def get_route_handler(self) -> Callable:
        original = super().get_route_handler()

        async def _handler(request: Request) -> Response:
            try:
                return await original(request)
            except RequestValidationError as exc:
                fields = sorted({".".join(str(p) for p in e["loc"][1:]) or "body" for e in exc.errors()})
                raise _err(422, "invalid_field", "Campo inválido: " + ", ".join(fields)) from exc

        return _handler


router = APIRouter(prefix="/api/channels", tags=["channels"], route_class=_ChannelRoute)


def _err(status_code: int, code: str, detail: str, *, headers: dict[str, str] | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"detail": detail, "code": code}, headers=headers)


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── agent resolution (M1) ───────────────────────────────────────────────────


def _resolve_channel_agent(studio_store: Any, ctx: AuthContext, agent_key: str) -> Any:
    """The ``llm`` studio agent ``agent_key`` of THIS token's org that THIS token
    is bound to. Anything else is a 404 ``agent_not_found`` (a channel token
    cannot probe legacy / claude_sdk / dev-advisor agents) or 403
    ``agent_not_allowed`` (a real agent the token was not minted for)."""
    try:
        agent = studio_store.get_agent(ctx.org_id, agent_key)
    except NotFound as exc:
        raise _err(404, "agent_not_found", "Agente não encontrado.") from exc
    if (
        agent.definition_mode != "studio"
        or agent.runtime != CHANNEL_STUDIO_RUNTIME
        or getattr(agent, "kind", "runtime") != "runtime"
    ):
        raise _err(404, "agent_not_found", "Agente não encontrado.")
    if ctx.principal_agent_id is None or ctx.principal_agent_id != agent.id:
        raise _err(403, "agent_not_allowed", "O token não pertence a este agente.")
    return agent


# ── idempotency (M2) ────────────────────────────────────────────────────────


class _BatchPlan:
    """What an inbound batch needs, given what the ledger already knows."""

    def __init__(self, replay: dict[str, Any] | None, new: list[Any]) -> None:
        self.replay = replay  # the stored reply, when the whole batch is a replay
        self.new = new  # messages not yet persisted


def _plan_batch(
    known: dict[str, ChannelInboundRecord], batch: list[Any], conversation_id: UUID | None
) -> _BatchPlan:
    """Classify the batch against the ledger. A known id whose text differs, or
    that belongs to another conversation, is a 409 ``idempotency_conflict``.
    Every message known AND replied ⇒ replay the stored reply (no second turn).
    Otherwise only the unknown messages are persisted; known-but-unreplied ones
    (a turn that failed after persisting) are re-run without re-persisting."""
    new: list[Any] = []
    for msg in batch:
        rec = known.get(msg.provider_message_id)
        if rec is None:
            new.append(msg)
            continue
        if rec.texto_sha256 != _sha(msg.texto) or conversation_id is None or rec.conversation_id != conversation_id:
            raise _err(
                409, "idempotency_conflict",
                "Este provider_message_id já foi recebido com outro conteúdo.",
            )
    if not new and all(known[m.provider_message_id].reply is not None for m in batch):
        return _BatchPlan(replay=known[batch[0].provider_message_id].reply, new=[])
    return _BatchPlan(replay=None, new=new)


# ── POST /api/channels/turns ────────────────────────────────────────────────


@router.post("/turns", response_model=ChannelTurnResponse)
async def run_channel_turn(
    payload: ChannelTurnRequest,
    ctx: AuthContext = Depends(require_channel_turn),
    studio_store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
    conv_store=Depends(get_conversation_store_dep),
    msg_store=Depends(get_message_store_dep),
    inbound=Depends(get_channel_inbound_store_dep),
    bus=Depends(get_realtime_bus_dep),
    runtime: Any = Depends(get_channel_llm_runtime_dep),
    collector: HandoffCollector = Depends(get_handoff_collector_dep),
) -> ChannelTurnResponse:
    org_id = ctx.org_id
    agent = _resolve_channel_agent(studio_store, ctx, payload.agent_key)
    channel_ref = payload.channel_ref.canonical()
    connection_id = payload.channel_ref.connection_id
    batch = list(payload.messages)
    ids = [m.provider_message_id for m in batch]

    existing = conv_store.find_channel(org_id, agent.id, payload.channel, channel_ref)

    # 1. Replay / conflict, before any gate: a stored reply is returned even if
    #    the agent has since been switched off — the model never runs twice.
    plan = _plan_batch(inbound.find(org_id, connection_id, ids), batch, existing.id if existing else None)
    if plan.replay is not None:
        return ChannelTurnResponse(**plan.replay)

    # 2. The agent must be publishable BEFORE anything is persisted.
    if not agent.ativo:
        raise _err(409, "agent_inactive", "O agente está desligado.")
    active = studio_store.get_active_version(org_id, agent.id)
    if active is None:
        raise _err(409, "no_active_version", "O agente não tem versão publicada.")
    # A channel conversation always runs the CURRENT active version (a lead chat
    # lasts months; the owner's tuning must reach it) — the version is stamped on
    # every assistant message it produces, like any studio turn.
    try:
        spec = build_studio_spec(
            agent, StudioTurnTarget(org_id=org_id, version_id=active.id),
            definitions=studio_store, catalog=catalog,
        )
    except StudioSpecError as exc:
        raise _err(409, exc.code, exc.detail) from exc

    # 3. Org key + budget (424 / 429) and capacity (429) — zero trace.
    try:
        await runtime.preflight(spec.provider, org_id)
    except LlmRuntimeError as exc:
        raise _llm_http(exc) from exc
    slot = runtime.try_reserve()
    if slot is None:
        raise _err(
            429, "capacidade", "Capacidade esgotada. Tente novamente em instantes.",
            headers={"Retry-After": "10"},
        ) from None

    conversation = None
    acquired = False
    try:
        conversation = existing or conv_store.create_channel(
            org_id, agent.id, payload.channel, channel_ref,
            payload.contact.model_dump(), version_id=active.id,
        )
        acquired = conv_store.try_acquire_turn(
            org_id, conversation.id, INSTANCE_ID, settings.turn_lock_ttl_seconds
        )
        if not acquired:
            raise _err(409, "turn_in_progress", "Já existe um turno em andamento.")

        # Authoritative idempotency check, UNDER the lock.
        plan = _plan_batch(inbound.find(org_id, connection_id, ids), batch, conversation.id)
        if plan.replay is not None:
            return ChannelTurnResponse(**plan.replay)

        conv_store.touch_activity(org_id, conversation.id, contact=payload.contact.model_dump())
        for msg in plan.new:
            record = msg_store.add(org_id, conversation.id, "user", msg.texto)
            try:
                inbound.add(org_id, connection_id, conversation.id, msg.provider_message_id, _sha(msg.texto))
            except Conflict as exc:
                raise _err(409, "turn_in_progress", "Já existe um turno em andamento.") from exc
            await publish_event(conversation.id, "message.new", _message_payload(record), bus=bus)

        response = await _drive_turn(
            spec=spec, agent=agent, conversation_id=conversation.id, org_id=org_id,
            runtime=runtime, slot=slot, collector=collector, msg_store=msg_store, bus=bus,
            conv_store=conv_store,
        )
        inbound.set_reply(org_id, connection_id, ids, response.model_dump(mode="json"))
        return response
    finally:
        if acquired and conversation is not None:
            conv_store.release_turn(org_id, conversation.id, INSTANCE_ID)
        await slot.release()


async def _drive_turn(
    *, spec: Any, agent: Any, conversation_id: UUID, org_id: UUID, runtime: Any, slot: Any,
    collector: HandoffCollector, msg_store: Any, bus: Any, conv_store: Any,
) -> ChannelTurnResponse:
    """Run the model over the persisted history, persist + publish what it
    produces and shape the §3.1 response. Every failure is a typed, lead-safe
    HTTP error (424/429/502); provider text is logged, never returned."""
    stamp = {"version_id": spec.version_id, "compiled_hash": spec.compiled_hash}
    ctx = TurnContext(
        org_id=org_id, conversation_id=conversation_id,
        requested_by=service_principal_id(agent.id), instance_id=INSTANCE_ID, sdk_session_id=None,
    )
    texts: list[str] = []
    current_message_id: UUID | None = None
    current_blocks: list[dict[str, Any]] = []
    usage: dict[str, Any] = {}
    collector.take(conversation_id)  # a stale entry from an aborted earlier turn is not this turn's

    try:
        async with asyncio.timeout(settings.channel_turn_timeout_seconds):
            await publish_event(conversation_id, "session.status", {"status": "pensando"}, bus=bus)
            # `prompt=""`: the whole batch is already stored as user rows (the
            # runtime then neither drops nor appends one).
            async for event in runtime.run_turn(spec, ctx, "", None, slot=slot):
                kind, evt = event["event"], event["payload"]
                if kind == "message.new":
                    record = msg_store.add(
                        org_id, conversation_id, "assistant", evt.get("texto", ""), blocks=[], **stamp
                    )
                    current_message_id, current_blocks = record.id, []
                    texts.append(evt.get("texto", ""))
                    await publish_event(conversation_id, "message.new", _message_payload(record), bus=bus)
                elif kind in ("tool.started", "tool.finished"):
                    current_message_id, current_blocks = await _apply_and_publish_block_event(
                        org_id=org_id, conversation_id=conversation_id, kind=kind, evt_payload=evt,
                        current_message_id=current_message_id, current_blocks=current_blocks,
                        msg_store=msg_store, bus=bus, apply_fn=_apply_tool_event, stamp=stamp,
                    )
                elif kind == "session.status":
                    usage = {k: evt.get(k) for k in ("custo_usd", "tokens_entrada", "tokens_saida")}
                    if current_message_id is None and usage.get("custo_usd"):
                        # A silent turn still SPENT money: keep it on the books
                        # (the daily cap sums `custo_usd`); an empty assistant row
                        # is skipped by the model's history.
                        record = msg_store.add(org_id, conversation_id, "assistant", "", blocks=[], **stamp)
                        current_message_id = record.id
                    if current_message_id is not None and any(v is not None for v in usage.values()):
                        msg_store.set_turn_cost(
                            org_id, conversation_id, current_message_id,
                            custo_usd=usage.get("custo_usd"),
                            tokens_entrada=usage.get("tokens_entrada"),
                            tokens_saida=usage.get("tokens_saida"),
                        )
                    await publish_event(conversation_id, "session.status", evt, bus=bus)
                else:
                    logger.warning(
                        "agents.channel.turn.unknown_event org_id=%s conversation_id=%s kind=%s",
                        org_id, conversation_id, kind,
                    )
    except LlmRuntimeError as exc:
        logger.warning(
            "agents.channel.turn.refused org_id=%s conversation_id=%s code=%s cause=%s",
            org_id, conversation_id, exc.code, getattr(exc, "cause_text", ""),
        )
        await _publish_error(conversation_id, bus)
        raise _llm_http(exc) from exc
    except TimeoutError as exc:
        logger.error(
            "agents.channel.turn.deadline_exceeded org_id=%s conversation_id=%s timeout_s=%s",
            org_id, conversation_id, settings.channel_turn_timeout_seconds,
        )
        await _publish_error(conversation_id, bus)
        raise _err(502, "llm_upstream", _UPSTREAM_DETAIL) from exc
    except Exception as exc:
        logger.exception(
            "agents.channel.turn.failed org_id=%s conversation_id=%s", org_id, conversation_id
        )
        await _publish_error(conversation_id, bus)
        raise _err(502, "llm_upstream", _UPSTREAM_DETAIL) from exc

    handoffs = collector.take(conversation_id)
    partes = split_into_bubbles("\n\n".join(t for t in texts if t and t.strip()))
    actions = [{"type": "handoff", "motivo": motivo} for motivo in handoffs[:1]]
    if actions:
        turn_status = "handoff"
    elif partes:
        turn_status = "respondido"
    else:
        turn_status = "silencio"
    try:
        updated = conv_store.get(org_id, conversation_id)
        await publish_event(conversation_id, "conversation.upsert", _conversation_payload(updated), bus=bus)
    except NotFound:  # pragma: no cover — the row vanished (a purge raced the turn)
        logger.warning("agents.channel.turn.conversation_gone conversation_id=%s", conversation_id)
    return ChannelTurnResponse(
        conversation_id=conversation_id,
        reply={"partes": partes},
        actions=actions,
        status=turn_status,
        usage={
            "custo_usd": usage.get("custo_usd"),
            "tokens_entrada": usage.get("tokens_entrada"),
            "tokens_saida": usage.get("tokens_saida"),
        },
    )


async def _publish_error(conversation_id: UUID, bus: Any) -> None:
    try:
        await publish_event(conversation_id, "session.status", {"status": "erro"}, bus=bus)
    except Exception:
        logger.exception("agents.channel.turn.error_publish_failed conversation_id=%s", conversation_id)


# ── GET /api/channels/agents/{agent_key}/status ─────────────────────────────


@router.get("/agents/{agent_key}/status", response_model=ChannelAgentStatusOut)
async def channel_agent_status(
    agent_key: str,
    ctx: AuthContext = Depends(require_channel_status),
    studio_store=Depends(get_studio_definition_store_dep),
    key_resolver=Depends(get_org_llm_key_resolver_dep),
) -> ChannelAgentStatusOut:
    agent = _resolve_channel_agent(studio_store, ctx, agent_key)
    active = studio_store.get_active_version(ctx.org_id, agent.id)
    # With no published version the key check follows the draft the owner is
    # about to publish; the response still reports provider/model as null.
    basis = active or studio_store.get_draft(ctx.org_id, agent.id)
    configured = bool(basis is not None and key_resolver(basis.provider, ctx.org_id))
    return ChannelAgentStatusOut(
        agent_key=agent.key,
        nome=agent.nome,
        ativo=agent.ativo,
        versao_ativa=active.versao if active else None,
        provider=active.provider if active else None,
        model=active.model if active else None,
        llm_configurado=configured,
    )


# ── DELETE /api/channels/conversations (deletion on request, LGPD) ──────────


@router.delete("/conversations", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel_conversation(
    payload: ChannelDeleteRequest,
    ctx: AuthContext = Depends(require_channel_turn),
    studio_store=Depends(get_studio_definition_store_dep),
    conv_store=Depends(get_conversation_store_dep),
    retention: ChannelRetention = Depends(get_channel_retention_dep),
) -> Response:
    """"Apagar meus dados": erase the conversation's messages, idempotency rows
    and contact (one transaction). Idempotent — 204 whether or not a
    conversation existed, so the call neither leaks existence nor fails a retry.
    A running turn blocks it (409 ``turn_in_progress``): erasing under a live
    turn would orphan the rows the turn is about to write."""
    agent = _resolve_channel_agent(studio_store, ctx, payload.agent_key)
    conversation = conv_store.find_channel(
        ctx.org_id, agent.id, payload.channel, payload.channel_ref.canonical()
    )
    if conversation is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    if not conv_store.try_acquire_turn(
        ctx.org_id, conversation.id, INSTANCE_ID, settings.turn_lock_ttl_seconds
    ):
        raise _err(409, "turn_in_progress", "Já existe um turno em andamento.")
    try:
        deleted = retention.delete_conversation(ctx.org_id, conversation.id)
    except BaseException:
        conv_store.release_turn(ctx.org_id, conversation.id, INSTANCE_ID)
        raise
    if not deleted:
        # Raced a purge: nothing left to erase (and the lock row is gone with it).
        logger.info("agents.channel.deletion_noop org_id=%s", ctx.org_id)
    else:
        logger.info(
            "agents.channel.conversation_deleted org_id=%s conversation_id=%s",
            ctx.org_id, conversation.id,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
