"""The shared lead thread + the agent controls API (Julia v2, contract §5 / §6 / §8.2).

Two audiences, one service layer (:mod:`app.channels.thread_service`,
:mod:`app.channels.controles`):

* **social-wiring** (a ``pk_*`` channel token bound to the agent, org from the token only):

  * ``GET    /api/channels/threads`` (``?channel=&connection_id=&chat_id=`` or ``?lead_ref=``)
    and ``GET /api/channels/threads/{thread_id}`` (``agents:channel-status``) — the thread,
    its participants and their states;
  * ``POST   /api/channels/threads/{thread_id}/mensagens`` (``agents:channel-turn``) — append the
    lead's / a human attendant's message WITHOUT a turn (idempotent through ``channel_inbound``);
  * ``PATCH  /api/channels/threads/{thread_id}/participantes/{agent_key}`` (``agents:channel-turn``)
    — the per-conversation on/off (pause / resume), the actor recorded;
  * ``GET    /api/channels/agents/{agent_key}/controle`` (``agents:channel-status``) — the agent's
    mode + the drain progress (read-only for SW: SW never decides the mode);
  * ``DELETE /api/channels/leads/{ref}`` (``agents:channel-turn``) — LGPD delete-by-lead across
    every agent (§6.4), idempotent.

* **Agents Studio** (the signed-in user's JWT):

  * ``GET /api/studio/agents/{agent_key}/controle`` (member) and ``PUT`` (admin) — the
    ligado / drenando / desligado switch + the drain idle days;
  * ``PATCH /api/studio/threads/{thread_id}/participantes/{agent_key}`` (admin) — Studio's
    per-thread pause / resume.

The TURN endpoint (``POST /api/channels/turns``) lives in ``channels_router`` and calls
:func:`app.channels.controles.aplicar_controles` under the turn lock — the controls are decided there,
never cached in SW (fail closed, D6).
"""
# NOTE: deliberately NO `from __future__ import annotations` (same reason as
# channels_router): FastAPI must resolve the body/dependency types eagerly.

import logging
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.channels.retention import ChannelRetention
from app.channels.thread_service import (
    IdempotencyConflict,
    MensagemEntrada,
    TransicaoInvalida,
    alterar_estado_humano,
    anexar_mensagens,
    apagar_lead,
    progresso_dreno,
)
from app.config import settings
from app.dependencies import (
    get_channel_inbound_store_dep,
    get_channel_retention_dep,
    get_conversation_store_dep,
    get_message_store_dep,
    get_org_llm_key_resolver_dep,
    get_realtime_bus_dep,
    require_admin,
    require_channel_status,
    require_channel_turn,
    require_member,
)
from app.realtime import publish_event
from app.routers.conversations_router import INSTANCE_ID, _message_payload
from app.routers.studio_agents_router import get_knowledge_catalog_dep, get_studio_definition_store_dep
from app.schemas.channel_threads import (
    ControleOut,
    ControleUpdateRequest,
    DrenagemOut,
    HandoffAceiteRequest,
    HandoffDestinoOut,
    HandoffOut,
    LeadConsentOut,
    MensagemThreadOut,
    OptInRequest,
    OptOutOut,
    OptOutRequest,
    ParticipanteEstadoRequest,
    ParticipanteOut,
    StudioParticipanteEstadoRequest,
    ThreadMensagemOut,
    ThreadMensagemRequest,
    ThreadOut,
)
from app.schemas.channels import ChannelRef
from app.stores._util import utcnow
from app.stores.agent_controles import get_agent_controle_store
from app.stores.errors import Conflict, NotFound, TurnInProgress
from app.stores.threads import OutroAgenteAtivo, get_thread_store, mapa_agentes
from app.studio.resolucao import conteudo_status, resolve_agent_for_org
from noctusai_lib.api.auth.session import AuthContext

logger = logging.getLogger(__name__)

__all__ = ["router", "get_thread_store_dep", "get_agent_controle_store_dep"]

#: Only an agent on the provider-neutral runtime has the channel controls (same rule as the turn API).
_CHANNEL_RUNTIME = "llm"

router = APIRouter(tags=["channel-threads"])


# ── dependency seams (overridden in tests — never patched) ──────────────────


def get_thread_store_dep():
    return get_thread_store(settings)


def get_agent_controle_store_dep():
    return get_agent_controle_store(settings)


def _err(status_code: int, code: str, detail: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"detail": detail, "code": code})


# ── agent / thread resolution ───────────────────────────────────────────────


def _canal_agent(agent: Any) -> bool:
    return (
        agent.definition_mode == "studio"
        and agent.runtime == _CHANNEL_RUNTIME
        and getattr(agent, "kind", "runtime") == "runtime"
    )


def _agente_por_chave(studio_store: Any, org_id: UUID, agent_key: str) -> Any:
    """The ``llm`` studio agent ``agent_key`` of THIS org; anything else is a 404 (no probing)."""
    try:
        agent = studio_store.get_agent(org_id, agent_key)
    except NotFound as exc:
        raise _err(404, "agent_not_found", "Agente não encontrado.") from exc
    if not _canal_agent(agent):
        raise _err(404, "agent_not_found", "Agente não encontrado.")
    return agent


def _agente_do_token(studio_store: Any, ctx: AuthContext, agent_key: str) -> Any:
    """:func:`_agente_por_chave`, and the token must be bound to that very agent (403 otherwise)."""
    agent = _agente_por_chave(studio_store, ctx.org_id, agent_key)
    if ctx.principal_agent_id is None or ctx.principal_agent_id != agent.id:
        raise _err(403, "agent_not_allowed", "O token não pertence a este agente.")
    return agent


def _thread_do_token(ctx: AuthContext, conv_store: Any, threads: Any, thread_id: UUID) -> Any:
    """The thread, if it exists in this org and the token's agent takes part in it (or opened it).
    Anything else is a 404 ``thread_not_found`` — no existence oracle across agents or orgs."""
    try:
        thread = conv_store.get(ctx.org_id, thread_id)
    except NotFound as exc:
        raise _err(404, "thread_not_found", "Conversa não encontrada.") from exc
    if thread.tipo != "thread_lead" or ctx.principal_agent_id is None:
        raise _err(404, "thread_not_found", "Conversa não encontrada.")
    participa = threads.get_participante(ctx.org_id, thread.id, ctx.principal_agent_id) is not None
    if not participa and thread.agent_id != ctx.principal_agent_id:
        raise _err(404, "thread_not_found", "Conversa não encontrada.")
    return thread


def _handoff_out(handoff: Any, agentes: dict, lead_externa: str | None) -> HandoffOut:
    para = handoff.para
    return HandoffOut(
        id=handoff.id, thread_id=handoff.thread_id, lead_ref=lead_externa,
        de_agent_key=agentes.get(handoff.de_agent_id, ("", ""))[0],
        para=HandoffDestinoOut(
            tipo=para.tipo, agent_key=agentes.get(para.agent_id, ("", ""))[0] if para.agent_id else None,
            user_id=para.user_id, papel=para.papel,
        ),
        motivo_codigo=handoff.motivo_codigo, resumo=handoff.resumo, perfil=handoff.perfil,
        identificacao_completa=handoff.identificacao_completa,
        identificacao_mascarada=handoff.identificacao_mascarada, perguntas_abertas=handoff.perguntas_abertas,
        compromissos=handoff.compromissos, created_at=handoff.created_at,
        aceito_em=handoff.aceito_em, aceito_por=handoff.aceito_por,
    )


def _supressao(lead: Any, propria: Any, agora: datetime) -> str | None:
    """Why SW must not send scheduled follow-ups (``None`` = it may). Mirrors the decision table: a
    re-engagement runs only for an ACTIVE participant (a timed pause that ran out counts as active)."""
    if lead is not None and lead.opt_out_ativo:
        return "opt_out"
    if propria is None:
        return "sem_participacao"
    if propria.estado == "pausado" and propria.pausado_ate is not None and agora >= propria.pausado_ate:
        return None
    return None if propria.estado == "ativo" else propria.estado


def _thread_out(
    org_id: UUID, thread: Any, threads: Any, studio_store: Any, *, agent_id: UUID | None = None
) -> ThreadOut:
    agentes = mapa_agentes(studio_store, org_id)
    participantes = threads.list_participantes(org_id, thread.id)
    lead = threads.get_lead_ref(org_id, thread.lead_ref_id) if thread.lead_ref_id else None
    turnos = [p.ultimo_turno_em for p in participantes if p.ultimo_turno_em is not None]
    propria = next((p for p in participantes if p.agent_id == agent_id), None) if agent_id else None
    motivo = _supressao(lead, propria, utcnow()) if agent_id else ("opt_out" if lead is not None and lead.opt_out_ativo else None)
    ultimo = threads.ultimo_handoff(org_id, thread.id)
    return ThreadOut(
        thread_id=thread.id,
        channel=thread.channel or "",
        lead_ref=lead.ref_externa if lead is not None else None,
        participantes=[
            ParticipanteOut(
                agent_key=agentes.get(p.agent_id, ("", ""))[0], agent_nome=agentes.get(p.agent_id, ("", ""))[1],
                estado=p.estado, entrou_em=p.entrou_em, saiu_em=p.saiu_em, motivo=p.motivo,
                ultimo_turno_em=p.ultimo_turno_em, pausado_ate=p.pausado_ate,
            )
            for p in participantes
        ],
        ultimo_turno_em=max(turnos) if turnos else None,
        ultima_mensagem_lead_em=thread.ultima_mensagem_lead_em,
        criado_em=thread.created_at,
        opt_in_em=lead.opt_in_em if lead else None,
        opt_in_origem=lead.opt_in_origem if lead else None,
        opt_out_em=lead.opt_out_em if lead else None,
        reengajamento_suprimido=motivo is not None,
        reengajamento_suprimido_motivo=motivo,
        ultimo_handoff=_handoff_out(ultimo, agentes, lead.ref_externa if lead else None) if ultimo else None,
    )


def _participante_out(org_id: UUID, agent: Any, rec: Any) -> ParticipanteOut:
    return ParticipanteOut(
        agent_key=agent.key, agent_nome=agent.nome, estado=rec.estado, entrou_em=rec.entrou_em,
        saiu_em=rec.saiu_em, motivo=rec.motivo, ultimo_turno_em=rec.ultimo_turno_em, pausado_ate=rec.pausado_ate,
    )


def _validar_ate(estado: str, ate: datetime | None) -> None:
    """``ate`` (pause until) only makes sense on a pause, and must be in the future."""
    if ate is None:
        return
    if estado != "pausado" or ate <= utcnow():
        raise _err(422, "invalid_field", "Campo inválido: ate")


def _estado_http(exc: Exception) -> HTTPException:
    """The store / service errors of a participant change as agents' flat error shape."""
    if isinstance(exc, NotFound):
        return _err(404, "participante_not_found", "O agente não participa desta conversa.")
    if isinstance(exc, TransicaoInvalida):
        return _err(409, "transicao_invalida", f"Não é possível mudar de {exc.de} para {exc.para}.")
    if isinstance(exc, OutroAgenteAtivo):
        return _err(409, "outro_agente_ativo", "Outro agente está ativo nesta conversa.")
    raise exc  # pragma: no cover — only the three above are raised by alterar_estado_humano


# ── GET /api/channels/threads[/{id}] ────────────────────────────────────────


@router.get("/api/channels/threads", response_model=ThreadOut)
async def find_thread(
    channel: str | None = Query(default=None, min_length=1, max_length=64),
    connection_id: UUID | None = Query(default=None),
    chat_id: str | None = Query(default=None, min_length=1, max_length=256),
    lead_ref: str | None = Query(default=None, min_length=1, max_length=256),
    ctx: AuthContext = Depends(require_channel_status),
    studio_store=Depends(get_studio_definition_store_dep),
    conv_store=Depends(get_conversation_store_dep),
    threads=Depends(get_thread_store_dep),
) -> ThreadOut:
    """Look a thread up by its channel identity (``channel`` + ``connection_id`` + ``chat_id``) or by
    the lead (``lead_ref`` = SW ``julia_contatos.id``; the most recently active thread of the lead the
    token's agent takes part in)."""
    by_channel = channel is not None and connection_id is not None and chat_id is not None
    if by_channel == (lead_ref is not None):
        raise _err(422, "invalid_field", "Informe channel+connection_id+chat_id OU lead_ref.")
    found = None
    if by_channel:
        found = conv_store.find_thread(
            ctx.org_id, channel, ChannelRef(connection_id=connection_id, chat_id=chat_id).canonical()
        )
    else:
        lead = threads.get_lead_ref_by_externa(ctx.org_id, lead_ref)
        if lead is not None:
            candidates = conv_store.list_threads_for_lead(ctx.org_id, lead.id)
            candidates.sort(key=lambda t: t.last_message_at or t.created_at, reverse=True)
            found = candidates[0] if candidates else None
    if found is None:
        raise _err(404, "thread_not_found", "Conversa não encontrada.")
    thread = _thread_do_token(ctx, conv_store, threads, found.id)
    return _thread_out(ctx.org_id, thread, threads, studio_store, agent_id=ctx.principal_agent_id)


@router.get("/api/channels/threads/{thread_id}", response_model=ThreadOut)
async def get_thread(
    thread_id: UUID,
    ctx: AuthContext = Depends(require_channel_status),
    studio_store=Depends(get_studio_definition_store_dep),
    conv_store=Depends(get_conversation_store_dep),
    threads=Depends(get_thread_store_dep),
) -> ThreadOut:
    thread = _thread_do_token(ctx, conv_store, threads, thread_id)
    return _thread_out(ctx.org_id, thread, threads, studio_store, agent_id=ctx.principal_agent_id)


# ── POST /api/channels/threads/{id}/mensagens ───────────────────────────────


@router.post("/api/channels/threads/{thread_id}/mensagens", response_model=ThreadMensagemOut)
async def append_thread_message(
    thread_id: UUID,
    payload: ThreadMensagemRequest,
    ctx: AuthContext = Depends(require_channel_turn),
    conv_store=Depends(get_conversation_store_dep),
    msg_store=Depends(get_message_store_dep),
    inbound=Depends(get_channel_inbound_store_dep),
    threads=Depends(get_thread_store_dep),
    bus=Depends(get_realtime_bus_dep),
) -> ThreadMensagemOut:
    """Append one message to the shared thread without a turn (no reply, no model): a human attendant's
    message (``role='humano'``, ``autor_user_id`` required) or a lead message that is not answered.
    Idempotent: a retried ``provider_message_id`` appends nothing (``duplicado=true``); the same id with
    other text is a 409 ``idempotency_conflict``. Takes the thread's turn lock, so it never interleaves
    with a running turn (409 ``turn_in_progress`` — the caller retries)."""
    if payload.role == "humano" and payload.autor_user_id is None:
        raise _err(422, "invalid_field", "Campo inválido: autor_user_id")
    thread = _thread_do_token(ctx, conv_store, threads, thread_id)
    if not conv_store.try_acquire_turn(ctx.org_id, thread.id, INSTANCE_ID, settings.turn_lock_ttl_seconds):
        raise _err(409, "turn_in_progress", "Já existe um turno em andamento.")
    try:
        try:
            result = anexar_mensagens(
                org_id=ctx.org_id, thread=thread, conversations=conv_store, messages=msg_store, inbound=inbound,
                mensagens=[MensagemEntrada(
                    texto=payload.texto, provider_message_id=payload.provider_message_id,
                    role=payload.role, autor_user_id=payload.autor_user_id,
                )],
            )
        except IdempotencyConflict as exc:
            raise _err(409, "idempotency_conflict", "Este provider_message_id já foi recebido com outro conteúdo.") from exc
        except Conflict as exc:  # the ledger unique index lost a race to a concurrent append
            raise _err(409, "turn_in_progress", "Já existe um turno em andamento.") from exc
        except ValueError as exc:
            raise _err(422, "invalid_field", "Conversa sem connection_id.") from exc
        for record in result.novas:
            await publish_event(thread.id, "message.new", _message_payload(record), bus=bus)
    finally:
        conv_store.release_turn(ctx.org_id, thread.id, INSTANCE_ID)
    return ThreadMensagemOut(
        message_id=result.novas[0].id if result.novas else None, duplicado=not result.novas
    )


# ── PATCH .../participantes/{agent_key} (the per-conversation on/off) ───────


@router.patch(
    "/api/channels/threads/{thread_id}/participantes/{agent_key}", response_model=ParticipanteOut
)
async def set_participant_state(
    thread_id: UUID,
    agent_key: str,
    payload: ParticipanteEstadoRequest,
    ctx: AuthContext = Depends(require_channel_turn),
    studio_store=Depends(get_studio_definition_store_dep),
    conv_store=Depends(get_conversation_store_dep),
    threads=Depends(get_thread_store_dep),
) -> ParticipanteOut:
    """Pause / resume the agent in ONE conversation (SW's per-conversation toggle). The token must be
    bound to ``agent_key``; the actor (``ator_user_id``) lands in the participant event and the agent
    audit log. Idempotent when already in the requested state."""
    agent = _agente_do_token(studio_store, ctx, agent_key)
    thread = _thread_do_token(ctx, conv_store, threads, thread_id)
    _validar_ate(payload.estado, payload.ate)
    try:
        rec = alterar_estado_humano(
            org_id=ctx.org_id, thread_id=thread.id, agent_id=agent.id, para=payload.estado,
            ator_user_id=payload.ator_user_id, motivo=payload.motivo, threads=threads, ate=payload.ate,
        )
    except (NotFound, TransicaoInvalida, OutroAgenteAtivo) as exc:
        raise _estado_http(exc) from exc
    return _participante_out(ctx.org_id, agent, rec)


@router.patch(
    "/api/studio/threads/{thread_id}/participantes/{agent_key}", response_model=ParticipanteOut
)
async def studio_set_participant_state(
    thread_id: UUID,
    agent_key: str,
    payload: StudioParticipanteEstadoRequest,
    ctx: AuthContext = Depends(require_admin),
    studio_store=Depends(get_studio_definition_store_dep),
    conv_store=Depends(get_conversation_store_dep),
    threads=Depends(get_thread_store_dep),
) -> ParticipanteOut:
    """Studio's per-thread pause / resume: same service, the actor is the signed-in admin."""
    agent = _agente_por_chave(studio_store, ctx.org_id, agent_key)
    try:
        thread = conv_store.get(ctx.org_id, thread_id)
    except NotFound as exc:
        raise _err(404, "thread_not_found", "Conversa não encontrada.") from exc
    if thread.tipo != "thread_lead":
        raise _err(404, "thread_not_found", "Conversa não encontrada.")
    _validar_ate(payload.estado, payload.ate)
    try:
        rec = alterar_estado_humano(
            org_id=ctx.org_id, thread_id=thread.id, agent_id=agent.id, para=payload.estado,
            ator_user_id=ctx.user_id, motivo=payload.motivo, threads=threads, ate=payload.ate,
        )
    except (NotFound, TransicaoInvalida, OutroAgenteAtivo) as exc:
        raise _estado_http(exc) from exc
    return _participante_out(ctx.org_id, agent, rec)


# ── the agent's controls (mode + drain progress) ────────────────────────────


def _controle_out(org_id: UUID, agent: Any, controles: Any, threads: Any) -> ControleOut:
    controle = controles.get(org_id, agent.id)
    drenagem = progresso_dreno(
        threads.list_abertos(org_id, agent.id), controle.dreno_inatividade_dias, utcnow()
    )
    return ControleOut(
        agent_key=agent.key,
        modo=controle.modo,
        aceita_novos_leads=controle.aceita_novos_leads,
        dreno_inatividade_dias=controle.dreno_inatividade_dias,
        threads_abertas=drenagem["abertas"],
        drenagem=DrenagemOut(**drenagem),
    )


@router.get("/api/channels/agents/{agent_key}/controle", response_model=ControleOut)
async def channel_agent_controle(
    agent_key: str,
    ctx: AuthContext = Depends(require_channel_status),
    studio_store=Depends(get_studio_definition_store_dep),
    controles=Depends(get_agent_controle_store_dep),
    threads=Depends(get_thread_store_dep),
) -> ControleOut:
    """Read-only for SW: the mode, whether new leads are accepted and the drain progress. SW never
    decides the mode and never gates on a cached copy of this — the turn endpoint decides."""
    agent = _agente_do_token(studio_store, ctx, agent_key)
    return _controle_out(ctx.org_id, agent, controles, threads)


@router.get("/api/studio/agents/{agent_key}/controle", response_model=ControleOut)
async def studio_agent_controle(
    agent_key: str,
    ctx: AuthContext = Depends(require_member),
    studio_store=Depends(get_studio_definition_store_dep),
    controles=Depends(get_agent_controle_store_dep),
    threads=Depends(get_thread_store_dep),
) -> ControleOut:
    agent = _agente_por_chave(studio_store, ctx.org_id, agent_key)
    return _controle_out(ctx.org_id, agent, controles, threads)


@router.put("/api/studio/agents/{agent_key}/controle", response_model=ControleOut)
async def studio_set_agent_controle(
    agent_key: str,
    payload: ControleUpdateRequest,
    ctx: AuthContext = Depends(require_admin),
    studio_store=Depends(get_studio_definition_store_dep),
    controles=Depends(get_agent_controle_store_dep),
    threads=Depends(get_thread_store_dep),
    key_resolver=Depends(get_org_llm_key_resolver_dep),
    catalog=Depends(get_knowledge_catalog_dep),
) -> ControleOut:
    """Switch the agent ligado / drenando / desligado (and set the drain idle days). Turning it ON
    (``ligado`` / ``drenando``) needs a published version, a configured LLM key and complete content (every
    required org spec filled, no blocking compile warning) -- 409 otherwise;
    turning it OFF never needs anything. Audited with the actor (``modo_alterado``)."""
    agent = _agente_por_chave(studio_store, ctx.org_id, agent_key)
    if payload.modo != "desligado":
        # The agent resolves through its platform definition (A-CONT): the published version, the org's
        # specs and the compiled content decide whether it may take leads.
        try:
            resolvido = resolve_agent_for_org(studio_store, ctx.org_id, agent_key)
        except NotFound as exc:
            raise _err(404, "agent_not_found", "Agente não encontrado.") from exc
        if resolvido.versao is None:
            raise _err(409, "no_active_version", "O agente não tem versão publicada.")
        if not key_resolver(resolvido.versao.provider, ctx.org_id):
            raise _err(409, "llm_nao_configurado", "A chave do provedor de IA não está configurada.")
        status_conteudo = conteudo_status(studio_store, catalog, resolvido)
        if not status_conteudo.completo:
            raise _err(
                409, "conteudo_incompleto",
                "O conteúdo do agente está incompleto: " + ", ".join(
                    (*status_conteudo.specs_faltando, *status_conteudo.avisos_bloqueantes)
                ),
            )
    try:
        controles.set(
            ctx.org_id, agent.id, modo=payload.modo,
            dreno_inatividade_dias=payload.dreno_inatividade_dias, actor=ctx.user_id,
        )
    except NotFound as exc:
        raise _err(404, "agent_not_found", "Agente não encontrado.") from exc
    return _controle_out(ctx.org_id, agent, controles, threads)


# ── DELETE /api/channels/leads/{ref} (LGPD delete-by-lead) ──────────────────


@router.delete("/api/channels/leads/{ref}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_lead(
    ref: str,
    ctx: AuthContext = Depends(require_channel_turn),
    conv_store=Depends(get_conversation_store_dep),
    threads=Depends(get_thread_store_dep),
    retention: ChannelRetention = Depends(get_channel_retention_dep),
) -> Response:
    """"Apagar meus dados" for a LEAD: erase every thread of the lead across all agents — messages,
    idempotency rows, participants, the qualification and the lead itself — in one transaction.
    Idempotent: 204 whether or not the lead existed (no existence leak, a retry never fails). A running
    turn on any of the lead's threads blocks it (409 ``turn_in_progress``)."""
    _valida_ref(ref)
    try:
        apagar_lead(
            org_id=ctx.org_id, ref_externa=ref, threads=threads, conversations=conv_store,
            retention=retention, instance_id=INSTANCE_ID, ttl_seconds=settings.turn_lock_ttl_seconds,
        )
    except TurnInProgress as exc:
        raise _err(409, "turn_in_progress", "Já existe um turno em andamento.") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ── hand-offs (read for SW / the next operator) ─────────────────────────────


@router.get("/api/channels/threads/{thread_id}/handoffs", response_model=list[HandoffOut])
async def list_thread_handoffs(
    thread_id: UUID,
    ctx: AuthContext = Depends(require_channel_status),
    studio_store=Depends(get_studio_definition_store_dep),
    conv_store=Depends(get_conversation_store_dep),
    threads=Depends(get_thread_store_dep),
) -> list[HandoffOut]:
    """The thread's hand-off notes, oldest first (the next agent reads the newest; SW renders it)."""
    thread = _thread_do_token(ctx, conv_store, threads, thread_id)
    agentes = mapa_agentes(studio_store, ctx.org_id)
    lead = threads.get_lead_ref(ctx.org_id, thread.lead_ref_id) if thread.lead_ref_id else None
    return [_handoff_out(h, agentes, lead.ref_externa if lead else None) for h in threads.list_handoffs(ctx.org_id, thread.id)]


def _handoff_do_token(ctx: AuthContext, conv_store: Any, threads: Any, handoff_id: UUID) -> Any:
    handoff = threads.get_handoff(ctx.org_id, handoff_id)
    if handoff is None:
        raise _err(404, "handoff_not_found", "Handoff não encontrado.")
    _thread_do_token(ctx, conv_store, threads, handoff.thread_id)  # same visibility as the thread
    return handoff


@router.get("/api/channels/handoffs/{handoff_id}", response_model=HandoffOut)
async def get_handoff(
    handoff_id: UUID,
    ctx: AuthContext = Depends(require_channel_status),
    studio_store=Depends(get_studio_definition_store_dep),
    conv_store=Depends(get_conversation_store_dep),
    threads=Depends(get_thread_store_dep),
) -> HandoffOut:
    handoff = _handoff_do_token(ctx, conv_store, threads, handoff_id)
    lead = threads.get_lead_ref(ctx.org_id, handoff.lead_ref_id) if handoff.lead_ref_id else None
    return _handoff_out(handoff, mapa_agentes(studio_store, ctx.org_id), lead.ref_externa if lead else None)


@router.post("/api/channels/handoffs/{handoff_id}/aceite", response_model=HandoffOut)
async def accept_handoff(
    handoff_id: UUID,
    payload: HandoffAceiteRequest,
    ctx: AuthContext = Depends(require_channel_turn),
    studio_store=Depends(get_studio_definition_store_dep),
    conv_store=Depends(get_conversation_store_dep),
    threads=Depends(get_thread_store_dep),
) -> HandoffOut:
    """The human operator took it (idempotent: the first acceptance wins)."""
    handoff = _handoff_do_token(ctx, conv_store, threads, handoff_id)
    handoff = threads.aceitar_handoff(ctx.org_id, handoff.id, payload.user_id)
    lead = threads.get_lead_ref(ctx.org_id, handoff.lead_ref_id) if handoff.lead_ref_id else None
    return _handoff_out(handoff, mapa_agentes(studio_store, ctx.org_id), lead.ref_externa if lead else None)


# ── consent (WhatsApp Business messaging policy) ────────────────────────────


def _consent_out(lead: Any, **extra: Any) -> dict:
    return dict(
        lead_ref=lead.ref_externa, opt_in_em=lead.opt_in_em, opt_in_origem=lead.opt_in_origem,
        opt_out_em=lead.opt_out_em, opt_out_ativo=lead.opt_out_ativo, **extra,
    )


@router.put("/api/channels/leads/{ref}/opt-in", response_model=LeadConsentOut)
async def lead_opt_in(
    ref: str,
    payload: OptInRequest,
    ctx: AuthContext = Depends(require_channel_turn),
    threads=Depends(get_thread_store_dep),
) -> LeadConsentOut:
    """Record how and when the lead consented to be contacted. A LATER opt-in lifts an earlier opt-out."""
    _valida_ref(ref)
    lead = threads.registrar_opt_in(ctx.org_id, ref, origem=payload.origem, em=payload.em)
    return LeadConsentOut(**_consent_out(lead))


@router.post("/api/channels/leads/{ref}/opt-out", response_model=OptOutOut)
async def lead_opt_out(
    ref: str,
    payload: OptOutRequest,
    ctx: AuthContext = Depends(require_channel_turn),
    threads=Depends(get_thread_store_dep),
) -> OptOutOut:
    """The lead asked to stop ("parar"): every agent's participation in every thread of the lead ends
    (``encerrado``, motivo ``opt_out``) and SW must suppress follow-ups. The lead is registered even when
    it has no thread yet, so a future thread respects the opt-out. Idempotent."""
    _valida_ref(ref)
    threads.upsert_lead_ref(ctx.org_id, ref)
    encerrados = threads.registrar_opt_out(ctx.org_id, ref, em=payload.em)
    lead = threads.get_lead_ref_by_externa(ctx.org_id, ref)
    return OptOutOut(**_consent_out(lead, participantes_encerrados=max(encerrados, 0)))


def _valida_ref(ref: str) -> None:
    if not ref.strip() or len(ref) > 256:
        raise _err(422, "invalid_field", "Campo inválido: ref")


# ── Studio: reading a thread (org admin) ────────────────────────────────────


@router.get("/api/studio/threads/{thread_id}/mensagens", response_model=list[MensagemThreadOut])
async def studio_thread_messages(
    thread_id: UUID,
    limite: int = Query(default=50, ge=1, le=200),
    ctx: AuthContext = Depends(require_admin),
    studio_store=Depends(get_studio_definition_store_dep),
    conv_store=Depends(get_conversation_store_dep),
    msg_store=Depends(get_message_store_dep),
) -> list[MensagemThreadOut]:
    """The conversation of a lead thread for an org admin: lead, agent, human and event lines with the
    author labelled. System notices, tool calls / results, token usage and version stamps are stripped
    (they are prompt-side internals, not part of what an org sees)."""
    try:
        thread = conv_store.get(ctx.org_id, thread_id)
    except NotFound as exc:
        raise _err(404, "thread_not_found", "Conversa não encontrada.") from exc
    if thread.tipo != "thread_lead":
        raise _err(404, "thread_not_found", "Conversa não encontrada.")
    agentes = mapa_agentes(studio_store, ctx.org_id)
    out = []
    for r in msg_store.list(ctx.org_id, thread.id, limite=limite):
        if r.role == "system" or (r.role == "assistant" and not (r.texto or "").strip()):
            continue
        key, nome = agentes.get(r.agent_id, (None, None)) if r.agent_id else (None, None)
        out.append(MensagemThreadOut(
            id=r.id, role=r.role, texto=r.texto, agent_key=key, agent_nome=nome,
            autor_user_id=r.autor_user_id, created_at=r.created_at,
        ))
    return out
