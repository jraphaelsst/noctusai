"""HTTP-level smoke test for the scheduling router against a real
Supabase backend.

Proves the FULL wiring path: TestClient → FastAPI router → real auth
dep (`get_current_user` calls Supabase auth.getUser) → real DB
(`generate_candidate_slots` reads `availability_slots` from `therapy`
schema) → seed engine → JSON response.

Auth: the `test_therapist` fixture creates a real Supabase user, then
this test calls `auth.sign_in_with_password(...)` to get a real
session JWT and passes it as the `Authorization: Bearer ...` header on
the TestClient request.

Run: `pytest tests/realdb/test_scheduling_router_realdb.py -v`
Skip: auto-skips when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY unset.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from supabase import create_client

pytestmark = pytest.mark.realdb


def _next_monday() -> date:
    today = date.today()
    days_ahead = (0 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


def _sign_in_token(email: str, password: str) -> str:
    """Sign in with the user-anon client to get a real session JWT."""
    url = os.environ["SUPABASE_URL"]
    anon_key = os.environ.get("SUPABASE_ANON_KEY") or os.environ.get(
        "SUPABASE_KEY"
    )
    if not anon_key:
        pytest.skip(
            "SUPABASE_ANON_KEY / SUPABASE_KEY not set — required for real-auth smoke"
        )
    user_client = create_client(url, anon_key)
    auth_resp = user_client.auth.sign_in_with_password(
        {"email": email, "password": password}
    )
    if not auth_resp.session or not auth_resp.session.access_token:
        pytest.fail(f"sign_in_with_password returned no session for {email}")
    return auth_resp.session.access_token


class TestSchedulingRouterEndToEnd:
    def test_get_candidates_via_http_with_real_auth_returns_200(
        self, therapy_db, test_clinic, test_therapist, cleanup
    ):
        # Seed a Monday-morning availability window so the engine has
        # something to emit.
        slot = (
            therapy_db.table("availability_slots")
            .insert(
                {
                    "therapist_id": test_therapist["user_id"],
                    "clinic_id": test_clinic["id"],
                    "day_of_week": 1,
                    "start_time": "09:00",
                    "end_time": "12:00",
                    "is_recurring": True,
                    "is_blocked": False,
                }
            )
            .execute()
            .data[0]
        )
        cleanup.append(("availability_slots", slot["id"]))

        token = _sign_in_token(test_therapist["email"], test_therapist["password"])

        # Import here so the app is constructed lazily after env is set.
        from app.main import app

        client = TestClient(app)
        target_monday = _next_monday()
        window_start = datetime(
            target_monday.year, target_monday.month, target_monday.day, tzinfo=timezone.utc
        )
        resp = client.get(
            "/api/scheduling/candidates",
            params={
                "therapist_id": test_therapist["user_id"],
                "window_start": window_start.isoformat(),
                "window_end": (window_start + timedelta(hours=23)).isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        candidates = body.get("data", [])
        assert isinstance(candidates, list)
        # 3-hour window with 50-min sessions + 15-min default buffer →
        # at minimum 2 candidates.
        assert len(candidates) >= 2, f"expected >=2 slots, got {candidates}"
        for slot_dto in candidates:
            assert "start_at" in slot_dto
            assert "end_at" in slot_dto
            assert slot_dto["duration_minutes"] == 50

    def test_book_appointment_via_http_persists_real_row(
        self, therapy_db, test_clinic, test_therapist, test_patient, cleanup
    ):
        target_monday = _next_monday()
        slot_start = datetime(
            target_monday.year,
            target_monday.month,
            target_monday.day,
            14,
            tzinfo=timezone.utc,
        )
        slot_end = slot_start + timedelta(minutes=50)

        token = _sign_in_token(test_therapist["email"], test_therapist["password"])

        from app.main import app

        client = TestClient(app)
        resp = client.post(
            "/api/scheduling/appointments",
            json={
                "therapist_id": test_therapist["user_id"],
                "patient_id": test_patient["user_id"],
                "clinic_id": test_clinic["id"],
                "slot_start": slot_start.isoformat(),
                "slot_end": slot_end.isoformat(),
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        appointment = body.get("data", {})
        appointment_id = appointment["id"]
        cleanup.append(("appointments", appointment_id))

        # Verify the real DB row exists.
        row = (
            therapy_db.table("appointments")
            .select("status, scheduled_start, google_event_id")
            .eq("id", appointment_id)
            .single()
            .execute()
            .data
        )
        assert row["status"] == "waiting"
        assert row["google_event_id"]  # Fake adapter populated this.
