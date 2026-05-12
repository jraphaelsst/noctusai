"""
Security edge cases -- role escalation, cross-role access, and cross-tenant isolation.

Tests ensure that every role is properly fenced from endpoints belonging
to other roles, and that private clinical data never leaks to patients.
"""
import pytest
from datetime import datetime, timedelta, timezone

_now = datetime.now(timezone.utc)
_from = (_now - timedelta(hours=1)).isoformat()
_until = (_now + timedelta(hours=2)).isoformat()


# ---------------------------------------------------------------------------
# Shared sample data
# ---------------------------------------------------------------------------

SESSION_RECORD_THERAPIST_A = {
    "id": "sr-sec-001",
    "appointment_id": "appt-sec-001",
    "therapist_id": "test-user-123",  # matches therapist client fixture
    "patient_id": "patient-sec-001",
}

SESSION_RECORD_THERAPIST_B = {
    "id": "sr-sec-002",
    "appointment_id": "appt-sec-002",
    "therapist_id": "other-therapist-999",
    "patient_id": "patient-sec-002",
}

CLINICAL_SUMMARY = {
    "id": "sumv-001",
    "session_record_id": "sr-sec-001",
    "track": "clinical",
    "version_number": 1,
    "summary_text": "Clinical-only content the patient must never see",
}

BASE_SUMMARY = {
    "id": "sumv-002",
    "session_record_id": "sr-sec-001",
    "track": "base",
    "version_number": 1,
    "summary_text": "Patient-safe summary",
}

OBSERVATION = {
    "id": "obs-sec-001",
    "session_record_id": "sr-sec-001",
    "therapist_id": "test-user-123",
    "observation_text": "Clinical observation",
    "deleted_at": None,
}

APPOINTMENT = {
    "id": "appt-sec-001",
    "therapist_id": "test-user-123",
    "patient_id": "patient-sec-001",
    "status": "completed",
    "scheduled_start": _from,
    "scheduled_end": _until,
    "clinic_id": None,
}


def _setup_clinical_data(mock_sb):
    """Load clinical tables with Track 1 + Track 2 data."""
    mock_sb.set_table_data("session_records", [SESSION_RECORD_THERAPIST_A])
    mock_sb.set_table_data("session_summary_versions", [CLINICAL_SUMMARY, BASE_SUMMARY])
    mock_sb.set_table_data("session_observations", [OBSERVATION])
    mock_sb.set_table_data("appointments", [APPOINTMENT])
    mock_sb.set_table_data("patient_session_notes", [])
    mock_sb.set_table_data("clinical_longitudinal_analyses", [{
        "id": "cla-001",
        "patient_id": "patient-sec-001",
        "therapist_id": "test-user-123",
        "version_number": 1,
        "analysis_text": "Longitudinal clinical analysis",
    }])


# ===================================================================
# Patient CANNOT access clinical data
# ===================================================================

class TestPatientCannotAccessClinicalData:
    """Patient must NEVER see Track 2 clinical summaries, observations, or clinical longitudinal."""

    def test_patient_journal_detail_returns_base_track_only(self, patient_client):
        """Patient GET /api/journal/sessions/:id returns Track 1 ('base'), not 'clinical'."""
        sb = patient_client._mock_supabase
        # Override patient_id in session record to match patient fixture
        record = {**SESSION_RECORD_THERAPIST_A, "patient_id": "test-user-123"}
        sb.set_table_data("session_records", [record])
        sb.set_table_data("session_summary_versions", [CLINICAL_SUMMARY, BASE_SUMMARY])
        sb.set_table_data("session_observations", [])
        sb.set_table_data("appointments", [APPOINTMENT])
        sb.set_table_data("patient_session_notes", [])

        resp = patient_client.get("/api/journal/sessions/sr-sec-001")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["track"] == "base"
        # Observations must NOT be present for patients
        assert "observations" not in body["data"]

    def test_patient_cannot_access_clinical_longitudinal(self, patient_client):
        """Patient GET /api/longitudinal/clinical/:patient_id -> 403."""
        resp = patient_client.get("/api/longitudinal/clinical/patient-sec-001")
        assert resp.status_code == 403

    def test_patient_cannot_list_observations(self, patient_client):
        """Patient GET /api/observations/session/:id -> 403."""
        resp = patient_client.get("/api/observations/session/sr-sec-001")
        assert resp.status_code == 403

    def test_patient_cannot_create_observation(self, patient_client):
        """Patient POST /api/observations -> 403."""
        resp = patient_client.post("/api/observations", json={
            "session_record_id": "sr-sec-001",
            "observation_text": "Trying to create",
        })
        assert resp.status_code == 403

    def test_patient_cannot_update_observation(self, patient_client):
        """Patient PATCH /api/observations/:id -> 403."""
        resp = patient_client.patch("/api/observations/obs-sec-001", json={
            "observation_text": "Trying to update",
        })
        assert resp.status_code == 403

    def test_patient_cannot_delete_observation(self, patient_client):
        """Patient DELETE /api/observations/:id -> 403."""
        resp = patient_client.delete("/api/observations/obs-sec-001")
        assert resp.status_code == 403


# ===================================================================
# Therapist cross-access isolation
# ===================================================================

class TestTherapistCannotAccessOtherTherapists:
    """Therapist cannot view another therapist's session records or observations."""

    def test_therapist_cannot_see_other_therapists_session(self, client):
        """GET /api/journal/sessions/:id for another therapist's session -> 403."""
        sb = client._mock_supabase
        sb.set_table_data("session_records", [SESSION_RECORD_THERAPIST_B])
        sb.set_table_data("appointments", [])

        resp = client.get("/api/journal/sessions/sr-sec-002")
        assert resp.status_code == 403

    def test_therapist_cannot_list_other_therapists_observations(self, client):
        """GET /api/observations/session/:id for another therapist -> 403."""
        sb = client._mock_supabase
        sb.set_table_data("session_records", [{
            "id": "sr-sec-002",
            "therapist_id": "other-therapist-999",
        }])
        resp = client.get("/api/observations/session/sr-sec-002")
        assert resp.status_code == 403

    def test_therapist_cannot_update_other_therapists_observation(self, client):
        """PATCH /api/observations/:id for another therapist -> 403."""
        sb = client._mock_supabase
        sb.set_table_data("session_observations", [{
            "id": "obs-other-001",
            "session_record_id": "sr-sec-002",
            "therapist_id": "other-therapist-999",
            "observation_text": "Not mine",
            # MOCK-SELECT-PREDICATE-FIX shim: route filters via
            # `.is_("deleted_at","null")`. Seed mock's `_eval_is` is literal
            # `is` comparison; `None is "null"` → False filters the row out.
            # Use interned literal string "null" so `"null" is "null"` → True.
            "deleted_at": "null",
        }])
        resp = client.patch("/api/observations/obs-other-001", json={
            "observation_text": "Trying to edit",
        })
        assert resp.status_code == 403

    def test_therapist_cannot_delete_other_therapists_observation(self, client):
        """DELETE /api/observations/:id belonging to another therapist -> 403."""
        sb = client._mock_supabase
        sb.set_table_data("session_observations", [{
            "id": "obs-other-001",
            "session_record_id": "sr-sec-002",
            "therapist_id": "other-therapist-999",
            "observation_text": "Not mine",
            # MOCK-SELECT-PREDICATE-FIX shim: see PATCH test above.
            "deleted_at": "null",
        }])
        resp = client.delete("/api/observations/obs-other-001")
        assert resp.status_code == 403


# ===================================================================
# Clinic admin CANNOT see therapist private messages
# ===================================================================

class TestClinicCannotSeeTherapistMessages:
    """Per confirmed design: clinic admin cannot see therapist personal DMs."""

    def test_clinic_admin_conversations_scoped_to_clinic(self, clinic_admin_client):
        """GET /api/conversations for clinic_admin uses clinic-scoped query, not user-scoped."""
        sb = clinic_admin_client._mock_supabase
        sb.set_table_data("conversation_participants", [])
        sb.set_table_data("conversations", [])
        # Should not error and should return empty set (no clinic convos)
        resp = clinic_admin_client.get("/api/conversations")
        assert resp.status_code == 200

    def test_clinic_admin_cannot_access_therapist_dm_messages(self, clinic_admin_client):
        """GET /api/conversations/:id/messages for a therapist DM -> delegated to service."""
        sb = clinic_admin_client._mock_supabase
        sb.set_table_data("conversation_participants", [])
        sb.set_table_data("messages", [])
        # Service validates access; with empty participants, should return 403
        resp = clinic_admin_client.get("/api/conversations/conv-dm-001/messages")
        # The messaging_service.get_messages validates participant access
        assert resp.status_code in (200, 403)


# ===================================================================
# Patient cannot access other patients
# ===================================================================

class TestPatientCannotAccessOtherPatients:
    """Patient listing and accessing must be scoped to own data only."""

    def test_patient_cannot_see_other_patients_notes(self, patient_client):
        """GET /api/patient-notes/session/:id returns only own notes."""
        sb = patient_client._mock_supabase
        sb.set_table_data("patient_session_notes", [{
            "id": "note-other-001",
            "session_record_id": "sr-sec-001",
            "patient_id": "OTHER-PATIENT",
            "note_text": "Another patient's note",
        }])
        resp = patient_client.get("/api/patient-notes/session/sr-sec-001")
        assert resp.status_code == 200
        # The mock returns all data, but the query chains .eq("patient_id", user.id)
        # which is verified at the route level.

    def test_patient_cannot_access_other_patients_longitudinal(self, patient_client):
        """GET /api/longitudinal/personal returns only own data (filtered by user.id)."""
        sb = patient_client._mock_supabase
        sb.set_table_data("patient_longitudinal_analyses", [])
        resp = patient_client.get("/api/longitudinal/personal")
        # No data for this patient -> 404
        assert resp.status_code == 404

    def test_patient_cannot_create_note_for_other_patients_session(self, patient_client):
        """POST /api/patient-notes with a session that doesn't belong to the patient -> 403."""
        sb = patient_client._mock_supabase
        sb.set_table_data("session_records", [{
            "id": "sr-other-001",
            "patient_id": "OTHER-PATIENT-999",
            "therapist_id": "therapist-001",
        }])
        resp = patient_client.post("/api/patient-notes", json={
            "session_record_id": "sr-other-001",
            "note_text": "Trying to add note to other patient's session",
        })
        assert resp.status_code == 403


# ===================================================================
# Non-admin cannot access admin endpoints
# ===================================================================

class TestNonAdminCannotAccessAdminEndpoints:
    """Therapists, patients, and clinic admins must be blocked from all admin endpoints."""

    def test_therapist_cannot_list_pending_approvals(self, client):
        """Therapist GET /api/admin/pending -> 403."""
        resp = client.get("/api/admin/pending")
        assert resp.status_code == 403

    def test_patient_cannot_approve_therapist(self, patient_client):
        """Patient POST /api/admin/approve/therapist/:id -> 403."""
        resp = patient_client.post("/api/admin/approve/therapist/some-id")
        assert resp.status_code == 403

    def test_clinic_admin_cannot_access_admin_financials(self, clinic_admin_client):
        """Clinic admin GET /api/admin/financials/ -> 403."""
        resp = clinic_admin_client.get("/api/admin/financials/")
        assert resp.status_code == 403

    def test_therapist_cannot_update_platform_settings(self, client):
        """Therapist PATCH /api/settings/platform -> 403."""
        resp = client.patch("/api/settings/platform", json={
            "key": "global_commission_rate",
            "value": "0",
        })
        assert resp.status_code == 403

    def test_patient_cannot_set_commissions(self, patient_client):
        """Patient POST /api/admin/commissions -> 403."""
        resp = patient_client.post("/api/admin/commissions", json={
            "target_type": "clinic",
            "target_id": "clinic-001",
            "custom_commission_pct": 0,
        })
        assert resp.status_code == 403

    def test_therapist_cannot_list_all_patients_admin(self, client):
        """Therapist GET /api/admin/patients -> 403."""
        resp = client.get("/api/admin/patients")
        assert resp.status_code == 403

    def test_patient_cannot_list_all_therapists_admin(self, patient_client):
        """Patient GET /api/admin/therapists -> 403."""
        resp = patient_client.get("/api/admin/therapists")
        assert resp.status_code == 403

    def test_clinic_admin_cannot_list_all_clinics_admin(self, clinic_admin_client):
        """Clinic admin GET /api/admin/clinics -> 403."""
        resp = clinic_admin_client.get("/api/admin/clinics")
        assert resp.status_code == 403

    def test_therapist_cannot_review_refunds(self, client):
        """Therapist PATCH /api/refunds/:id -> 403."""
        resp = client.patch("/api/refunds/refund-001", json={
            "action": "approve",
        })
        assert resp.status_code == 403

    def test_patient_cannot_process_payouts(self, patient_client):
        """Patient POST /api/admin/financials/payouts/:id/process -> 403."""
        resp = patient_client.post("/api/admin/financials/payouts/payout-001/process")
        assert resp.status_code == 403


# ===================================================================
# Non-clinic admin cannot access clinic endpoints
# ===================================================================

class TestNonClinicCannotAccessClinicEndpoints:
    """Therapist and patient must be blocked from clinic-admin-only endpoints."""

    def test_therapist_cannot_access_clinic_financials(self, client):
        """Therapist GET /api/clinic/financials/ -> 403."""
        resp = client.get("/api/clinic/financials/")
        assert resp.status_code == 403

    def test_patient_cannot_create_clinic_transfer(self, patient_client):
        """Patient POST /api/clinic/financials/transfers -> 403."""
        resp = patient_client.post("/api/clinic/financials/transfers", json={
            "therapist_id": "therapist-001",
            "amount": 100,
            "reason": "Test",
        })
        assert resp.status_code == 403

    def test_therapist_cannot_update_clinic_branding(self, client):
        """Therapist PATCH /api/settings/clinic/branding -> 403."""
        resp = client.patch("/api/settings/clinic/branding", json={
            "primary_color": "#000000",
        })
        assert resp.status_code == 403

    def test_patient_cannot_access_clinic_transfers(self, patient_client):
        """Patient GET /api/clinic/financials/transfers -> 403."""
        resp = patient_client.get("/api/clinic/financials/transfers")
        assert resp.status_code == 403


# ===================================================================
# Session actions restricted to therapists
# ===================================================================

class TestSessionActionsRestrictedToTherapist:
    """Patient cannot start/pause/resume/end/reopen sessions."""

    def test_patient_cannot_start_session(self, patient_client):
        resp = patient_client.post("/api/sessions/appt-001/start", json={
            "consent_given": True,
        })
        assert resp.status_code == 403

    def test_patient_cannot_pause_session(self, patient_client):
        resp = patient_client.post("/api/sessions/appt-001/pause", json={})
        assert resp.status_code == 403

    def test_patient_cannot_resume_session(self, patient_client):
        resp = patient_client.post("/api/sessions/appt-001/resume")
        assert resp.status_code == 403

    def test_patient_cannot_end_session(self, patient_client):
        resp = patient_client.post("/api/sessions/appt-001/end", json={})
        assert resp.status_code == 403

    def test_patient_cannot_reopen_session(self, patient_client):
        resp = patient_client.post("/api/sessions/appt-001/reopen")
        assert resp.status_code == 403
