"""Delete a Google Calendar event."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from context import NoctusContext, noctus_context


class DeleteEventInput(BaseModel):
    calendar_id: str = Field(description="Google Calendar ID.")
    event_id: str = Field(description="The event's Google ID.")


class DeleteEventOutput(BaseModel):
    deleted: bool


def delete_event(
    payload: DeleteEventInput,
    ctx: NoctusContext | None = None,
) -> DeleteEventOutput:
    """Delete a Google Calendar event by ID."""
    if ctx is not None:
        return _impl(payload, ctx)
    with noctus_context() as owned_ctx:
        return _impl(payload, owned_ctx)


def _impl(payload: DeleteEventInput, ctx: NoctusContext) -> DeleteEventOutput:
    ctx.calendar.delete_event(payload.calendar_id, payload.event_id)
    return DeleteEventOutput(deleted=True)


def register(server: FastMCP) -> None:
    @server.tool(
        name="google.calendar.delete_event",
        description=delete_event.__doc__,
    )
    def _handler(payload: DeleteEventInput) -> DeleteEventOutput:
        return delete_event(payload)
