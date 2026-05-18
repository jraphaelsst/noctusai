"""google.calendar.* tools — thin wrappers over the seed Calendar adapter.

Tools registered:
- google.calendar.create_event  — WRITE. Required `confirm: bool` gate +
  structured audit log on the side-effect.
- google.calendar.list_events   — READ. No confirm gate.

NO connector logic lives here beyond composition: the value objects,
adapter selection (Fake vs Real), and the Google v3 mapping all ship in
`noctusai_lib.integrations.google_calendar`. This module only:
  1. parses the Pydantic Input,
  2. picks Fake (no OAuth creds) vs Real (OAuth-configured) via the lib
     factory `get_calendar_adapter(resolver, tenant_id)`,
  3. enforces the confirm-then-execute gate + emits the audit log,
  4. shapes the Pydantic Output.
"""
from __future__ import annotations

import logging
from datetime import datetime

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.google_calendar import (
    CalendarCredentialResolver,
    CalendarCredentials,
    EventAttendee,
    EventInput,
    OAuthCalendarCredentials,
    get_calendar_adapter,
)

from _kit.errors import typed_error

from settings import GoogleConnectorSettings, get_settings
from schemas import (
    CreatedEventModel,
    CreateEventInput,
    CreateEventOutput,
    ListEventsInput,
    ListEventsOutput,
)

logger = logging.getLogger(__name__)

# A dedicated audit logger so write side-effects emit a structured,
# greppable line independent of the connector's general logging.
_audit = logging.getLogger("google.audit")


class _EnvOAuthResolver:
    """`CalendarCredentialResolver` backed by the connector's env/.env
    OAuth trio. Returns `OAuthCalendarCredentials` when the trio is
    present, else `None` (the lib factory then falls back to the Fake).

    Connector-side wiring is legitimate: `_kit` owns only generic
    plumbing; vendor credential resolution stays connector-side (same
    boundary vista draws with its calibration module)."""

    def __init__(self, settings: GoogleConnectorSettings) -> None:
        self._s = settings

    def get_credentials(
        self, tenant_id: str | None = None
    ) -> CalendarCredentials | None:
        if not self._s.oauth_configured:
            return None
        return OAuthCalendarCredentials(
            refresh_token=self._s.oauth_refresh_token,  # type: ignore[arg-type]
            client_id=self._s.oauth_client_id,  # type: ignore[arg-type]
            client_secret=self._s.oauth_client_secret,  # type: ignore[arg-type]
        )


def _adapter_and_kind():
    """Return (adapter, kind_str). 'real' when OAuth trio present (lib
    builds GoogleCalendarOAuthAdapter), else 'fake'."""
    s = get_settings()
    if s.oauth_configured:
        resolver: CalendarCredentialResolver = _EnvOAuthResolver(s)
        return get_calendar_adapter(resolver, tenant_id=None), "real"
    return get_calendar_adapter(), "fake"


# ─── Handlers ────────────────────────────────────────────────────────────


async def create_event(args: dict) -> dict:
    inp = CreateEventInput(**args)

    if not inp.confirm:
        # confirm-then-execute: refuse the side-effect, no mutation.
        return CreateEventOutput(created=None, adapter="unconfirmed").model_dump() | {
            "error": typed_error(
                PermissionError(
                    "google.calendar.create_event is a WRITE — re-call with "
                    "confirm=true to actually create the event."
                )
            )
        }

    adapter, kind = _adapter_and_kind()
    event = EventInput(
        summary=inp.summary,
        start_at=datetime.fromisoformat(inp.start_at),
        end_at=datetime.fromisoformat(inp.end_at),
        timezone=inp.timezone,
        description=inp.description,
        location=inp.location,
        attendees=[
            EventAttendee(email=a.email, display_name=a.display_name)
            for a in inp.attendees
        ],
        request_id=inp.request_id,
    )

    # Structured audit log BEFORE the side-effect (intent), then result.
    _audit.info(
        "AUDIT google.calendar.create_event adapter=%s calendar_id=%s "
        "summary=%r start=%s confirm=true",
        kind,
        inp.calendar_id,
        inp.summary,
        inp.start_at,
    )
    try:
        created = adapter.create_event(inp.calendar_id, event)
    except Exception as e:  # noqa: BLE001 — re-rendered as typed payload
        _audit.warning(
            "AUDIT google.calendar.create_event FAILED adapter=%s err=%s",
            kind,
            e,
        )
        return CreateEventOutput(created=None, adapter=kind).model_dump() | {
            "error": typed_error(e)
        }

    _audit.info(
        "AUDIT google.calendar.create_event OK adapter=%s event_id=%s",
        kind,
        created.event_id,
    )
    return CreateEventOutput(
        created=CreatedEventModel(
            event_id=created.event_id,
            html_link=created.html_link,
            raw=created.raw,
        ),
        adapter=kind,
    ).model_dump()


async def list_events(args: dict) -> dict:
    inp = ListEventsInput(**args)
    adapter, kind = _adapter_and_kind()
    try:
        events = adapter.list_events(
            inp.calendar_id,
            datetime.fromisoformat(inp.time_min),
            datetime.fromisoformat(inp.time_max),
        )
    except Exception as e:  # noqa: BLE001
        return ListEventsOutput(events=[], adapter=kind).model_dump() | {
            "error": typed_error(e)
        }
    return ListEventsOutput(
        events=[
            CreatedEventModel(
                event_id=ev.event_id, html_link=ev.html_link, raw=ev.raw
            )
            for ev in events
        ],
        adapter=kind,
    ).model_dump()


# ─── Registration ───────────────────────────────────────────────────────


HANDLERS = {
    "google.calendar.create_event": create_event,
    "google.calendar.list_events": list_events,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="google.calendar.create_event",
            description=(
                "Create a Google Calendar event. WRITE side-effect — you "
                "MUST pass confirm=true or the call is refused with a typed "
                "error and Calendar is left untouched. Uses the OAuth "
                "user-delegated adapter when the connector's OAuth trio is "
                "configured; otherwise an in-memory Fake (dev/test). The "
                "`adapter` field in the result tells you which ran."
            ),
            inputSchema=CreateEventInput.model_json_schema(),
        ),
        Tool(
            name="google.calendar.list_events",
            description=(
                "List Google Calendar events in [time_min, time_max]. "
                "Read-only — no confirm gate. Fake adapter when OAuth is "
                "unconfigured."
            ),
            inputSchema=ListEventsInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
