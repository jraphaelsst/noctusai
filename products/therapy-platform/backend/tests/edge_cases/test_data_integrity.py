"""
Data integrity edge cases -- validation constraints, required fields, pagination.

Tests cover Pydantic schema validation boundaries, LGPD confirmation requirements,
and pagination edge cases.
"""
import pytest


# ===================================================================
# Review validation constraints
# ===================================================================

class TestReviewValidation:
    """Star rating must be 1-5; review text max 2000 chars."""

    def test_star_rating_zero_rejected(self, patient_client):
        """star_rating=0 -> 422 (ge=1)."""
        resp = patient_client.post("/api/reviews", json={
            "therapist_id": "therapist-001",
            "star_rating": 0,
        })
        assert resp.status_code == 422

    def test_star_rating_six_rejected(self, patient_client):
        """star_rating=6 -> 422 (le=5)."""
        resp = patient_client.post("/api/reviews", json={
            "therapist_id": "therapist-001",
            "star_rating": 6,
        })
        assert resp.status_code == 422

    def test_star_rating_negative_rejected(self, patient_client):
        """star_rating=-1 -> 422 (ge=1)."""
        resp = patient_client.post("/api/reviews", json={
            "therapist_id": "therapist-001",
            "star_rating": -1,
        })
        assert resp.status_code == 422

    def test_star_rating_1_accepted(self, patient_client):
        """star_rating=1 -> passes schema validation (minimum valid rating)."""
        sb = patient_client._mock_supabase
        sb.set_table_data("sessions", [
            {"id": "sess-001", "patient_id": "test-user-123",
             "therapist_id": "therapist-001", "status": "completed"},
        ])
        # therapist_reviews: empty for existing-check, but insert returns this row
        sb.set_table_data("therapist_reviews", [
            {"id": "rev-new", "patient_id": "test-user-123",
             "therapist_id": "therapist-001", "star_rating": 1},
        ])
        resp = patient_client.post("/api/reviews", json={
            "therapist_id": "therapist-001",
            "star_rating": 1,
        })
        # The mock returns therapist_reviews data for both the existing-check
        # and the insert, so the existing-check sees a row and returns 409.
        # This is a mock limitation; the schema validation (ge=1) passes.
        assert resp.status_code in (200, 409)

    def test_star_rating_5_accepted(self, patient_client):
        """star_rating=5 -> passes schema validation (maximum valid rating)."""
        resp = patient_client.post("/api/reviews", json={
            "therapist_id": "therapist-001",
            "star_rating": 5,
        })
        # If service-level checks fail (mock), that's fine -- schema accepted it.
        # Key: it does NOT return 422 (Pydantic validation error).
        assert resp.status_code != 422

    def test_review_text_too_long_rejected(self, patient_client):
        """review_text > 2000 chars -> 422."""
        resp = patient_client.post("/api/reviews", json={
            "therapist_id": "therapist-001",
            "star_rating": 5,
            "review_text": "A" * 2001,
        })
        assert resp.status_code == 422

    def test_clinic_review_star_zero_rejected(self, patient_client):
        """Clinic review with star_rating=0 -> 422."""
        resp = patient_client.post("/api/reviews/clinic", json={
            "clinic_id": "clinic-001",
            "star_rating": 0,
        })
        assert resp.status_code == 422


# ===================================================================
# Review role restrictions
# ===================================================================

class TestReviewRoleRestrictions:
    """Only patients can create reviews; only therapists can respond."""

    def test_therapist_cannot_create_review(self, client):
        """Therapist POST /api/reviews -> 403."""
        resp = client.post("/api/reviews", json={
            "therapist_id": "therapist-001",
            "star_rating": 5,
        })
        assert resp.status_code == 403

    def test_therapist_cannot_create_clinic_review(self, client):
        """Therapist POST /api/reviews/clinic -> 403."""
        resp = client.post("/api/reviews/clinic", json={
            "clinic_id": "clinic-001",
            "star_rating": 5,
        })
        assert resp.status_code == 403

    def test_patient_cannot_respond_to_review(self, patient_client):
        """Patient POST /api/reviews/:id/respond -> 403."""
        resp = patient_client.post("/api/reviews/rev-001/respond", json={
            "response_text": "Thank you!",
        })
        assert resp.status_code == 403

    def test_patient_cannot_flag_review(self, patient_client):
        """Patient POST /api/reviews/:id/flag -> 403."""
        resp = patient_client.post("/api/reviews/rev-001/flag", json={
            "reason": "This review is inappropriate and offensive",
        })
        assert resp.status_code == 403


# ===================================================================
# Commission override validation
# ===================================================================

class TestCommissionOverrideValidation:
    """Commission overrides must have valid percentages and target types."""

    def test_commission_pct_above_100_rejected(self, admin_client):
        """custom_commission_pct > 100 -> 422."""
        resp = admin_client.post("/api/admin/financials/commissions", json={
            "target_type": "clinic",
            "target_id": "clinic-001",
            "custom_commission_pct": 101,
        })
        assert resp.status_code == 422

    def test_commission_pct_negative_rejected(self, admin_client):
        """custom_commission_pct < 0 -> 422."""
        resp = admin_client.post("/api/admin/financials/commissions", json={
            "target_type": "therapist",
            "target_id": "therapist-001",
            "custom_commission_pct": -5,
        })
        assert resp.status_code == 422

    def test_commission_pct_zero_accepted(self, admin_client):
        """custom_commission_pct=0 -> accepted (free)."""
        sb = admin_client._mock_supabase
        sb.set_table_data("platform_commission_overrides", [
            {"id": "pco-001", "target_type": "therapist", "target_id": "therapist-001",
             "custom_commission_pct": 0},
        ])
        resp = admin_client.post("/api/admin/financials/commissions", json={
            "target_type": "therapist",
            "target_id": "therapist-001",
            "custom_commission_pct": 0,
        })
        assert resp.status_code == 200

    def test_commission_pct_100_accepted(self, admin_client):
        """custom_commission_pct=100 -> accepted (full fee)."""
        sb = admin_client._mock_supabase
        sb.set_table_data("platform_commission_overrides", [
            {"id": "pco-002", "target_type": "clinic", "target_id": "clinic-001",
             "custom_commission_pct": 100},
        ])
        resp = admin_client.post("/api/admin/financials/commissions", json={
            "target_type": "clinic",
            "target_id": "clinic-001",
            "custom_commission_pct": 100,
        })
        assert resp.status_code == 200


# ===================================================================
# LGPD deletion confirmation
# ===================================================================

class TestLGPDDeletion:
    """LGPD deletion requires exact confirmation text."""

    def test_lgpd_wrong_confirmation_rejected(self, patient_client):
        """Wrong confirmation text -> 422."""
        resp = patient_client.post("/api/lgpd/delete-my-data", json={
            "confirmation": "confirmar exclusao",  # wrong case
        })
        assert resp.status_code == 422

    def test_lgpd_empty_confirmation_rejected(self, patient_client):
        """Empty confirmation -> 422."""
        resp = patient_client.post("/api/lgpd/delete-my-data", json={
            "confirmation": "",
        })
        assert resp.status_code == 422

    def test_lgpd_correct_confirmation_accepted(self, patient_client):
        """Exact 'CONFIRMAR EXCLUSAO' -> accepted."""
        sb = patient_client._mock_supabase
        sb.set_table_data("patient_profiles", [])
        sb.set_table_data("appointments", [])
        sb.set_table_data("session_records", [])
        sb.set_table_data("messages", [])
        sb.set_table_data("reviews", [])
        sb.set_table_data("wallets", [])
        sb.set_table_data("patient_session_notes", [])
        sb.set_table_data("conversation_participants", [])
        sb.set_table_data("patient_longitudinal_analyses", [])
        resp = patient_client.post("/api/lgpd/delete-my-data", json={
            "confirmation": "CONFIRMAR EXCLUSAO",
        })
        assert resp.status_code == 200

    def test_lgpd_therapist_cannot_use_patient_endpoint(self, client):
        """Therapist POST /api/lgpd/delete-my-data -> 403."""
        resp = client.post("/api/lgpd/delete-my-data", json={
            "confirmation": "CONFIRMAR EXCLUSAO",
        })
        assert resp.status_code == 403

    def test_lgpd_patient_cannot_use_therapist_endpoint(self, patient_client):
        """Patient POST /api/lgpd/delete-data/:entity_type/:id -> 403."""
        resp = patient_client.post("/api/lgpd/delete-data/session/session-001")
        assert resp.status_code == 403

    def test_lgpd_therapist_invalid_entity_type(self, client):
        """Therapist with invalid entity_type -> 400."""
        resp = client.post("/api/lgpd/delete-data/invalid_type/some-id")
        assert resp.status_code == 400

    def test_lgpd_therapist_delete_all(self, client):
        """Therapist can delete all data via LGPD entity_type='all'."""
        sb = client._mock_supabase
        sb.set_table_data("session_summary_versions", [])
        sb.set_table_data("session_records", [])
        sb.set_table_data("session_observations", [])
        sb.set_table_data("therapist_profiles", [])
        sb.set_table_data("therapist_settings", [])
        sb.set_table_data("messages", [])
        sb.set_table_data("wallets", [])
        sb.set_table_data("wallet_movements", [])
        sb.set_table_data("conversation_participants", [])
        sb.set_table_data("action_log", [])
        resp = client.post("/api/lgpd/delete-data/all/ignored")
        assert resp.status_code == 200

    def test_lgpd_therapist_delete_session_requires_ownership(self, client):
        """Therapist deleting session that doesn't exist -> 404."""
        sb = client._mock_supabase
        sb.set_table_data("session_records", [])
        sb.set_table_data("action_log", [])
        resp = client.post("/api/lgpd/delete-data/session/nonexistent-id")
        assert resp.status_code == 404

    def test_lgpd_therapist_delete_own_session(self, client):
        """Therapist can delete a session they own.

        Ownership flows session_records.appointment_id → appointments.therapist_id
        (no direct therapist_id column on session_records per live schema).
        """
        sb = client._mock_supabase
        sb.set_table_data("session_records", [
            {"id": "sr-lgpd-001", "appointment_id": "appt-lgpd-001"},
        ])
        sb.set_table_data("appointments", [
            {"id": "appt-lgpd-001", "therapist_id": "test-user-123"},
        ])
        sb.set_table_data("session_summary_versions", [])
        sb.set_table_data("session_observations", [])
        sb.set_table_data("action_log", [])
        resp = client.post("/api/lgpd/delete-data/session/sr-lgpd-001")
        assert resp.status_code == 200

    def test_lgpd_therapist_delete_observation_requires_ownership(self, client):
        """Therapist deleting observation that doesn't exist -> 404."""
        sb = client._mock_supabase
        sb.set_table_data("session_observations", [])
        sb.set_table_data("action_log", [])
        resp = client.post("/api/lgpd/delete-data/observation/nonexistent-id")
        assert resp.status_code == 404


# ===================================================================
# Pagination edge cases
# ===================================================================

class TestPaginationEdgeCases:
    """Pagination parameters are validated by FastAPI Query constraints."""

    def test_page_zero_rejected(self, client):
        """page=0 -> 422 (ge=1)."""
        resp = client.get("/api/appointments", params={"page": 0})
        assert resp.status_code == 422

    def test_page_size_zero_rejected(self, client):
        """page_size=0 -> 422 (ge=1)."""
        resp = client.get("/api/appointments", params={"page_size": 0})
        assert resp.status_code == 422

    def test_page_size_above_max_rejected(self, client):
        """page_size > max (100) -> 422 (le=100)."""
        resp = client.get("/api/appointments", params={"page_size": 101})
        assert resp.status_code == 422

    def test_page_beyond_total_returns_empty(self, client):
        """Page beyond total -> empty data, valid response."""
        sb = client._mock_supabase
        sb.set_table_data("appointments", [])
        resp = client.get("/api/appointments", params={"page": 999})
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []

    def test_negative_page_rejected(self, client):
        """page=-1 -> 422 (ge=1)."""
        resp = client.get("/api/appointments", params={"page": -1})
        assert resp.status_code == 422


# ===================================================================
# Settings role restrictions
# ===================================================================

class TestSettingsRoleRestrictions:
    """Settings endpoints enforce correct role."""

    def test_patient_cannot_access_therapist_settings(self, patient_client):
        """Patient GET /api/settings/therapist -> 403."""
        resp = patient_client.get("/api/settings/therapist")
        assert resp.status_code == 403

    def test_therapist_cannot_access_patient_settings(self, client):
        """Therapist GET /api/settings/patient -> 403."""
        resp = client.get("/api/settings/patient")
        assert resp.status_code == 403

    def test_patient_cannot_get_platform_settings(self, patient_client):
        """Patient GET /api/settings/platform -> 403."""
        resp = patient_client.get("/api/settings/platform")
        assert resp.status_code == 403

    def test_therapist_cannot_get_platform_settings(self, client):
        """Therapist GET /api/settings/platform -> 403."""
        resp = client.get("/api/settings/platform")
        assert resp.status_code == 403

    def test_therapist_cannot_update_ai_prompts(self, client):
        """Therapist PATCH /api/settings/platform/ai-prompts -> 403."""
        resp = client.patch("/api/settings/platform/ai-prompts", json={
            "prompt_key": "summary_v1",
            "prompt_text": "New prompt text that is at least 10 chars",
        })
        assert resp.status_code == 403

    def test_patient_cannot_access_clinic_branding(self, patient_client):
        """Patient GET /api/settings/clinic/branding -> 403."""
        resp = patient_client.get("/api/settings/clinic/branding")
        assert resp.status_code == 403


# ===================================================================
# Patient notes role restrictions
# ===================================================================

class TestPatientNotesRoleRestrictions:
    """Only patients can create and view patient notes."""

    def test_therapist_cannot_create_patient_note(self, client):
        """Therapist POST /api/patient-notes -> 403."""
        resp = client.post("/api/patient-notes", json={
            "session_record_id": "sr-001",
            "note_text": "Should not work",
        })
        assert resp.status_code == 403

    def test_therapist_cannot_view_patient_notes(self, client):
        """Therapist GET /api/patient-notes/session/:id -> 403."""
        resp = client.get("/api/patient-notes/session/sr-001")
        assert resp.status_code == 403

    def test_therapist_cannot_update_patient_note(self, client):
        """Therapist PATCH /api/patient-notes/:id -> 403."""
        resp = client.patch("/api/patient-notes/note-001", json={
            "note_text": "Updated by therapist",
        })
        assert resp.status_code == 403

    def test_clinic_admin_cannot_view_patient_notes(self, clinic_admin_client):
        """Clinic admin GET /api/patient-notes/session/:id -> 403."""
        resp = clinic_admin_client.get("/api/patient-notes/session/sr-001")
        assert resp.status_code == 403
