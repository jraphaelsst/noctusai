"""Create a Google Calendar event."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from context import NoctusContext, noctus_context


class AttendeeInput(BaseModel):
    email: str = Field(description="Attendee email address.")
    display_name: str | None = Field(
        default=None, description="Optional display name."
    )


class CreateEventInput(BaseModel):
    calendar_id: str = Field(
        description="Google Calendar ID (e.g. 'primary' or a shared-calendar ID)."
    )
    summary: str = Field(description="Event title.")
    start_at: datetime = Field(description="Start datetime (timezone-aware).")
    end_at: datetime = Field(description="End datetime (timezone-aware).")
    timezone: str = Field(
        description="IANA timezone name, e.g. 'America/Sao_Paulo'."
    )
    description: str | None = Field(
        default=None, description="Optional event description / agenda."
    )
    location: str | None = Field(
        default=None, description="Optional location string."
    )
    attendees: list[AttendeeInput] = Field(
        default_factory=list,
        description=(
            "Attendees. Note: a service-account adapter cannot add attendees on "
            "personal Gmail calendars without Domain-Wide Delegation; use the "
            "OAuth adapter for that case."
        ),
    )
    request_id: str | None = Field(
        default=None,
        description=(
            "Optional Google idempotency key for events.insert (~24h replay window). "
            "Derive from a stable identifier (e.g. appointment_request.id) so retries "
            "don't double-create events."
        ),
    )


class CreateEventOutput(BaseModel):
    event_id: str
    html_link: str | None
    raw: dict[str, Any]


def create_event(
    payload: CreateEventInput,
    ctx: NoctusContext | None = None,
) -> CreateEventOutput:
    """Create a Google Calendar event on the given calendar."""
    if ctx is not None:
        return _impl(payload, ctx)
    with noctus_context() as owned_ctx:
        return _impl(payload, owned_ctx)


def _impl(payload: CreateEventInput, ctx: NoctusContext) -> CreateEventOutput:
    from noctusai_lib.integrations.google_calendar import EventAttendee, EventInput

    event = EventInput(
        summary=payload.summary,
        start_at=payload.start_at,
        end_at=payload.end_at,
        timezone=payload.timezone,
        description=payload.description,
        location=payload.location,
        attendees=[
            EventAttendee(email=a.email, display_name=a.display_name)
            for a in payload.attendees
        ],
        request_id=payload.request_id,
    )
    created = ctx.calendar.create_event(payload.calendar_id, event)
    return CreateEventOutput(
        event_id=created.event_id,
        html_link=created.html_link,
        raw=created.raw,
    )


def register(server: FastMCP) -> None:
    @server.tool(
        name="google.calendar.create_event",
        description=create_event.__doc__,
    )
    def _handler(payload: CreateEventInput) -> CreateEventOutput:
        return create_event(payload)
