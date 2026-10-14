"""The page-0 channel tool: ``handoff(motivo)`` (Lais contract §3.1 / §7).

The model asks for a human; the tool does NOT message anyone — it records the
request on a per-turn :class:`HandoffCollector`, and the turn API returns
``actions:[{type:"handoff", motivo}]`` + ``status:"handoff"``. The transport
(social-wiring) pauses the chat and notifies the owner.

``motivo`` is LEAD-INFLUENCED text, so it is normalised before it leaves
(§10.1 M3): control characters stripped, whitespace collapsed, markup-ish
angle brackets removed, hard cap 280 characters. Downstream renders it escaped
and treats it as untrusted.
"""
from __future__ import annotations

import re
import threading
from uuid import UUID

from noctusai_lib.integrations.llm import ToolCall, ToolResult, ToolSpec

from app.runtime.llm_runtime import LlmToolset
from app.runtime.types import AgentSpec, TurnContext

__all__ = [
    "HANDOFF_TOOL_NAME",
    "MOTIVO_MAX_CHARS",
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


class HandoffCollector:
    """Per-conversation record of handoffs asked during the turn in flight.

    Keyed by conversation id: the per-conversation turn lock guarantees at
    most one live turn per key, so one process-wide collector is race-free.
    ``take`` pops (a turn reads its own handoffs exactly once). The studio
    TEST chat runs the same tool but never ``take``s, so the map is bounded
    (oldest conversation dropped past ``max_conversations``) instead of
    growing for the life of the process."""

    def __init__(self, max_conversations: int = 512) -> None:
        self._lock = threading.Lock()
        self._max = max(1, int(max_conversations))
        self._by_conversation: dict[UUID, list[str]] = {}

    def record(self, conversation_id: UUID, motivo: str) -> None:
        with self._lock:
            self._by_conversation.setdefault(conversation_id, []).append(motivo)
            while len(self._by_conversation) > self._max:
                self._by_conversation.pop(next(iter(self._by_conversation)))

    def take(self, conversation_id: UUID) -> list[str]:
        with self._lock:
            return self._by_conversation.pop(conversation_id, [])


def make_channel_tools_factory(collector: HandoffCollector):
    """``(spec, ctx) -> LlmToolset`` for a channel turn. Every id the tool uses
    comes from the SERVER-built context, never from the model's arguments."""

    def _factory(spec: AgentSpec, ctx: TurnContext) -> LlmToolset:
        def _handler(call: ToolCall) -> ToolResult:
            if call.name != HANDOFF_TOOL_NAME:
                return ToolResult(call.call_id, "Ferramenta desconhecida.", is_error=True)
            motivo = sanitize_motivo((call.arguments or {}).get("motivo"))
            collector.record(ctx.conversation_id, motivo)
            return ToolResult(
                call.call_id,
                "Transferência registrada. Avise o cliente, em uma frase, que uma pessoa da "
                "equipe vai continuar o atendimento.",
            )

        return LlmToolset(
            tools=(HANDOFF_SPEC,),
            handler=_handler,
            resumo=lambda name, args: "Passar o atendimento para uma pessoa.",
        )

    return _factory
