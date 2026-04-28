"""
Tests for the Anamnese Router.

Covers: create anamnese (therapist only), get by patient, update,
list, and auth/permission checks.
"""
import pytest

SAMPLE_ANAMNESE = {
    "id": "anamnese-001",
    "patient_id": "patient-001",
    "therapist_id": "test-user-123",
    "queixa_principal": "Ansiedade generalizada",
    "historia_pregressa": "Histórico de crises de ansiedade desde a adolescência",
    "historico_familiar": "Mãe com depressão",
    "medicacoes": "Sertralina 50mg",
    "observacoes": "Paciente cooperativo",
    "created_at": "2026-04-01T10:00:00Z",
}


class TestCreateAnamnese:
    """POST /api/anamnese"""

    def test_create_anamnese_duplicate_returns_409(self, client):
        """Creating anamnese for existing pair returns 409."""
        client._mock_supabase.set_table_data("anamneses", [SAMPLE_ANAMNESE])
        resp = client.post("/api/anamnese", json={
            "patient_id": "patient-001",
            "queixa_principal": "Ansiedade generalizada",
        })
        assert resp.status_code == 409

    def test_create_anamnese_patient_forbidden(self, patient_client):
        """Patient cannot create anamneses."""
        resp = patient_client.post("/api/anamnese", json={
            "patient_id": "patient-001",
            "queixa_principal": "Ansiedade",
        })
        assert resp.status_code == 403

    def test_create_anamnese_clinic_admin_forbidden(self, clinic_admin_client):
        """Clinic admin cannot create anamneses (therapist only)."""
        resp = clinic_admin_client.post("/api/anamnese", json={
            "patient_id": "patient-001",
            "queixa_principal": "Ansiedade",
        })
        assert resp.status_code == 403

    def test_create_anamnese_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/anamnese", json={
            "patient_id": "patient-001",
            "queixa_principal": "Ansiedade",
        })
        assert resp.status_code == 401


class TestListAnamneses:
    """GET /api/anamnese"""

    def test_list_anamneses(self, client):
        """Therapist lists their anamneses."""
        client._mock_supabase.set_table_data("anamneses", [SAMPLE_ANAMNESE])
        resp = client.get("/api/anamnese")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_anamneses_patient_forbidden(self, patient_client):
        """Patient cannot list anamneses."""
        resp = patient_client.get("/api/anamnese")
        assert resp.status_code == 403


class TestGetAnamneseForPatient:
    """GET /api/anamnese/paciente/{patient_id}"""

    def test_get_anamnese_for_patient(self, client):
        """Therapist gets anamnese for a patient."""
        client._mock_supabase.set_table_data("anamneses", [SAMPLE_ANAMNESE])
        resp = client.get("/api/anamnese/paciente/patient-001")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_get_anamnese_patient_role_forbidden(self, patient_client):
        """Patient cannot view anamneses."""
        resp = patient_client.get("/api/anamnese/paciente/patient-001")
        assert resp.status_code == 403

    def test_get_anamnese_admin_denied(self, admin_client):
        """Platform admin cannot view anamneses — clinical content is
        therapist-only per Q2 of `compliance-audit-reconciliation` 2026-04-22.
        """
        admin_client._mock_supabase.set_table_data("anamneses", [SAMPLE_ANAMNESE])
        resp = admin_client.get("/api/anamnese/paciente/patient-001")
        assert resp.status_code == 403


class TestUpdateAnamnese:
    """PATCH /api/anamnese/{anamnese_id}"""

    def test_update_anamnese(self, client):
        """Therapist updates their own anamnese."""
        client._mock_supabase.set_table_data("anamneses", [SAMPLE_ANAMNESE])
        resp = client.patch("/api/anamnese/anamnese-001", json={
            "queixa_principal": "Depressão e ansiedade",
        })
        assert resp.status_code == 200

    def test_update_anamnese_not_found(self, client):
        """Non-existent anamnese returns 404."""
        client._mock_supabase.set_table_data("anamneses", [])
        resp = client.patch("/api/anamnese/nonexistent", json={
            "queixa_principal": "Depressão",
        })
        assert resp.status_code == 404

    def test_update_anamnese_not_owner(self, client):
        """Therapist cannot update another therapist's anamnese."""
        other_anamnese = {**SAMPLE_ANAMNESE, "therapist_id": "other-therapist-999"}
        client._mock_supabase.set_table_data("anamneses", [other_anamnese])
        resp = client.patch("/api/anamnese/anamnese-001", json={
            "queixa_principal": "Depressão",
        })
        assert resp.status_code == 403

    def test_update_anamnese_patient_forbidden(self, patient_client):
        """Patient cannot update anamneses."""
        resp = patient_client.patch("/api/anamnese/anamnese-001", json={
            "queixa_principal": "Depressão",
        })
        assert resp.status_code == 403
