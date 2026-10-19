"""`AgentsClient` -- social-wiring's client of the `agents` product's channel API.

Contract: products/social-wiring/projects/lais/specs/julia-agent-contract.md
  section 3.1  POST /api/channels/turns                 -> `run_turn`
  section 3.2  GET  /api/channels/agents/{key}/status   -> `agent_status`
  section 10.1 M5  deletion on request                  -> `delete_conversation_data`
Lais build contract (lais-build-contract.md) 2.1:
  (a) `contexto` rides in the turn request; (d) the response carries action objects
  (`JuliaAction`); (e) POST /api/channels/conversations/{id}/resumo -> `resumo`;
  (f) PUT /api/channels/ferramentas-token -> `put_ferramentas_token`.
Owner 2026-10-19: POST /api/channels/agents/{key}/decisoes/{chave} -> `decidir` (a choice decided by the rule the
  owner keeps in the agent's prompt section `decisao-<chave>`; `regra_padrao` applies while that section is absent).

Fake + Real + factory (KB § PATTERNS/backend/seed-fake-real-adapter.md):
  * `AgentsClient`      -- the Protocol the lead path depends on;
  * `FakeAgentsClient`  -- scripted replies, deterministic, records every call;
  * `HttpAgentsClient`  -- the real one, base URL + per-org token;
  * `make_agents_client`-- the pure factory (token/base_url/dev decision in, client out).

Every row of the section 3.1 error table maps to ONE typed exception below, so
the lead path decides what to do from the TYPE, never from a status code or a
message string. The lead never sees any of this (L2): errors end in "no reply".

Deletion wire (shipped by A2): DELETE /api/channels/conversations, JSON body, 204.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Optional, Protocol, Sequence, Union, runtime_checkable

import httpx
from noctusai_lib.primitives.not_configured import IntegrationNotConfigured
from urllib.parse import quote

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_S = 60.0
DEFAULT_RETRY_AFTER_S = 30

#: Hard shape limits of section 3.1 -- the lead path trims to these BEFORE the call.
MAX_BATCH_MESSAGES = 20
MAX_MESSAGE_CHARS = 8000


# ── wire types ──────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class TurnMessage:
    texto: str
    provider_message_id: str
    at: datetime


@dataclass(frozen=True)
class TurnRequest:
    agent_key: str
    connection_id: str
    chat_id: str
    messages: tuple[TurnMessage, ...]
    phone_e164: Optional[str] = None
    display_name: Optional[str] = None
    channel: str = "whatsapp"
    #: Lais build contract 2.1(a): the per-turn dynamic context SW renders
    #: (`julia_contexto_service.montar`). None = page-0 behaviour, key omitted.
    contexto: Optional[dict[str, Any]] = None

    def to_wire(self) -> dict[str, Any]:
        wire = self._base_wire()
        if self.contexto is not None:
            wire["contexto"] = self.contexto
        return wire

    def _base_wire(self) -> dict[str, Any]:
        return {
            "agent_key": self.agent_key,
            "channel": self.channel,
            "channel_ref": {"connection_id": self.connection_id, "chat_id": self.chat_id},
            "contact": {"phone_e164": self.phone_e164, "display_name": self.display_name},
            "messages": [
                {
                    "texto": m.texto,
                    "provider_message_id": m.provider_message_id,
                    "at": m.at.isoformat(),
                }
                for m in self.messages
            ],
        }


@dataclass(frozen=True)
class HandoffAction:
    motivo: str
    type: str = "handoff"


@dataclass(frozen=True)
class JuliaAction:
    """One of the Julia action shapes of contract 2.1(d) (`salvar_slots`, `definir_operacao`,
    `qualificar_lead`, `pedido_visita`, `captacao`, `encerrar`). `payload` is the action
    object minus `type`/`seq`. An UNKNOWN type is kept (not dropped): the apply service
    answers it with an `acao_sem_handler` event so a newer agents build never loses data
    silently."""

    type: str
    seq: int
    payload: dict[str, Any] = field(default_factory=dict)


Action = Union[HandoffAction, JuliaAction]


@dataclass(frozen=True)
class TurnResult:
    conversation_id: str
    partes: tuple[str, ...]
    status: str  # respondido | silencio | handoff | encerrado
    actions: tuple[Action, ...] = ()
    custo_usd: Optional[float] = None
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None

    @property
    def handoff(self) -> Optional[HandoffAction]:
        return next((a for a in self.actions if isinstance(a, HandoffAction)), None)

    @property
    def julia_actions(self) -> tuple[JuliaAction, ...]:
        """The non-handoff actions, in `seq` order (ties keep arrival order)."""
        return tuple(sorted((a for a in self.actions if isinstance(a, JuliaAction)), key=lambda a: a.seq))


@dataclass(frozen=True)
class AgentStatus:
    agent_key: str
    nome: str
    ativo: bool
    versao_ativa: Optional[int]
    provider: Optional[str]
    model: Optional[str]
    llm_configurado: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "agent_key": self.agent_key,
            "nome": self.nome,
            "ativo": self.ativo,
            "versao_ativa": self.versao_ativa,
            "provider": self.provider,
            "model": self.model,
            "llm_configurado": self.llm_configurado,
        }


@dataclass(frozen=True)
class AgentUso:
    """`GET /api/channels/uso?mes=YYYY-MM`: the org's channel turns + cost for the month and
    its per-day cost cap (the Painel "Consumo do plano")."""

    turnos: int
    custo_usd: float
    limite_diario_usd: float


@dataclass(frozen=True)
class DeletionRequest:
    agent_key: str
    connection_id: str
    chat_id: str


@dataclass(frozen=True)
class DeletionResult:
    """`deleted` is False when agents had nothing for that chat (not an error)."""

    deleted: bool
    messages_deleted: int = 0


@dataclass(frozen=True)
class ResumoRequest:
    """Contract 2.1(e) body: the question catalogue + the window to summarise."""

    perguntas: tuple[dict[str, Any], ...] = ()
    desde: Optional[datetime] = None

    def to_wire(self) -> dict[str, Any]:
        return {
            "perguntas": [dict(p) for p in self.perguntas],
            "desde": self.desde.isoformat() if self.desde else None,
        }


@dataclass(frozen=True)
class ResumoResult:
    resumo: str
    slots: dict[str, str] = field(default_factory=dict)
    operacao: Optional[str] = None
    intencoes: tuple[str, ...] = ()
    desfecho: str = "em_andamento"
    custo_usd: Optional[float] = None
    tokens_entrada: Optional[int] = None
    tokens_saida: Optional[int] = None


@dataclass(frozen=True)
class DecisaoRequest:
    opcoes: tuple[str, ...]
    regra_padrao: str
    dados: dict[str, Any] = field(default_factory=dict)

    def to_wire(self) -> dict[str, Any]:
        return {"opcoes": list(self.opcoes), "dados": dict(self.dados), "regra_padrao": self.regra_padrao}


@dataclass(frozen=True)
class DecisaoResult:
    escolha: str
    motivo: str = ""
    #: `secao` = the owner's prompt section decided; `padrao` = our `regra_padrao`.
    regra: str = "padrao"
    custo_usd: Optional[float] = None


# ── typed errors (one per row of the section 3.1 error table) ───────────────
class AgentsClientError(Exception):
    """Base of every failure of a call to agents. `code` is agents' own code."""

    def __init__(self, message: str = "", *, code: Optional[str] = None):
        super().__init__(message or code or self.__class__.__name__)
        self.code = code


class AgentsNotConfigured(AgentsClientError, IntegrationNotConfigured):
    """No token for this org (prod): the link is simply not set up."""


class AgentsTokenInvalid(AgentsClientError):
    """401, or 403 product_required / scope_missing / issuer_not_allowed."""


class AgentNotFound(AgentsClientError):
    """404 agent_not_found."""


class ConversationNotFound(AgentsClientError):
    """404 conversation_not_found (the `resumo` route)."""


class AgentUnavailable(AgentsClientError):
    """409 agent_inactive / no_active_version / prompt_too_large."""


class TurnInProgress(AgentsClientError):
    """409 turn_in_progress -- SW re-queues the batch once after 5 s."""


class IdempotencyConflict(AgentsClientError):
    """409 on a replayed provider_message_id with different text (M2). A bug on our side."""


class AgentsBadRequest(AgentsClientError):
    """422 invalid_field -- a bug, logged as an error."""


class LlmNotConfigured(AgentsClientError, IntegrationNotConfigured):
    """424 llm_not_configured -- no org key for the provider."""


class CapacityExceeded(AgentsClientError):
    """429 capacidade -- slots full / org budget exhausted; honours Retry-After."""

    def __init__(self, message: str = "", *, code: Optional[str] = None, retry_after: int = DEFAULT_RETRY_AFTER_S):
        super().__init__(message, code=code)
        self.retry_after = retry_after


class AgentsUpstreamError(AgentsClientError):
    """502 llm_upstream (and any other 5xx / malformed 2xx): no reply, logged."""


class AgentsTimeout(AgentsClientError):
    """No answer within the 60 s budget (or the network is down)."""


# ── Protocol ────────────────────────────────────────────────────────────────
@runtime_checkable
class AgentsClient(Protocol):
    async def run_turn(self, req: TurnRequest) -> TurnResult: ...

    async def agent_status(self, agent_key: str) -> AgentStatus: ...

    async def delete_conversation_data(self, req: DeletionRequest) -> DeletionResult: ...

    async def resumo(self, conversation_id: str, req: ResumoRequest) -> ResumoResult: ...

    async def decidir(self, agent_key: str, chave: str, req: DecisaoRequest) -> DecisaoResult: ...

    async def put_ferramentas_token(self, token: str) -> None: ...

    async def uso(self, mes: str) -> AgentUso: ...


# ── Fake ────────────────────────────────────────────────────────────────────
ScriptedReply = Union[TurnResult, AgentsClientError, Callable[[TurnRequest], TurnResult]]

_NAMESPACE = uuid.UUID("5f0e3b0a-7c1d-4a52-9d55-3a0c1b5a8f10")


class FakeAgentsClient:
    """Scripted, deterministic, records every call.

    `script` is consumed one entry per `run_turn`: a `TurnResult` is returned, an
    `AgentsClientError` is raised, a callable is called with the request. When the
    script is exhausted the default reply is returned. A replayed set of
    `provider_message_id`s returns the stored result without consuming the script
    (agents' idempotency, section 3.1 side effect 1).
    """

    DEFAULT_PARTES = ("Prazer! Você procura comprar ou alugar?",)

    def __init__(
        self,
        script: Sequence[ScriptedReply] = (),
        *,
        status: Optional[AgentStatus] = None,
        status_error: Optional[AgentsClientError] = None,
        default_partes: Sequence[str] = DEFAULT_PARTES,
        resumo_script: Sequence[Union[ResumoResult, AgentsClientError]] = (),
        decisao_script: Sequence[Union[DecisaoResult, AgentsClientError]] = (),
        ferramentas_token_error: Optional[AgentsClientError] = None,
        uso: Union[AgentUso, AgentsClientError, None] = None,
    ):
        self._uso = uso
        self.uso_calls: list[str] = []
        self._script = list(script)
        self._resumo_script = list(resumo_script)
        self._decisao_script = list(decisao_script)
        self.decisoes: list[tuple[str, str, DecisaoRequest]] = []
        self._ferramentas_token_error = ferramentas_token_error
        self._status = status
        self._status_error = status_error
        self._default_partes = tuple(default_partes)
        self._replays: dict[tuple[str, ...], TurnResult] = {}
        self.turns: list[TurnRequest] = []
        self.status_calls: list[str] = []
        self.deletions: list[DeletionRequest] = []
        self.resumos: list[tuple[str, ResumoRequest]] = []
        self.ferramentas_tokens: list[str] = []

    @staticmethod
    def conversation_id_for(req: TurnRequest) -> str:
        return str(uuid.uuid5(_NAMESPACE, f"{req.agent_key}|{req.connection_id}|{req.chat_id}"))

    async def run_turn(self, req: TurnRequest) -> TurnResult:
        self.turns.append(req)
        ids = tuple(m.provider_message_id for m in req.messages)
        if ids in self._replays:
            return self._replays[ids]
        if self._script:
            nxt = self._script.pop(0)
            if isinstance(nxt, AgentsClientError):
                raise nxt
            result = nxt(req) if callable(nxt) and not isinstance(nxt, TurnResult) else nxt
        else:
            result = TurnResult(
                conversation_id=self.conversation_id_for(req),
                partes=self._default_partes,
                status="respondido",
                custo_usd=0.0,
                tokens_entrada=0,
                tokens_saida=0,
            )
        self._replays[ids] = result
        return result

    async def agent_status(self, agent_key: str) -> AgentStatus:
        self.status_calls.append(agent_key)
        if self._status_error is not None:
            raise self._status_error
        return self._status or AgentStatus(
            agent_key=agent_key, nome="Julia", ativo=True, versao_ativa=1,
            provider="openai", model="gpt-5-mini", llm_configurado=True,
        )

    async def delete_conversation_data(self, req: DeletionRequest) -> DeletionResult:
        self.deletions.append(req)
        had = any(
            t.connection_id == req.connection_id and t.chat_id == req.chat_id and t.agent_key == req.agent_key
            for t in self.turns
        )
        return DeletionResult(deleted=had, messages_deleted=2 * len(self.turns) if had else 0)


    async def resumo(self, conversation_id: str, req: ResumoRequest) -> ResumoResult:
        self.resumos.append((conversation_id, req))
        if self._resumo_script:
            nxt = self._resumo_script.pop(0)
            if isinstance(nxt, AgentsClientError):
                raise nxt
            return nxt
        return ResumoResult(resumo="Resumo de teste da conversa.", desfecho="em_andamento", custo_usd=0.0,
                            tokens_entrada=0, tokens_saida=0)

    async def decidir(self, agent_key: str, chave: str, req: DecisaoRequest) -> DecisaoResult:
        """Scripted; with no script, the FIRST option (deterministic) decided by `padrao`."""
        self.decisoes.append((agent_key, chave, req))
        if self._decisao_script:
            nxt = self._decisao_script.pop(0)
            if isinstance(nxt, AgentsClientError):
                raise nxt
            return nxt
        return DecisaoResult(escolha=req.opcoes[0], motivo="decisão de teste", regra="padrao", custo_usd=0.0)

    async def uso(self, mes: str) -> AgentUso:
        self.uso_calls.append(mes)
        if isinstance(self._uso, AgentsClientError):
            raise self._uso
        return self._uso or AgentUso(turnos=0, custo_usd=0.0, limite_diario_usd=5.0)

    async def put_ferramentas_token(self, token: str) -> None:
        if self._ferramentas_token_error is not None:
            raise self._ferramentas_token_error
        self.ferramentas_tokens.append(token)


# ── Real ────────────────────────────────────────────────────────────────────
def _error_code(response: httpx.Response) -> Optional[str]:
    """agents' errors are `HTTPException(detail={"detail", "code"})`; the seed auth
    deps raise plain-string details. Read both shapes defensively."""
    try:
        body = response.json()
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    detail = body.get("detail")
    if isinstance(detail, dict):
        code = detail.get("code")
        return str(code) if code else None
    code = body.get("code")
    return str(code) if code else None


def _retry_after(response: httpx.Response) -> int:
    raw = response.headers.get("Retry-After", "")
    try:
        value = int(float(raw))
    except (TypeError, ValueError):
        return DEFAULT_RETRY_AFTER_S
    return max(1, min(value, 3600))


def _raise_for_agents_status(response: httpx.Response) -> None:
    """Section 3.1 error table -> typed exception. 2xx returns."""
    status = response.status_code
    if status < 400:
        return
    code = _error_code(response)
    if status in (401, 403):
        raise AgentsTokenInvalid(f"agents refused the token ({status})", code=code)
    if status == 404:
        if code == "agent_not_found":
            raise AgentNotFound("agent not found", code=code)
        if code == "conversation_not_found":
            raise ConversationNotFound("conversation not found", code=code)
        raise AgentsUpstreamError("agents answered 404", code=code)
    if status == 409:
        if code == "turn_in_progress":
            raise TurnInProgress("turn in progress", code=code)
        if code in ("agent_inactive", "no_active_version", "prompt_too_large"):
            raise AgentUnavailable(code, code=code)
        raise IdempotencyConflict(f"agents answered 409 ({code})", code=code)
    if status == 422:
        raise AgentsBadRequest("agents rejected the request shape", code=code)
    if status == 424:
        raise LlmNotConfigured("llm not configured for the org", code=code or "llm_not_configured")
    if status == 429:
        raise CapacityExceeded("agents at capacity", code=code or "capacidade", retry_after=_retry_after(response))
    raise AgentsUpstreamError(f"agents answered {status}", code=code)


def _need(body: Any, key: str, kind: type | tuple) -> Any:
    if not isinstance(body, dict) or key not in body or not isinstance(body[key], kind):
        raise AgentsUpstreamError(f"malformed agents response: '{key}'")
    return body[key]


def parse_turn_result(body: Any) -> TurnResult:
    """Strict parse of the section 3.1 200 body -- a malformed reply is an upstream
    fault (no reply sent), never a half-trusted result."""
    conversation_id = _need(body, "conversation_id", str)
    reply = _need(body, "reply", dict)
    partes = _need(reply, "partes", list)
    if not all(isinstance(p, str) for p in partes):
        raise AgentsUpstreamError("malformed agents response: reply.partes")
    status = _need(body, "status", str)
    if status not in ("respondido", "silencio", "handoff", "encerrado"):
        raise AgentsUpstreamError("malformed agents response: status")
    actions_raw = _need(body, "actions", list)
    actions: list[Action] = []
    for idx, a in enumerate(actions_raw):
        if not isinstance(a, dict) or not isinstance(a.get("type"), str) or not a.get("type"):
            logger.warning("agents returned a malformed action: %r", a)
            continue
        if a["type"] == "handoff":
            actions.append(HandoffAction(motivo=str(a.get("motivo") or "")[:280]))
            continue
        # A Julia action (contract 2.1(d)); an unknown type is kept so the apply
        # service can report `acao_sem_handler` instead of losing it silently.
        seq = a.get("seq")
        actions.append(JuliaAction(
            type=a["type"],
            seq=seq if isinstance(seq, int) and not isinstance(seq, bool) else idx,
            payload={k: v for k, v in a.items() if k not in ("type", "seq")},
        ))
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    return TurnResult(
        conversation_id=conversation_id,
        partes=tuple(p for p in partes if p.strip()),
        status=status,
        actions=tuple(actions),
        custo_usd=usage.get("custo_usd"),
        tokens_entrada=usage.get("tokens_entrada"),
        tokens_saida=usage.get("tokens_saida"),
    )


def parse_resumo_result(body: Any) -> ResumoResult:
    """Strict parse of the contract 2.1(e) 200 body; a malformed one is an upstream fault."""
    resumo = _need(body, "resumo", str)
    slots_raw = _need(body, "slots", dict)
    intencoes = _need(body, "intencoes", list)
    desfecho = _need(body, "desfecho", str)
    operacao = body.get("operacao")
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    return ResumoResult(
        resumo=resumo,
        slots={str(k): str(v) for k, v in slots_raw.items() if v is not None},
        operacao=operacao if isinstance(operacao, str) else None,
        intencoes=tuple(str(i) for i in intencoes if isinstance(i, str)),
        desfecho=desfecho,
        custo_usd=usage.get("custo_usd"),
        tokens_entrada=usage.get("tokens_entrada"),
        tokens_saida=usage.get("tokens_saida"),
    )


def parse_decisao_result(body: Any, opcoes: Sequence[str]) -> DecisaoResult:
    """Strict parse; an `escolha` outside what we offered is an upstream fault, never used."""
    escolha = _need(body, "escolha", str)
    if escolha not in opcoes:
        raise AgentsUpstreamError("agents chose an option that was not offered")
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    regra = body.get("regra")
    return DecisaoResult(
        escolha=escolha,
        motivo=body.get("motivo") if isinstance(body.get("motivo"), str) else "",
        regra=regra if regra in ("secao", "padrao") else "padrao",
        custo_usd=usage.get("custo_usd"),
    )


def parse_uso(body: Any) -> AgentUso:
    turnos = _need(body, "turnos", int)
    custo = _need(body, "custo_usd", (int, float))
    limite = _need(body, "limite_diario_usd", (int, float))
    return AgentUso(turnos=int(turnos), custo_usd=float(custo), limite_diario_usd=float(limite))


def parse_agent_status(body: Any) -> AgentStatus:
    return AgentStatus(
        agent_key=_need(body, "agent_key", str),
        nome=_need(body, "nome", str),
        ativo=bool(_need(body, "ativo", bool)),
        versao_ativa=body.get("versao_ativa") if isinstance(body.get("versao_ativa"), int) else None,
        provider=body.get("provider") if isinstance(body.get("provider"), str) else None,
        model=body.get("model") if isinstance(body.get("model"), str) else None,
        llm_configurado=bool(_need(body, "llm_configurado", bool)),
    )


class HttpAgentsClient:
    """The real client. `base_url` = `resolve_product_url("agents")`; `token` is the
    org's `pk_...` channel token (sent as a bearer). The token is never logged."""

    def __init__(
        self,
        base_url: str,
        token: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_S,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ):
        if not base_url:
            raise ValueError("HttpAgentsClient needs a base_url")
        if not token:
            raise ValueError("HttpAgentsClient needs a token")
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout
        self._transport = transport

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout,
            headers={"Authorization": f"Bearer {self._token}"},
            transport=self._transport,
        )

    async def _send(
        self, method: str, path: str, *, json: Optional[dict] = None, ok_statuses: tuple[int, ...] = ()
    ) -> Any:
        try:
            async with self._client() as client:
                response = await client.request(method, path, json=json)
        except httpx.TimeoutException as exc:
            raise AgentsTimeout("agents did not answer in time") from exc
        except httpx.HTTPError as exc:
            # Connection refused / DNS / TLS: same user-visible outcome as a timeout.
            raise AgentsTimeout(f"agents unreachable: {type(exc).__name__}") from exc
        if response.status_code in ok_statuses:
            return None
        _raise_for_agents_status(response)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            return response.json()
        except ValueError as exc:
            raise AgentsUpstreamError("agents returned a non-JSON body") from exc

    async def run_turn(self, req: TurnRequest) -> TurnResult:
        return parse_turn_result(await self._send("POST", "/api/channels/turns", json=req.to_wire()))

    async def agent_status(self, agent_key: str) -> AgentStatus:
        return parse_agent_status(await self._send("GET", f"/api/channels/agents/{quote(agent_key, safe='')}/status"))

    async def delete_conversation_data(self, req: DeletionRequest) -> DeletionResult:
        """`DELETE /api/channels/conversations` (A2): 204 empty, also when nothing exists;
        409 `turn_in_progress` while a turn runs (raised as `TurnInProgress`)."""
        # 404 is tolerated too (an older agents build): nothing stored = already gone.
        body = await self._send(
            "DELETE",
            "/api/channels/conversations",
            json={
                "agent_key": req.agent_key,
                "channel": "whatsapp",
                "channel_ref": {"connection_id": req.connection_id, "chat_id": req.chat_id},
            },
            ok_statuses=(404,),
        )
        # A 204 carries no body, so "was something deleted" is not knowable; the 2xx
        # itself is the guarantee that nothing remains.
        if isinstance(body, dict) and "deleted" in body:
            return DeletionResult(deleted=bool(body["deleted"]))
        return DeletionResult(deleted=body is not None)

    async def uso(self, mes: str) -> AgentUso:
        """`GET /api/channels/uso?mes=YYYY-MM` (Julia w9 Painel)."""
        return parse_uso(await self._send("GET", f"/api/channels/uso?mes={quote(mes, safe='')}"))

    async def resumo(self, conversation_id: str, req: ResumoRequest) -> ResumoResult:
        """`POST /api/channels/conversations/{id}/resumo` (contract 2.1(e))."""
        body = await self._send(
            "POST", f"/api/channels/conversations/{quote(conversation_id, safe='')}/resumo", json=req.to_wire()
        )
        return parse_resumo_result(body)

    async def decidir(self, agent_key: str, chave: str, req: DecisaoRequest) -> DecisaoResult:
        """`POST /api/channels/agents/{key}/decisoes/{chave}` (owner 2026-10-19)."""
        body = await self._send(
            "POST", f"/api/channels/agents/{quote(agent_key, safe='')}/decisoes/{quote(chave, safe='')}",
            json=req.to_wire(),
        )
        return parse_decisao_result(body, req.opcoes)

    async def put_ferramentas_token(self, token: str) -> None:
        """`PUT /api/channels/ferramentas-token` (contract 2.1(f)); auth = the org's channel
        token (this client's own bearer). 204 on success."""
        if not token:
            raise ValueError("put_ferramentas_token needs a token")
        await self._send("PUT", "/api/channels/ferramentas-token", json={"token": token})


# ── factory ─────────────────────────────────────────────────────────────────
def make_agents_client(
    *,
    token: Optional[str],
    base_url: Optional[str],
    allow_fake: bool,
) -> Optional[AgentsClient]:
    """Pure factory. Token + URL present -> the real client. Otherwise the Fake when
    `allow_fake` (dev), else `None` -- the caller reports "nao configurado" and sends
    no reply (prod: a lead is never answered by a scripted fake)."""
    if token and base_url:
        return HttpAgentsClient(base_url, token)
    if allow_fake:
        logger.warning("agents token/base_url missing: using FakeAgentsClient (dev only)")
        return FakeAgentsClient()
    return None


__all__ = [
    "AgentNotFound", "AgentStatus", "AgentUso", "AgentUnavailable", "AgentsBadRequest", "AgentsClient",
    "AgentsClientError", "AgentsNotConfigured", "AgentsTimeout", "AgentsTokenInvalid",
    "AgentsUpstreamError", "Action", "CapacityExceeded", "ConversationNotFound", "DecisaoRequest",
    "DecisaoResult", "DeletionRequest",
    "DeletionResult", "FakeAgentsClient", "HandoffAction", "HttpAgentsClient", "IdempotencyConflict",
    "JuliaAction", "LlmNotConfigured", "MAX_BATCH_MESSAGES", "MAX_MESSAGE_CHARS", "ResumoRequest",
    "ResumoResult", "TurnInProgress", "TurnMessage", "TurnRequest", "TurnResult", "make_agents_client",
    "parse_agent_status", "parse_decisao_result", "parse_uso", "parse_resumo_result", "parse_turn_result",
]
