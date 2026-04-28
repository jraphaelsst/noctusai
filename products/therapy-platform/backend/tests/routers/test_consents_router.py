"""
Tests for the Consents Router.

Covers: grant, revoke, list. Actor restrictions (patient/therapist-of-session
only). compliance-audit-reconciliation Phase 5 / Q5 (2026-04-22).
"""
SAMPLE_APPOINTMENT = {
    "id": "appt-c-001",
    "therapist_id": "test-user-123",
    "patient_id": "patient-c-001",
    "clinic_id": None,
    "status": "waiting",
}

SAMPLE_CONSENT = {
    "id": "consent-c-001",
    "appointment_id": "appt-c-001",
    "patient_id": "patient-c-001",
    "therapist_id": "test-user-123",
    "clinic_id": None,
    "scope": "recording",
    "policy_version": "v1",
    "purpose_text": "Consentimento para gravação da sessão.",
    "actor_user_id": "patient-c-001",
    "granted_at": "2026-04-22T10:00:00-03:00",
    "revoked_at": None,
}


def _setup(mock_sb, consents=None):
    mock_sb.set_table_data("appointments", [SAMPLE_APPOINTMENT])
    mock_sb.set_table_data("consent_records", consents or [])


class TestGrantConsent:
    """POST /api/consents/grant"""

    def test_grant_as_therapist(self, client):
        _setup(client._mock_supabase)
        resp = client.post("/api/consents/grant", json={
            "appointment_id": "appt-c-001",
            "scope": "recording",
            "policy_version": "v1",
            "purpose_text": "Gravação para fins clínicos.",
        })
        assert resp.status_code == 200

    def test_grant_as_patient_accepted(self, patient_client):
        """Patient grants their own consent — accepted if they're the
        patient of the appointment (RLS scoped)."""
        # Mock the appointment so patient_client (user=patient-001) is the
        # participant. The test-patient fixture's user id is `test-user-123`
        # by default — align the appointment accordingly.
        appt = {**SAMPLE_APPOINTMENT, "patient_id": "test-user-123"}
        patient_client._mock_supabase.set_table_data("appointments", [appt])
        patient_client._mock_supabase.set_table_data("consent_records", [])
        resp = patient_client.post("/api/consents/grant", json={
            "appointment_id": "appt-c-001",
            "scope": "recording",
            "policy_version": "v1",
            "purpose_text": "Gravação para fins clínicos.",
        })
        assert resp.status_code == 200

    def test_grant_clinic_admin_forbidden(self, clinic_admin_client):
        """Clinic admin cannot register consent on behalf of a session."""
        _setup(clinic_admin_client._mock_supabase)
        resp = clinic_admin_client.post("/api/consents/grant", json={
            "appointment_id": "appt-c-001",
            "scope": "recording",
            "policy_version": "v1",
            "purpose_text": "Gravação para fins clínicos.",
        })
        assert resp.status_code == 403

    def test_grant_unknown_appointment_returns_404(self, client):
        client._mock_supabase.set_table_data("appointments", [])
        client._mock_supabase.set_table_data("consent_records", [])
        resp = client.post("/api/consents/grant", json={
            "appointment_id": "does-not-exist",
            "scope": "recording",
            "policy_version": "v1",
            "purpose_text": "x",
        })
        assert resp.status_code == 404

    def test_grant_invalid_scope_rejected(self, client):
        _setup(client._mock_supabase)
        resp = client.post("/api/consents/grant", json={
            "appointment_id": "appt-c-001",
            "scope": "something_else",
            "policy_version": "v1",
            "purpose_text": "x",
        })
        assert resp.status_code == 422

    def test_grant_401(self, client):
        resp = client._tc.post("/api/consents/grant", json={
            "appointment_id": "appt-c-001",
            "scope": "recording",
            "policy_version": "v1",
            "purpose_text": "x",
        })
        assert resp.status_code == 401


class TestRevokeConsent:
    """POST /api/consents/revoke"""

    def test_revoke_active_consent(self, client):
        _setup(client._mock_supabase, consents=[SAMPLE_CONSENT])
        resp = client.post("/api/consents/revoke", json={
            "appointment_id": "appt-c-001",
            "scope": "recording",
        })
        assert resp.status_code == 200

    def test_revoke_when_no_record_returns_404(self, client):
        _setup(client._mock_supabase, consents=[])
        resp = client.post("/api/consents/revoke", json={
            "appointment_id": "appt-c-001",
            "scope": "recording",
        })
        assert resp.status_code == 404

    def test_revoke_already_revoked_returns_400(self, client):
        revoked = {**SAMPLE_CONSENT, "revoked_at": "2026-04-22T11:00:00-03:00"}
        _setup(client._mock_supabase, consents=[revoked])
        resp = client.post("/api/consents/revoke", json={
            "appointment_id": "appt-c-001",
            "scope": "recording",
        })
        assert resp.status_code == 400

    def test_revoke_clinic_admin_forbidden(self, clinic_admin_client):
        _setup(clinic_admin_client._mock_supabase, consents=[SAMPLE_CONSENT])
        resp = clinic_admin_client.post("/api/consents/revoke", json={
            "appointment_id": "appt-c-001",
            "scope": "recording",
        })
        assert resp.status_code == 403


class TestListConsents:
    """GET /api/consents/{appointment_id}"""

    def test_list_returns_all_scopes(self, client):
        other_scope = {
            **SAMPLE_CONSENT, "id": "consent-c-002", "scope": "transcription",
        }
        _setup(client._mock_supabase, consents=[SAMPLE_CONSENT, other_scope])
        resp = client.get("/api/consents/appt-c-001")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2

    def test_list_401(self, client):
        resp = client._tc.get("/api/consents/appt-c-001")
        assert resp.status_code == 401
