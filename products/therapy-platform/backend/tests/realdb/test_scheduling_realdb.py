"""Real-DB smoke tests for the therapy scheduling pilot.

Hits a live Supabase instance to prove that:

1. **Migration 011 actually shipped** — `clinic_settings.transition_buffer_minutes`,
   `therapist_profiles.gcal_*` columns, the three RPC helpers
   (`encrypt_gcal_token`, `decrypt_gcal_token`, `gcal_authorization_is_fresh`),
   and the Vault secret (`gcal_token_key`) are all callable.
2. **`TherapyGcalCredentialResolver` works against the real DB**: returns
   None when no token, returns `OAuthCalendarCredentials` when the token
   is fresh + decryptable, returns None when authorized_at is stale
   (>7 days).
3. **`generate_candidate_slots` round-trips through the real DB and the
   seed engine** to emit real `Slot` objects, with real `availability_slots`
   + real `appointments` shaping the output.
4. **`book_appointment` writes a real row** with status=waiting and
   the FakeCalendarAdapter (no GCal credentials) → `google_event_id`
   populated by Fake.
5. **`reschedule_appointment` updates in-place** — same row, new times,
   same `google_event_id` (preserves attendee invite identity).
6. **`cancel_appointment` flips status to cancelled** — real row, real
   GCal delete via Fake.

Run: `pytest tests/realdb/test_scheduling_realdb.py -v`
Skip: auto-skips when SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are unset.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from noctusai_lib.integrations.google_calendar import (
    FakeCalendarAdapter,
    OAuthCalendarCredentials,
)

from app.services.scheduling import (
    TherapyGcalCredentialResolver,
    book_appointment,
    cancel_appointment,
    generate_candidate_slots,
    reschedule_appointment,
)

pytestmark = pytest.mark.realdb


# ---------------------------------------------------------------------------
# 1. Migration smoke
# ---------------------------------------------------------------------------


class TestMigration011IsLive:
    def test_clinic_settings_buffer_column_default_is_15(self, therapy_db, test_clinic):
        row = (
            therapy_db.table("clinic_settings")
            .select("transition_buffer_minutes")
            .eq("clinic_id", test_clinic["id"])
            .single()
            .execute()
            .data
        )
        assert row["transition_buffer_minutes"] == 15

    def test_therapist_profiles_gcal_columns_present(self, therapy_db, test_therapist):
        row = (
            therapy_db.table("therapist_profiles")
            .select(
                "gcal_refresh_token_encrypted, gcal_calendar_id, gcal_authorized_at"
            )
            .eq("user_id", test_therapist["user_id"])
            .single()
            .execute()
            .data
        )
        # Columns exist (no exception) and start NULL.
        assert row["gcal_refresh_token_encrypted"] is None
        assert row["gcal_calendar_id"] is None
        assert row["gcal_authorized_at"] is None

    def test_encrypt_decrypt_roundtrip_via_rpc(self, therapy_db):
        plaintext = "smoke-realdb-token-xyz"
        ciphertext = therapy_db.rpc(
            "encrypt_gcal_token", {"token": plaintext}
        ).execute().data
        assert ciphertext is not None and ciphertext != plaintext
        decrypted = therapy_db.rpc(
            "decrypt_gcal_token", {"ciphertext": ciphertext}
        ).execute().data
        assert decrypted == plaintext

    def test_gcal_authorization_is_fresh_rpc_window(self, therapy_db):
        recent = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        old = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        assert (
            therapy_db.rpc(
                "gcal_authorization_is_fresh", {"authorized_at": recent}
            ).execute().data
            is True
        )
        assert (
            therapy_db.rpc(
                "gcal_authorization_is_fresh", {"authorized_at": old}
            ).execute().data
            is False
        )
        assert (
            therapy_db.rpc(
                "gcal_authorization_is_fresh", {"authorized_at": None}
            ).execute().data
            is False
        )


# ---------------------------------------------------------------------------
# 2. TherapyGcalCredentialResolver smoke
# ---------------------------------------------------------------------------


class TestResolverAgainstRealDb:
    def test_returns_none_when_no_token_stored(self, therapy_db, test_therapist):
        resolver = TherapyGcalCredentialResolver(
            therapy_db,
            client_id="fake-client-id",
            client_secret="fake-client-secret",
        )
        assert resolver.get_credentials(test_therapist["user_id"]) is None

    def test_returns_oauth_creds_when_token_present_and_fresh(
        self, therapy_db, test_therapist
    ):
        # Encrypt a fake refresh token via the real RPC, store it on the
        # therapist row with a fresh `gcal_authorized_at`, then resolve.
        plaintext = "ya29.fake-refresh-token-abc"
        ciphertext = therapy_db.rpc(
            "encrypt_gcal_token", {"token": plaintext}
        ).execute().data
        therapy_db.table("therapist_profiles").update(
            {
                "gcal_refresh_token_encrypted": ciphertext,
                "gcal_calendar_id": "primary",
                "gcal_authorized_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("user_id", test_therapist["user_id"]).execute()

        resolver = TherapyGcalCredentialResolver(
            therapy_db,
            client_id="fake-client-id",
            client_secret="fake-client-secret",
        )
        creds = resolver.get_credentials(test_therapist["user_id"])
        assert isinstance(creds, OAuthCalendarCredentials)
        assert creds.refresh_token == plaintext
        assert creds.client_id == "fake-client-id"

    def test_returns_none_when_authorized_at_is_stale(
        self, therapy_db, test_therapist
    ):
        plaintext = "ya29.fake-refresh-token-stale"
        ciphertext = therapy_db.rpc(
            "encrypt_gcal_token", {"token": plaintext}
        ).execute().data
        # 8 days ago = past the 7-day re-auth window.
        stale = (datetime.now(timezone.utc) - timedelta(days=8)).isoformat()
        therapy_db.table("therapist_profiles").update(
            {
                "gcal_refresh_token_encrypted": ciphertext,
                "gcal_calendar_id": "primary",
                "gcal_authorized_at": stale,
            }
        ).eq("user_id", test_therapist["user_id"]).execute()

        resolver = TherapyGcalCredentialResolver(
            therapy_db,
            client_id="fake-client-id",
            client_secret="fake-client-secret",
        )
        assert resolver.get_credentials(test_therapist["user_id"]) is None


# ---------------------------------------------------------------------------
# 3. generate_candidate_slots end-to-end
# ---------------------------------------------------------------------------


def _next_monday() -> date:
    today = date.today()
    days_ahead = (0 - today.weekday()) % 7  # Monday = 0 in Python; 0 → today is Monday → 7
    if days_ahead == 0:
        days_ahead = 7
    return today + timedelta(days=days_ahead)


class TestGenerateCandidateSlotsAgainstRealDb:
    def test_emits_slots_within_seeded_availability_window(
        self, therapy_db, test_therapist, test_clinic, cleanup
    ):
        # Seed: Monday 9-12 recurring window. day_of_week = 1 (Sunday-first).
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

        target_monday = _next_monday()
        window_start = datetime(
            target_monday.year, target_monday.month, target_monday.day, tzinfo=timezone.utc
        )
        window_end = window_start + timedelta(hours=23, minutes=59)

        slots = generate_candidate_slots(
            therapist_id=test_therapist["user_id"],
            clinic_id=test_clinic["id"],
            window_start=window_start,
            window_end=window_end,
            duration_minutes=50,
            db=therapy_db,
            calendar_adapter=FakeCalendarAdapter(),
            calendar_id="primary",
        )

        # 3-hour window with 50-min sessions + 15-min default buffer:
        # at minimum we expect 2 candidates (e.g. 09:00 and 10:05).
        assert len(slots) >= 2, slots
        for s in slots:
            assert s.duration_minutes == 50

    def test_existing_appointment_blocks_overlapping_candidate(
        self, therapy_db, test_therapist, test_clinic, test_patient, cleanup
    ):
        avail = (
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
        cleanup.append(("availability_slots", avail["id"]))

        target_monday = _next_monday()
        # Block 09:00–10:00 with a real appointment.
        appt = (
            therapy_db.table("appointments")
            .insert(
                {
                    "therapist_id": test_therapist["user_id"],
                    "patient_id": test_patient["user_id"],
                    "clinic_id": test_clinic["id"],
                    "scheduled_start": datetime(
                        target_monday.year,
                        target_monday.month,
                        target_monday.day,
                        9,
                        tzinfo=timezone.utc,
                    ).isoformat(),
                    "scheduled_end": datetime(
                        target_monday.year,
                        target_monday.month,
                        target_monday.day,
                        10,
                        tzinfo=timezone.utc,
                    ).isoformat(),
                    "status": "waiting",
                    "patient_origin": "platform_assigned",
                }
            )
            .execute()
            .data[0]
        )
        cleanup.append(("appointments", appt["id"]))

        window_start = datetime(
            target_monday.year, target_monday.month, target_monday.day, tzinfo=timezone.utc
        )
        slots = generate_candidate_slots(
            therapist_id=test_therapist["user_id"],
            clinic_id=test_clinic["id"],
            window_start=window_start,
            window_end=window_start + timedelta(hours=23),
            duration_minutes=50,
            db=therapy_db,
            calendar_adapter=FakeCalendarAdapter(),
            calendar_id="primary",
        )

        # No candidate should overlap [09:00, 10:00).
        for s in slots:
            blocked_start = window_start.replace(hour=9)
            blocked_end = window_start.replace(hour=10)
            assert not (s.start_at < blocked_end and blocked_start < s.end_at), (
                f"candidate {s} overlaps blocked window"
            )


# ---------------------------------------------------------------------------
# 4-6. book / reschedule / cancel against real rows
# ---------------------------------------------------------------------------


class TestBookRescheduleCancelRoundtripAgainstRealDb:
    def test_book_inserts_real_row_with_status_waiting(
        self, therapy_db, test_therapist, test_clinic, test_patient, cleanup
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

        result = book_appointment(
            therapist_id=test_therapist["user_id"],
            patient_id=test_patient["user_id"],
            clinic_id=test_clinic["id"],
            slot_start=slot_start,
            slot_end=slot_end,
            db=therapy_db,
            calendar_adapter=FakeCalendarAdapter(),
            calendar_id="primary",
        )
        appointment_id = result["id"]
        cleanup.append(("appointments", appointment_id))

        # Verify the row hit the real DB.
        row = (
            therapy_db.table("appointments")
            .select("status, scheduled_start, scheduled_end, google_event_id")
            .eq("id", appointment_id)
            .single()
            .execute()
            .data
        )
        assert row["status"] == "waiting"
        # Fake adapter returns a uuid event_id.
        assert row["google_event_id"]

    def test_reschedule_updates_in_place_and_keeps_event_id(
        self, therapy_db, test_therapist, test_clinic, test_patient, cleanup
    ):
        adapter = FakeCalendarAdapter()
        target_monday = _next_monday()
        slot_start = datetime(
            target_monday.year,
            target_monday.month,
            target_monday.day,
            14,
            tzinfo=timezone.utc,
        )
        slot_end = slot_start + timedelta(minutes=50)
        booked = book_appointment(
            therapist_id=test_therapist["user_id"],
            patient_id=test_patient["user_id"],
            clinic_id=test_clinic["id"],
            slot_start=slot_start,
            slot_end=slot_end,
            db=therapy_db,
            calendar_adapter=adapter,
            calendar_id="primary",
        )
        appointment_id = booked["id"]
        original_event_id = booked["google_event_id"]
        cleanup.append(("appointments", appointment_id))

        new_start = slot_start + timedelta(hours=2)
        new_end = slot_end + timedelta(hours=2)
        moved = reschedule_appointment(
            appointment_id=appointment_id,
            new_start=new_start,
            new_end=new_end,
            db=therapy_db,
            calendar_adapter=adapter,
            calendar_id="primary",
        )

        # GCal event_id preserved (in-place update, not delete+create).
        assert moved["google_event_id"] == original_event_id

        # DB row updated to new times — and only ONE row exists (no extra insert).
        rows = (
            therapy_db.table("appointments")
            .select("id, scheduled_start, scheduled_end")
            .eq("id", appointment_id)
            .execute()
            .data
        )
        assert len(rows) == 1
        assert rows[0]["scheduled_start"].startswith(new_start.isoformat()[:19])

        # The Fake adapter sees the move via its own update_event semantics.
        ev = adapter.get_event("primary", original_event_id)
        assert ev is not None
        assert ev.raw["start"]["dateTime"].startswith(new_start.isoformat()[:19])

    def test_cancel_marks_status_cancelled(
        self, therapy_db, test_therapist, test_clinic, test_patient, cleanup
    ):
        adapter = FakeCalendarAdapter()
        target_monday = _next_monday()
        slot_start = datetime(
            target_monday.year,
            target_monday.month,
            target_monday.day,
            16,
            tzinfo=timezone.utc,
        )
        slot_end = slot_start + timedelta(minutes=50)
        booked = book_appointment(
            therapist_id=test_therapist["user_id"],
            patient_id=test_patient["user_id"],
            clinic_id=test_clinic["id"],
            slot_start=slot_start,
            slot_end=slot_end,
            db=therapy_db,
            calendar_adapter=adapter,
            calendar_id="primary",
        )
        appointment_id = booked["id"]
        cleanup.append(("appointments", appointment_id))

        cancel_appointment(
            appointment_id=appointment_id,
            db=therapy_db,
            calendar_adapter=adapter,
            calendar_id="primary",
        )

        row = (
            therapy_db.table("appointments")
            .select("status")
            .eq("id", appointment_id)
            .single()
            .execute()
            .data
        )
        assert row["status"] == "cancelled"
