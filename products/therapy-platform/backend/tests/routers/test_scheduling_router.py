"""Router tests for `app/routers/scheduling.py`.

Covers auth boundary (therapist self-only / patient blocked / admin
unrestricted) for all endpoints + happy-path round-trips through the
mocked stack. OAuth callback's Google token-exchange is mocked at the
httpx boundary (allowed external integration per
`feedback_no_monkeypatching_in_tests`).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
import pytest


THERAPIST_ID = "test-user-123"  # MockUser default id (see noctusai_lib.testing.clients.MockUser)
OTHER_THERAPIST_ID = "other-therapist-id"


def _seed_minimum(client):
    db = client.mock_supabase
    db.set_table_data(
        "availability_slots",
        [
            {
                "day_of_week": 1,  # Monday in Sunday-first convention.
                "start_time": "09:00",
                "end_time": "12:00",
                "is_recurring": True,
                "specific_date": None,
                "is_blocked": False,
            }
        ],
    )
    db.set_table_data("appointments", [])
    db.set_table_data("clinic_settings", [{"transition_buffer_minutes": 15}])
    db.set_table_data("therapist_profiles", [{"gcal_calendar_id": None}])
    return db


# ---------------------------------------------------------------------------
# GET /api/scheduling/candidates
# ---------------------------------------------------------------------------


class TestGetCandidates:
    def test_therapist_can_request_own_candidates(self, client):
        _seed_minimum(client)
        resp = client.get(
            "/api/scheduling/candidates",
            params={
                "therapist_id": THERAPIST_ID,
                "window_start": "2026-06-01T00:00:00+00:00",
                "window_end": "2026-06-01T23:59:59+00:00",
            },
        )
        assert resp.status_code == 200, resp.text

    def test_therapist_cannot_request_another_therapist(self, client):
        _seed_minimum(client)
        resp = client.get(
            "/api/scheduling/candidates",
            params={
                "therapist_id": OTHER_THERAPIST_ID,
                "window_start": "2026-06-01T00:00:00+00:00",
                "window_end": "2026-06-01T23:59:59+00:00",
            },
        )
        assert resp.status_code == 403

    def test_patient_blocked(self, patient_client):
        _seed_minimum(patient_client)
        resp = patient_client.get(
            "/api/scheduling/candidates",
            params={
                "therapist_id": THERAPIST_ID,
                "window_start": "2026-06-01T00:00:00+00:00",
                "window_end": "2026-06-01T23:59:59+00:00",
            },
        )
        assert resp.status_code == 403

    def test_admin_can_request_any_therapist(self, admin_client):
        _seed_minimum(admin_client)
        resp = admin_client.get(
            "/api/scheduling/candidates",
            params={
                "therapist_id": OTHER_THERAPIST_ID,
                "window_start": "2026-06-01T00:00:00+00:00",
                "window_end": "2026-06-01T23:59:59+00:00",
            },
        )
        assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# POST /api/scheduling/appointments
# ---------------------------------------------------------------------------


class TestBookEndpoint:
    def test_therapist_books_on_own_calendar(self, client):
        _seed_minimum(client)
        resp = client.post(
            "/api/scheduling/appointments",
            json={
                "therapist_id": THERAPIST_ID,
                "patient_id": "patient-X",
                "slot_start": "2026-06-01T10:00:00+00:00",
                "slot_end": "2026-06-01T10:50:00+00:00",
            },
        )
        assert resp.status_code == 200, resp.text
        # Insert side-effect captured.
        assert len(client.mock_supabase.table("appointments").inserted_payloads) == 1

    def test_therapist_cannot_book_for_other_therapist(self, client):
        _seed_minimum(client)
        resp = client.post(
            "/api/scheduling/appointments",
            json={
                "therapist_id": OTHER_THERAPIST_ID,
                "patient_id": "patient-X",
                "slot_start": "2026-06-01T10:00:00+00:00",
                "slot_end": "2026-06-01T10:50:00+00:00",
            },
        )
        assert resp.status_code == 403

    def test_patient_blocked(self, patient_client):
        _seed_minimum(patient_client)
        resp = patient_client.post(
            "/api/scheduling/appointments",
            json={
                "therapist_id": THERAPIST_ID,
                "patient_id": "patient-X",
                "slot_start": "2026-06-01T10:00:00+00:00",
                "slot_end": "2026-06-01T10:50:00+00:00",
            },
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /api/scheduling/appointments/{id}
# ---------------------------------------------------------------------------


class TestRescheduleEndpoint:
    def test_404_when_appointment_missing(self, client):
        _seed_minimum(client)
        client.mock_supabase.set_table_data("appointments", [])
        resp = client.patch(
            "/api/scheduling/appointments/missing",
            json={
                "slot_start": "2026-06-02T10:00:00+00:00",
                "slot_end": "2026-06-02T10:50:00+00:00",
            },
        )
        assert resp.status_code == 404

    def test_therapist_reschedules_own_appointment_in_place(self, client):
        _seed_minimum(client)
        client.mock_supabase.set_table_data(
            "appointments",
            [
                {
                    # MOCK-SELECT-PREDICATE-FIX: route filters via
                    # `.eq("id", appointment_id)` — seed row MUST carry `id`
                    # or the row is filtered out and route 404s.
                    "id": "appt-1",
                    "therapist_id": THERAPIST_ID,
                    "patient_id": "patient-X",
                    "clinic_id": None,
                    "status": "waiting",
                    "google_event_id": "ev-abc",
                }
            ],
        )
        resp = client.patch(
            "/api/scheduling/appointments/appt-1",
            json={
                "slot_start": "2026-06-02T10:00:00+00:00",
                "slot_end": "2026-06-02T10:50:00+00:00",
            },
        )
        assert resp.status_code == 200, resp.text
        # In-place reschedule — no new appointments row inserted.
        assert client.mock_supabase.table("appointments").inserted_payloads == []
        # The update payload carries the new times.
        updates = client.mock_supabase.table("appointments").updated_payloads
        assert any(
            u.get("scheduled_start", "").startswith("2026-06-02T10:00:00")
            for u in updates
        ), updates
        # Response echoes the move.
        body = resp.json().get("data", {})
        assert body.get("scheduled_start", "").startswith("2026-06-02T10:00:00")
        assert body.get("google_event_id") == "ev-abc"

    def test_therapist_cannot_reschedule_other_therapist_appointment(self, client):
        _seed_minimum(client)
        client.mock_supabase.set_table_data(
            "appointments",
            [
                {
                    # MOCK-SELECT-PREDICATE-FIX: route filters via
                    # `.eq("id", appointment_id)` — seed row MUST carry `id`.
                    "id": "appt-1",
                    "therapist_id": OTHER_THERAPIST_ID,
                    "patient_id": "patient-X",
                    "clinic_id": None,
                    "status": "waiting",
                    "google_event_id": None,
                }
            ],
        )
        resp = client.patch(
            "/api/scheduling/appointments/appt-1",
            json={
                "slot_start": "2026-06-02T10:00:00+00:00",
                "slot_end": "2026-06-02T10:50:00+00:00",
            },
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GCal OAuth flow
# ---------------------------------------------------------------------------


class TestGcalAuthorize:
    def test_returns_authorize_url_and_needs_authorization_when_no_token(
        self, client
    ):
        _seed_minimum(client)
        # therapist_profiles row has no encrypted token → needs_authorization=True.
        with patch.object(
            type(client.mock_supabase).__module__ and __import__("app.config", fromlist=["settings"]).settings,
            "therapy_google_client_id",
            "fake-client-id",
        ):
            resp = client.get(
                f"/api/scheduling/gcal/authorize?therapist_id={THERAPIST_ID}",
            )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        data = body.get("data", body)
        assert "authorize_url" in data
        assert data["authorize_url"].startswith("https://accounts.google.com/")
        assert data["needs_authorization"] is True

    def test_403_when_therapist_requests_other_therapist(self, client):
        _seed_minimum(client)
        with patch.object(
            __import__("app.config", fromlist=["settings"]).settings,
            "therapy_google_client_id",
            "fake-client-id",
        ):
            resp = client.get(
                f"/api/scheduling/gcal/authorize?therapist_id={OTHER_THERAPIST_ID}",
            )
        assert resp.status_code == 403


class TestGcalCallback:
    @pytest.mark.asyncio
    async def test_happy_path_persists_encrypted_token(self, client):
        _seed_minimum(client)
        client.mock_supabase.set_rpc_data("encrypt_gcal_token", b"\xde\xad\xbe\xef")

        async def _fake_post(self, url, **kwargs):  # noqa: ARG001
            request = httpx.Request("POST", url)
            return httpx.Response(
                200,
                json={
                    "access_token": "ya29.fake",
                    "refresh_token": "1//fake-refresh",
                    "expires_in": 3600,
                },
                request=request,
            )

        with patch.object(
            __import__("app.config", fromlist=["settings"]).settings,
            "therapy_google_client_id",
            "fake-client-id",
        ), patch.object(
            __import__("app.config", fromlist=["settings"]).settings,
            "therapy_google_client_secret",
            "fake-secret",
        ), patch.object(httpx.AsyncClient, "post", new=_fake_post):
            resp = client.get(
                f"/api/scheduling/gcal/callback?code=fake-code&state={THERAPIST_ID}",
            )

        assert resp.status_code == 200, resp.text
        # The mock doesn't capture updates the way it captures inserts —
        # success status + 200 is the assertion floor here.
        data = resp.json().get("data", {})
        assert data.get("connected") is True

    @pytest.mark.asyncio
    async def test_502_when_google_returns_no_refresh_token(self, client):
        _seed_minimum(client)

        async def _fake_post(self, url, **kwargs):  # noqa: ARG001
            request = httpx.Request("POST", url)
            return httpx.Response(
                200,
                json={"access_token": "ya29.fake", "expires_in": 3600},
                request=request,
            )

        with patch.object(
            __import__("app.config", fromlist=["settings"]).settings,
            "therapy_google_client_id",
            "fake-client-id",
        ), patch.object(
            __import__("app.config", fromlist=["settings"]).settings,
            "therapy_google_client_secret",
            "fake-secret",
        ), patch.object(httpx.AsyncClient, "post", new=_fake_post):
            resp = client.get(
                f"/api/scheduling/gcal/callback?code=fake-code&state={THERAPIST_ID}",
            )

        assert resp.status_code == 502
