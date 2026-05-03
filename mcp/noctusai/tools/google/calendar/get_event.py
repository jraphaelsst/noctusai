"""Fetch a single Google Calendar event."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from context import NoctusContext, noctus_context


class GetEventInput(BaseModel):
    calendar_id: str = Field(description="Google Calendar ID.")
    event_id: str = Field(description="The event's Google ID.")


class GetEventOutput(BaseModel):
    found: bool
    event_id: str | None
    html_link: str | None
    raw: dict[str, Any] | None


def get_event(
    payload: GetEventInput,
    ctx: NoctusContext | None = None,
) -> GetEventOutput:
    """Fetch a Google Calendar event by ID. Returns ``found=False`` if the event does not exist."""
    if ctx is not None:
        return _impl(payload, ctx)
    with noctus_context() as owned_ctx:
        return _impl(payload, owned_ctx)


def _impl(payload: GetEventInput, ctx: NoctusContext) -> GetEventOutput:
    event = ctx.calendar.get_event(payload.calendar_id, payload.event_id)
    if event is None:
        return GetEventOutput(found=False, event_id=None, html_link=None, raw=None)
    return GetEventOutput(
        found=True,
        event_id=event.event_id,
        html_link=event.html_link,
        raw=event.raw,
    )


def register(server: FastMCP) -> None:
    @server.tool(
        name="google.calendar.get_event",
        description=get_event.__doc__,
    )
    def _handler(payload: GetEventInput) -> GetEventOutput:
        return get_event(payload)
