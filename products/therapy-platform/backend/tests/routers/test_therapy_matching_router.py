"""
Tests for the Therapy Matching Router.

Covers: embed therapist, embed patient, search matching therapists,
get suggestions, and auth/permission checks.
"""
import pytest

SAMPLE_MATCH = {
    "therapist_id": "therapist-001",
    "score": 0.85,
    "breakdown": {
        "embedding_similarity": 0.9,
        "specialty_overlap": 0.8,
        "approach_compatibility": 0.7,
        "price_range": 1.0,
        "availability_overlap": 0.6,
    },
    "therapist_nome": "Dr. Maria",
    "therapist_specialties": ["ansiedade", "depressão"],
}


class TestEmbedTherapistProfile:
    """POST /api/matching/embed-terapeuta"""

    def test_embed_therapist_no_api_key(self, client):
        """Embedding without API key raises ValueError (unhandled in router)."""
        client._mock_supabase.set_table_data("therapist_profiles", [
            {"user_id": "test-user-123", "specialties": ["ansiedade"]},
        ])
        with pytest.raises(Exception):
            client.post("/api/matching/embed-terapeuta")

    def test_embed_therapist_patient_forbidden(self, patient_client):
        """Patient cannot embed therapist profile."""
        resp = patient_client.post("/api/matching/embed-terapeuta")
        assert resp.status_code == 403

    def test_embed_therapist_admin_no_api_key(self, admin_client):
        """Platform admin passes permission but key missing raises ValueError."""
        admin_client._mock_supabase.set_table_data("therapist_profiles", [
            {"user_id": "test-user-123", "specialties": ["ansiedade"]},
        ])
        with pytest.raises(Exception):
            admin_client.post("/api/matching/embed-terapeuta")


class TestEmbedPatientProfile:
    """POST /api/matching/embed-paciente"""

    def test_embed_patient_no_api_key(self, patient_client):
        """Patient embedding without API key raises ValueError."""
        patient_client._mock_supabase.set_table_data("patient_profiles", [
            {"user_id": "test-user-123", "preferred_specialties": ["ansiedade"]},
        ])
        with pytest.raises(Exception):
            patient_client.post("/api/matching/embed-paciente")

    def test_embed_patient_therapist_forbidden(self, client):
        """Therapist cannot embed patient profile."""
        resp = client.post("/api/matching/embed-paciente")
        assert resp.status_code == 403

    def test_embed_patient_admin_no_api_key(self, admin_client):
        """Platform admin passes permission but key missing raises ValueError."""
        admin_client._mock_supabase.set_table_data("patient_profiles", [
            {"user_id": "test-user-123", "preferred_specialties": ["ansiedade"]},
        ])
        with pytest.raises(Exception):
            admin_client.post("/api/matching/embed-paciente")


class TestFindMatchingTherapists:
    """GET /api/matching/buscar/{patient_id}"""

    def test_find_matches_as_patient(self, patient_client):
        """Patient finds matching therapists for themselves."""
        patient_client._mock_supabase.set_table_data("patient_profiles", [
            {"user_id": "test-user-123", "preferred_specialties": ["ansiedade"]},
        ])
        patient_client._mock_supabase.set_table_data("therapist_profiles", [])
        resp = patient_client.get("/api/matching/buscar/test-user-123")
        assert resp.status_code == 200

    def test_find_matches_other_patient_forbidden(self, patient_client):
        """Patient cannot search for another patient."""
        resp = patient_client.get("/api/matching/buscar/other-patient-999")
        assert resp.status_code == 403

    def test_find_matches_therapist_forbidden(self, client):
        """Therapist cannot use matching search."""
        resp = client.get("/api/matching/buscar/patient-001")
        assert resp.status_code == 403

    def test_find_matches_admin_allowed(self, admin_client):
        """Platform admin can search for any patient."""
        admin_client._mock_supabase.set_table_data("patient_profiles", [
            {"user_id": "patient-001", "preferred_specialties": ["ansiedade"]},
        ])
        admin_client._mock_supabase.set_table_data("therapist_profiles", [])
        resp = admin_client.get("/api/matching/buscar/patient-001")
        assert resp.status_code == 200


class TestGetSuggestions:
    """GET /api/matching/sugestoes"""

    def test_get_suggestions(self, patient_client):
        """Patient gets match suggestions."""
        patient_client._mock_supabase.set_table_data("patient_profiles", [
            {"user_id": "test-user-123", "preferred_specialties": ["ansiedade"]},
        ])
        patient_client._mock_supabase.set_table_data("therapist_profiles", [])
        resp = patient_client.get("/api/matching/sugestoes")
        assert resp.status_code == 200

    def test_get_suggestions_therapist_forbidden(self, client):
        """Therapist cannot get match suggestions."""
        resp = client.get("/api/matching/sugestoes")
        assert resp.status_code == 403

    def test_get_suggestions_401(self, patient_client):
        """No auth returns 401."""
        resp = patient_client._tc.get("/api/matching/sugestoes")
        assert resp.status_code == 401
