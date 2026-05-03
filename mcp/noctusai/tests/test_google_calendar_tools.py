"""Tests for ``google.calendar.*`` MCP tools.

Inject a ``FakeCalendarAdapter`` via ``NoctusContext`` so tests run
without real Google credentials.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from context import NoctusContext  # noqa: E402
from noctusai_lib.integrations.google_calendar import FakeCalendarAdapter  # noqa: E402
from tools.google.calendar.create_event import (  # noqa: E402
    AttendeeInput,
    CreateEventInput,
    create_event,
)
from tools.google.calendar.delete_event import DeleteEventInput, delete_event  # noqa: E402
from tools.google.calendar.get_event import GetEventInput, get_event  # noqa: E402
from tools.google.calendar.list_events import ListEventsInput, list_events  # noqa: E402

CAL_ID = "primary"
TZ = "America/Sao_Paulo"


def _ctx() -> NoctusContext:
    return NoctusContext(calendar=FakeCalendarAdapter(supports_attendees=True))


def test_create_event_returns_id_and_link():
    ctx = _ctx()
    payload = CreateEventInput(
        calendar_id=CAL_ID,
        summary="Vistoria 9h",
        start_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
        end_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
        timezone=TZ,
        description="Inspeção de imóvel",
        location="Rua A, 100",
        attendees=[AttendeeInput(email="cliente@example.com")],
    )
    out = create_event(payload, ctx=ctx)

    assert out.event_id
    assert out.html_link and out.html_link.startswith("https://calendar.google.com/")
    assert out.raw["status"] == "confirmed"


def test_create_then_get_event_round_trip():
    ctx = _ctx()
    created = create_event(
        CreateEventInput(
            calendar_id=CAL_ID,
            summary="X",
            start_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            timezone=TZ,
        ),
        ctx=ctx,
    )

    fetched = get_event(
        GetEventInput(calendar_id=CAL_ID, event_id=created.event_id), ctx=ctx
    )
    assert fetched.found is True
    assert fetched.event_id == created.event_id


def test_get_event_returns_not_found_for_missing_id():
    ctx = _ctx()
    out = get_event(
        GetEventInput(calendar_id=CAL_ID, event_id="does-not-exist"), ctx=ctx
    )
    assert out.found is False
    assert out.event_id is None


def test_list_events_returns_inserted_events_in_window():
    ctx = _ctx()
    create_event(
        CreateEventInput(
            calendar_id=CAL_ID,
            summary="A",
            start_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            timezone=TZ,
        ),
        ctx=ctx,
    )
    create_event(
        CreateEventInput(
            calendar_id=CAL_ID,
            summary="B",
            start_at=datetime(2026, 6, 1, 11, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
            timezone=TZ,
        ),
        ctx=ctx,
    )

    out = list_events(
        ListEventsInput(
            calendar_id=CAL_ID,
            time_min=datetime(2026, 6, 1, 0, 0, tzinfo=timezone.utc),
            time_max=datetime(2026, 6, 2, 0, 0, tzinfo=timezone.utc),
        ),
        ctx=ctx,
    )

    assert len(out.events) == 2


def test_delete_event_removes_event():
    ctx = _ctx()
    created = create_event(
        CreateEventInput(
            calendar_id=CAL_ID,
            summary="To delete",
            start_at=datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc),
            timezone=TZ,
        ),
        ctx=ctx,
    )

    out = delete_event(
        DeleteEventInput(calendar_id=CAL_ID, event_id=created.event_id), ctx=ctx
    )
    assert out.deleted is True

    after = get_event(
        GetEventInput(calendar_id=CAL_ID, event_id=created.event_id), ctx=ctx
    )
    assert after.found is False
