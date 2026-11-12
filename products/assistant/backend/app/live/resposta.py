"""The live reply: one admitted inbound text -> one agent turn -> bubbles to the same chat -> one immutable event.

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
    MAX_MESSAGE_CHARS, STATUS_RESPONDEU, AgentsClient, TurnMessage, TurnRequest,
)

from app.live import registro as r
from app.live.controles import ControleIlegivel, ler_controles
from app.live.numeros import eh_conversa_individual, numero_do_chat, numero_permitido
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
    agent_key: str
    max_age_s: int = 900
    paragraph_delay_s: float = 0.6


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
        agents: Optional[AgentsClient],
        waha_for: Callable[[UUID, UUID], Awaitable[Any]],
        registro: Any,
        config: ReplyConfig,
        identity_key: Callable[[], str],
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._agents = agents
        self._waha_for = waha_for
        self._reg = registro
        self._cfg = config
        self._identity_key = identity_key
        self._sleep = sleep
        self._now = now
        self._locks: dict[str, asyncio.Lock] = {}

    async def _io(self, fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        return await anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))

    async def _evento(self, org_id: UUID, connection_id: UUID, message: Any, desfecho: str, motivo: Optional[str] = None,
                      dados: Optional[dict[str, Any]] = None) -> str:
        try:
            await self._io(
                self._reg.registrar, org_id=str(org_id), connection_id=str(connection_id), waha_message_id=message.id,
                desfecho=desfecho, motivo=motivo, dados=dados,
            )
        except Exception:  # noqa: BLE001 - the attempt already happened; a failed log must be LOUD, never silent
            logger.exception("assistant live reply: could not record outcome=%s connection=%s", desfecho, connection_id)
        logger.info("assistant live reply: outcome=%s motivo=%s connection=%s", desfecho, motivo, connection_id)
        return desfecho

    async def responder(self, org_id: UUID, connection_id: UUID, message: Any) -> Optional[str]:
        """Handle one stored inbound message. Returns the outcome, or None for a silent no-op. Never raises."""
        if not self._cfg.enabled or message.from_me or not eh_conversa_individual(message.chat_id):
            return None
        # One conversation at a time: two quick messages must not race two turns/sends to the same person.
        lock = self._locks.setdefault(str(message.chat_id), asyncio.Lock())
        async with lock:
            try:
                return await self._responder(org_id, connection_id, message)
            except Exception:  # noqa: BLE001 - last wall: nothing escapes to the webhook
                logger.exception("assistant live reply: unexpected failure connection=%s", connection_id)
                return await self._evento(org_id, connection_id, message, r.ERRO_TURNO, "inesperado")

    async def _responder(self, org_id: UUID, connection_id: UUID, message: Any) -> Optional[str]:
        intake = await self._io(self._reg.desfecho_do_intake, str(connection_id), message.id)
        if not self._reg.intake_responsavel(intake):
            return None  # history / excluded / no text / unknown row: shadow only
        if (self._now() - _at(message)).total_seconds() > self._cfg.max_age_s:
            return await self._evento(org_id, connection_id, message, r.MENSAGEM_ANTIGA)

        numero = (message.sender_phone and numero_do_chat(f"{message.sender_phone}@c.us")) or numero_do_chat(message.chat_id)
        if self._agents is None:
            return await self._evento(org_id, connection_id, message, r.ERRO_TURNO, "agents_nao_configurado")

        try:
            result = await self._agents.run_turn(TurnRequest(
                agent_key=self._cfg.agent_key,
                connection_id=str(connection_id),
                chat_id=chat_ref(self._identity_key(), message.chat_id),
                messages=(TurnMessage(
                    texto=(message.body or "")[:MAX_MESSAGE_CHARS], provider_message_id=message.id, at=_at(message),
                ),),
                phone_e164=f"+{numero}" if numero else None,
            ))
        except Exception as exc:  # noqa: BLE001 - typed agents errors + transport => no reply, logged, event
            return await self._evento(org_id, connection_id, message, r.ERRO_TURNO, _codigo(exc))

        if result.status not in STATUS_RESPONDEU:
            if result.status in _STATUS_DESLIGADO:
                return await self._evento(org_id, connection_id, message, r.AGENTE_DESLIGADO, result.status)
            if result.status in _STATUS_LISTA:
                return await self._evento(org_id, connection_id, message, r.RECUSADA_LISTA, result.status)
            return await self._evento(org_id, connection_id, message, r.SEM_ATENDIMENTO, result.status)
        partes = [p for p in (result.partes or ()) if p and p.strip()]
        if not partes:
            return await self._evento(org_id, connection_id, message, r.SEM_ATENDIMENTO, f"{result.status}_sem_resposta")

        veto = await self._guarda_de_envio(numero)
        if veto is not None:
            desfecho, motivo = veto
            return await self._evento(org_id, connection_id, message, desfecho, motivo)
        return await self._enviar(org_id, connection_id, message, partes)

    async def _guarda_de_envio(self, numero: Optional[str]) -> Optional[tuple[str, str]]:
        """The send-seam allow-list guard: a FRESH read of agents' on/off + allow-list; fail CLOSED when unreadable."""
        try:
            ctl = await ler_controles(self._agents, self._cfg.agent_key)  # type: ignore[arg-type]
        except ControleIlegivel as exc:
            return r.CONTROLE_INDISPONIVEL, str(exc)[:80]
        if not ctl.ligado:
            return r.AGENTE_DESLIGADO, "guarda_de_envio"
        if not numero_permitido(numero, ctl.numeros_permitidos):
            return r.RECUSADA_LISTA, "guarda_de_envio"
        return None

    async def _enviar(self, org_id: UUID, connection_id: UUID, message: Any, partes: list[str]) -> str:
        bolhas = [b for p in partes for b in split_reply(p)]
        enviadas = 0
        try:
            waha = await self._waha_for(org_id, connection_id)
            for idx, bolha in enumerate(bolhas):
                if idx:
                    await self._sleep(self._cfg.paragraph_delay_s)
                await waha.send_text(message.chat_id, bolha)
                enviadas += 1
        except Exception as exc:  # noqa: BLE001 - line policy refusal, WAHA down, ...: stop, record, never retry blindly
            logger.error("assistant live reply: send failed after %s/%s bubbles (%s)", enviadas, len(bolhas), _codigo(exc))
            desfecho = r.ENVIADA_PARCIAL if enviadas else r.ERRO_ENVIO
            return await self._evento(org_id, connection_id, message, desfecho, _codigo(exc),
                                      {"bolhas": enviadas, "de": len(bolhas)})
        return await self._evento(org_id, connection_id, message, r.ENVIADA, None, {"bolhas": enviadas})
