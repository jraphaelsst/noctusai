"""
Tests for the Therapists Router — directory listing, profile detail, profile update.
"""
import pytest


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_THERAPIST = {
    "user_id": "test-user-123",
    "clinic_id": None,
    "crp": "06/123456",
    "bio": "Psicóloga clínica",
    "specialties": ["ansiedade", "depressão"],
    "approaches": ["TCC", "psicanálise"],
    "photo_url": None,
    "default_session_price": 200.00,
    "session_duration_minutes": 50,
    "is_approved": True,
    "created_at": "2026-04-01T10:00:00Z",
    "updated_at": "2026-04-01T10:00:00Z",
    "is_active": True,
}

SAMPLE_THERAPIST_2 = {
    "user_id": "therapist-002",
    "clinic_id": "clinic-001",
    "crp": "06/654321",
    "bio": "Terapeuta cognitivo-comportamental",
    "specialties": ["fobias", "TOC"],
    "approaches": ["TCC"],
    "photo_url": None,
    "default_session_price": 180.00,
    "session_duration_minutes": 50,
    "is_approved": True,
    "created_at": "2026-04-01T11:00:00Z",
    "updated_at": "2026-04-01T11:00:00Z",
    "is_active": True,
}


# ---------------------------------------------------------------------------
# List Therapists
# ---------------------------------------------------------------------------

class TestListTherapists:
    def test_list_therapists_returns_data(self, client):
        client._mock_supabase.set_table_data(
            "therapist_profiles", [SAMPLE_THERAPIST, SAMPLE_THERAPIST_2]
        )
        resp = client.get("/api/therapists")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert "pagination" in body
        assert body["pagination"]["total"] == 2

    def test_list_therapists_empty(self, client):
        client._mock_supabase.set_table_data("therapist_profiles", [])
        resp = client.get("/api/therapists")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []
        assert body["pagination"]["total"] == 0

    def test_list_therapists_with_busca(self, client):
        client._mock_supabase.set_table_data("therapist_profiles", [SAMPLE_THERAPIST])
        resp = client.get("/api/therapists?busca=clínica")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 0

    def test_list_therapists_with_specialty_filter(self, client):
        client._mock_supabase.set_table_data("therapist_profiles", [SAMPLE_THERAPIST])
        resp = client.get("/api/therapists?specialty=ansiedade")
        assert resp.status_code == 200

    def test_list_therapists_with_price_filter(self, client):
        client._mock_supabase.set_table_data("therapist_profiles", [SAMPLE_THERAPIST])
        resp = client.get("/api/therapists?min_price=100&max_price=300")
        assert resp.status_code == 200

    def test_list_therapists_pagination(self, client):
        client._mock_supabase.set_table_data("therapist_profiles", [SAMPLE_THERAPIST])
        resp = client.get("/api/therapists?page=1&page_size=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["page_size"] == 10

    def test_list_therapists_sort_lowest_price(self, client):
        client._mock_supabase.set_table_data(
            "therapist_profiles", [SAMPLE_THERAPIST, SAMPLE_THERAPIST_2]
        )
        resp = client.get("/api/therapists?sort=lowest_price")
        assert resp.status_code == 200

    def test_list_therapists_no_auth(self, client):
        resp = client._tc.get("/api/therapists")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Get Therapist
# ---------------------------------------------------------------------------

class TestGetTherapist:
    def test_get_therapist_found(self, client):
        client._mock_supabase.set_table_data(
            "therapist_profiles", [SAMPLE_THERAPIST]
        )
        client._mock_supabase.set_table_data("therapist_reviews", [])
        client._mock_supabase.set_table_data("therapist_settings", [
            {"therapist_id": "test-user-123", "session_duration_minutes": 50},
        ])
        resp = client.get("/api/therapists/test-user-123")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["user_id"] == "test-user-123"
        assert data["review_count"] == 0

    def test_get_therapist_with_reviews(self, client):
        client._mock_supabase.set_table_data(
            "therapist_profiles", [SAMPLE_THERAPIST]
        )
        client._mock_supabase.set_table_data("therapist_reviews", [
            {"star_rating": 5, "therapist_id": "test-user-123"},
            {"star_rating": 4, "therapist_id": "test-user-123"},
        ])
        client._mock_supabase.set_table_data("therapist_settings", [
            {"therapist_id": "test-user-123", "session_duration_minutes": 50},
        ])
        resp = client.get("/api/therapists/test-user-123")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["avg_rating"] == 4.5
        assert data["review_count"] == 2

    def test_get_therapist_not_found(self, client):
        client._mock_supabase.set_table_data("therapist_profiles", [])
        resp = client.get("/api/therapists/nonexistent-id")
        assert resp.status_code == 404

    def test_get_therapist_no_auth(self, client):
        resp = client._tc.get("/api/therapists/test-user-123")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Update Therapist
# ---------------------------------------------------------------------------

class TestUpdateTherapist:
    def test_update_own_profile(self, client):
        updated = {**SAMPLE_THERAPIST, "bio": "Atualizado"}
        client._mock_supabase.set_table_data("therapist_profiles", [updated])
        resp = client.patch(
            "/api/therapists/test-user-123",
            json={"bio": "Atualizado"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["bio"] == "Atualizado"

    def test_update_other_therapist_forbidden(self, client):
        """A therapist cannot update someone else's profile."""
        resp = client.patch(
            "/api/therapists/other-therapist-456",
            json={"bio": "Hack"},
        )
        assert resp.status_code == 403

    def test_update_therapist_as_patient_forbidden(self, patient_client):
        """A patient role cannot update a therapist profile."""
        resp = patient_client.patch(
            "/api/therapists/test-user-123",
            json={"bio": "Hack"},
        )
        assert resp.status_code == 403

    def test_update_therapist_no_auth(self, client):
        resp = client._tc.patch(
            "/api/therapists/test-user-123",
            json={"bio": "No auth"},
        )
        assert resp.status_code == 401

    def test_update_therapist_specialties(self, client):
        updated = {**SAMPLE_THERAPIST, "specialties": ["TCC", "humanista"]}
        client._mock_supabase.set_table_data("therapist_profiles", [updated])
        resp = client.patch(
            "/api/therapists/test-user-123",
            json={"specialties": ["TCC", "humanista"]},
        )
        assert resp.status_code == 200
