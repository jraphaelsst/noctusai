"""LLM tool registry for the Imobi Scheduling bot.

Defines the three initial tools the bot's LLM tool-loop may call (per
PROJECT.md §6 Phase 6 / Phase 7 — `lookup_property`, `propose_appointment`,
`confirm_appointment`). Cancellation + reschedule tools land in Phase 9.

**Wiring.** Each tool is shipped in two halves:

1. **OpenAI tool descriptor** (`TOOL_DESCRIPTORS`) — a list of dicts in
   the shape OpenAI's chat-completion API consumes via the ``tools=``
   kwarg. Names, parameters schema, descriptions all live here.
2. **Tool handler** (`build_tool_handler(scheduling_service=...)`) — a
   callable matching `noctusai_lib.domain.chatbot.ToolHandler` (i.e.
   `ToolCall -> ToolResult`) that dispatches by ``call.name`` to the
   per-tool implementation. When a `SchedulingService` is injected, the
   real implementations run; when omitted, the stubs from Phase 6 run
   (this preserves the test path that exercises the dispatch loop
   without DB / engine).

**MCP-tool shape** (per project §3 design principle 4) — these tools
SHOULD land as MCP tools under ``platform.business.<service>.<action>``
once ``projects/mcp-server-expansion/`` Phase 5 ships its business-tool
mounting infrastructure. Until then, the bot consumes the in-process
shape declared here, and the future MCP-server exposure imports these
same handlers (no duplicate definition). Flagged as deferred in the
project's `**Improvements:**` block — same shape as Phase 5's
``whatsapp_webhook`` standard-router-promotion deferral.

**Phase 7 — scheduling-engine wiring (LIVE).** `propose_appointment` and
`confirm_appointment` route through `SchedulingService` when wired,
calling `noctusai_lib.domain.scheduling.SchedulingEngine.candidate_slots`
under the hood. `lookup_property` does a real DB lookup. Stubs from
Phase 6 remain reachable via `build_tool_handler()` (no args) so the
existing dispatch-loop tests keep passing — the stub path is now a
"service-not-wired" fallback rather than a "not-yet-implemented" lie.

See `KB § PATTERNS/whatsapp-chatbot-seed.md § Tool registry shape` for
the canonical tool-handler convention.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional, TYPE_CHECKING

from noctusai_lib.domain.chatbot import ToolCall, ToolResult

if TYPE_CHECKING:
    from app.services.scheduling import SchedulingService

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


def _impl_lookup_property(
    arguments: dict[str, Any],
    scheduling_service: "SchedulingService",
) -> dict[str, Any]:
    """Live `lookup_property` via `SchedulingService.lookup_property`."""
    code = str(arguments.get("code", "")).strip()
    if not code:
        return {
            "status": "failure",
            "tool": "lookup_property",
            "error": "Missing required argument: code",
        }
    result = scheduling_service.lookup_property(code)
    if not result.found:
        return {
            "status": "not_found",
            "tool": "lookup_property",
            "code": code,
            "message": f"Imóvel com código '{code}' não encontrado.",
        }
    return {
        "status": "success",
        "tool": "lookup_property",
        "code": code,
        "property_id": result.property_id,
        "condominium_id": result.condominium_id,
        "condominium_name": result.condominium_name,
    }


def _impl_propose_appointment(
    arguments: dict[str, Any],
    scheduling_service: "SchedulingService",
) -> dict[str, Any]:
    """Live `propose_appointment` via the SchedulingEngine."""
    property_code = str(arguments.get("property_code", "")).strip()
    requested_date = arguments.get("requested_date")
    time_window = str(arguments.get("time_window", "any")).strip() or "any"

    if not property_code or not requested_date:
        return {
            "status": "failure",
            "tool": "propose_appointment",
            "error": "Missing required arguments: property_code, requested_date",
        }
    try:
        proposed = scheduling_service.propose_appointment(
            property_code=property_code,
            requested_date=requested_date,
            time_window=time_window,
        )
    except ValueError as exc:
        return {
            "status": "failure",
            "tool": "propose_appointment",
            "error": str(exc),
        }

    if not proposed:
        return {
            "status": "no_slots",
            "tool": "propose_appointment",
            "property_code": property_code,
            "requested_date": str(requested_date),
            "time_window": time_window,
            "message": (
                "Nenhum horário disponível na data e janela informadas. "
                "Sugira outra data ou janela ao corretor."
            ),
        }
    return {
        "status": "success",
        "tool": "propose_appointment",
        "property_code": property_code,
        "requested_date": str(requested_date),
        "time_window": time_window,
        "slots": [
            {
                "start_at": s.start_at,
                "end_at": s.end_at,
                "duration_minutes": s.duration_minutes,
                "score": s.score,
            }
            for s in proposed
        ],
    }


def _impl_confirm_appointment(
    arguments: dict[str, Any],
    scheduling_service: "SchedulingService",
) -> dict[str, Any]:
    """Live `confirm_appointment` — DB-insert path (Phase 7).

    Calendar event creation lands at Phase 8. Phase 7 confirms the
    in-DB row + the slot re-validation against current bookings.
    """
    property_code = str(arguments.get("property_code", "")).strip()
    services = arguments.get("services") or []
    start_at = arguments.get("start_at")
    end_at = arguments.get("end_at")

    if not property_code or not start_at or not end_at:
        return {
            "status": "failure",
            "tool": "confirm_appointment",
            "error": (
                "Missing required arguments: property_code, start_at, end_at"
            ),
        }

    try:
        result = scheduling_service.confirm_appointment(
            property_code=property_code,
            start_at=start_at,
            end_at=end_at,
            services=services if isinstance(services, list) else None,
        )
    except ValueError as exc:
        return {
            "status": "failure",
            "tool": "confirm_appointment",
            "error": str(exc),
        }

    if not result.created:
        return {
            "status": "conflict" if (result.reason or "").startswith("slot conflicts") else "failure",
            "tool": "confirm_appointment",
            "property_code": property_code,
            "reason": result.reason or "(unknown)",
        }
    return {
        "status": "success",
        "tool": "confirm_appointment",
        "property_code": property_code,
        "appointment_id": result.appointment_id,
        "start_at": start_at,
        "end_at": end_at,
        "services": services if isinstance(services, list) else [],
    }


def build_tool_handler(
    scheduling_service: Optional["SchedulingService"] = None,
) -> Callable[[ToolCall], ToolResult]:
    """Return a `ToolHandler` closure that dispatches by `ToolCall.name`.

    The closure matches `noctusai_lib.domain.chatbot.ToolHandler` —
    `Callable[[ToolCall], ToolResult]`. Unknown tool names return a
    structured `unknown_tool` response (not an exception); the
    dispatcher's audit writer wraps the call regardless of status.

    Args:
        scheduling_service: Optional `SchedulingService`. When supplied
            (the runtime path), `lookup_property` / `propose_appointment`
            / `confirm_appointment` route through the live engine.
            When omitted (legacy dispatch-loop tests), stubs run and
            return ``status='not_implemented'`` payloads.

    Returns:
        A handler. Tests can monkey-patch `TOOL_IMPLEMENTATIONS` map
        entries OR pass a stand-in `scheduling_service`.
    """

    def _resolve(name: str) -> Optional[ToolImpl]:
        # Service-bound implementations override the stub map when wired.
        # Lookup the LIVE map at every call to honor test-time monkeypatching
        # of `TOOL_IMPLEMENTATIONS` (see `test_handler_catches_implementation_exceptions`).
        if scheduling_service is not None:
            live = _LIVE_IMPLEMENTATIONS.get(name)
            if live is not None:
                return lambda args: live(args, scheduling_service)
        return TOOL_IMPLEMENTATIONS.get(name)

    def _handler(call: ToolCall) -> ToolResult:
        impl = _resolve(call.name)
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


# Live implementations expect ``(arguments, scheduling_service)`` — kept
# separate from `TOOL_IMPLEMENTATIONS` (which match the stub signature
# `(arguments)`) so the dispatch loop is uniform.
LiveToolImpl = Callable[[dict[str, Any], "SchedulingService"], dict[str, Any]]

_LIVE_IMPLEMENTATIONS: dict[str, LiveToolImpl] = {
    "lookup_property": _impl_lookup_property,
    "propose_appointment": _impl_propose_appointment,
    "confirm_appointment": _impl_confirm_appointment,
}


def tool_names() -> list[str]:
    """Names registered in the current tool registry (testing convenience)."""
    return list(TOOL_IMPLEMENTATIONS.keys())


__all__ = [
    "LiveToolImpl",
    "TOOL_DESCRIPTORS",
    "TOOL_IMPLEMENTATIONS",
    "build_tool_handler",
    "tool_names",
]
