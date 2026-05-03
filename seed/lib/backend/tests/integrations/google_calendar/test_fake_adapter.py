"""FakeCalendarAdapter + mappers tests."""

from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.integrations.google_calendar import (
    EventAttendee,
    EventInput,
    FakeCalendarAdapter,
    event_to_google_body,
    google_body_to_created_event,
    parse_google_datetime,
)


def _event(start: datetime, end: datetime, **kwargs) -> EventInput:
    return EventInput(
        summary=kwargs.pop("summary", "Test event"),
        start_at=start,
        end_at=end,
        timezone=kwargs.pop("timezone", "America/Sao_Paulo"),
        **kwargs,
    )


def test_event_to_google_body_includes_required_fields() -> None:
    start = datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc)
    end = datetime(2026, 5, 12, 10, 30, tzinfo=timezone.utc)
    body = event_to_google_body(_event(start, end))

    assert body["summary"] == "Test event"
    assert body["start"]["dateTime"].startswith("2026-05-12T09:00:00")
    assert body["start"]["timeZone"] == "America/Sao_Paulo"
    assert body["end"]["dateTime"].startswith("2026-05-12T10:30:00")
    assert "description" not in body
    assert "attendees" not in body


def test_event_to_google_body_includes_attendees_and_optional_fields() -> None:
    start = datetime(2026, 5, 12, 9, 0)
    end = datetime(2026, 5, 12, 10, 30)
    body = event_to_google_body(
        _event(
            start,
            end,
            description="Notes",
            location="Room 1",
            attendees=[
                EventAttendee(email="a@x.com"),
                EventAttendee(email="b@x.com", display_name="Beta"),
            ],
        )
    )

    assert body["description"] == "Notes"
    assert body["location"] == "Room 1"
    assert body["attendees"] == [
        {"email": "a@x.com"},
        {"email": "b@x.com", "displayName": "Beta"},
    ]


def test_parse_google_datetime_round_trip() -> None:
    iso = "2026-05-12T09:00:00+00:00"
    parsed = parse_google_datetime(iso)
    assert parsed == datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc)


def test_fake_adapter_create_then_get_returns_same_event() -> None:
    adapter = FakeCalendarAdapter()
    event = _event(
        datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
    )

    created = adapter.create_event("primary", event)

    assert created.event_id  # non-empty
    assert created.html_link is not None
    assert created.raw["status"] == "confirmed"

    fetched = adapter.get_event("primary", created.event_id)
    assert fetched is not None
    assert fetched.event_id == created.event_id


def test_fake_adapter_get_returns_none_for_unknown_event() -> None:
    adapter = FakeCalendarAdapter()
    assert adapter.get_event("primary", "missing") is None


def test_fake_adapter_list_events_filters_by_time_window() -> None:
    adapter = FakeCalendarAdapter()
    base = datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc)
    in_window = adapter.create_event("primary", _event(base, base + timedelta(hours=1)))
    adapter.create_event(
        "primary",
        _event(base + timedelta(days=2), base + timedelta(days=2, hours=1)),
    )

    events = adapter.list_events(
        "primary",
        time_min=base - timedelta(hours=1),
        time_max=base + timedelta(hours=2),
    )

    assert [e.event_id for e in events] == [in_window.event_id]


def test_fake_adapter_delete_removes_event() -> None:
    adapter = FakeCalendarAdapter()
    created = adapter.create_event(
        "primary",
        _event(
            datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        ),
    )

    adapter.delete_event("primary", created.event_id)
    assert adapter.get_event("primary", created.event_id) is None


def test_fake_adapter_update_event_replaces_in_place_preserving_event_id() -> None:
    adapter = FakeCalendarAdapter()
    created = adapter.create_event(
        "primary",
        _event(
            datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        ),
    )

    moved = adapter.update_event(
        "primary",
        created.event_id,
        _event(
            datetime(2026, 5, 12, 11, 0, tzinfo=timezone.utc),
            datetime(2026, 5, 12, 12, 0, tzinfo=timezone.utc),
        ),
    )

    assert moved.event_id == created.event_id
    fetched = adapter.get_event("primary", created.event_id)
    assert fetched is not None
    assert fetched.raw["start"]["dateTime"].startswith("2026-05-12T11:00:00")


def test_fake_adapter_update_event_raises_for_unknown_event() -> None:
    adapter = FakeCalendarAdapter()

    with pytest.raises(KeyError):
        adapter.update_event(
            "primary",
            "missing-event-id",
            _event(
                datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
                datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
            ),
        )


def test_fake_adapter_preserves_request_id_for_idempotency() -> None:
    adapter = FakeCalendarAdapter()
    event = _event(
        datetime(2026, 5, 12, 9, 0, tzinfo=timezone.utc),
        datetime(2026, 5, 12, 10, 0, tzinfo=timezone.utc),
        request_id="appt-req-42",
    )

    created = adapter.create_event("primary", event)

    assert created.raw.get("x_request_id") == "appt-req-42"


def test_fake_adapter_supports_attendees_flag_defaults_false() -> None:
    """Service-account default — sibling parity. OAuth adapter (deferred)
    will set this True."""
    assert FakeCalendarAdapter().supports_attendees is False
    assert FakeCalendarAdapter(supports_attendees=True).supports_attendees is True
