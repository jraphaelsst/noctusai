"""LLM tool registry for the social-wiring ``scheduling`` module.

Absorbed from ``imobi-scheduling`` (Wave 2.3). Defines the five tools the
chatbot's LLM tool-loop may call: ``lookup_property``,
``propose_appointment``, ``confirm_appointment``, ``cancel_appointment``,
``reschedule_appointment``.

The handler closure matches ``noctusai_lib.domain.chatbot.ToolHandler``
(``Callable[[ToolCall], ToolResult]``) — consumed by the seed
``LLMDispatcher``. When a ``SchedulingService`` is injected the real
implementations run; without one the stubs run (preserves the
dispatch-loop test path).

See ``KB § PATTERNS/whatsapp-chatbot-seed.md § Tool registry shape``.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional, TYPE_CHECKING

from noctusai_lib.domain.chatbot import ToolCall, ToolResult

if TYPE_CHECKING:
    from app.modules.scheduling.engine import SchedulingService

logger = logging.getLogger(__name__)


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
    {
        "type": "function",
        "function": {
            "name": "cancel_appointment",
            "description": (
                "Cancela um agendamento existente. SÓ chame após o corretor "
                "confirmar explicitamente o cancelamento (use uma pergunta "
                "de confirmação como 'Confirma o cancelamento do agendamento "
                "em <data> <hora>?' ANTES de invocar esta ferramenta). "
                "Idempotente — agendamentos já cancelados retornam status "
                "informativo, não erro."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {
                        "type": "string",
                        "description": "UUID do agendamento a ser cancelado.",
                    },
                    "reason": {
                        "type": "string",
                        "description": (
                            "Motivo do cancelamento (texto livre vindo do "
                            "corretor — resumido pelo modelo quando longo)."
                        ),
                    },
                },
                "required": ["appointment_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "reschedule_appointment",
            "description": (
                "Reagenda um agendamento existente para uma nova data/hora. "
                "SÓ chame após o corretor confirmar EXPLICITAMENTE o novo "
                "horário (use uma pergunta de confirmação como 'Confirma "
                "mover o agendamento de <antigo> para <novo>?' ANTES de "
                "invocar). Re-valida o novo horário contra outras reservas "
                "antes de gravar — se conflitar, retorna conflict e sugere "
                "chamar propose_appointment novamente."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "appointment_id": {
                        "type": "string",
                        "description": "UUID do agendamento a ser reagendado.",
                    },
                    "new_start_at": {
                        "type": "string",
                        "description": "Novo início (ISO 8601 com timezone — America/Sao_Paulo).",
                    },
                    "new_end_at": {
                        "type": "string",
                        "description": "Novo fim (ISO 8601 com timezone — America/Sao_Paulo).",
                    },
                },
                "required": ["appointment_id", "new_start_at", "new_end_at"],
            },
        },
    },
]


ToolImpl = Callable[[dict[str, Any]], dict[str, Any]]


def _stub_lookup_property(arguments: dict[str, Any]) -> dict[str, Any]:
    code = arguments.get("code", "")
    logger.info("[stub] lookup_property called with code=%s", code)
    return {
        "status": "not_implemented",
        "tool": "lookup_property",
        "message": "Lookup property is not wired (no SchedulingService injected).",
        "echo": {"code": code},
    }


def _stub_propose_appointment(arguments: dict[str, Any]) -> dict[str, Any]:
    logger.info("[stub] propose_appointment called with %s", arguments)
    return {
        "status": "not_implemented",
        "tool": "propose_appointment",
        "message": "Propose appointment is not wired (no SchedulingService injected).",
        "echo": arguments,
    }


def _stub_confirm_appointment(arguments: dict[str, Any]) -> dict[str, Any]:
    logger.info("[stub] confirm_appointment called with %s", arguments)
    return {
        "status": "not_implemented",
        "tool": "confirm_appointment",
        "message": "Confirm appointment is not wired (no SchedulingService injected).",
        "echo": arguments,
    }


def _stub_cancel_appointment(arguments: dict[str, Any]) -> dict[str, Any]:
    logger.info("[stub] cancel_appointment called with %s", arguments)
    return {
        "status": "not_implemented",
        "tool": "cancel_appointment",
        "message": "Cancel appointment is not wired (no SchedulingService injected).",
        "echo": arguments,
    }


def _stub_reschedule_appointment(arguments: dict[str, Any]) -> dict[str, Any]:
    logger.info("[stub] reschedule_appointment called with %s", arguments)
    return {
        "status": "not_implemented",
        "tool": "reschedule_appointment",
        "message": "Reschedule appointment is not wired (no SchedulingService injected).",
        "echo": arguments,
    }


TOOL_IMPLEMENTATIONS: dict[str, ToolImpl] = {
    "lookup_property": _stub_lookup_property,
    "propose_appointment": _stub_propose_appointment,
    "confirm_appointment": _stub_confirm_appointment,
    "cancel_appointment": _stub_cancel_appointment,
    "reschedule_appointment": _stub_reschedule_appointment,
}


def _impl_lookup_property(
    arguments: dict[str, Any],
    scheduling_service: "SchedulingService",
) -> dict[str, Any]:
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
    property_code = str(arguments.get("property_code", "")).strip()
    services = arguments.get("services") or []
    start_at = arguments.get("start_at")
    end_at = arguments.get("end_at")

    if not property_code or not start_at or not end_at:
        return {
            "status": "failure",
            "tool": "confirm_appointment",
            "error": "Missing required arguments: property_code, start_at, end_at",
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


def _impl_cancel_appointment(
    arguments: dict[str, Any],
    scheduling_service: "SchedulingService",
) -> dict[str, Any]:
    appointment_id = str(arguments.get("appointment_id", "")).strip()
    reason = arguments.get("reason")
    if not appointment_id:
        return {
            "status": "failure",
            "tool": "cancel_appointment",
            "error": "Missing required argument: appointment_id",
        }

    result = scheduling_service.cancel_appointment(
        appointment_id=appointment_id,
        reason=reason if isinstance(reason, str) else None,
    )
    if not result.cancelled:
        reason_text = (result.reason or "").lower()
        status = "already_cancelled" if "status is 'cancelled'" in reason_text else (
            "not_found" if "appointment not found" in reason_text else "failure"
        )
        return {
            "status": status,
            "tool": "cancel_appointment",
            "appointment_id": appointment_id,
            "reason": result.reason or "(unknown)",
        }
    return {
        "status": "success",
        "tool": "cancel_appointment",
        "appointment_id": appointment_id,
        "calendar_deleted": result.calendar_deleted,
    }


def _impl_reschedule_appointment(
    arguments: dict[str, Any],
    scheduling_service: "SchedulingService",
) -> dict[str, Any]:
    appointment_id = str(arguments.get("appointment_id", "")).strip()
    new_start_at = arguments.get("new_start_at")
    new_end_at = arguments.get("new_end_at")

    if not appointment_id or not new_start_at or not new_end_at:
        return {
            "status": "failure",
            "tool": "reschedule_appointment",
            "error": "Missing required arguments: appointment_id, new_start_at, new_end_at",
        }

    try:
        result = scheduling_service.reschedule_appointment(
            appointment_id=appointment_id,
            new_start_at=new_start_at,
            new_end_at=new_end_at,
        )
    except ValueError as exc:
        return {
            "status": "failure",
            "tool": "reschedule_appointment",
            "error": str(exc),
        }

    if not result.rescheduled:
        reason_text = (result.reason or "").lower()
        if "conflicts with" in reason_text:
            status = "conflict"
        elif "appointment not found" in reason_text:
            status = "not_found"
        else:
            status = "failure"
        return {
            "status": status,
            "tool": "reschedule_appointment",
            "appointment_id": appointment_id,
            "reason": result.reason or "(unknown)",
        }
    return {
        "status": "success",
        "tool": "reschedule_appointment",
        "appointment_id": appointment_id,
        "new_start_at": new_start_at,
        "new_end_at": new_end_at,
        "calendar_updated": result.calendar_updated,
    }


def build_tool_handler(
    scheduling_service: Optional["SchedulingService"] = None,
) -> Callable[[ToolCall], ToolResult]:
    """Return a ``ToolHandler`` closure that dispatches by ``ToolCall.name``.

    When ``scheduling_service`` is supplied (runtime path) the live
    implementations run; otherwise the stubs run. Unknown tool names
    return a structured ``unknown_tool`` response (not an exception).
    """

    def _resolve(name: str) -> Optional[ToolImpl]:
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


LiveToolImpl = Callable[[dict[str, Any], "SchedulingService"], dict[str, Any]]

_LIVE_IMPLEMENTATIONS: dict[str, LiveToolImpl] = {
    "lookup_property": _impl_lookup_property,
    "propose_appointment": _impl_propose_appointment,
    "confirm_appointment": _impl_confirm_appointment,
    "cancel_appointment": _impl_cancel_appointment,
    "reschedule_appointment": _impl_reschedule_appointment,
}


def tool_names() -> list[str]:
    return list(TOOL_IMPLEMENTATIONS.keys())


__all__ = [
    "LiveToolImpl",
    "TOOL_DESCRIPTORS",
    "TOOL_IMPLEMENTATIONS",
    "build_tool_handler",
    "tool_names",
]
