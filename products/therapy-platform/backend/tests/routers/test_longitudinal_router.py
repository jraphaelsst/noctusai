"""
Tests for the Longitudinal Router.

Covers: clinical longitudinal (therapist), clinical versions,
personal longitudinal (patient), personal versions,
and auth/permission checks.
"""
import pytest

SAMPLE_CLINICAL_ANALYSIS = {
    "id": "cla-001",
    "patient_id": "patient-001",
    "therapist_id": "test-user-123",
    "version_number": 1,
    "summary": "Paciente apresenta evolucao positiva no tratamento.",
    "key_themes": ["ansiedade", "autoconhecimento"],
    "created_at": "2026-04-01T12:00:00Z",
}

SAMPLE_PERSONAL_ANALYSIS = {
    "id": "pla-001",
    "patient_id": "test-user-123",
    "therapist_id": "therapist-001",
    "version_number": 1,
    "summary": "Minha jornada de autoconhecimento continua.",
    "created_at": "2026-04-01T12:00:00Z",
}


class TestGetClinicalLongitudinal:
    """GET /api/longitudinal/clinical/:patient_id"""

    def test_get_clinical_longitudinal_therapist(self, client):
        """Therapist gets clinical longitudinal analysis for a patient."""
        client._mock_supabase.set_table_data(
            "clinical_longitudinal_analyses", [SAMPLE_CLINICAL_ANALYSIS]
        )
        resp = client.get("/api/longitudinal/clinical/patient-001")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "analysis" in body["data"]

    def test_get_clinical_longitudinal_not_found(self, client):
        """No analysis found returns 404."""
        client._mock_supabase.set_table_data("clinical_longitudinal_analyses", [])
        resp = client.get("/api/longitudinal/clinical/patient-001")
        assert resp.status_code == 404

    def test_get_clinical_longitudinal_patient_forbidden(self, patient_client):
        """Patient cannot access clinical longitudinal."""
        resp = patient_client.get("/api/longitudinal/clinical/patient-001")
        assert resp.status_code == 403

    def test_get_clinical_longitudinal_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/longitudinal/clinical/patient-001")
        assert resp.status_code == 401


class TestListClinicalLongitudinalVersions:
    """GET /api/longitudinal/clinical/:patient_id/versions"""

    def test_list_clinical_versions(self, client):
        """Therapist lists clinical longitudinal versions."""
        client._mock_supabase.set_table_data(
            "clinical_longitudinal_analyses", [SAMPLE_CLINICAL_ANALYSIS]
        )
        resp = client.get("/api/longitudinal/clinical/patient-001/versions")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_clinical_versions_patient_forbidden(self, patient_client):
        """Patient cannot list clinical longitudinal versions."""
        resp = patient_client.get("/api/longitudinal/clinical/patient-001/versions")
        assert resp.status_code == 403


class TestGetPersonalLongitudinal:
    """GET /api/longitudinal/personal"""

    def test_get_personal_longitudinal(self, patient_client):
        """Patient gets own personal longitudinal analysis."""
        patient_client._mock_supabase.set_table_data(
            "patient_longitudinal_analyses", [SAMPLE_PERSONAL_ANALYSIS]
        )
        resp = patient_client.get("/api/longitudinal/personal")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_get_personal_longitudinal_not_found(self, patient_client):
        """No analysis found returns 404."""
        patient_client._mock_supabase.set_table_data("patient_longitudinal_analyses", [])
        resp = patient_client.get("/api/longitudinal/personal")
        assert resp.status_code == 404

    def test_get_personal_longitudinal_therapist_forbidden(self, client):
        """Therapist cannot access patient's personal longitudinal."""
        resp = client.get("/api/longitudinal/personal")
        assert resp.status_code == 403


class TestListPersonalLongitudinalVersions:
    """GET /api/longitudinal/personal/versions"""

    def test_list_personal_versions(self, patient_client):
        """Patient lists own personal longitudinal versions."""
        patient_client._mock_supabase.set_table_data(
            "patient_longitudinal_analyses", [SAMPLE_PERSONAL_ANALYSIS]
        )
        resp = patient_client.get("/api/longitudinal/personal/versions")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_personal_versions_therapist_forbidden(self, client):
        """Therapist cannot access patient's personal versions."""
        resp = client.get("/api/longitudinal/personal/versions")
        assert resp.status_code == 403

    def test_list_personal_versions_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/longitudinal/personal/versions")
        assert resp.status_code == 401
