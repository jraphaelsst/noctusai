"""``/api/channels`` — the product-to-product turn API (Lais contract §3; Julia v2 CONTRACT §8).

A CHANNEL TRANSPORT (social-wiring, over WhatsApp) drives a platform-defined ``llm`` studio agent (Julia) with
a minted ``pk_*`` product token:

* ``POST /api/channels/turns`` (``agents:channel-turn``) — run one turn for a lead's thread (a debounced batch
  of the lead's messages, or a re-engagement trigger, in; the reply bubbles + actions + the computed
  qualification out);
* ``GET /api/channels/agents/{agent_key}/status`` (``agents:channel-status``) — link health, mode, readiness;
* ``DELETE /api/channels/conversations`` (``agents:channel-turn``) — deletion of one thread (pre-v2 alias of
  delete-by-lead, which lives in ``channel_threads_router``);
* ``POST /api/channels/threads/{id}/resumo`` (+ the ``/conversations/{id}/resumo`` alias) — narrative summary;
* ``POST /api/channels/agents/{agent_key}/decisoes/{chave}`` — a transport-side choice decided by the rule of
  the agent version's decision row (``agent_version_decisoes``, D13).

**Turn v2** (CONTRACT §5.2 / §8.1). The agent is the platform DEFINITION resolved for the token's org
(``resolve_agent_for_org``: the platform version + the org's specs); the controls (``ligado`` / ``drenando`` /
``desligado``, the per-thread pause) are applied UNDER THE TURN LOCK before the lead's text is persisted or any
model is called (``aplicar_controles``); a non-``normal`` status answers without a reply. Every assistant
message is stamped with the version tuple (definition version, compiled hash, org-specs hash, skill versions).

Trust model (§10.1 M1): ``org_id`` comes ONLY from the token; ``agent_key`` is resolved INSIDE that org and the
token must be bound to that very agent (``principal_agent_id``); the issuer is read from the STORED token row.
Errors are ``HTTPException(detail={"detail", "code"})``. A lead never sees error details (L2): messages here are
fixed strings, provider text is never echoed; nothing a prompt or a rule says ever appears in a response.

Order of refusals — every one BEFORE the lead's text is persisted: agent resolution (404/403) → idempotency
replay / conflict (409) → ``no_active_version`` / ``qualificacao_indisponivel`` / ``conteudo_incompleto`` /
``prompt_too_large`` (409) → org key + budget preflight (424 / 429) → capacity slot (429) → turn lock
(409 ``turn_in_progress``) → controls (503 ``controle_indisponivel`` fails closed).
"""
# NOTE: deliberately NO `from __future__ import annotations` (same reason as
# conversations_router): FastAPI must resolve the body/dependency types eagerly.

import asyncio
import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import UUID
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.routing import APIRoute

from app.channels import extracao
from app.channels import turno as turno_mod
from app.channels.bubbles import split_into_bubbles
from app.channels.controles import ControleIndisponivel, LeadIdentidade, aplicar_controles
from app.channels.retention import ChannelRetention
from app.config import settings
from app.dependencies import (
    get_channel_inbound_store_dep,
    get_channel_llm_runtime_dep,
    get_channel_retention_dep,
    get_conformidade_store_dep,
    get_conversation_store_dep,
    get_julia_tools_client_dep,
    get_message_store_dep,
    get_org_llm_key_resolver_dep,
    get_realtime_bus_dep,
    get_skills_factory_dep,
    require_channel_status,
    require_channel_turn,
)
from app.qualificacao.service import QualificacaoService
from app.realtime import publish_event
from app.routers.channel_threads_router import get_agent_controle_store_dep, get_thread_store_dep
from app.routers.conversations_router import INSTANCE_ID, _conversation_payload, _llm_http
from app.routers.qualificacao_router import (
    get_identificacao_service_dep,
    get_padrao_store_dep,
    get_qualificacao_service_dep,
)
from app.routers.studio_agents_router import (
    get_knowledge_catalog_dep,
    get_studio_definition_store_dep,
)
from app.runtime.errors import LlmRuntimeError, LlmUpstreamError
from app.schemas.channels import (
    DECISAO_CHAVE_PATTERN,
    EstagioOut,
    ChannelAgentStatusOut,
    ChannelDecisaoRequest,
    ChannelDecisaoResponse,
    ChannelDeleteRequest,
    ChannelResumoRequest,
    ChannelResumoResponse,
    ChannelTurnRequest,
    ChannelTurnResponse,
    ChannelUsoOut,
)
from app.stores.channel_inbound import ChannelInboundRecord
from app.stores.errors import Conflict, NotFound
from app.studio.julia import canonical_channel_agent_key
from app.studio.resolucao import compile_for_org, resolve_agent_for_org
from noctusai_lib.api.auth.session import AuthContext

logger = logging.getLogger(__name__)

__all__ = ["router", "CHANNEL_STUDIO_RUNTIME", "get_qualificacao_service_dep"]

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
                if any("contexto_grande" in str(e.get("msg", "")) for e in exc.errors()):
                    raise _err(422, "contexto_grande", "O contexto passa do limite de tamanho.") from exc
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
    """The ``llm`` studio agent ``agent_key`` of THIS token's org (its INSTANCE, for a platform-defined key)
    that THIS token is bound to. Anything else is a 404 ``agent_not_found`` (a channel token cannot probe
    legacy / claude_sdk / dev-advisor agents) or 403 ``agent_not_allowed`` (a real agent the token was not
    minted for)."""
    agent_key = canonical_channel_agent_key(agent_key)
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
    if batch and not new and all(known[m.provider_message_id].reply is not None for m in batch):
        return _BatchPlan(replay=known[batch[0].provider_message_id].reply, new=[])
    return _BatchPlan(replay=None, new=new)


def _lead_identidade(payload: ChannelTurnRequest) -> LeadIdentidade:
    """The turn's lead. A v1-shaped request (no ``lead``) is keyed by its channel identity for one release."""
    ref = payload.channel_ref
    contato = {
        k: v for k, v in (("nome", payload.contact.display_name), ("telefone_e164", payload.contact.phone_e164))
        if v
    } or None
    if payload.lead is not None:
        return LeadIdentidade(ref=payload.lead.ref, crm_lead_id=payload.lead.crm_lead_id, contato=contato)
    return LeadIdentidade(ref=f"{ref.connection_id}:{ref.chat_id}", contato=contato)


def _persistir_lote(
    *, org_id: UUID, thread: Any, plan: _BatchPlan, connection_id: UUID, msg_store: Any, inbound: Any,
    conv_store: Any,
) -> list[Any]:
    """Store the batch's NEW messages in the shared thread (the lead's ``user`` rows) and book them in the
    idempotency ledger; the thread's last-LEAD-message clock (the drain-idle clock) moves."""
    records = []
    for msg in plan.new:
        records.append(msg_store.add(org_id, thread.id, "user", msg.texto, lead_ref_id=thread.lead_ref_id))
        try:
            inbound.add(org_id, connection_id, thread.id, msg.provider_message_id, _sha(msg.texto))
        except Conflict as exc:
            raise _err(409, "turn_in_progress", "Já existe um turno em andamento.") from exc
    if records:
        conv_store.touch_lead_message(org_id, thread.id)
    return records


def _resposta_sem_turno(
    status_: str, thread: Any, agent: Any, participante: Any, violacoes: list[Any] | None = None,
) -> ChannelTurnResponse:
    return ChannelTurnResponse(
        thread_id=thread.id if thread is not None else None,
        conversation_id=thread.id if thread is not None else None,
        status=status_, reply={"partes": []}, actions=[],
        participante={"agent_key": agent.key, "estado": participante.estado} if participante is not None else None,
        conformidade={"violacoes": [
            {"regra": v.regra, "politica": v.politica, "bloqueada": v.bloqueada} for v in (violacoes or [])]},
    )


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
    threads=Depends(get_thread_store_dep),
    controles=Depends(get_agent_controle_store_dep),
    conformidade=Depends(get_conformidade_store_dep),
    qual: QualificacaoService = Depends(get_qualificacao_service_dep),
    padroes=Depends(get_padrao_store_dep),
    ident=Depends(get_identificacao_service_dep),
    sw=Depends(get_julia_tools_client_dep),
    skills_factory=Depends(get_skills_factory_dep),
) -> ChannelTurnResponse:
    org_id = ctx.org_id
    agent = _resolve_channel_agent(studio_store, ctx, payload.agent_key)
    channel_ref = payload.channel_ref.canonical()
    connection_id = payload.channel_ref.connection_id
    batch = list(payload.messages)
    ids = [m.provider_message_id for m in batch]
    svc = turno_mod.ServicosCanal(
        studio_store=studio_store, catalog=catalog, conversations=conv_store, messages=msg_store, threads=threads,
        controles=controles, conformidade=conformidade, qual=qual, padroes=padroes, ident=ident, sw=sw,
        skills_factory=skills_factory,
    )

    existing = conv_store.find_thread(org_id, payload.channel, channel_ref)

    # 1. Replay / conflict, before any gate: a stored reply is returned even if the agent has since been
    #    switched off — the model never runs twice.
    plan = _plan_batch(inbound.find(org_id, connection_id, ids), batch, existing.id if existing else None)
    if plan.replay is not None:
        return ChannelTurnResponse(**plan.replay)

    # 2. The agent must be publishable BEFORE anything is persisted — unless it is off (it will not run).
    try:
        controle = controles.get(org_id, agent.id)
    except Exception as exc:
        logger.exception("agents.channel.turn.controle_ilegivel org_id=%s", org_id)
        raise ControleIndisponivel().as_http_exception() from exc
    prep = None
    slot = None
    if controle.modo != "desligado":
        try:
            prep = turno_mod.preparar(svc, org_id, agent)
        except turno_mod.TurnoRecusado as exc:
            raise _err(exc.status, exc.codigo, exc.detalhe) from exc
        # 3. Org key + budget (424 / 429) and capacity (429) — zero trace.
        try:
            await runtime.preflight(prep.spec.provider, org_id)
        except LlmRuntimeError as exc:
            raise _llm_http(exc) from exc
        slot = runtime.try_reserve()
        if slot is None:
            raise _err(
                429, "capacidade", "Capacidade esgotada. Tente novamente em instantes.",
                headers={"Retry-After": "10"},
            ) from None

    thread = None
    acquired = False
    try:
        if existing is not None:
            thread = existing
            acquired = conv_store.try_acquire_turn(org_id, thread.id, INSTANCE_ID, settings.turn_lock_ttl_seconds)
            if not acquired:
                raise _err(409, "turn_in_progress", "Já existe um turno em andamento.")
            # Authoritative idempotency check, UNDER the lock.
            plan = _plan_batch(inbound.find(org_id, connection_id, ids), batch, thread.id)
            if plan.replay is not None:
                return ChannelTurnResponse(**plan.replay)

        # 4. The controls, under the lock, BEFORE the text is stored or a model is called (fail closed).
        agora = datetime.now(timezone.utc)
        try:
            ctl = aplicar_controles(
                org_id=org_id, agent_id=agent.id, gatilho=payload.gatilho, channel=payload.channel,
                channel_ref=channel_ref, controles=controles, conversations=conv_store, threads=threads,
                lead=_lead_identidade(payload), contact=payload.contact.model_dump(mode="json"),
                version_id=prep.r.versao.id if prep is not None else None, messages=msg_store, agora=agora,
            )
        except ControleIndisponivel as exc:
            raise exc.as_http_exception() from exc
        if ctl.thread is not None and thread is None:  # a brand-new thread: lock it now
            thread = ctl.thread
            acquired = conv_store.try_acquire_turn(org_id, thread.id, INSTANCE_ID, settings.turn_lock_ttl_seconds)
            if not acquired:
                raise _err(409, "turn_in_progress", "Já existe um turno em andamento.")
        thread = ctl.thread if ctl.thread is not None else thread
        ultima_antes = existing.ultima_mensagem_lead_em if existing is not None else None

        # Non-normal status: store what the decision says, answer without a reply.
        if not ctl.prosseguir:
            if thread is not None and ctl.decisao.persistir_inbound and plan.new:
                novos = _persistir_lote(
                    org_id=org_id, thread=thread, plan=plan, connection_id=connection_id,
                    msg_store=msg_store, inbound=inbound, conv_store=conv_store)
                for rec in novos:
                    await publish_event(thread.id, "message.new", turno_mod.mensagem_publica(rec), bus=bus)
            resp = _resposta_sem_turno(ctl.status, thread, agent, ctl.participante)
            if thread is not None and ids:
                inbound.set_reply(org_id, connection_id, ids, resp.model_dump(mode="json"))
            return resp

        if prep is None:  # the control flipped on between the peek and the lock: refuse, retry re-evaluates
            raise _err(409, "turn_in_progress", "Já existe um turno em andamento.")

        novos = _persistir_lote(
            org_id=org_id, thread=thread, plan=plan, connection_id=connection_id, msg_store=msg_store,
            inbound=inbound, conv_store=conv_store)
        for rec in novos:
            await publish_event(thread.id, "message.new", turno_mod.mensagem_publica(rec), bus=bus)

        # 5. Abuse limits, in data, under the lock.
        if payload.gatilho == "mensagem":
            tripped = turno_mod.limite_atingido(svc, org_id, thread.id, agent.id, agora)
            if tripped is not None:
                logger.warning("agents.channel.turn.limite_atingido org_id=%s limite=%s", org_id, tripped)
                resp = _resposta_sem_turno("limite_atingido", thread, agent, ctl.participante)
                if ids:
                    inbound.set_reply(org_id, connection_id, ids, resp.model_dump(mode="json"))
                return resp

        lote_lead = [m.texto for m in batch]
        ultima = max((m.at for m in batch), default=None) if batch else ultima_antes
        try:
            resultado = await turno_mod.executar(
                svc=svc, prep=prep, agent=agent, org_id=org_id, thread=thread, runtime=runtime, slot=slot, bus=bus,
                contexto=payload.contexto, gatilho=payload.gatilho, lote_lead=lote_lead,
                ultima_resposta_em=ultima, agora=agora,
            )
        except LlmRuntimeError as exc:
            logger.warning(
                "agents.channel.turn.refused org_id=%s thread_id=%s code=%s cause=%s",
                org_id, thread.id, exc.code, getattr(exc, "cause_text", ""),
            )
            await _publish_error(thread.id, bus)
            raise _llm_http(exc) from exc
        except turno_mod.TurnoRecusado as exc:
            await _publish_error(thread.id, bus)
            raise _err(exc.status, exc.codigo, exc.detalhe) from exc
        except TimeoutError as exc:
            logger.error(
                "agents.channel.turn.deadline_exceeded org_id=%s thread_id=%s timeout_s=%s",
                org_id, thread.id, settings.channel_turn_timeout_seconds,
            )
            await _publish_error(thread.id, bus)
            raise _err(502, "llm_upstream", _UPSTREAM_DETAIL) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("agents.channel.turn.failed org_id=%s thread_id=%s", org_id, thread.id)
            await _publish_error(thread.id, bus)
            raise _err(502, "llm_upstream", _UPSTREAM_DETAIL) from exc

        await publish_event(thread.id, "session.status", {"status": "ociosa"}, bus=bus)
        try:
            await publish_event(
                thread.id, "conversation.upsert", _conversation_payload(conv_store.get(org_id, thread.id)), bus=bus)
        except NotFound:  # pragma: no cover — the row vanished (a purge raced the turn)
            logger.warning("agents.channel.turn.conversation_gone thread_id=%s", thread.id)
        response = ChannelTurnResponse(
            thread_id=thread.id, conversation_id=thread.id, status=resultado.status,
            reply={"partes": split_into_bubbles(resultado.partes_texto)}, actions=resultado.actions,
            participante=(
                {"agent_key": agent.key, "estado": resultado.participante_estado}
                if resultado.participante_estado else None),
            qualificacao=resultado.qualificacao,
            conformidade={"violacoes": [
                {"regra": v.regra, "politica": v.politica, "bloqueada": v.bloqueada} for v in resultado.violacoes]},
            usage={
                "custo_usd": resultado.usage.get("custo_usd"),
                "tokens_entrada": resultado.usage.get("tokens_entrada"),
                "tokens_saida": resultado.usage.get("tokens_saida"),
            },
        )
        if ids:
            inbound.set_reply(org_id, connection_id, ids, response.model_dump(mode="json"))
        return response
    finally:
        if acquired and thread is not None:
            conv_store.release_turn(org_id, thread.id, INSTANCE_ID)
        if slot is not None:
            await slot.release()


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
    catalog=Depends(get_knowledge_catalog_dep),
    key_resolver=Depends(get_org_llm_key_resolver_dep),
    controles=Depends(get_agent_controle_store_dep),
    threads=Depends(get_thread_store_dep),
    conformidade=Depends(get_conformidade_store_dep),
    qual: QualificacaoService = Depends(get_qualificacao_service_dep),
    padroes=Depends(get_padrao_store_dep),
) -> ChannelAgentStatusOut:
    agent = _resolve_channel_agent(studio_store, ctx, agent_key)
    r = resolve_agent_for_org(studio_store, ctx.org_id, agent.key)
    active = r.versao
    # With no published version the key check follows the draft the owner is about to publish; the
    # response still reports provider/model as null.
    basis = active or studio_store.get_draft(r.definicao.org_id, r.definicao.id)
    configured = bool(basis is not None and key_resolver(basis.provider, ctx.org_id))
    controle = controles.get(ctx.org_id, agent.id)
    svc = turno_mod.ServicosCanal(
        studio_store=studio_store, catalog=catalog, conversations=None, messages=None, threads=threads,
        controles=controles, conformidade=conformidade, qual=qual, padroes=padroes, ident=None, sw=None,
    )
    return ChannelAgentStatusOut(
        agent_key=agent.key,
        nome=agent.nome,
        ativo=agent.ativo,
        versao_ativa=active.versao if active else None,
        provider=active.provider if active else None,
        model=active.model if active else None,
        llm_configurado=configured,
        modo=controle.modo,
        aceita_novos_leads=controle.aceita_novos_leads,
        threads_abertas=len(threads.list_abertos(ctx.org_id, agent.id)),
        conteudo_completo=turno_mod.conteudo_completo(svc, ctx.org_id, agent),
    )


# ── GET /api/channels/agents/{agent_key}/qualificacao/estagios ──────────────


@router.get("/agents/{agent_key}/qualificacao/estagios", response_model=list[EstagioOut])
async def channel_agent_estagios(
    agent_key: str,
    ctx: AuthContext = Depends(require_channel_status),
    studio_store=Depends(get_studio_definition_store_dep),
    padroes=Depends(get_padrao_store_dep),
) -> list[EstagioOut]:
    """The ordered stages of the standard THIS agent runs for THIS org (the pinned version of the active agent
    version, else the newest published): ``[{chave, rotulo, ordem, conclusivo}]`` and nothing else, for a
    consumer's stage dropdown and its "this stage or beyond" comparator."""
    agent = _resolve_channel_agent(studio_store, ctx, agent_key)
    r = resolve_agent_for_org(studio_store, ctx.org_id, agent.key)
    if r.versao is None:
        raise _err(409, "no_active_version", "O agente não tem versão publicada.")
    svc = turno_mod.ServicosCanal(
        studio_store=studio_store, catalog=None, conversations=None, messages=None, threads=None,
        controles=None, conformidade=None, qual=None, padroes=padroes, ident=None, sw=None,
    )
    try:
        padrao = turno_mod.padrao_do_turno(svc, r)
    except turno_mod.TurnoRecusado as exc:
        raise _err(exc.status, exc.codigo, exc.detalhe) from exc
    return [
        EstagioOut(chave=e.chave, rotulo=e.rotulo, ordem=e.ordem, conclusivo=e.conclusivo)
        for e in sorted(padrao.estagios, key=lambda x: (x.ordem, x.chave))
    ]


# ── GET /api/channels/uso (Lais Painel: month usage vs the daily cap) ───────

_SP = ZoneInfo("America/Sao_Paulo")


def _month_window_utc(mes: str) -> tuple[datetime, datetime]:
    """``YYYY-MM`` -> ``[start, end)`` as UTC instants, month edges taken in
    America/Sao_Paulo (a turn at 23:30 SP on the 31st is still that month)."""
    try:
        year, month = (int(p) for p in mes.split("-"))
        start = datetime(year, month, 1, tzinfo=_SP)
    except (ValueError, TypeError) as exc:
        raise _err(422, "invalid_field", "Campo inválido: mes") from exc
    end = datetime(year + (month == 12), month % 12 + 1, 1, tzinfo=_SP)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


@router.get("/uso", response_model=ChannelUsoOut)
async def channel_usage(
    mes: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
    ctx: AuthContext = Depends(require_channel_turn),
    msg_store=Depends(get_message_store_dep),
) -> ChannelUsoOut:
    since, until = _month_window_utc(mes)
    turnos, custo = msg_store.usage_between(ctx.org_id, since, until)
    return ChannelUsoOut(
        turnos=turnos,
        custo_usd=round(custo, 6),
        limite_diario_usd=float(settings.channel_daily_budget_usd),
    )


# ── DELETE /api/channels/conversations (deletion of one thread; pre-v2 alias) ──


@router.delete("/conversations", status_code=status.HTTP_204_NO_CONTENT)
async def delete_channel_conversation(
    payload: ChannelDeleteRequest,
    ctx: AuthContext = Depends(require_channel_turn),
    studio_store=Depends(get_studio_definition_store_dep),
    conv_store=Depends(get_conversation_store_dep),
    retention: ChannelRetention = Depends(get_channel_retention_dep),
) -> Response:
    """"Apagar meus dados" for ONE thread: erase its messages, idempotency rows and contact (one
    transaction). Idempotent — 204 whether or not a thread existed, so the call neither leaks existence
    nor fails a retry. A running turn blocks it (409 ``turn_in_progress``): erasing under a live turn would
    orphan the rows the turn is about to write. Delete-by-LEAD (``DELETE /leads/{ref}``) is the v2 call."""
    _resolve_channel_agent(studio_store, ctx, payload.agent_key)
    conversation = conv_store.find_thread(ctx.org_id, payload.channel, payload.channel_ref.canonical())
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


# ── POST /api/channels/threads/{thread_id}/resumo ───────────────────────────

#: How many of the thread's most recent stored messages a summary reads.
RESUMO_HISTORY_LIMIT = 200


def _conteudo_da_versao_ativa(studio_store: Any, catalog: Any, org_id: UUID, agent: Any):
    """``(resolved agent, content bundle)`` of the agent's active definition version, compiled for the org."""
    r = resolve_agent_for_org(studio_store, org_id, agent.key)
    if r.versao is None:
        raise _err(409, "no_active_version", "O agente não tem versão publicada.")
    conteudo = compile_for_org(studio_store, catalog, r).conteudo
    if conteudo is None:
        raise _err(409, "conteudo_incompleto", "O conteúdo do agente está incompleto.")
    return r, conteudo


async def _resumir(
    conversation_id: UUID,
    payload: ChannelResumoRequest,
    ctx: AuthContext,
    studio_store: Any,
    catalog: Any,
    conv_store: Any,
    msg_store: Any,
    threads: Any,
    runtime: Any,
) -> ChannelResumoResponse:
    org_id = ctx.org_id
    try:
        conversation = conv_store.get(org_id, conversation_id)
    except NotFound as exc:
        raise _err(404, "conversation_not_found", "Conversa não encontrada.") from exc
    if conversation.channel is None or ctx.principal_agent_id is None:
        raise _err(404, "conversation_not_found", "Conversa não encontrada.")
    agent = next((a for a in studio_store.list_agents(org_id) if a.id == ctx.principal_agent_id), None)
    if (
        agent is None
        or agent.runtime != CHANNEL_STUDIO_RUNTIME
        or not (conversation.agent_id == agent.id or threads.get_participante(org_id, conversation_id, agent.id))
    ):
        raise _err(404, "conversation_not_found", "Conversa não encontrada.")
    r, conteudo = _conteudo_da_versao_ativa(studio_store, catalog, org_id, agent)
    active = r.versao

    try:
        await runtime.preflight(active.provider, org_id)
    except LlmRuntimeError as exc:
        raise _llm_http(exc) from exc
    slot = runtime.try_reserve()
    if slot is None:
        raise _err(
            429, "capacidade", "Capacidade esgotada. Tente novamente em instantes.",
            headers={"Retry-After": "10"},
        ) from None
    try:
        records = list(msg_store.list(org_id, conversation_id, limite=RESUMO_HISTORY_LIMIT))
        try:
            system, user = extracao.montar_resumo_pedido(conteudo, records, payload.desde)
            tool = extracao.resumo_tool(conteudo)
        except extracao.ConteudoIncompleto as exc:
            raise _err(409, "conteudo_incompleto", "O conteúdo do agente está incompleto.") from exc
        try:
            async with asyncio.timeout(settings.channel_turn_timeout_seconds):
                raw, usage = await runtime.structured_extract(
                    provider=active.provider, model=active.model, org_id=org_id,
                    system=system, user=user, tool=tool,
                )
            shaped = extracao.shape_resumo(raw)
        except LlmRuntimeError as exc:
            logger.warning(
                "agents.channel.resumo.refused org_id=%s conversation_id=%s code=%s cause=%s",
                org_id, conversation_id, exc.code, getattr(exc, "cause_text", ""),
            )
            raise _llm_http(exc) from exc
        except (TimeoutError, ValueError) as exc:
            logger.error(
                "agents.channel.resumo.failed org_id=%s conversation_id=%s cause=%s",
                org_id, conversation_id, type(exc).__name__,
            )
            raise _err(502, "llm_upstream", _UPSTREAM_DETAIL) from exc
        except HTTPException:
            raise
        except Exception as exc:
            logger.exception("agents.channel.resumo.failed org_id=%s conversation_id=%s", org_id, conversation_id)
            raise _err(502, "llm_upstream", _UPSTREAM_DETAIL) from exc
        if usage.cost_usd:
            # Book the spend (the daily cap sums `custo_usd`): an empty assistant row is skipped by the model's history.
            row = msg_store.add(
                org_id, conversation_id, "assistant", "", blocks=[], agent_id=agent.id,
                version_id=active.id, compiled_hash=getattr(active, "compiled_hash", None),
            )
            msg_store.set_turn_cost(
                org_id, conversation_id, row.id, custo_usd=usage.cost_usd,
                tokens_entrada=usage.prompt_tokens, tokens_saida=usage.completion_tokens,
            )
        return ChannelResumoResponse(
            **shaped,
            usage={
                "custo_usd": usage.cost_usd,
                "tokens_entrada": usage.prompt_tokens,
                "tokens_saida": usage.completion_tokens,
            },
        )
    finally:
        await slot.release()


@router.post("/threads/{thread_id}/resumo", response_model=ChannelResumoResponse)
async def summarize_channel_thread(
    thread_id: UUID,
    payload: ChannelResumoRequest,
    ctx: AuthContext = Depends(require_channel_turn),
    studio_store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
    conv_store=Depends(get_conversation_store_dep),
    msg_store=Depends(get_message_store_dep),
    threads=Depends(get_thread_store_dep),
    runtime: Any = Depends(get_channel_llm_runtime_dep),
) -> ChannelResumoResponse:
    """Narrative summary of a lead's thread (episode close). Same trust model as ``/turns``: org from the
    token only; the thread must be one THIS token's agent takes part in (anything else is a 404
    ``conversation_not_found`` — no existence oracle). The org's own key runs it (B1), it counts toward the
    org daily cap (booked on an empty assistant row, like a silent turn), errors are as ``/turns``. The
    criteria come from the qualification records, never from this call."""
    return await _resumir(thread_id, payload, ctx, studio_store, catalog, conv_store, msg_store, threads, runtime)


@router.post("/conversations/{conversation_id}/resumo", response_model=ChannelResumoResponse)
async def summarize_channel_conversation(
    conversation_id: UUID,
    payload: ChannelResumoRequest,
    ctx: AuthContext = Depends(require_channel_turn),
    studio_store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
    conv_store=Depends(get_conversation_store_dep),
    msg_store=Depends(get_message_store_dep),
    threads=Depends(get_thread_store_dep),
    runtime: Any = Depends(get_channel_llm_runtime_dep),
) -> ChannelResumoResponse:
    """Pre-v2 alias of ``/threads/{id}/resumo`` (one release)."""
    return await _resumir(conversation_id, payload, ctx, studio_store, catalog, conv_store, msg_store, threads, runtime)


# ── POST /api/channels/agents/{agent_key}/decisoes/{chave} ──────────────────


@router.post("/agents/{agent_key}/decisoes/{chave}", response_model=ChannelDecisaoResponse)
async def decide_channel_choice(
    agent_key: str,
    chave: str,
    payload: ChannelDecisaoRequest,
    ctx: AuthContext = Depends(require_channel_turn),
    studio_store=Depends(get_studio_definition_store_dep),
    catalog=Depends(get_knowledge_catalog_dep),
    runtime: Any = Depends(get_channel_llm_runtime_dep),
) -> ChannelDecisaoResponse:
    """One structured choice among ``opcoes`` by the rule of the agent version's decision row
    (``agent_version_decisoes.chave``, D13). A row with no rule text, or a model that cannot decide, answers
    the option the row flags ``padrao`` (``regra='padrao_da_versao'``): the fallback is DATA, never a rule
    the caller carries. Same trust model + error taxonomy as ``/resumo``; a budget / key failure is still
    424 / 429 (nothing is guessed there)."""
    if not re.fullmatch(DECISAO_CHAVE_PATTERN, chave):
        raise _err(422, "invalid_field", "Campo inválido: chave")
    org_id = ctx.org_id
    agent = _resolve_channel_agent(studio_store, ctx, agent_key)
    r, conteudo = _conteudo_da_versao_ativa(studio_store, catalog, org_id, agent)
    active = r.versao
    row = next((d for d in studio_store.list_decisoes(r.definicao.org_id, active.id) if d.chave == chave), None)
    if row is None:
        raise _err(404, "decisao_nao_encontrada", "Decisão não encontrada.")
    por_valor = {o["valor"]: o for o in row.opcoes}
    efetivas = [o for o in payload.opcoes if o in por_valor]
    if len(efetivas) < 2:
        raise _err(422, "invalid_field", "Campo inválido: opcoes")
    padrao = next((o["valor"] for o in row.opcoes if o.get("padrao") and o["valor"] in efetivas), efetivas[0])
    usage_zero = {"custo_usd": None, "tokens_entrada": None, "tokens_saida": None}
    if not (row.regra or "").strip():
        return ChannelDecisaoResponse(escolha=padrao, motivo="", regra="padrao_da_versao", usage=usage_zero)

    try:
        await runtime.preflight(active.provider, org_id)
    except LlmRuntimeError as exc:
        raise _llm_http(exc) from exc
    slot = runtime.try_reserve()
    if slot is None:
        raise _err(
            429, "capacidade", "Capacidade esgotada. Tente novamente em instantes.",
            headers={"Retry-After": "10"},
        ) from None
    try:
        try:
            system, user = extracao.montar_escolha_pedido(conteudo, row.regra.strip(), efetivas, payload.dados)
            tool = extracao.escolha_tool(conteudo, efetivas)
        except extracao.ConteudoIncompleto as exc:
            raise _err(409, "conteudo_incompleto", "O conteúdo do agente está incompleto.") from exc
        try:
            async with asyncio.timeout(settings.channel_turn_timeout_seconds):
                raw, usage = await runtime.structured_extract(
                    provider=active.provider, model=active.model, org_id=org_id,
                    system=system, user=user, tool=tool,
                )
            escolha = raw.get("escolha")
            if escolha not in efetivas:
                raise ValueError("escolha fora das opcoes")
        except LlmUpstreamError as exc:
            # The provider is down / answered nothing usable: the row's `padrao` option answers (a lead is
            # never held up by an outage; the owner picked that default).
            logger.warning(
                "agents.channel.decisao.upstream org_id=%s chave=%s cause=%s", org_id, chave, getattr(exc, "cause_text", ""))
            return ChannelDecisaoResponse(escolha=padrao, motivo="", regra="padrao_da_versao", usage=usage_zero)
        except LlmRuntimeError as exc:
            logger.warning(
                "agents.channel.decisao.refused org_id=%s chave=%s code=%s cause=%s",
                org_id, chave, exc.code, getattr(exc, "cause_text", ""),
            )
            raise _llm_http(exc) from exc
        except (TimeoutError, ValueError, AttributeError) as exc:
            logger.error("agents.channel.decisao.failed org_id=%s chave=%s cause=%s", org_id, chave, type(exc).__name__)
            return ChannelDecisaoResponse(escolha=padrao, motivo="", regra="padrao_da_versao", usage=usage_zero)
        except HTTPException:
            raise
        except Exception:
            logger.exception("agents.channel.decisao.failed org_id=%s chave=%s", org_id, chave)
            return ChannelDecisaoResponse(escolha=padrao, motivo="", regra="padrao_da_versao", usage=usage_zero)
        motivo = raw.get("motivo") if isinstance(raw.get("motivo"), str) else ""
        motivo = " ".join(extracao.redigir_contatos(motivo).split())[: extracao.ESCOLHA_MOTIVO_MAX]
        # NOC-REMEDIATE[agents-decisao-custo]: this call has no channel conversation yet, so its cost is not booked
        # on a message row and does not count toward the org daily cap (`msg_store.usage_between`); it is returned
        # in `usage` and logged here. Book it once an org-level usage ledger exists (one small extraction per
        # Meta lead today) -- 2026-10-19
        logger.info(
            "agents.channel.decisao org_id=%s chave=%s escolha=%s custo_usd=%s", org_id, chave, escolha, usage.cost_usd,
        )
        return ChannelDecisaoResponse(
            escolha=escolha, motivo=motivo, regra="versao",
            usage={
                "custo_usd": usage.cost_usd,
                "tokens_entrada": usage.prompt_tokens,
                "tokens_saida": usage.completion_tokens,
            },
        )
    finally:
        await slot.release()
