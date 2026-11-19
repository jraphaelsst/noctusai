"""The chat's turn through the Diretor de Criação (``criacao-pipeline-contract.md`` section 4, slice S9).

The headline / roteiro chat turn is answered by the platform agent ``diretor-de-criacao`` (the ``agents`` product), reached
the way Julia is: the seed ``agents_channel`` client (``POST /api/channels/turns``) with the org's own token. SW keeps what
the contract leaves with it: the ``@`` mentions, the parsing of the reply (``propostas.py`` + ``publicacoes.py``), the
multi-select and the saga -- the agent never writes. Tenant data reaches the agent through its read tools
(``/api/criacao/ferramentas``), never through this call.

Fake + Real + factory (``KB § PATTERNS/backend/seed-fake-real-adapter.md``): :class:`DiretorCriacao` is the port,
:class:`FakeDiretorCriacao` the scripted double, :class:`AgentsDiretorCriacao` the real one over an ``AgentsClient`` and
:func:`make_diretor_criacao` the factory. A failure is a CODE (:class:`DiretorIndisponivel`), never exception text.

Per-org strangler (contract 4 / 8): ``chat_diretor_criacao`` selects, per org, which engine answers the chat -- the legacy
direct-model stream (``mc/prompts/chat_unificado.py``) or this agent. It is a TIME-BOXED switch, not a fallback: with it ON a
missing or failing agent is a coded refusal (``diretor_indisponivel``), never a silent drop to the legacy engine.
``NOC-REMEDIATE[chat-legado-estrangulado]`` -- 2026-12-31: delete the legacy chat engine and this switch once every org runs
the Diretor.

Wire (the part the ``agents`` product must still accept -- see the S9 return note): ``agent_key='diretor-de-criacao'``,
``channel='app'``, ``channel_ref = {connection_id: <marca_id>, chat_id: <conversa_id>}``, one message whose
``provider_message_id`` is the user message id (the turn is idempotent on it). No ``contexto`` is sent: its schema is Julia's
and closed.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol, Union

from noctusai_lib.config.credentials import resolve_credential
from noctusai_lib.integrations.agents_channel import (
    AgentNotFound,
    AgentsBadRequest,
    AgentsClient,
    AgentsClientError,
    AgentsNotConfigured,
    AgentsTimeout,
    AgentsTokenInvalid,
    AgentsUpstreamError,
    AgentUnavailable,
    CapacityExceeded,
    LlmNotConfigured,
    TurnInProgress,
    TurnMessage,
    TurnRequest,
)

logger = logging.getLogger(__name__)

AGENT_KEY = "diretor-de-criacao"
CANAL = "app"
CHAVE_FLAG = "chat_diretor_criacao"
VIA_LEGADO = "legado"
VIA_DIRETOR = "diretor"
_VERDADEIRO = frozenset({"1", "true", "on", "sim", "yes"})

#: AgentsClientError subclass -> the code the chat reports (the exception text never leaves the process).
_CODIGOS: tuple[tuple[type[AgentsClientError], str], ...] = (
    (AgentsNotConfigured, "nao_configurado"),
    (AgentsTokenInvalid, "token_invalido"),
    (AgentNotFound, "agente_nao_encontrado"),
    (LlmNotConfigured, "ia_nao_configurada"),
    (CapacityExceeded, "capacidade"),
    (TurnInProgress, "turno_em_andamento"),
    (AgentsTimeout, "timeout"),
    (AgentUnavailable, "agente_indisponivel"),
    (AgentsUpstreamError, "erro_upstream"),
    (AgentsBadRequest, "pedido_recusado"),
)


class DiretorIndisponivel(Exception):
    """The Diretor could not answer. ``codigo`` is the only thing callers show or log."""

    def __init__(self, codigo: str) -> None:
        super().__init__(codigo)
        self.codigo = codigo


@dataclass(frozen=True)
class TurnoDiretor:
    org_id: str
    marca_id: str
    conversa_id: str
    mensagem_id: str  # the user message: the turn's idempotency key
    texto: str


@dataclass(frozen=True)
class RespostaDiretor:
    texto: str
    custo_usd: Optional[float] = None
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None


class DiretorCriacao(Protocol):
    async def responder(self, turno: TurnoDiretor) -> RespostaDiretor: ...


ScriptedReply = Union[str, RespostaDiretor, Exception, Callable[[TurnoDiretor], Union[str, RespostaDiretor]]]


class FakeDiretorCriacao:
    """Scripted, deterministic, records every turn. A string / :class:`RespostaDiretor` is returned, an exception raised, a
    callable called with the turn; once the script is exhausted the last entry repeats."""

    def __init__(self, *script: ScriptedReply) -> None:
        self._script = list(script) or ["Opções prontas."]
        self.turnos: list[TurnoDiretor] = []

    async def responder(self, turno: TurnoDiretor) -> RespostaDiretor:
        self.turnos.append(turno)
        nxt = self._script[min(len(self.turnos) - 1, len(self._script) - 1)]
        if isinstance(nxt, Exception):
            raise nxt
        if callable(nxt) and not isinstance(nxt, (str, RespostaDiretor)):
            nxt = nxt(turno)
        return nxt if isinstance(nxt, RespostaDiretor) else RespostaDiretor(texto=str(nxt))


class AgentsDiretorCriacao:
    """The real Diretor: one ``run_turn`` on the org's agents client."""

    def __init__(self, client: AgentsClient) -> None:
        self.client = client

    async def responder(self, turno: TurnoDiretor) -> RespostaDiretor:
        req = TurnRequest(
            agent_key=AGENT_KEY, connection_id=turno.marca_id, chat_id=turno.conversa_id, channel=CANAL,
            messages=(TurnMessage(texto=turno.texto, provider_message_id=turno.mensagem_id, at=datetime.now(timezone.utc)),),
        )
        try:
            res = await self.client.run_turn(req)
        except AgentsClientError as exc:
            codigo = next((c for tipo, c in _CODIGOS if isinstance(exc, tipo)), "indisponivel")
            logger.warning("diretor: turno recusado org=%s codigo=%s", turno.org_id, codigo)
            raise DiretorIndisponivel(codigo) from exc
        texto = "\n".join(p for p in res.partes if p and p.strip()).strip()
        if not res.atendeu or not texto:
            logger.warning("diretor: turno sem resposta org=%s status=%s", turno.org_id, res.status)
            raise DiretorIndisponivel("sem_resposta")
        return RespostaDiretor(
            texto=texto, custo_usd=res.custo_usd, tokens_entrada=res.tokens_entrada, tokens_saida=res.tokens_saida,
        )


def make_diretor_criacao(client: Optional[AgentsClient]) -> Optional[DiretorCriacao]:
    """Pure factory: the real Diretor over ``client``; ``None`` (the caller refuses, coded) when there is no client. A Fake
    ``AgentsClient`` is the dev shape the org's resolver already returns outside a deploy -- it is still the real adapter."""
    return AgentsDiretorCriacao(client) if client is not None else None


#: ``(org_id) -> DiretorCriacao | None`` -- the chat router's DI seam. Tests override it with a Fake.
DiretorFactory = Callable[[str], Optional[DiretorCriacao]]


def diretor_padrao(org_id: str) -> Optional[DiretorCriacao]:
    from app.services.julia_agente_service import resolve_agents_client  # lazy: pulls the Julia grant stack

    return make_diretor_criacao(resolve_agents_client(org_id))


def get_diretor_factory() -> DiretorFactory:
    """FastAPI dependency. Tests override it."""
    return diretor_padrao


def diretor_ativo(org_id: Optional[str], cfg: Any, *, ler: Callable[[str, Optional[str]], Optional[str]] = resolve_credential) -> bool:
    """Does ``org_id`` run the Diretor? ``org_settings`` -> ``platform_settings`` -> env -> ``cfg.chat_diretor_criacao``
    (default OFF): the first answer that is a recognised value wins."""
    for valor in (ler(CHAVE_FLAG, str(org_id)) if org_id else None, ler(CHAVE_FLAG, None)):
        if valor is None or not str(valor).strip():
            continue
        return str(valor).strip().lower() in _VERDADEIRO
    return bool(getattr(cfg, CHAVE_FLAG, False))


__all__ = [
    "AGENT_KEY", "AgentsDiretorCriacao", "CANAL", "CHAVE_FLAG", "DiretorCriacao", "DiretorFactory", "DiretorIndisponivel",
    "FakeDiretorCriacao", "RespostaDiretor", "TurnoDiretor", "VIA_DIRETOR", "VIA_LEGADO", "diretor_ativo",
    "diretor_padrao", "get_diretor_factory", "make_diretor_criacao",
]
