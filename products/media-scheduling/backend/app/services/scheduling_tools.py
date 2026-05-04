"""LLM tool handlers + dispatcher integration.

INTEGRATION CONTRACT (Engineer C consumes):

    from app.services.scheduling_tools import register_scheduling_tools
    register_scheduling_tools(dispatcher, context_provider=lambda: ctx)

After registration, `dispatcher.tool_payload` carries the OpenAI-shaped
`tools=[{type:"function",...}, ...]` list and `dispatcher.tool_handler`
carries the `Callable[[ToolCall], ToolResult]` matching the seed
`LLMDispatcher.reply(tools=, tool_handler=)` seam.

Per-tool handlers satisfy the in-product `SchedulingToolHandler` Protocol:
- `name` (str)
- `description` (str)
- `parameters` (JSON-Schema dict)
- `__call__(args: dict[str, Any], context: ToolContext) -> ToolResult`

The seed `ToolHandler` type alias is `Callable[[ToolCall], ToolResult]`
(per-call, no name/description/parameters). The richer per-tool object
shape lives here because the registry needs it to build the OpenAI
`tools=[...]` payload — only the consumer knows that shape; the seed
dispatcher is provider-agnostic at the loop-mechanics level.

Today's handlers (ported from
`whatsapp-google-scheduling/app/services/openai/tools/`):
- `propose_appointment` — generate candidate slots for a property+date.
- `confirm_appointment` — book a slot (Google Calendar + DB row + WAHA
  out-bound is Engineer C's worker's follow-up; this handler returns the
  decision payload).
- `cancel_appointment` — delete a scheduled appointment.
- `find_authorized_user` — look up a user by phone for LID resolution.
- `lookup_property` — verify a property code exists (kept from source).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date as date_cls, datetime
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from noctusai_lib.domain.chatbot import LLMDispatcher, ToolCall, ToolResult
from noctusai_lib.domain.scheduling import BlockedInterval

from app.services.calendar_writer import CalendarWriter, build_event_input
from app.services.condominium_travel import default_scheduling_rules
from app.services.crew_assignment import pick_crew_for_services
from app.services.routing_lookup import RoutingLookup
from app.services.scheduling_adapters import make_scheduling_engine

if TYPE_CHECKING:
    from supabase import Client

logger = logging.getLogger(__name__)

MAX_CANDIDATES_RETURNED = 6


# ---------------------------------------------------------------------------
# Context object — what every tool handler needs to do its job
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ToolContext:
    """Per-tick bundle the worker (Engineer C) populates and passes via
    a `context_provider` closure into `register_scheduling_tools`.

    `org_id` is the SSO tenant id (used by calendar credential resolver).
    `caller_phone` is the WhatsApp phone of the user driving the
    conversation; tool handlers gate on `find_authorized_user` to populate
    `caller_user_id`. `caller_user_id` is None for unauthorized callers
    (the worker should reject confirm/cancel before calling those tools,
    but the handlers double-check defensively).
    """

    supabase: "Client"
    calendar_writer: CalendarWriter
    routing_lookup: RoutingLookup
    timezone_name: str
    org_id: str | None = None
    caller_phone: str | None = None
    caller_user_id: int | None = None
    conversation_id: str | None = None


# ---------------------------------------------------------------------------
# Handler Protocol — each tool satisfies this
# ---------------------------------------------------------------------------


@runtime_checkable
class SchedulingToolHandler(Protocol):
    """Per-tool object the registry collects. Engineer C's worker never
    instantiates these directly — it goes through `register_scheduling_tools`."""

    name: str
    description: str
    parameters: dict[str, Any]

    def __call__(
        self, args: dict[str, Any], context: ToolContext
    ) -> ToolResult: ...


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok(call_id: str, payload: dict[str, Any]) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        content=json.dumps(payload, ensure_ascii=False, default=str),
    )


def _err(call_id: str, code: str, **extra: Any) -> ToolResult:
    payload = {"error": code, **extra}
    return ToolResult(
        call_id=call_id,
        content=json.dumps(payload, ensure_ascii=False, default=str),
    )


def _fetch_property_by_code(
    supabase: "Client", code: str
) -> dict[str, Any] | None:
    try:
        response = (
            supabase.schema("media_scheduling")
            .table("properties")
            .select("id, code, condominium_id, unit, address_notes, active")
            .eq("code", code)
            .eq("active", True)
            .single()
            .execute()
        )
    except Exception:
        logger.warning("Property lookup failed for code=%s", code, exc_info=True)
        return None
    return response.data if response is not None else None


def _fetch_condominium(
    supabase: "Client", condo_id: int
) -> dict[str, Any] | None:
    try:
        response = (
            supabase.schema("media_scheduling")
            .table("condominiums")
            .select("id, name, address, latitude, longitude, active")
            .eq("id", condo_id)
            .single()
            .execute()
        )
    except Exception:
        logger.warning("Condominium lookup failed id=%s", condo_id, exc_info=True)
        return None
    return response.data if response is not None else None


def _fetch_existing_intervals_for_date(
    supabase: "Client", target_date: date_cls
) -> list[BlockedInterval]:
    """All scheduled appointments on `target_date` as seed `BlockedInterval`s.

    Re-queried per scheduling pass (source repo convention — slot
    landscape can shift between propose and confirm).
    """
    start_of_day = datetime.combine(target_date, datetime.min.time()).isoformat()
    next_day = datetime.combine(target_date, datetime.max.time()).isoformat()
    try:
        response = (
            supabase.schema("media_scheduling")
            .table("appointments")
            .select("start_at, end_at, condominium_id, status")
            .eq("status", "scheduled")
            .gte("start_at", start_of_day)
            .lte("start_at", next_day)
            .execute()
        )
    except Exception:
        logger.warning(
            "Existing-intervals fetch failed date=%s", target_date, exc_info=True
        )
        return []

    rows = response.data or []
    intervals: list[BlockedInterval] = []
    for row in rows:
        try:
            intervals.append(
                BlockedInterval(
                    start=datetime.fromisoformat(row["start_at"]),
                    end=datetime.fromisoformat(row["end_at"]),
                    location_id=int(row["condominium_id"]),
                )
            )
        except (KeyError, ValueError, TypeError):
            logger.warning("Skipping malformed appointment row %r", row)
    return intervals


# ---------------------------------------------------------------------------
# Tool handlers
# ---------------------------------------------------------------------------


@dataclass
class ProposeAppointment:
    name: str = "propose_appointment"
    description: str = (
        "Generate valid candidate slots for a content production appointment "
        "on a given date for a given property. Respects working hours, "
        "lunch blocking, same-condo vs different-condo duration, and travel-time "
        "buffers between back-to-back appointments. NEVER invent slots — always "
        "call this tool to get valid options before offering them to the user."
    )
    parameters: dict[str, Any] = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "property_code": {
                    "type": "string",
                    "description": "Property code, e.g. ONE0007.",
                },
                "requested_date": {
                    "type": "string",
                    "description": "ISO 8601 date (YYYY-MM-DD), e.g. 2026-05-12.",
                },
                "time_window": {
                    "type": "string",
                    "enum": ["morning", "afternoon"],
                    "description": "Optional: agent's preferred half of the day.",
                },
            },
            "required": ["property_code", "requested_date"],
            "additionalProperties": False,
        }
    )

    def __call__(
        self, args: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        call_id = args.get("__call_id", "")
        property_code = (args.get("property_code") or "").strip().upper()
        if not property_code:
            return _err(call_id, "missing_property_code")

        try:
            requested_date = date_cls.fromisoformat(args["requested_date"])
        except (KeyError, ValueError, TypeError):
            return _err(call_id, "invalid_date", value=args.get("requested_date"))

        time_window = args.get("time_window")
        prop = _fetch_property_by_code(context.supabase, property_code)
        if prop is None:
            return _err(call_id, "property_not_found", code=property_code)

        rules = default_scheduling_rules(context.timezone_name)
        engine = make_scheduling_engine(rules=rules, routing_lookup=context.routing_lookup)
        existing = _fetch_existing_intervals_for_date(
            context.supabase, requested_date
        )
        slots = engine.candidate_slots(
            requested_date=requested_date,
            target_location_id=int(prop["condominium_id"]),
            existing_intervals=existing,
            window_name=time_window,
        )

        return _ok(
            call_id,
            {
                "property_code": property_code,
                "requested_date": requested_date.isoformat(),
                "time_window": time_window,
                "candidate_count": len(slots),
                "candidates": [
                    {
                        "start_at": s.start_at.isoformat(),
                        "end_at": s.end_at.isoformat(),
                        "duration_minutes": s.duration_minutes,
                        "score": s.score,
                    }
                    for s in slots[:MAX_CANDIDATES_RETURNED]
                ],
            },
        )


@dataclass
class ConfirmAppointment:
    name: str = "confirm_appointment"
    description: str = (
        "Book a previously-proposed slot: validates the slot is still available, "
        "auto-assigns crew by skill match, creates the Google Calendar event, "
        "writes the appointment row, and returns the booking details. Only call "
        "AFTER the user has explicitly confirmed property + services + start/end."
    )
    parameters: dict[str, Any] = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "property_code": {"type": "string"},
                "services": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of service-type names, e.g. ['photos','videos'].",
                },
                "start_at": {
                    "type": "string",
                    "description": "ISO 8601 datetime with tz offset; must match a propose_appointment slot.",
                },
                "end_at": {"type": "string"},
                "notes": {"type": "string"},
            },
            "required": ["property_code", "services", "start_at", "end_at"],
            "additionalProperties": False,
        }
    )

    def __call__(
        self, args: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        call_id = args.get("__call_id", "")
        if context.caller_user_id is None:
            return _err(call_id, "unauthorized_user")

        property_code = (args.get("property_code") or "").strip().upper()
        if not property_code:
            return _err(call_id, "missing_property_code")

        services = args.get("services") or []
        if not services:
            return _err(call_id, "missing_services")

        try:
            start_at = datetime.fromisoformat(args["start_at"])
            end_at = datetime.fromisoformat(args["end_at"])
        except (KeyError, ValueError, TypeError):
            return _err(
                call_id,
                "invalid_datetime",
                values=[args.get("start_at"), args.get("end_at")],
            )
        if end_at <= start_at:
            return _err(call_id, "end_at_not_after_start_at")

        prop = _fetch_property_by_code(context.supabase, property_code)
        if prop is None:
            return _err(call_id, "property_not_found", code=property_code)

        # Idempotency check — same (property, start_at, scheduled).
        existing_resp = (
            context.supabase.schema("media_scheduling")
            .table("appointments")
            .select("id, google_calendar_event_id, start_at, end_at")
            .eq("property_id", int(prop["id"]))
            .eq("start_at", start_at.isoformat())
            .eq("status", "scheduled")
            .execute()
        )
        existing_rows = existing_resp.data or []
        if existing_rows:
            existing = existing_rows[0]
            return _ok(
                call_id,
                {
                    "already_scheduled": True,
                    "appointment_id": existing["id"],
                    "event_id": existing.get("google_calendar_event_id"),
                    "property_code": property_code,
                    "start_at": existing["start_at"],
                    "end_at": existing["end_at"],
                },
            )

        # Re-validate slot against current calendar state (source convention).
        rules = default_scheduling_rules(context.timezone_name)
        engine = make_scheduling_engine(rules=rules, routing_lookup=context.routing_lookup)
        existing_intervals = _fetch_existing_intervals_for_date(
            context.supabase, start_at.date()
        )
        slots = engine.candidate_slots(
            requested_date=start_at.date(),
            target_location_id=int(prop["condominium_id"]),
            existing_intervals=existing_intervals,
        )
        if not any(s.start_at == start_at and s.end_at == end_at for s in slots):
            return _err(
                call_id,
                "slot_unavailable",
                property_code=property_code,
                requested_start_at=start_at.isoformat(),
                requested_end_at=end_at.isoformat(),
                current_candidates=[
                    {
                        "start_at": s.start_at.isoformat(),
                        "end_at": s.end_at.isoformat(),
                        "duration_minutes": s.duration_minutes,
                    }
                    for s in slots[:MAX_CANDIDATES_RETURNED]
                ],
            )

        condo = _fetch_condominium(context.supabase, int(prop["condominium_id"]))
        if condo is None:
            return _err(call_id, "condominium_missing")

        crew = pick_crew_for_services(context.supabase, services)
        if crew is None:
            return _err(
                call_id,
                "no_crew_available_for_services",
                requested_services=list(services),
            )

        # Build calendar event.
        event = build_event_input(
            summary=f"{', '.join(services)} — {property_code} ({condo['name']})",
            start_at=start_at,
            end_at=end_at,
            timezone=context.timezone_name,
            description=args.get("notes"),
            location=condo.get("address"),
        )
        try:
            created = context.calendar_writer.create_event(event)
        except Exception as exc:
            logger.exception("Calendar create_event failed")
            return _err(call_id, "calendar_create_failed", message=str(exc))

        # Persist the appointment row.
        try:
            insert_resp = (
                context.supabase.schema("media_scheduling")
                .table("appointments")
                .insert(
                    {
                        "google_calendar_event_id": created.event_id,
                        "start_at": start_at.isoformat(),
                        "end_at": end_at.isoformat(),
                        "property_id": int(prop["id"]),
                        "condominium_id": int(condo["id"]),
                        "status": "scheduled",
                    }
                )
                .execute()
            )
        except Exception as exc:
            logger.exception("Appointment insert failed; calendar event was created")
            return _err(
                call_id,
                "appointment_insert_failed",
                event_id=created.event_id,
                message=str(exc),
            )

        appointment_row = (insert_resp.data or [{}])[0]
        return _ok(
            call_id,
            {
                "appointment_id": appointment_row.get("id"),
                "event_id": created.event_id,
                "html_link": created.html_link,
                "crew_name": crew.name,
                "crew_phone": crew.phone_number,
            },
        )


@dataclass
class CancelAppointment:
    name: str = "cancel_appointment"
    description: str = (
        "Cancel a scheduled appointment by id: deletes the Google Calendar "
        "event and marks the appointment row status='canceled'."
    )
    parameters: dict[str, Any] = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "appointment_id": {
                    "type": "integer",
                    "description": "Numeric appointment id (from previous propose/confirm).",
                },
            },
            "required": ["appointment_id"],
            "additionalProperties": False,
        }
    )

    def __call__(
        self, args: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        call_id = args.get("__call_id", "")
        if context.caller_user_id is None:
            return _err(call_id, "unauthorized_user")

        try:
            appointment_id = int(args["appointment_id"])
        except (KeyError, ValueError, TypeError):
            return _err(call_id, "invalid_appointment_id")

        try:
            response = (
                context.supabase.schema("media_scheduling")
                .table("appointments")
                .select("id, google_calendar_event_id, status")
                .eq("id", appointment_id)
                .single()
                .execute()
            )
        except Exception:
            logger.warning("Appointment lookup failed id=%s", appointment_id, exc_info=True)
            return _err(call_id, "appointment_not_found", appointment_id=appointment_id)

        row = response.data if response is not None else None
        if row is None:
            return _err(call_id, "appointment_not_found", appointment_id=appointment_id)
        if row.get("status") != "scheduled":
            return _err(
                call_id,
                "appointment_not_cancelable",
                appointment_id=appointment_id,
                current_status=row.get("status"),
            )

        event_id = row.get("google_calendar_event_id")
        if event_id:
            try:
                context.calendar_writer.delete_event(event_id)
            except Exception:
                logger.warning(
                    "Calendar delete_event failed for event_id=%s; proceeding to mark canceled",
                    event_id,
                    exc_info=True,
                )

        try:
            (
                context.supabase.schema("media_scheduling")
                .table("appointments")
                .update({"status": "canceled"})
                .eq("id", appointment_id)
                .execute()
            )
        except Exception as exc:
            logger.exception("Appointment status update failed")
            return _err(call_id, "appointment_update_failed", message=str(exc))

        return _ok(
            call_id,
            {"appointment_id": appointment_id, "status": "canceled"},
        )


@dataclass
class FindAuthorizedUser:
    name: str = "find_authorized_user"
    description: str = (
        "Look up an authorized user by phone number. Returns the user's "
        "id, name, role, and active flag — or found=false if no row matches."
    )
    parameters: dict[str, Any] = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "phone": {
                    "type": "string",
                    "description": "Phone number in international format, e.g. +5511999998888.",
                },
            },
            "required": ["phone"],
            "additionalProperties": False,
        }
    )

    def __call__(
        self, args: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        call_id = args.get("__call_id", "")
        phone = (args.get("phone") or "").strip()
        if not phone:
            return _err(call_id, "missing_phone")

        try:
            response = (
                context.supabase.schema("media_scheduling")
                .table("authorized_users")
                .select("id, name, role, phone_number, email, active")
                .eq("phone_number", phone)
                .single()
                .execute()
            )
        except Exception:
            return _ok(call_id, {"found": False, "phone": phone})

        row = response.data if response is not None else None
        if row is None:
            return _ok(call_id, {"found": False, "phone": phone})

        return _ok(
            call_id,
            {
                "found": True,
                "user_id": row["id"],
                "name": row.get("name"),
                "role": row.get("role"),
                "active": row.get("active"),
            },
        )


@dataclass
class LookupProperty:
    name: str = "lookup_property"
    description: str = (
        "Verify a property code exists and return its condominium info. "
        "ALWAYS call this before discussing or confirming any appointment."
    )
    parameters: dict[str, Any] = field(
        default_factory=lambda: {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Property code, normalized to uppercase before lookup.",
                },
            },
            "required": ["code"],
            "additionalProperties": False,
        }
    )

    def __call__(
        self, args: dict[str, Any], context: ToolContext
    ) -> ToolResult:
        call_id = args.get("__call_id", "")
        raw = (args.get("code") or "").strip()
        if not raw:
            return _ok(call_id, {"found": False, "error": "missing_code"})
        code = raw.upper()

        prop = _fetch_property_by_code(context.supabase, code)
        if prop is None:
            return _ok(call_id, {"found": False, "code": code})
        condo = _fetch_condominium(context.supabase, int(prop["condominium_id"]))
        return _ok(
            call_id,
            {
                "found": True,
                "code": prop["code"],
                "unit": prop.get("unit"),
                "address_notes": prop.get("address_notes"),
                "active": prop.get("active"),
                "condominium": (
                    {
                        "id": condo["id"],
                        "name": condo["name"],
                        "address": condo["address"],
                        "active": condo.get("active"),
                        "has_coordinates": (
                            condo.get("latitude") is not None
                            and condo.get("longitude") is not None
                        ),
                    }
                    if condo
                    else None
                ),
            },
        )


# ---------------------------------------------------------------------------
# Registry + dispatcher integration
# ---------------------------------------------------------------------------


def all_scheduling_tools() -> list[SchedulingToolHandler]:
    """Default scheduling tool roster."""
    return [
        ProposeAppointment(),
        ConfirmAppointment(),
        CancelAppointment(),
        FindAuthorizedUser(),
        LookupProperty(),
    ]


def to_openai_tool_payload(
    tools: list[SchedulingToolHandler],
) -> list[dict[str, Any]]:
    """Build the OpenAI `tools=[...]` payload from the per-tool handlers."""
    return [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.parameters,
            },
        }
        for t in tools
    ]


def make_dispatcher_handler(
    tools: list[SchedulingToolHandler],
    context_provider: Callable[[], ToolContext],
) -> Callable[[ToolCall], ToolResult]:
    """Wrap the per-tool handlers into the seed `LLMDispatcher` ``tool_handler``
    seam (a single `Callable[[ToolCall], ToolResult]`).

    `context_provider` is a closure the worker (Engineer C) supplies; it
    returns the per-tick `ToolContext` (carries the active supabase client,
    calendar writer, routing lookup, caller phone/user_id, conversation_id,
    org_id, timezone). Re-evaluated on EACH tool call so per-call state
    (caller_user_id resolved mid-loop) is fresh.
    """
    by_name: dict[str, SchedulingToolHandler] = {t.name: t for t in tools}

    def handler(call: ToolCall) -> ToolResult:
        tool = by_name.get(call.name)
        if tool is None:
            return ToolResult(
                call_id=call.call_id,
                content=json.dumps({"error": "unknown_tool", "name": call.name}),
            )
        # Pass call_id into the args bag so the per-tool _ok / _err helpers
        # can stamp it onto the ToolResult without a second parameter.
        args = dict(call.arguments or {})
        args["__call_id"] = call.call_id
        try:
            return tool(args, context_provider())
        except Exception as exc:
            logger.exception("Tool %s raised", call.name)
            return ToolResult(
                call_id=call.call_id,
                content=json.dumps(
                    {"error": "tool_exception", "message": str(exc)}
                ),
            )

    return handler


def register_scheduling_tools(
    dispatcher: LLMDispatcher,
    context_provider: Callable[[], ToolContext] | None = None,
    tools: list[SchedulingToolHandler] | None = None,
) -> None:
    """Wire the scheduling tool registry onto the seed LLM dispatcher.

    INTEGRATION POINT for Engineer C — call once at worker startup.
    After this call, the dispatcher carries:

      * ``dispatcher.tool_payload`` — list[dict] OpenAI tools= payload.
      * ``dispatcher.tool_handler`` — Callable[[ToolCall], ToolResult]
        ready to pass into `dispatcher.reply(messages, tools=
        dispatcher.tool_payload, tool_handler=dispatcher.tool_handler,
        audit_writer=...)`.
      * ``dispatcher.tool_registry`` — the underlying handler list (for
        introspection / admin views).

    `context_provider` MAY be None at registration time (Engineer C might
    register before the worker has the per-tick context shape resolved).
    In that case the dispatcher.tool_handler will refuse calls until
    `register_scheduling_tools` is re-called with a real provider — keeps
    the contract symmetric with the brief's "stable contract, not stable
    timing" framing.
    """
    roster = tools if tools is not None else all_scheduling_tools()
    dispatcher.tool_payload = to_openai_tool_payload(roster)  # type: ignore[attr-defined]
    dispatcher.tool_registry = roster  # type: ignore[attr-defined]

    if context_provider is None:
        def _refuse(call: ToolCall) -> ToolResult:
            return ToolResult(
                call_id=call.call_id,
                content=json.dumps(
                    {
                        "error": "tool_context_unavailable",
                        "message": (
                            "register_scheduling_tools called without "
                            "context_provider — wire one before invoking."
                        ),
                    }
                ),
            )

        dispatcher.tool_handler = _refuse  # type: ignore[attr-defined]
        return

    dispatcher.tool_handler = make_dispatcher_handler(  # type: ignore[attr-defined]
        roster, context_provider
    )
