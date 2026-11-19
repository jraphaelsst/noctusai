"""One ``app``-channel turn of the Diretor de Criacao (``POST /api/channels/turns`` with ``channel='app'``).

The caller (social-wiring, seed ``agents_channel`` client, the org's own ``social-wiring:criacao-tools`` issuer token) sends
``channel_ref = {connection_id: <marca_id>, chat_id: <conversa_id>}`` and ONE user message; no ``contexto`` (its schema is
Julia's and closed). This module is the whole of that turn and deliberately shares NOTHING of Julia's lead pipeline
(:mod:`app.channels.turno`: qualification, hand-off, opt-out, conformity): the route sends a ``whatsapp`` turn to
that pipeline untouched and an ``app`` turn here.

* The brand is the ``connection_id``. The model never names it: it is bound into :class:`CriacaoTurno` and injected into
  every tool call. Before the FIRST turn of a conversation the org must prove it owns the brand (an own-token
  ``contexto_marca`` read: SW answers 404 for a brand of another org, and the token is per org); a conversation that already
  exists was created under the same org (every read here is org-scoped), so it is not asked again.
* Idempotent on the user message's ``provider_message_id`` (the same ledger, the same replay / conflict rules as Julia's).
* The conversation is a plain ``chat`` row of channel ``app`` (no lead): the retention purge covers it, the lead
  machinery (``thread_lead``) never sees it.
* The reply is DATA for SW: SW parses the proposals / ``### Publicação`` blocks and is the only writer. Nothing here writes.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from app.channels import turno as turno_mod
from app.channels.bubbles import split_into_bubbles
from app.channels.controles import ControleIndisponivel
from app.config import settings
from app.criacao.canais import CANAL_APP
from app.criacao.ferramentas import CriacaoTurno
from app.runtime.errors import LlmRuntimeError
from app.runtime.llm_runtime import service_principal_id
from app.runtime.types import TurnContext
from app.schemas.channels import ChannelTurnRequest, ChannelTurnResponse
from app.stores.errors import Conflict

logger = logging.getLogger(__name__)


def _marca_do_org(resposta: dict[str, Any], marca_id: UUID) -> bool:
    """SW answered the brand read with data of THIS brand: it echoes the brand id it found for the token's org. An error
    envelope, a missing id or another brand's id all mean "not verified"."""
    if resposta.get("erro") is not None:
        return False
    return str(resposta.get("marca_id") or "") == str(marca_id)


async def executar_turno_app(
    *, payload: ChannelTurnRequest, org_id: UUID, agent: Any, svc: Any, runtime: Any, inbound: Any, controles: Any,
    plataforma: Any,
) -> ChannelTurnResponse:
    # imported here: the router imports this module lazily, so these are fully defined by now (no import cycle)
    from app.routers.channels_router import _UPSTREAM_DETAIL, _err, _llm_http, _plan_batch, _sha
    from app.routers.conversations_router import INSTANCE_ID

    assert payload.channel == CANAL_APP
    marca_id = payload.channel_ref.connection_id
    channel_ref = payload.channel_ref.canonical()
    batch = list(payload.messages)
    ids = [m.provider_message_id for m in batch]
    conv_store, msgs = svc.conversations, svc.messages
    to_thread = asyncio.to_thread

    existente = await to_thread(conv_store.find_channel, org_id, agent.id, CANAL_APP, channel_ref)
    plan = _plan_batch(await to_thread(inbound.find, org_id, marca_id, ids), batch, existente.id if existente else None)
    if plan.replay is not None:  # a stored reply is returned even if the agent was switched off since
        return ChannelTurnResponse(**plan.replay)

    try:
        controle = await to_thread(controles.get, org_id, agent.id)
        kill = bool((await to_thread(plataforma.get, agent.key)).desligado)
    except Exception as exc:
        logger.exception("agents.channel.app.controle_ilegivel org_id=%s", org_id)
        raise ControleIndisponivel().as_http_exception() from exc
    if kill or controle.modo == "desligado":
        return ChannelTurnResponse(
            thread_id=existente.id if existente else None, conversation_id=existente.id if existente else None,
            status="agente_desligado_plataforma" if kill else "agente_desligado", reply={"partes": []}, actions=[])

    sw = svc.sw
    if sw is None or not sw.criacao_tools_available(org_id):
        raise _err(424, "criacao_nao_configurada", "As ferramentas de criação não estão configuradas para esta organização.")
    if existente is None:
        # tenant isolation: this org must own the brand BEFORE anything is stored or any model is called. Fail closed:
        # an unreachable SW is "not verified", answered like a brand that is not the org's (no existence oracle).
        if not _marca_do_org(await sw.criacao_ferramenta(org_id, "contexto_marca", {"marca_id": str(marca_id)}), marca_id):
            logger.warning("agents.channel.app.marca_nao_verificada org_id=%s", org_id)
            raise _err(404, "marca_nao_encontrada", "Marca não encontrada.")

    try:
        prep = turno_mod.preparar(svc, org_id, agent, sem_padrao_ok=True)
    except turno_mod.TurnoRecusado as exc:
        raise _err(exc.status, exc.codigo, exc.detalhe) from exc
    conteudo = prep.compiled.conteudo
    if conteudo is None:
        raise _err(409, "conteudo_incompleto", "O conteúdo do agente está incompleto.")
    try:
        await runtime.preflight(prep.spec.provider, org_id)
    except LlmRuntimeError as exc:
        raise _llm_http(exc) from exc
    slot = runtime.try_reserve()
    if slot is None:
        raise _err(429, "capacidade", "Capacidade esgotada. Tente novamente em instantes.", headers={"Retry-After": "10"})

    conv = None
    acquired = False
    try:
        conv = existente or await to_thread(
            lambda: conv_store.create_channel(
                org_id, agent.id, CANAL_APP, channel_ref, None, version_id=prep.r.versao.id, tipo="chat"))
        acquired = await to_thread(conv_store.try_acquire_turn, org_id, conv.id, INSTANCE_ID, settings.turn_lock_ttl_seconds)
        if not acquired:
            raise _err(409, "turn_in_progress", "Já existe um turno em andamento.")
        plan = _plan_batch(await to_thread(inbound.find, org_id, marca_id, ids), batch, conv.id)  # under the lock
        if plan.replay is not None:
            return ChannelTurnResponse(**plan.replay)

        for msg in plan.new:
            await to_thread(
                msgs.add, org_id, conv.id, "user", msg.texto, meta={"provider_message_id": msg.provider_message_id})
            try:
                await to_thread(inbound.add, org_id, marca_id, conv.id, msg.provider_message_id, _sha(msg.assinatura()))
            except Conflict as exc:
                raise _err(409, "turn_in_progress", "Já existe um turno em andamento.") from exc
        if plan.new:
            await to_thread(conv_store.touch_activity, org_id, conv.id)

        turno = CriacaoTurno(org_id=org_id, marca_id=marca_id, sw=sw, conteudo=conteudo)
        ctx = TurnContext(
            org_id=org_id, conversation_id=conv.id, requested_by=service_principal_id(agent.id), instance_id=INSTANCE_ID,
            sdk_session_id=None, julia=turno, resposta_fallback=conteudo.texto("runtime.resposta_fallback").strip())
        textos: list[str] = []
        usage: dict[str, Any] = {}
        try:
            async with asyncio.timeout(settings.channel_turn_timeout_seconds):
                async for event in runtime.run_turn(prep.spec, ctx, "", None, slot=slot):
                    kind, evt = event["event"], event["payload"]
                    if kind == "message.new":
                        textos.append(evt.get("texto", ""))
                    elif kind == "session.status":
                        usage = {k: evt.get(k) for k in ("custo_usd", "tokens_entrada", "tokens_saida")}
        except LlmRuntimeError as exc:
            logger.warning("agents.channel.app.refused org_id=%s code=%s", org_id, exc.code)
            raise _llm_http(exc) from exc
        except TimeoutError as exc:
            logger.error("agents.channel.app.deadline_exceeded org_id=%s", org_id)
            raise _err(502, "llm_upstream", _UPSTREAM_DETAIL) from exc
        except Exception as exc:  # noqa: BLE001 -- a coded 502; the cause is logged, never returned
            logger.exception("agents.channel.app.failed org_id=%s", org_id)
            raise _err(502, "llm_upstream", _UPSTREAM_DETAIL) from exc

        texto_final = "\n\n".join(t for t in textos if t and t.strip())
        carimbo = prep.carimbo
        if texto_final.strip() or usage.get("custo_usd"):
            registro = await to_thread(lambda: msgs.add(
                org_id, conv.id, "assistant", texto_final, agent_id=agent.id, version_id=carimbo.definition_version_id,
                compiled_hash=carimbo.compiled_hash, definition_version_id=carimbo.definition_version_id,
                org_specs_hash=carimbo.org_specs_hash, skill_version_ids=list(carimbo.skill_version_ids) or None))
            if any(v is not None for v in usage.values()):
                await to_thread(lambda: msgs.set_turn_cost(
                    org_id, conv.id, registro.id, custo_usd=usage.get("custo_usd"),
                    tokens_entrada=usage.get("tokens_entrada"), tokens_saida=usage.get("tokens_saida")))
            await to_thread(conv_store.touch_activity, org_id, conv.id)
        resposta = ChannelTurnResponse(
            thread_id=conv.id, conversation_id=conv.id, status="respondido" if texto_final.strip() else "silencio",
            reply={"partes": split_into_bubbles(texto_final)}, actions=[],
            usage={k: usage.get(k) for k in ("custo_usd", "tokens_entrada", "tokens_saida")})
        if ids:
            await to_thread(lambda: inbound.set_reply(org_id, marca_id, ids, resposta.model_dump(mode="json")))
        return resposta
    finally:
        if acquired and conv is not None:
            await to_thread(conv_store.release_turn, org_id, conv.id, INSTANCE_ID)
        await slot.release()


__all__ = ["executar_turno_app"]
