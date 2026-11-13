"""The live reply: one admitted inbound text -> one agent turn -> bubbles to the same chat -> one immutable event.

Debounce: a conversation's messages are collected until it has been quiet for `debounce_s`; the whole burst is ONE turn
(`messages` = the burst, in order) and ONE reply; each message still gets its own event row (same outcome).

Decision order (every exit but a silent no-op lands as ONE `respostas_eventos` row, outcome as enum):

  0. silent no-ops (no turn, no event): the product switch is off; the message is from me / not a 1:1; the intake row was
     not taken in as a live message (pre-pairing history, excluded, no text).
  1. too old (webhook redelivery after an outage)           -> `mensagem_antiga`
  2. the agent turn (`agents` decides on/off, allow-list, limits):
       not served (`agente_desligado*` / `restrito_avaliacao` / any other no-service status) -> NO reply, never an error
       to the contact; a typed client error or anything unexpected -> `erro_turno`
  3. the SEND-SEAM guard (defence in depth, independent of the turn): re-read the agent's on/off + allow-list from
     `agents`; unreadable -> `controle_indisponivel` (FAIL CLOSED); off -> `agente_desligado`; a non-empty list that does
     not name this number -> `recusada_lista`. Empty list = every number.
  4. send one WhatsApp message per paragraph under the line policy -> `enviada` / `enviada_parcial` / `erro_envio`.

The contact's number exists only in this call's stack: the agent gets it (to match its own list), the database never does
(`chat_ref` is a keyed HMAC). No mark-read, no typing, no presence (the line policy forbids them on a personal line).
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID

import anyio.to_thread

from noctusai_lib.domain.chatbot import split_reply
from noctusai_lib.integrations.agents_channel import (
    MAX_MESSAGE_CHARS, REMETENTE_CONTATO, REMETENTE_DONO, STATUS_RESPONDEU, MAX_BATCH_MESSAGES, TurnMessage, TurnRequest,
)

from app.live import registro as r
from app.live.controles import ControleIlegivel, ler_controles
from app.live.numeros import eh_conversa_individual, eh_dono, numero_do_chat, numero_permitido
from app.services.agents_grant import AgentsAccess
from app.services.intake import chat_ref

logger = logging.getLogger(__name__)

#: `status` words of the turn response that mean "the owner's rule says this contact is not served right now".
_STATUS_DESLIGADO = ("agente_desligado", "agente_desligado_plataforma")
_STATUS_LISTA = ("restrito_avaliacao",)


def _codigo(exc: BaseException) -> str:
    """CamelCase class -> snake_case reason code (never the message: it may carry tokens / ids)."""
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", "_", type(exc).__name__).lower()


@dataclass(frozen=True)
class ReplyConfig:
    enabled: bool
    max_age_s: int = 900
    paragraph_delay_s: float = 0.6
    #: Quiet window of a conversation before its burst of messages becomes ONE turn.
    debounce_s: float = 4.0
    #: Canonical digits of the owner's other phones (`numeros_do_dono`); empty = nobody is the owner.
    owner_numbers: frozenset = frozenset()


def _at(message: Any) -> datetime:
    try:
        d = datetime.fromisoformat(str(message.timestamp).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


class LiveReplier:
    def __init__(
        self,
        *,
        agents_for: Callable[[UUID], Awaitable[Optional[AgentsAccess]]],
        waha_for: Callable[[UUID, UUID], Awaitable[Any]],
        registro: Any,
        config: ReplyConfig,
        identity_key: Callable[[], str],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._agents_for = agents_for  # org -> its grant's channel client + agent key; None = no live grant
        self._waha_for = waha_for
        self._reg = registro
        self._cfg = config
        self._identity_key = identity_key
        self._sleep = sleep
        self._now = now
        self._locks: dict[str, asyncio.Lock] = {}
        self._pending: dict[str, list[Any]] = {}
        self._collecting: set[str] = set()

    async def _io(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))

    async def _evento(self, org_id: UUID, connection_id: UUID, msgs: list[Any], desfecho: str, motivo: Optional[str] = None,
                      dados: Optional[dict[str, Any]] = None) -> str:
        """One immutable event per message of the batch (each intake row is its own attempt), same outcome."""
        for message in msgs:
            try:
                await self._io(
                    self._reg.registrar, org_id=str(org_id), connection_id=str(connection_id), waha_message_id=message.id,
                    desfecho=desfecho, motivo=motivo, dados={**(dados or {}), **({"lote": len(msgs)} if len(msgs) > 1 else {})},
                )
            except Exception:  # noqa: BLE001 - the attempt already happened; a failed log must be LOUD, never silent
                logger.exception("assistant live reply: could not record outcome=%s connection=%s", desfecho, connection_id)
        logger.info("assistant live reply: outcome=%s motivo=%s connection=%s batch=%s", desfecho, motivo, connection_id, len(msgs))
        return desfecho

    async def responder(self, org_id: UUID, connection_id: UUID, message: Any) -> Optional[str]:
        """Handle one stored inbound message. Returns the outcome, or None for a silent no-op or a message that joined a
        batch another call is already collecting (that call answers for all of them). Never raises."""
        if not self._cfg.enabled or message.from_me or not eh_conversa_individual(message.chat_id):
            return None
        key = str(message.chat_id)
        self._pending.setdefault(key, []).append(message)
        if key in self._collecting:
            return None
        # Debounce: wait for a quiet window (no new message from this conversation), then ONE turn for the whole burst.
        self._collecting.add(key)
        try:
            while True:
                n = len(self._pending[key])
                await self._sleep(self._cfg.debounce_s)
                if len(self._pending[key]) == n:
                    break
            batch = self._pending.pop(key)
        finally:
            self._collecting.discard(key)
        # One conversation at a time: a burst that arrives while this batch is being answered waits its turn.
        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            try:
                return await self._responder(org_id, connection_id, batch)
            except Exception:  # noqa: BLE001 - last wall: nothing escapes to the webhook
                logger.exception("assistant live reply: unexpected failure connection=%s", connection_id)
                return await self._evento(org_id, connection_id, batch, r.ERRO_TURNO, "inesperado")

    async def _responder(self, org_id: UUID, connection_id: UUID, batch: list[Any]) -> Optional[str]:
        vivas: list[Any] = []
        for m in batch:
            intake = await self._io(self._reg.desfecho_do_intake, str(connection_id), m.id)
            if self._reg.intake_responsavel(intake):  # history / excluded / no text / unknown row: shadow only
                vivas.append(m)
        if not vivas:
            return None
        agora = self._now()
        antigas = [m for m in vivas if (agora - _at(m)).total_seconds() > self._cfg.max_age_s]
        if antigas:
            await self._evento(org_id, connection_id, antigas, r.MENSAGEM_ANTIGA)
        msgs = [m for m in vivas if m not in antigas]
        if not msgs:
            return r.MENSAGEM_ANTIGA
        ultima = msgs[-1]

        numero = (ultima.sender_phone and numero_do_chat(f"{ultima.sender_phone}@c.us")) or numero_do_chat(ultima.chat_id)
        try:
            acesso = await self._agents_for(org_id)
        except Exception as exc:  # noqa: BLE001 - the grant store is unreadable (decrypt / DB): an error, NOT "no grant"
            return await self._evento(org_id, connection_id, msgs, r.ERRO_TURNO, f"grant_ilegivel_{_codigo(exc)}"[:80])
        if acesso is None:  # the org has no live agents grant (declared refusal: no reply, one event, never a Fake)
            return await self._evento(org_id, connection_id, msgs, r.ERRO_TURNO, "sem_grant_agents")

        remetente = REMETENTE_DONO if eh_dono(numero, self._cfg.owner_numbers) else REMETENTE_CONTATO
        dr = {"remetente": remetente}  # measurement: who wrote (enum only, never the number)
        try:
            result = await acesso.client.run_turn(TurnRequest(
                agent_key=acesso.agent_key,
                connection_id=str(connection_id),
                chat_id=chat_ref(self._identity_key(), ultima.chat_id),
                messages=tuple(
                    TurnMessage(texto=(m.body or "")[:MAX_MESSAGE_CHARS], provider_message_id=m.id, at=_at(m))
                    for m in msgs[-MAX_BATCH_MESSAGES:]
                ),
                phone_e164=f"+{numero}" if numero else None,
                remetente=remetente,
            ))
        except Exception as exc:  # noqa: BLE001 - typed agents errors + transport => no reply, logged, event
            return await self._evento(org_id, connection_id, msgs, r.ERRO_TURNO, _codigo(exc), dr)

        if result.status not in STATUS_RESPONDEU:
            if result.status in _STATUS_DESLIGADO:
                return await self._evento(org_id, connection_id, msgs, r.AGENTE_DESLIGADO, result.status, dr)
            if result.status in _STATUS_LISTA:
                return await self._evento(org_id, connection_id, msgs, r.RECUSADA_LISTA, result.status, dr)
            return await self._evento(org_id, connection_id, msgs, r.SEM_ATENDIMENTO, result.status, dr)
        partes = [p for p in (result.partes or ()) if p and p.strip()]
        if not partes:
            return await self._evento(org_id, connection_id, msgs, r.SEM_ATENDIMENTO, f"{result.status}_sem_resposta", dr)

        veto = await self._guarda_de_envio(numero, acesso)
        if veto is not None:
            desfecho, motivo = veto
            return await self._evento(org_id, connection_id, msgs, desfecho, motivo, dr)
        return await self._enviar(org_id, connection_id, msgs, partes, dr)

    async def _guarda_de_envio(self, numero: Optional[str], acesso: AgentsAccess) -> Optional[tuple[str, str]]:
        """The send-seam allow-list guard: a FRESH read of agents' on/off + allow-list; fail CLOSED when unreadable."""
        try:
            ctl = await ler_controles(acesso.client, acesso.agent_key)
        except ControleIlegivel as exc:
            return r.CONTROLE_INDISPONIVEL, str(exc)[:80]
        if not ctl.ligado:
            return r.AGENTE_DESLIGADO, "guarda_de_envio"
        if not numero_permitido(numero, ctl.numeros_permitidos):
            return r.RECUSADA_LISTA, "guarda_de_envio"
        return None

    async def _enviar(self, org_id: UUID, connection_id: UUID, msgs: list[Any], partes: list[str],
                     dados_base: Optional[dict[str, Any]] = None) -> str:
        bolhas = [b for p in partes for b in split_reply(p)]
        chat_id = msgs[-1].chat_id
        enviadas = 0
        # NOC-REMEDIATE[assistant-reply-claim-before-send]: the attempt's event is written AFTER the send, so a crash between
        # the first bubble and the event leaves a reply with no row. A claim row before the send would close it (needs a
        # claim step in `registrar_resposta`; no new outcome type) - accepted for now (owner/tech-lead 2026-11-12) - 2026-11-12
        try:
            waha = await self._waha_for(org_id, connection_id)
            for idx, bolha in enumerate(bolhas):
                if idx:
                    await self._sleep(self._cfg.paragraph_delay_s)
                await waha.send_text(chat_id, bolha)
                enviadas += 1
        except Exception as exc:  # noqa: BLE001 - line policy refusal, WAHA down, ...: stop, record, never retry blindly
            logger.error("assistant live reply: send failed after %s/%s bubbles (%s)", enviadas, len(bolhas), _codigo(exc))
            desfecho = r.ENVIADA_PARCIAL if enviadas else r.ERRO_ENVIO
            return await self._evento(org_id, connection_id, msgs, desfecho, _codigo(exc),
                                      {**(dados_base or {}), "bolhas": enviadas, "de": len(bolhas)})
        return await self._evento(org_id, connection_id, msgs, r.ENVIADA, None, {**(dados_base or {}), "bolhas": enviadas})
