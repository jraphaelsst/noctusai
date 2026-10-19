"""The channel tools: page-0 ``handoff(motivo)`` (Lais contract §3.1 / §7) plus,
when the turn carries a ``contexto`` (build contract §2.1(c)), the ACTION tools
and the READ tools it enables.

The model asks for a human; the tool does NOT message anyone — it records the
request on a per-turn :class:`ActionCollector`, and the turn API returns
``actions:[{type:"handoff", motivo, seq}]`` + ``status:"handoff"``. The transport
(social-wiring) pauses the chat and notifies the owner.

Action tools (``salvar_slots`` · ``definir_operacao`` · ``qualificar_lead`` ·
``pedido_visita`` · ``captacao`` · ``encerrar``) never call SW during the turn:
the handler validates the arguments (strict) and appends to the collector; the
tool result is always ``{"registrado": true}``. SW applies the batch after the
turn, idempotently. Read tools (``buscar_imoveis`` …) call SW through
``SocialWiringClient.lais_ferramenta`` with the ORG's own token; no token ⇒ the
tool is not offered; SW slow/down ⇒ ``{"erro": "indisponivel"}``.

``motivo`` is LEAD-INFLUENCED text, so it is normalised before it leaves
(§10.1 M3): control characters stripped, whitespace collapsed, markup-ish
angle brackets removed, hard cap 280 characters. Downstream renders it escaped
and treats it as untrusted.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import threading
from collections.abc import Callable
from typing import Any
from uuid import UUID

from pydantic import ValidationError

from noctusai_lib.integrations.llm import ToolCall, ToolResult, ToolSpec

from app.clients.social_wiring import (
    LAIS_TOOL_TIMEOUT_SECONDS,
    LAIS_TOOL_UNAVAILABLE,
    SocialWiringClient,
    get_lais_tools_client,
)
from app.runtime.llm_runtime import LlmToolset
from app.runtime.types import AgentSpec, TurnContext
from app.schemas.channels import ActionArgs

logger = logging.getLogger(__name__)

__all__ = [
    "HANDOFF_TOOL_NAME",
    "MOTIVO_MAX_CHARS",
    "ActionCollector",
    "HandoffCollector",
    "make_channel_tools_factory",
    "sanitize_motivo",
]

HANDOFF_TOOL_NAME = "handoff"
MOTIVO_MAX_CHARS = 280
_DEFAULT_MOTIVO = "Atendimento humano solicitado."

HANDOFF_SPEC = ToolSpec(
    name=HANDOFF_TOOL_NAME,
    description=(
        "Passa a conversa para uma pessoa da equipe. Use quando o cliente pedir para falar com "
        "um humano, fizer uma reclamação ou o assunto fugir do que você pode resolver. "
        "`motivo`: uma frase curta, em texto simples, dizendo por que (máx. 280 caracteres)."
    ),
    parameters={
        "type": "object",
        "properties": {
            "motivo": {
                "type": "string",
                "description": "Por que a conversa precisa de uma pessoa (texto simples, até 280 caracteres).",
                "maxLength": MOTIVO_MAX_CHARS,
            }
        },
        "required": ["motivo"],
        "additionalProperties": False,
    },
)

_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f  ]")
_ANGLE = re.compile(r"[<>]")


def sanitize_motivo(raw: object) -> str:
    """Plain text, single-spaced, no markup brackets, ≤ 280 chars; never empty."""
    text = raw if isinstance(raw, str) else ""
    text = _CONTROL.sub(" ", text)
    text = _ANGLE.sub("", text)
    text = " ".join(text.split())
    if len(text) > MOTIVO_MAX_CHARS:
        text = text[: MOTIVO_MAX_CHARS - 1].rstrip() + "…"
    return text or _DEFAULT_MOTIVO


ACTION_SLOT_VALUE_MAX = 500
#: Slot keys always allowed besides ``contexto.perguntas[].chave`` (§2.1(c)).
ALWAYS_SLOT_KEYS = frozenset({"nome", "email"})
_REGISTRADO = '{"registrado": true}'


def _text_schema(max_len: int, description: str) -> dict[str, Any]:
    return {"type": "string", "description": description, "maxLength": max_len}


_NULLABLE_STR = {"type": ["string", "null"]}
_DT = {"type": "string", "format": "date-time"}

ACTION_SPECS: dict[str, ToolSpec] = {
    "salvar_slots": ToolSpec(
        name="salvar_slots",
        description=(
            "Registra dados que o cliente informou (use as chaves das perguntas essenciais, "
            "ou `nome`/`email`). Chame assim que o cliente responder, sem avisar que está anotando."
        ),
        parameters={
            "type": "object",
            "properties": {"slots": {
                "type": "object", "additionalProperties": _text_schema(ACTION_SLOT_VALUE_MAX, "Valor informado."),
                "description": "Mapa chave -> valor informado pelo cliente.",
            }},
            "required": ["slots"], "additionalProperties": False,
        },
    ),
    "definir_operacao": ToolSpec(
        name="definir_operacao",
        description="Registra o que o cliente quer fazer: compra, aluguel, administracao ou atualizacao.",
        parameters={
            "type": "object",
            "properties": {"operacao": {"type": "string", "enum": ["compra", "aluguel", "administracao", "atualizacao"]}},
            "required": ["operacao"], "additionalProperties": False,
        },
    ),
    "qualificar_lead": ToolSpec(
        name="qualificar_lead",
        description="Sinaliza que o cliente já deu as informações essenciais e está pronto para a equipe. `motivo`: uma frase (até 300 caracteres).",
        parameters={
            "type": "object",
            "properties": {"motivo": _text_schema(300, "Por que o lead está qualificado.")},
            "required": ["motivo"], "additionalProperties": False,
        },
    ),
    "pedido_visita": ToolSpec(
        name="pedido_visita",
        description="Registra um pedido de visita a um imóvel num horário que o cliente escolheu entre os disponíveis.",
        parameters={
            "type": "object",
            "properties": {
                "codigo_imovel": _NULLABLE_STR, "inicio": _DT, "fim": _DT, "cpf": _NULLABLE_STR,
            },
            "required": ["inicio", "fim"], "additionalProperties": False,
        },
    ),
    "captacao": ToolSpec(
        name="captacao",
        description="Registra que o cliente quer anunciar/vender/alugar um imóvel (captação). `descricao` até 1000 caracteres.",
        parameters={
            "type": "object",
            "properties": {
                "descricao": _text_schema(1000, "Resumo do imóvel e do pedido."),
                "endereco": _NULLABLE_STR,
                "operacao": {"type": ["string", "null"], "enum": ["venda", "aluguel", None]},
            },
            "required": ["descricao"], "additionalProperties": False,
        },
    ),
    "encerrar": ToolSpec(
        name="encerrar",
        description="Encerra o atendimento atual (o cliente se despediu, sem interesse, contato inválido ou outro motivo).",
        parameters={
            "type": "object",
            "properties": {"motivo": {"type": "string", "enum": ["lead_encerrou", "sem_interesse", "invalido", "outro"]}},
            "required": ["motivo"], "additionalProperties": False,
        },
    ),
    "consentimento_credito": ToolSpec(
        name="consentimento_credito",
        description=(
            "Registra a resposta do cliente ao pedido de consentimento para a análise de crédito "
            "(aceito=true se ele concordou explicitamente; false se recusou). Só chame depois de "
            "perguntar e receber uma resposta clara."
        ),
        parameters={
            "type": "object",
            "properties": {"aceito": {"type": "boolean"}},
            "required": ["aceito"], "additionalProperties": False,
        },
    ),
}

#: SW overlays an owner-confirmed status/price on the Vista listing (`confirmacao_proprietario`, additive key).
_CONFIRMACAO_HINT = (
    "Se um imóvel trouxer `confirmacao_proprietario`, o status/preço dali é o mais recente: use-o e, ao citar, "
    "diga a procedência com o texto de `provenance`."
)
_LINK_HINT = (
    "Quando o imóvel trouxer `link`, envie esse link exatamente como veio; sem `link`, não invente nenhum."
)

#: Read tools whose lookup SW records for Relatórios (top imóveis); the turn's interação is attached
#: SERVER-side from ``contexto.estado.interacao_id`` — never a model argument (it is not in their schema).
_TOOLS_WITH_INTERACAO = frozenset({"buscar_imoveis", "detalhes_imovel"})

READ_SPECS: dict[str, ToolSpec] = {
    "buscar_imoveis": ToolSpec(
        name="buscar_imoveis",
        description=("Busca imóveis do catálogo da imobiliária (máx. 5). Se retornar {\"erro\": \"indisponivel\"}, peça desculpas e siga o atendimento. "
                     + _CONFIRMACAO_HINT + " " + _LINK_HINT),
        parameters={
            "type": "object",
            "properties": {
                "operacao": {"type": "string", "enum": ["compra", "aluguel"]},
                "bairro": {"type": "string"}, "cidade": {"type": "string"}, "tipo": {"type": "string"},
                "preco_max": {"type": "number"}, "quartos_min": {"type": "integer"},
                "limite": {"type": "integer", "minimum": 1, "maximum": 5},
            },
            "required": ["operacao"], "additionalProperties": False,
        },
    ),
    "detalhes_imovel": ToolSpec(
        name="detalhes_imovel",
        description="Detalhes de um imóvel pelo código. " + _CONFIRMACAO_HINT + " " + _LINK_HINT,
        parameters={
            "type": "object", "properties": {"codigo": {"type": "string"}},
            "required": ["codigo"], "additionalProperties": False,
        },
    ),
    "horarios_visita": ToolSpec(
        name="horarios_visita",
        description="Horários disponíveis para visita nos próximos dias (até 7).",
        parameters={
            "type": "object",
            "properties": {"codigo": {"type": "string"}, "dias": {"type": "integer", "minimum": 1, "maximum": 7}},
            "additionalProperties": False,
        },
    ),
    "consultar_empreendimento": ToolSpec(
        name="consultar_empreendimento",
        description="Consulta um empreendimento pelo nome.",
        parameters={
            "type": "object", "properties": {"nome": {"type": "string"}},
            "required": ["nome"], "additionalProperties": False,
        },
    ),
}

#: Per-tool argument shape of the read tools: ``{name: (required, optional)}``;
#: anything else is refused before SW is called (SW's route is strict too).
_READ_ARGS: dict[str, tuple[frozenset[str], frozenset[str]]] = {
    "buscar_imoveis": (
        frozenset({"operacao"}),
        frozenset({"bairro", "cidade", "tipo", "preco_max", "quartos_min", "limite"}),
    ),
    "detalhes_imovel": (frozenset({"codigo"}), frozenset()),
    "horarios_visita": (frozenset(), frozenset({"codigo", "dias"})),
    "consultar_empreendimento": (frozenset({"nome"}), frozenset()),
}


class ActionCollector:
    """Per-conversation record of the actions the model asked for during the
    turn in flight (handoff + the six Lais actions), in call order.

    Keyed by conversation id: the per-conversation turn lock guarantees at
    most one live turn per key, so one process-wide collector is race-free.
    ``take_actions`` pops (a turn reads its own actions exactly once). The studio
    TEST chat runs the same tools but never takes, so the map is bounded
    (oldest conversation dropped past ``max_conversations``) instead of
    growing for the life of the process.

    ``record`` / ``take`` keep the pre-F-AG handoff-only API
    (``HandoffCollector`` is an alias for one release)."""

    def __init__(self, max_conversations: int = 512) -> None:
        self._lock = threading.Lock()
        self._max = max(1, int(max_conversations))
        self._by_conversation: dict[UUID, list[dict[str, Any]]] = {}

    def record_action(self, conversation_id: UUID, action: dict[str, Any]) -> None:
        with self._lock:
            self._by_conversation.setdefault(conversation_id, []).append(action)
            while len(self._by_conversation) > self._max:
                self._by_conversation.pop(next(iter(self._by_conversation)))

    def take_actions(self, conversation_id: UUID) -> list[dict[str, Any]]:
        with self._lock:
            return self._by_conversation.pop(conversation_id, [])

    # ── pre-F-AG handoff-only API ─────────────────────────────────────────
    def record(self, conversation_id: UUID, motivo: str) -> None:
        self.record_action(conversation_id, {"type": "handoff", "motivo": motivo})

    def take(self, conversation_id: UUID) -> list[str]:
        return [a["motivo"] for a in self.take_actions(conversation_id) if a["type"] == "handoff"]


#: Deprecated name, kept for one release (build contract §2.1 Deprecations).
HandoffCollector = ActionCollector


def _clean_text(raw: object, max_chars: int) -> str | None:
    """Same normalisation as :func:`sanitize_motivo` without the default; ``None`` ⇒ empty."""
    text = raw if isinstance(raw, str) else ""
    text = _ANGLE.sub("", _CONTROL.sub(" ", text))
    text = " ".join(text.split())
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text or None


def _refuse(call: ToolCall, why: str) -> ToolResult:
    return ToolResult(call.call_id, f"Argumentos inválidos: {why}", is_error=True)


def _build_action(name: str, args: dict[str, Any], allowed_slot_keys: frozenset[str]) -> dict[str, Any]:
    """Validate the model's arguments for one action tool and return the
    action dict (without ``seq``). Raises ``ValueError`` with a short reason."""
    model = ActionArgs[name]
    fields = set(model.model_fields) - {"type", "seq"}
    unknown = sorted(set(args) - fields)
    if unknown:
        raise ValueError("campos desconhecidos: " + ", ".join(unknown))
    clean = dict(args)
    if name == "salvar_slots":
        slots = clean.get("slots")
        if not isinstance(slots, dict) or not slots:
            raise ValueError("`slots` deve ser um mapa não vazio")
        out: dict[str, str] = {}
        for key, value in slots.items():
            if key not in allowed_slot_keys:
                raise ValueError(f"chave de slot não permitida: {str(key)[:40]}")
            if not isinstance(value, str):
                raise ValueError(f"valor do slot `{key}` deve ser texto")
            if len(value) > ACTION_SLOT_VALUE_MAX:
                raise ValueError(f"valor do slot `{key}` passa de {ACTION_SLOT_VALUE_MAX} caracteres")
            cleaned = _clean_text(value, ACTION_SLOT_VALUE_MAX)
            if cleaned is not None:
                out[key] = cleaned
        if not out:
            raise ValueError("nenhum valor de slot utilizável")
        clean["slots"] = out
    elif name == "qualificar_lead":
        clean["motivo"] = _clean_text(clean.get("motivo"), 300)
        if clean["motivo"] is None:
            raise ValueError("`motivo` obrigatório")
    elif name == "captacao":
        descricao = clean.get("descricao")
        if isinstance(descricao, str) and len(descricao) > 1000:
            raise ValueError("`descricao` passa de 1000 caracteres")
        clean["descricao"] = _clean_text(descricao, 1000)
        if clean["descricao"] is None:
            raise ValueError("`descricao` obrigatória")
        if clean.get("endereco") is not None:
            clean["endereco"] = _clean_text(clean["endereco"], 300)
    elif name == "pedido_visita":
        for key in ("codigo_imovel", "cpf"):
            if clean.get(key) is not None:
                clean[key] = _clean_text(clean[key], 64)
    try:
        parsed = model.model_validate({**clean, "type": name})
    except ValidationError as exc:
        raise ValueError("; ".join(sorted({str(e["loc"][-1]) + ": " + e["msg"] for e in exc.errors()}))) from exc
    if name == "pedido_visita" and parsed.fim <= parsed.inicio:
        raise ValueError("`fim` deve ser depois de `inicio`")
    return parsed.model_dump(mode="json", exclude={"seq"}, exclude_none=False)


def make_channel_tools_factory(
    collector: ActionCollector,
    *,
    lais_client_factory: Callable[[], SocialWiringClient] | None = None,
):
    """``(spec, ctx) -> LlmToolset`` for a channel turn. Every id the tool uses
    comes from the SERVER-built context, never from the model's arguments.

    ``handoff`` is always offered. With ``ctx.contexto`` it also offers the
    action tools named in ``contexto.acoes`` and the read tools named in
    ``contexto.ferramentas`` (the latter only when the org holds a tools token).
    ``lais_client_factory`` is the DI seam for the SW client (tests pass a Fake)."""
    client_factory = lais_client_factory or get_lais_tools_client

    def _factory(spec: AgentSpec, ctx: TurnContext) -> LlmToolset:
        contexto = ctx.contexto
        tools: list[ToolSpec] = [HANDOFF_SPEC]
        action_names: set[str] = set()
        read_names: set[str] = set()
        allowed_slot_keys: frozenset[str] = ALWAYS_SLOT_KEYS
        client: SocialWiringClient | None = None
        if contexto is not None:
            allowed_slot_keys = ALWAYS_SLOT_KEYS | {p.chave for p in contexto.perguntas}
            for name in contexto.acoes:
                if name in ACTION_SPECS and name not in action_names:
                    action_names.add(name)
                    tools.append(ACTION_SPECS[name])
            wanted = [n for n in contexto.ferramentas if n in READ_SPECS]
            if wanted:
                client = client_factory()
                if client.lais_tools_available(ctx.org_id):
                    for name in wanted:
                        if name not in read_names:
                            read_names.add(name)
                            tools.append(READ_SPECS[name])
                else:
                    client = None

        def _sw_args(name: str, args: dict[str, Any]) -> dict[str, Any]:
            body = dict(args)
            if name in _TOOLS_WITH_INTERACAO and contexto is not None:
                body["interacao_id"] = str(contexto.estado.interacao_id)
            return body

        async def _read(call: ToolCall) -> ToolResult:
            assert client is not None
            args = call.arguments or {}
            required, optional = _READ_ARGS[call.name]
            unknown = sorted(set(args) - required - optional)
            missing = sorted(required - set(args))
            if unknown or missing:
                return _refuse(call, "; ".join(
                    ([f"campos desconhecidos: {', '.join(unknown)}"] if unknown else [])
                    + ([f"faltando: {', '.join(missing)}"] if missing else [])
                ))
            try:
                body = await asyncio.wait_for(
                    client.lais_ferramenta(ctx.org_id, call.name, _sw_args(call.name, args)), LAIS_TOOL_TIMEOUT_SECONDS
                )
            except Exception as exc:  # noqa: BLE001 — a tool failure is a result, never a crashed turn
                logger.warning(
                    "agents.lais_tool.failed org_id=%s conversation_id=%s tool=%s error=%s",
                    ctx.org_id, ctx.conversation_id, call.name, type(exc).__name__,
                )
                body = dict(LAIS_TOOL_UNAVAILABLE)
            return ToolResult(call.call_id, json.dumps(body, ensure_ascii=False, default=str))

        async def _handler(call: ToolCall) -> ToolResult:
            if call.name == HANDOFF_TOOL_NAME:
                motivo = sanitize_motivo((call.arguments or {}).get("motivo"))
                collector.record(ctx.conversation_id, motivo)
                return ToolResult(
                    call.call_id,
                    "Transferência registrada. Avise o cliente, em uma frase, que uma pessoa da "
                    "equipe vai continuar o atendimento.",
                )
            if call.name in action_names:
                try:
                    action = _build_action(call.name, call.arguments or {}, allowed_slot_keys)
                except ValueError as exc:
                    return _refuse(call, str(exc))
                collector.record_action(ctx.conversation_id, action)
                return ToolResult(call.call_id, _REGISTRADO)
            if call.name in read_names:
                return await _read(call)
            return ToolResult(call.call_id, "Ferramenta desconhecida.", is_error=True)

        def _resumo(name: str, args: dict[str, Any]) -> str:
            if name == HANDOFF_TOOL_NAME:
                return "Passar o atendimento para uma pessoa."
            if name in action_names:
                return f"Registrar: {name.replace('_', ' ')}."
            return f"Consultar: {name.replace('_', ' ')}."

        return LlmToolset(tools=tuple(tools), handler=_handler, resumo=_resumo)

    return _factory
