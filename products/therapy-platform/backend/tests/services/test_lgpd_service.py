"""Tests for the LGPD Service — data deletion per Brazilian data protection law.

Rewritten 2026-04-22 (compliance-audit-reconciliation Phase 2) to exercise the
real schema-aware call shape:

  - `session_records` ownership goes through `appointments.therapist_id`.
  - `session_summary_versions` / `session_observations` link via
    `session_record_id` (not `session_id`).
  - `wallets` is keyed by (owner_id, owner_type).
  - `messages` sender is `sender_user_id` + `sender_type='user'`.
  - `conversation_participants` membership is `participant_id` +
    `participant_type='user'`.
  - `therapist_settings` is keyed by `therapist_id` (not `user_id`).

KNOWN LIMITATION — the current `MockSupabaseClient` does NOT mutate state on
`.delete()` calls and does NOT validate column names. These tests assert the
service's RESPONSE shape (the `deleted` list + HTTP error behavior), not the
actual row counts. True row-removal verification requires either a real-DB
integration test OR the `mock-supabase-schema-validation` follow-up project
(deferred; captured in compliance-audit-reconciliation Phase 0 improvements).
"""
from __future__ import annotations

import pytest
from unittest.mock import patch

from tests.conftest import MockSupabaseClient
from app.services import lgpd_service


@pytest.fixture(autouse=True)
def _mock_log_action():
    """Suppress log_action calls (it uses admin client)."""
    with patch("app.services.lgpd_service.log_action"):
        yield


# ---------------------------------------------------------------------------
# Patient data deletion
# ---------------------------------------------------------------------------

class TestDeletePatientData:
    @pytest.mark.asyncio
    async def test_delete_patient_data_covers_all_patient_tables(self):
        db = MockSupabaseClient()
        # Shape fixtures to match real columns. See service docstring for schema.
        db.set_table_data("messages", [])
        db.set_table_data("conversation_participants", [])
        db.set_table_data("wallets", [
            {"id": "wallet-001", "owner_id": "patient-001", "owner_type": "patient"},
        ])
        db.set_table_data("wallet_movements", [])
        db.set_table_data("patient_longitudinal_analyses", [])
        db.set_table_data("patient_session_notes", [])
        db.set_table_data("patient_profiles", [])

        result = await lgpd_service.delete_patient_data("patient-001", db)

        # Every patient-owned table is included in the deletion record.
        for table in [
            "messages",
            "conversation_participants",
            "wallet_movements",
            "wallets",
            "patient_longitudinal_analyses",
            "patient_session_notes",
            "patient_profiles",
        ]:
            assert table in result["deleted_tables"], f"{table} missing from deleted_tables"

        assert len(result["deleted_tables"]) == 7

    @pytest.mark.asyncio
    async def test_delete_patient_data_preserves_therapist_clinical_records(self):
        db = MockSupabaseClient()
        for t in ("messages", "conversation_participants", "wallets", "wallet_movements",
                  "patient_longitudinal_analyses", "patient_session_notes", "patient_profiles"):
            db.set_table_data(t, [])

        result = await lgpd_service.delete_patient_data("patient-001", db)

        # Therapist's clinical memory of the patient stays (professional records).
        for kept in ("session_records", "session_observations", "session_summary_versions"):
            assert kept in result["kept_tables"]

    @pytest.mark.asyncio
    async def test_delete_patient_data_iterates_over_multiple_wallets(self):
        db = MockSupabaseClient()
        db.set_table_data("wallets", [
            {"id": "w-1", "owner_id": "patient-001", "owner_type": "patient"},
            {"id": "w-2", "owner_id": "patient-001", "owner_type": "patient"},
        ])
        for t in ("messages", "conversation_participants", "wallet_movements",
                  "patient_longitudinal_analyses", "patient_session_notes", "patient_profiles"):
            db.set_table_data(t, [])

        result = await lgpd_service.delete_patient_data("patient-001", db)

        # Multiple wallets all covered; wallet_movements only recorded once (correct — it's a list-deletion, not per-wallet).
        assert "wallet_movements" in result["deleted_tables"]
        assert "wallets" in result["deleted_tables"]


# ---------------------------------------------------------------------------
# Therapist data deletion — specific session
# ---------------------------------------------------------------------------

class TestDeleteTherapistSession:
    @pytest.mark.asyncio
    async def test_delete_session_owned_by_therapist(self):
        """Therapist ownership of a session flows session_records → appointments."""
        db = MockSupabaseClient()
        db.set_table_data("session_records", [
            {"id": "sr-001", "appointment_id": "appt-t1"},
        ])
        db.set_table_data("appointments", [
            {"id": "appt-t1", "therapist_id": "therapist-001"},
        ])
        db.set_table_data("session_observations", [])
        db.set_table_data("session_summary_versions", [])

        result = await lgpd_service.delete_therapist_data(
            "therapist-001", "session", "sr-001", db,
        )

        for expected in ("session_summary_versions", "session_observations", "session_records"):
            assert expected in result["deleted"]

    @pytest.mark.asyncio
    async def test_delete_session_not_found_returns_404(self):
        db = MockSupabaseClient()
        db.set_table_data("session_records", [])
        db.set_table_data("appointments", [])

        with pytest.raises(Exception) as exc_info:
            await lgpd_service.delete_therapist_data(
                "therapist-001", "session", "nonexistent", db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_session_owned_by_other_therapist_returns_404(self):
        """Session exists but belongs to a different therapist via the appointment chain."""
        db = MockSupabaseClient()
        db.set_table_data("session_records", [
            {"id": "sr-002", "appointment_id": "appt-other"},
        ])
        db.set_table_data("appointments", [
            {"id": "appt-other", "therapist_id": "other-therapist"},
        ])

        with pytest.raises(Exception) as exc_info:
            await lgpd_service.delete_therapist_data(
                "therapist-001", "session", "sr-002", db,
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Therapist data deletion — specific observation
# ---------------------------------------------------------------------------

class TestDeleteTherapistObservation:
    @pytest.mark.asyncio
    async def test_delete_observation_owned_by_therapist(self):
        """Observation ownership chains observation → session_record → appointment → therapist."""
        db = MockSupabaseClient()
        db.set_table_data("session_observations", [
            {"id": "obs-001", "session_record_id": "sr-001"},
        ])
        db.set_table_data("session_records", [
            {"id": "sr-001", "appointment_id": "appt-t1"},
        ])
        db.set_table_data("appointments", [
            {"id": "appt-t1", "therapist_id": "therapist-001"},
        ])

        result = await lgpd_service.delete_therapist_data(
            "therapist-001", "observation", "obs-001", db,
        )

        assert "session_observations" in result["deleted"]

    @pytest.mark.asyncio
    async def test_delete_observation_not_found_returns_404(self):
        db = MockSupabaseClient()
        db.set_table_data("session_observations", [])

        with pytest.raises(Exception) as exc_info:
            await lgpd_service.delete_therapist_data(
                "therapist-001", "observation", "nonexistent", db,
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_observation_owned_by_other_therapist_returns_404(self):
        db = MockSupabaseClient()
        db.set_table_data("session_observations", [
            {"id": "obs-002", "session_record_id": "sr-002"},
        ])
        db.set_table_data("session_records", [
            {"id": "sr-002", "appointment_id": "appt-other"},
        ])
        db.set_table_data("appointments", [
            {"id": "appt-other", "therapist_id": "other-therapist"},
        ])

        with pytest.raises(Exception) as exc_info:
            await lgpd_service.delete_therapist_data(
                "therapist-001", "observation", "obs-002", db,
            )
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# Therapist data deletion — full wipe
# ---------------------------------------------------------------------------

class TestDeleteTherapistAll:
    @pytest.mark.asyncio
    async def test_delete_all_covers_every_therapist_owned_table(self):
        """Full wipe exercises the entire dependency graph. Fixtures shape-correct to real columns."""
        db = MockSupabaseClient()
        # Therapist owns one appointment → one session_record → one video_room.
        db.set_table_data("appointments", [
            {"id": "appt-t1", "therapist_id": "therapist-001"},
        ])
        db.set_table_data("session_records", [
            {"id": "sr-001", "appointment_id": "appt-t1"},
        ])
        db.set_table_data("video_rooms", [
            {"id": "vr-001", "appointment_id": "appt-t1"},
        ])
        # The deletion chain below consults these tables.
        for t in (
            "session_summary_versions", "session_observations",
            "session_audio_segments", "session_interruptions",
            "clinical_longitudinal_analyses", "patient_longitudinal_analyses",
            "messages", "conversation_participants",
            "wallets", "wallet_movements",
            "therapist_settings", "therapist_profiles",
        ):
            db.set_table_data(t, [])
        # Explicit wallet for the wallet-movements iteration.
        db.set_table_data("wallets", [
            {"id": "w-1", "owner_id": "therapist-001", "owner_type": "therapist"},
        ])

        result = await lgpd_service.delete_therapist_data(
            "therapist-001", "all", None, db,
        )

        # Every table in the therapist's dependency graph should appear.
        expected = {
            "session_summary_versions", "session_observations",
            "session_audio_segments", "session_interruptions",
            "session_records",
            "clinical_longitudinal_analyses", "patient_longitudinal_analyses",
            "messages", "conversation_participants",
            "wallet_movements", "wallets",
            "therapist_settings", "therapist_profiles",
        }
        for table in expected:
            assert table in result["deleted"], f"{table} missing from deleted"

        assert len(result["deleted"]) == len(expected)

    @pytest.mark.asyncio
    async def test_delete_all_with_no_sessions_skips_session_branches(self):
        """Therapist with zero appointments should skip all session-related deletion branches.

        Depth cascades (summaries/observations/audio/interruptions/session_records)
        are only issued when there's something to cascade to — avoids running
        wasteful `.in_("x", [])` queries and keeps the `deleted` list honest.
        """
        db = MockSupabaseClient()
        db.set_table_data("appointments", [])  # no appointments for this therapist
        db.set_table_data("session_records", [])
        db.set_table_data("video_rooms", [])
        for t in (
            "clinical_longitudinal_analyses", "patient_longitudinal_analyses",
            "messages", "conversation_participants",
            "wallets", "wallet_movements",
            "therapist_settings", "therapist_profiles",
        ):
            db.set_table_data(t, [])

        result = await lgpd_service.delete_therapist_data(
            "therapist-001", "all", None, db,
        )

        # Session-chain tables NOT in the deleted list (no IDs to delete).
        for skipped in (
            "session_summary_versions", "session_observations",
            "session_audio_segments", "session_interruptions",
            "session_records",
        ):
            assert skipped not in result["deleted"], f"{skipped} should be skipped when no sessions exist"

        # Non-session tables still run.
        for always in (
            "clinical_longitudinal_analyses", "patient_longitudinal_analyses",
            "messages", "conversation_participants",
            "wallet_movements", "wallets",
            "therapist_settings", "therapist_profiles",
        ):
            assert always in result["deleted"], f"{always} should always run in 'all' deletion"

    @pytest.mark.asyncio
    async def test_delete_invalid_entity_type_returns_400(self):
        db = MockSupabaseClient()
        with pytest.raises(Exception) as exc_info:
            await lgpd_service.delete_therapist_data(
                "therapist-001", "invalid", None, db,
            )
        assert exc_info.value.status_code == 400
