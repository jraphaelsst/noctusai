"""Tests for the Google integrations ported from whatsapp-scheduling.

The mocked tests cover wire-shape correctness (request bodies, response
parsing, factory selection logic) without hitting the real APIs.
End-to-end validation against live Google services lives in the
SESSION-NOTES doc + the manual validation log; mocked tests guard
against regressions that would silently corrupt those live calls.
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from app.services.calendar import (
    CALENDAR_PROVIDER,
    EventAttendee,
    EventInput,
    FakeCalendarAdapter,
)
from app.services.calendar.mappers import (
    event_to_google_body,
    google_body_to_created_event,
    parse_google_datetime,
)
from app.services.routing import (
    Coordinates,
    StaticRoutingAdapter,
    TravelEstimate,
)
from app.services.routing.mappers import build_routes_request, parse_routes_response


# ─── Calendar mappers ─────────────────────────────────────────────────
class TestCalendarMappers:
    def test_event_to_google_body_minimal(self):
        event = EventInput(
            summary="Visita ao ONE5555",
            start_at=datetime(2026, 5, 15, 14, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc),
            timezone="America/Sao_Paulo",
        )
        body = event_to_google_body(event)
        assert body["summary"] == "Visita ao ONE5555"
        assert body["start"]["timeZone"] == "America/Sao_Paulo"
        assert body["end"]["dateTime"] == "2026-05-15T15:00:00+00:00"
        assert "attendees" not in body
        assert "location" not in body

    def test_event_to_google_body_with_attendees_and_location(self):
        event = EventInput(
            summary="Reuniao",
            start_at=datetime(2026, 5, 15, 14, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc),
            timezone="America/Sao_Paulo",
            description="Pauta inicial",
            location="Av Paulista 1000",
            attendees=[
                EventAttendee(email="a@example.com"),
                EventAttendee(email="b@example.com", display_name="Bee"),
            ],
        )
        body = event_to_google_body(event)
        assert body["description"] == "Pauta inicial"
        assert body["location"] == "Av Paulista 1000"
        assert len(body["attendees"]) == 2
        assert body["attendees"][1]["displayName"] == "Bee"

    def test_google_body_to_created_event(self):
        body = {
            "id": "evt_abc",
            "htmlLink": "https://calendar.google.com/calendar/event?eid=evt_abc",
            "summary": "x",
        }
        created = google_body_to_created_event(body)
        assert created.event_id == "evt_abc"
        assert created.html_link == "https://calendar.google.com/calendar/event?eid=evt_abc"
        assert created.raw["summary"] == "x"


# ─── FakeCalendarAdapter ──────────────────────────────────────────────
class TestFakeCalendarAdapter:
    def test_create_and_get(self):
        adapter = FakeCalendarAdapter()
        event = EventInput(
            summary="Test",
            start_at=datetime(2026, 5, 15, 14, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc),
            timezone="America/Sao_Paulo",
        )
        created = adapter.create_event("primary", event)
        fetched = adapter.get_event("primary", created.event_id)
        assert fetched is not None
        assert fetched.event_id == created.event_id

    def test_list_filters_by_time_range(self):
        adapter = FakeCalendarAdapter()
        e1 = EventInput(
            summary="In range",
            start_at=datetime(2026, 5, 15, 14, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc),
            timezone="UTC",
        )
        e2 = EventInput(
            summary="Out of range",
            start_at=datetime(2026, 6, 1, 14, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 6, 1, 15, 0, tzinfo=timezone.utc),
            timezone="UTC",
        )
        adapter.create_event("primary", e1)
        adapter.create_event("primary", e2)
        items = adapter.list_events(
            "primary",
            datetime(2026, 5, 1, tzinfo=timezone.utc),
            datetime(2026, 5, 31, tzinfo=timezone.utc),
        )
        assert len(items) == 1
        assert items[0].raw["summary"] == "In range"

    def test_delete(self):
        adapter = FakeCalendarAdapter()
        event = EventInput(
            summary="Delete me",
            start_at=datetime(2026, 5, 15, 14, 0, tzinfo=timezone.utc),
            end_at=datetime(2026, 5, 15, 15, 0, tzinfo=timezone.utc),
            timezone="UTC",
        )
        created = adapter.create_event("primary", event)
        adapter.delete_event("primary", created.event_id)
        assert adapter.get_event("primary", created.event_id) is None

    def test_supports_attendees_flag(self):
        adapter = FakeCalendarAdapter(supports_attendees=True)
        assert adapter.supports_attendees is True


# ─── Routing (Maps) ───────────────────────────────────────────────────
class TestRoutingMappers:
    def test_build_routes_request_shape(self):
        origin = Coordinates(latitude=-23.55, longitude=-46.63)
        dest = Coordinates(latitude=-23.43, longitude=-46.47)
        body = build_routes_request(origin, dest)
        assert body["travelMode"] == "DRIVE"
        assert body["routingPreference"] == "TRAFFIC_UNAWARE"
        assert body["origin"]["location"]["latLng"]["latitude"] == -23.55
        assert body["destination"]["location"]["latLng"]["longitude"] == -46.47

    def test_parse_routes_response_minutes_rounded_up(self):
        # 90 seconds → 2 minutes (ceil-rounded so we never under-report).
        resp = {"routes": [{"duration": "90s", "distanceMeters": 1234}]}
        est = parse_routes_response(resp)
        assert est.minutes == 2
        assert est.distance_meters == 1234

    def test_parse_routes_response_empty(self):
        est = parse_routes_response({"routes": []})
        assert est.minutes == 0
        assert est.distance_meters is None


class TestStaticRoutingAdapter:
    def test_distinct_coords_returns_default_minutes(self):
        adapter = StaticRoutingAdapter(default_minutes=42)
        est = adapter.travel_estimate(
            Coordinates(0.0, 0.0), Coordinates(1.0, 1.0)
        )
        assert est.minutes == 42

    def test_identical_coords_returns_zero(self):
        adapter = StaticRoutingAdapter()
        est = adapter.travel_estimate(
            Coordinates(-23.55, -46.63), Coordinates(-23.55, -46.63)
        )
        assert est.minutes == 0


# ─── Factory selection ────────────────────────────────────────────────
class TestCalendarFactory:
    def test_no_config_falls_back_to_fake(self):
        from app.services.calendar import get_calendar_adapter

        class _FakeSettings:
            google_oauth_client_id = ""
            google_oauth_client_secret = ""
            google_service_account_file = ""

        adapter = get_calendar_adapter(settings=_FakeSettings())
        assert isinstance(adapter, FakeCalendarAdapter)

    def test_invalid_service_account_path_falls_back_to_fake(self):
        from app.services.calendar import get_calendar_adapter

        class _FakeSettings:
            google_oauth_client_id = ""
            google_oauth_client_secret = ""
            google_service_account_file = "/nonexistent/path.json"

        adapter = get_calendar_adapter(settings=_FakeSettings())
        assert isinstance(adapter, FakeCalendarAdapter)


class TestRoutingFactory:
    def test_no_api_key_falls_back_to_static(self):
        from app.services.routing import get_routing_adapter

        class _FakeSettings:
            google_maps_api_key = ""

        adapter = get_routing_adapter(settings=_FakeSettings())
        assert isinstance(adapter, StaticRoutingAdapter)

    def test_api_key_selects_google_adapter(self):
        from app.services.routing import (
            GoogleMapsRoutingAdapter,
            get_routing_adapter,
        )

        class _FakeSettings:
            google_maps_api_key = "AIza-fake"

        adapter = get_routing_adapter(settings=_FakeSettings())
        assert isinstance(adapter, GoogleMapsRoutingAdapter)
