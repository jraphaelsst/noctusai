"""LLM tool registry for the Imobi Scheduling bot.

Defines the three initial tools the bot's LLM tool-loop may call (per
PROJECT.md §6 Phase 6 — `lookup_property`, `propose_appointment`,
`confirm_appointment`). Cancellation + reschedule tools land in Phase 9.

**Wiring.** Each tool is shipped in two halves:

1. **OpenAI tool descriptor** (`TOOL_DESCRIPTORS`) — a list of dicts in
   the shape OpenAI's chat-completion API consumes via the ``tools=``
   kwarg. Names, parameters schema, descriptions all live here.
2. **Tool handler** (`build_tool_handler(...)`) — a callable matching
   `noctusai_lib.domain.chatbot.ToolHandler` (i.e. `ToolCall -> ToolResult`)
   that dispatches by ``call.name`` to the per-tool stub implementation.

**MCP-tool shape** (per project §3 design principle 4) — these tools
SHOULD land as MCP tools under ``platform.business.<service>.<action>``
once ``projects/mcp-server-expansion/`` Phase 5 ships its business-tool
mounting infrastructure. Until then, the bot consumes the in-process
shape declared here, and the future MCP-server exposure imports these
same handlers (no duplicate definition). Flagged as deferred in the
project's `**Improvements:**` block — same shape as Phase 5's
``whatsapp_webhook`` standard-router-promotion deferral.

**Stub semantics for Phase 6.** This phase wires the *bot framework*, not
the *business logic*. Each tool stub returns a structured "not yet
implemented" response payload so the LLM tool-loop and audit-row
persistence can be exercised end-to-end without hitting Calendar / Maps
/ scheduling-engine seams. Phases 7-9 replace the stubs with real
service calls.

See `KB § PATTERNS/whatsapp-chatbot-seed.md § Tool registry shape` for
the canonical tool-handler convention.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable

from noctusai_lib.domain.chatbot import ToolCall, ToolResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# OpenAI tool descriptors
#
# Shape mirrors OpenAI's chat-completion ``tools=`` parameter:
# ``{"type": "function", "function": {"name", "description", "parameters"}}``.
# The dispatcher (`LLMDispatcher.reply(tools=..., ...)`) passes this list
# straight through. Parameter schemas are JSON Schema (draft-07 subset).
# ---------------------------------------------------------------------------
TOOL_DESCRIPTORS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "lookup_property",
            "description": (
                "Verifica se um código de imóvel existe e retorna info "
                "do condomínio. Chame ANTES de discutir qualquer código "
                "de imóvel com o corretor."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Código do imóvel (ex.: AP-2034).",
                    },
                },
                "required": ["code"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "propose_appointment",
            "description": (
                "Retorna horários candidatos válidos para a data e janela "
                "informadas. NUNCA invente horários — sempre chame esta "
                "ferramenta antes de propor um horário."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "property_code": {
                        "type": "string",
                        "description": "Código do imóvel já validado por lookup_property.",
                    },
                    "requested_date": {
                        "type": "string",
                        "description": "Data desejada (formato ISO YYYY-MM-DD).",
                    },
                    "time_window": {
                        "type": "string",
                        "description": "'morning', 'afternoon', ou 'any'.",
                        "enum": ["morning", "afternoon", "any"],
                    },
                },
                "required": ["property_code", "requested_date", "time_window"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "confirm_appointment",
            "description": (
                "Cria o evento no Google Calendar e envia confirmações "
                "pelo WhatsApp para o corretor e a equipe de mídia. SÓ "
                "chame após o corretor confirmar TODOS os detalhes "
                "(imóvel, serviços, data, horário) de forma explícita."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "property_code": {
                        "type": "string",
                        "description": "Código do imóvel.",
                    },
                    "services": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["photos", "videos", "reels", "virtual_tour"],
                        },
                        "description": "Serviços a serem prestados na visita.",
                    },
                    "start_at": {
                        "type": "string",
                        "description": "Início (ISO 8601 com timezone — America/Sao_Paulo).",
                    },
                    "end_at": {
                        "type": "string",
                        "description": "Fim (ISO 8601 com timezone — America/Sao_Paulo).",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Observações opcionais (ex.: acesso, contato porteiro).",
                    },
                },
                "required": ["property_code", "services", "start_at", "end_at"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Tool stubs — Phase 6 wiring only
#
# Each stub returns a JSON-encoded response the LLM tool-loop can feed
# back into the next iteration. The audit row reflects the stub call;
# Phases 7-9 wire real Calendar / Maps / scheduling-engine semantics.
# ---------------------------------------------------------------------------
ToolImpl = Callable[[dict[str, Any]], dict[str, Any]]


def _stub_lookup_property(arguments: dict[str, Any]) -> dict[str, Any]:
    """Phase 6 stub. Phase 7+ replaces with real DB lookup."""
    code = arguments.get("code", "")
    logger.info("[stub] lookup_property called with code=%s", code)
    return {
        "status": "not_implemented",
        "tool": "lookup_property",
        "message": (
            "Lookup property is not yet wired to the database. "
            "Phase 7 (scheduling engine) lands this."
        ),
        "echo": {"code": code},
    }


def _stub_propose_appointment(arguments: dict[str, Any]) -> dict[str, Any]:
    """Phase 6 stub. Phase 7+ replaces with real scheduling-engine call."""
    logger.info("[stub] propose_appointment called with %s", arguments)
    return {
        "status": "not_implemented",
        "tool": "propose_appointment",
        "message": (
            "Propose appointment is not yet wired. "
            "Phase 7 (scheduling engine) lands this."
        ),
        "echo": arguments,
    }


def _stub_confirm_appointment(arguments: dict[str, Any]) -> dict[str, Any]:
    """Phase 6 stub. Phase 8+ replaces with real Calendar create + WAHA send."""
    logger.info("[stub] confirm_appointment called with %s", arguments)
    return {
        "status": "not_implemented",
        "tool": "confirm_appointment",
        "message": (
            "Confirm appointment is not yet wired to Calendar/WAHA. "
            "Phase 8 (Calendar + Maps) + Phase 9 (cancellation/reschedule) "
            "land this."
        ),
        "echo": arguments,
    }


# Name → implementation map. Registry of record.
TOOL_IMPLEMENTATIONS: dict[str, ToolImpl] = {
    "lookup_property": _stub_lookup_property,
    "propose_appointment": _stub_propose_appointment,
    "confirm_appointment": _stub_confirm_appointment,
}


def build_tool_handler() -> Callable[[ToolCall], ToolResult]:
    """Return a `ToolHandler` closure that dispatches by `ToolCall.name`.

    The closure matches `noctusai_lib.domain.chatbot.ToolHandler` —
    `Callable[[ToolCall], ToolResult]`. Unknown tool names return a
    structured `unknown_tool` response (not an exception); the
    dispatcher's audit writer wraps the call regardless of status.

    Returns:
        A handler bound to the module-level `TOOL_IMPLEMENTATIONS` map.
        Tests can monkey-patch the map entries OR call individual
        `_stub_*` helpers directly.
    """

    def _handler(call: ToolCall) -> ToolResult:
        impl = TOOL_IMPLEMENTATIONS.get(call.name)
        if impl is None:
            payload = {
                "status": "unknown_tool",
                "tool": call.name,
                "message": f"No implementation registered for tool '{call.name}'.",
            }
            return ToolResult(
                call_id=call.call_id,
                content=json.dumps(payload, ensure_ascii=False),
            )
        try:
            result = impl(call.arguments)
            return ToolResult(
                call_id=call.call_id,
                content=json.dumps(result, ensure_ascii=False, default=str),
            )
        except Exception as exc:  # noqa: BLE001 — loud failure return to LLM.
            logger.exception("Tool '%s' raised", call.name)
            payload = {
                "status": "failure",
                "tool": call.name,
                "error": str(exc),
            }
            return ToolResult(
                call_id=call.call_id,
                content=json.dumps(payload, ensure_ascii=False),
            )

    return _handler


def tool_names() -> list[str]:
    """Names registered in the current tool registry (testing convenience)."""
    return list(TOOL_IMPLEMENTATIONS.keys())


__all__ = [
    "TOOL_DESCRIPTORS",
    "TOOL_IMPLEMENTATIONS",
    "build_tool_handler",
    "tool_names",
]
