"""List Google Calendar events in a time window."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from context import NoctusContext, noctus_context


class ListEventsInput(BaseModel):
    calendar_id: str = Field(description="Google Calendar ID.")
    time_min: datetime = Field(description="Lower bound of the time window (inclusive).")
    time_max: datetime = Field(description="Upper bound of the time window (exclusive).")


class EventOut(BaseModel):
    event_id: str
    html_link: str | None
    raw: dict[str, Any]


class ListEventsOutput(BaseModel):
    events: list[EventOut]


def list_events(
    payload: ListEventsInput,
    ctx: NoctusContext | None = None,
) -> ListEventsOutput:
    """List Google Calendar events between ``time_min`` and ``time_max``."""
    if ctx is not None:
        return _impl(payload, ctx)
    with noctus_context() as owned_ctx:
        return _impl(payload, owned_ctx)


def _impl(payload: ListEventsInput, ctx: NoctusContext) -> ListEventsOutput:
    events = ctx.calendar.list_events(
        payload.calendar_id,
        payload.time_min,
        payload.time_max,
    )
    return ListEventsOutput(
        events=[
            EventOut(event_id=e.event_id, html_link=e.html_link, raw=e.raw)
            for e in events
        ]
    )


def register(server: FastMCP) -> None:
    @server.tool(
        name="google.calendar.list_events",
        description=list_events.__doc__,
    )
    def _handler(payload: ListEventsInput) -> ListEventsOutput:
        return list_events(payload)
