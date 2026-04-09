"""
Tests for the Crisis Alerts Router.

Covers: list alerts (role-filtered), get alert, review alert,
manual scan (admin only), and auth/permission checks.
"""
import pytest

SAMPLE_ALERT = {
    "id": "alert-001",
    "patient_id": "patient-001",
    "therapist_id": "test-user-123",
    "source_type": "journal",
    "source_id": "journal-001",
    "keywords_found": ["quero morrer", "sem saída"],
    "severity": "alta",
    "status": "pendente",
    "detected_at": "2026-04-01T10:00:00Z",
}


class TestListAlerts:
    """GET /api/alertas-crise"""

    def test_list_alerts_therapist(self, client):
        """Therapist lists crisis alerts for their patients."""
        client._mock_supabase.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        resp = client.get("/api/alertas-crise")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_alerts_admin(self, admin_client):
        """Platform admin lists all crisis alerts."""
        admin_client._mock_supabase.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        resp = admin_client.get("/api/alertas-crise")
        assert resp.status_code == 200

    def test_list_alerts_with_status_filter(self, client):
        """Therapist filters alerts by status."""
        client._mock_supabase.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        resp = client.get("/api/alertas-crise", params={"status": "pendente"})
        assert resp.status_code == 200

    def test_list_alerts_patient_forbidden(self, patient_client):
        """Patient cannot view crisis alerts."""
        resp = patient_client.get("/api/alertas-crise")
        assert resp.status_code == 403


class TestGetAlert:
    """GET /api/alertas-crise/{alert_id}"""

    def test_get_alert_therapist(self, client):
        """Therapist gets their own patient's alert."""
        client._mock_supabase.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        resp = client.get("/api/alertas-crise/alert-001")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_get_alert_not_found(self, client):
        """Non-existent alert returns 404."""
        client._mock_supabase.set_table_data("crisis_alerts", [])
        resp = client.get("/api/alertas-crise/nonexistent")
        assert resp.status_code == 404

    def test_get_alert_not_owner(self, client):
        """Therapist cannot view another therapist's alert."""
        other_alert = {**SAMPLE_ALERT, "therapist_id": "other-therapist-999"}
        client._mock_supabase.set_table_data("crisis_alerts", [other_alert])
        resp = client.get("/api/alertas-crise/alert-001")
        assert resp.status_code == 403

    def test_get_alert_admin_can_view_all(self, admin_client):
        """Platform admin can view any alert."""
        admin_client._mock_supabase.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        resp = admin_client.get("/api/alertas-crise/alert-001")
        assert resp.status_code == 200

    def test_get_alert_patient_forbidden(self, patient_client):
        """Patient cannot view crisis alerts."""
        resp = patient_client.get("/api/alertas-crise/alert-001")
        assert resp.status_code == 403


class TestReviewAlert:
    """PATCH /api/alertas-crise/{alert_id}/revisar"""

    def test_review_alert(self, client):
        """Therapist reviews their own patient's alert."""
        client._mock_supabase.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        resp = client.patch("/api/alertas-crise/alert-001/revisar", json={
            "status": "revisado",
        })
        assert resp.status_code == 200

    def test_review_alert_not_found(self, client):
        """Non-existent alert returns 404."""
        client._mock_supabase.set_table_data("crisis_alerts", [])
        resp = client.patch("/api/alertas-crise/nonexistent/revisar", json={
            "status": "revisado",
        })
        assert resp.status_code == 404

    def test_review_alert_not_owner(self, client):
        """Therapist cannot review another therapist's alert."""
        other_alert = {**SAMPLE_ALERT, "therapist_id": "other-therapist-999"}
        client._mock_supabase.set_table_data("crisis_alerts", [other_alert])
        resp = client.patch("/api/alertas-crise/alert-001/revisar", json={
            "status": "revisado",
        })
        assert resp.status_code == 403

    def test_review_alert_patient_forbidden(self, patient_client):
        """Patient cannot review crisis alerts."""
        resp = patient_client.patch("/api/alertas-crise/alert-001/revisar", json={
            "status": "revisado",
        })
        assert resp.status_code == 403

    def test_review_alert_admin_allowed(self, admin_client):
        """Platform admin can review any alert."""
        admin_client._mock_supabase.set_table_data("crisis_alerts", [SAMPLE_ALERT])
        resp = admin_client.patch("/api/alertas-crise/alert-001/revisar", json={
            "status": "revisado",
        })
        assert resp.status_code == 200


class TestManualScan:
    """POST /api/alertas-crise/escanear"""

    def test_manual_scan_admin(self, admin_client):
        """Platform admin triggers a manual scan."""
        admin_client._mock_supabase.set_table_data("mood_entries", [])
        admin_client._mock_supabase.set_table_data("journal_entries", [])
        resp = admin_client.post("/api/alertas-crise/escanear")
        assert resp.status_code == 200

    def test_manual_scan_clinic_admin(self, clinic_admin_client):
        """Clinic admin triggers a manual scan."""
        clinic_admin_client._mock_supabase.set_table_data("mood_entries", [])
        clinic_admin_client._mock_supabase.set_table_data("journal_entries", [])
        resp = clinic_admin_client.post("/api/alertas-crise/escanear")
        assert resp.status_code == 200

    def test_manual_scan_therapist_forbidden(self, client):
        """Therapist cannot trigger manual scan."""
        resp = client.post("/api/alertas-crise/escanear")
        assert resp.status_code == 403

    def test_manual_scan_patient_forbidden(self, patient_client):
        """Patient cannot trigger manual scan."""
        resp = patient_client.post("/api/alertas-crise/escanear")
        assert resp.status_code == 403
