"""
Tests for the Reviews Router — therapist reviews, clinic reviews, responses, flags.
"""
import pytest
from unittest.mock import patch, AsyncMock


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_REVIEW = {
    "id": "review-001",
    "patient_id": "patient-001",
    "therapist_id": "test-user-123",
    "star_rating": 5,
    "review_text": "Excelente profissional",
    "tags": ["empatico", "profissional"],
    "is_flagged": False,
    "is_hidden": False,
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_CLINIC_REVIEW = {
    "id": "clinic-review-001",
    "patient_id": "patient-001",
    "clinic_id": "clinic-001",
    "star_rating": 4,
    "review_text": "Boa clínica",
    "tags": ["organizada"],
    "is_flagged": False,
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_SESSION = {
    "id": "session-001",
    "patient_id": "test-user-123",
    "therapist_id": "therapist-target",
    "status": "completed",
}

SAMPLE_THERAPIST_IN_CLINIC = {
    "user_id": "therapist-in-clinic",
    "clinic_id": "clinic-001",
}


# ---------------------------------------------------------------------------
# Create Therapist Review
# ---------------------------------------------------------------------------

class TestCreateReview:
    def test_create_review_success(self, patient_client):
        """Pattern 3: seed a completed session and an empty existing-review
        list; real `create_review` validates eligibility, finds no duplicate,
        inserts via `MockSupabaseClient` (auto-id) and returns the row."""
        patient_client._mock_supabase.set_table_data("appointments", [
            {"id": "s-1", "patient_id": "test-user-123",
             "therapist_id": "therapist-target", "status": "completed"},
        ])
        patient_client._mock_supabase.set_table_data("reviews", [])
        resp = patient_client.post("/api/reviews", json={
            "therapist_id": "therapist-target",
            "star_rating": 5,
            "review_text": "Excelente",
            "tags": ["empatico"],
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["star_rating"] == 5
        assert data["therapist_id"] == "therapist-target"

    def test_create_review_duplicate(self, patient_client):
        """Mock returns existing review data, triggering 409 conflict."""
        patient_client._mock_supabase.set_table_data("appointments", [
            {"id": "s-1", "patient_id": "test-user-123", "therapist_id": "therapist-target", "status": "completed"},
        ])
        patient_client._mock_supabase.set_table_data("reviews", [
            {**SAMPLE_REVIEW, "patient_id": "test-user-123", "therapist_id": "therapist-target"},
        ])
        resp = patient_client.post("/api/reviews", json={
            "therapist_id": "therapist-target",
            "star_rating": 5,
        })
        assert resp.status_code == 409

    def test_create_review_missing_star_rating(self, patient_client):
        resp = patient_client.post("/api/reviews", json={
            "therapist_id": "therapist-target",
            "review_text": "Sem nota",
        })
        assert resp.status_code == 422

    def test_create_review_invalid_star_rating(self, patient_client):
        resp = patient_client.post("/api/reviews", json={
            "therapist_id": "therapist-target",
            "star_rating": 6,
        })
        assert resp.status_code == 422

    def test_create_review_star_rating_zero(self, patient_client):
        resp = patient_client.post("/api/reviews", json={
            "therapist_id": "therapist-target",
            "star_rating": 0,
        })
        assert resp.status_code == 422

    def test_create_review_as_therapist_forbidden(self, client):
        resp = client.post("/api/reviews", json={
            "therapist_id": "other-therapist",
            "star_rating": 5,
        })
        assert resp.status_code == 403

    def test_create_review_no_session(self, patient_client):
        """Cannot review a therapist without a completed session."""
        patient_client._mock_supabase.set_table_data("appointments", [])
        resp = patient_client.post("/api/reviews", json={
            "therapist_id": "therapist-no-session",
            "star_rating": 4,
        })
        assert resp.status_code == 403

    def test_create_review_no_auth(self, client):
        resp = client._tc.post("/api/reviews", json={
            "therapist_id": "therapist-target",
            "star_rating": 5,
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Update Review
# ---------------------------------------------------------------------------

class TestUpdateReview:
    def test_update_review_success(self, patient_client):
        updated = {**SAMPLE_REVIEW, "star_rating": 4, "patient_id": "test-user-123"}
        patient_client._mock_supabase.set_table_data("reviews", [updated])
        resp = patient_client.patch("/api/reviews/review-001", json={
            "star_rating": 4,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["star_rating"] == 4

    def test_update_review_text(self, patient_client):
        updated = {**SAMPLE_REVIEW, "review_text": "Atualizado", "patient_id": "test-user-123"}
        patient_client._mock_supabase.set_table_data("reviews", [updated])
        resp = patient_client.patch("/api/reviews/review-001", json={
            "review_text": "Atualizado",
        })
        assert resp.status_code == 200

    def test_update_review_as_therapist_forbidden(self, client):
        resp = client.patch("/api/reviews/review-001", json={
            "star_rating": 1,
        })
        assert resp.status_code == 403

    def test_update_review_no_auth(self, client):
        resp = client._tc.patch("/api/reviews/review-001", json={
            "star_rating": 3,
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# List Therapist Reviews
# ---------------------------------------------------------------------------

class TestListTherapistReviews:
    def test_list_reviews_returns_data(self, client):
        client._mock_supabase.set_table_data("reviews", [
            SAMPLE_REVIEW,
            {**SAMPLE_REVIEW, "id": "review-002", "star_rating": 4},
        ])
        resp = client.get("/api/reviews/therapist/test-user-123")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert "pagination" in body

    def test_list_reviews_empty(self, client):
        client._mock_supabase.set_table_data("reviews", [])
        resp = client.get("/api/reviews/therapist/test-user-123")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_reviews_pagination(self, client):
        client._mock_supabase.set_table_data("reviews", [SAMPLE_REVIEW])
        resp = client.get("/api/reviews/therapist/test-user-123?page=1&page_size=5")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page_size"] == 5

    def test_list_reviews_no_auth(self, client):
        resp = client._tc.get("/api/reviews/therapist/test-user-123")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Create Clinic Review
# ---------------------------------------------------------------------------

class TestCreateClinicReview:
    def test_create_clinic_review_success(self, patient_client):
        """Pattern 3: seed (a) the clinic's therapists, (b) a completed
        session, (c) empty existing-clinic-reviews. Real `create_clinic_review`
        runs the eligibility chain and inserts."""
        patient_client._mock_supabase.set_table_data("therapist_profiles", [
            SAMPLE_THERAPIST_IN_CLINIC,
        ])
        patient_client._mock_supabase.set_table_data("appointments", [
            {"id": "s-1", "patient_id": "test-user-123",
             "therapist_id": "therapist-in-clinic", "status": "completed"},
        ])
        patient_client._mock_supabase.set_table_data("clinic_reviews", [])
        resp = patient_client.post("/api/reviews/clinic", json={
            "clinic_id": "clinic-001",
            "star_rating": 4,
            "review_text": "Boa clínica",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["star_rating"] == 4
        assert data["clinic_id"] == "clinic-001"

    def test_create_clinic_review_duplicate(self, patient_client):
        """Mock returns existing review data, triggering 409 conflict."""
        patient_client._mock_supabase.set_table_data("therapist_profiles", [
            SAMPLE_THERAPIST_IN_CLINIC,
        ])
        patient_client._mock_supabase.set_table_data("appointments", [
            {"id": "s-1", "patient_id": "test-user-123", "therapist_id": "therapist-in-clinic", "status": "completed"},
        ])
        patient_client._mock_supabase.set_table_data("clinic_reviews", [
            {**SAMPLE_CLINIC_REVIEW, "patient_id": "test-user-123"},
        ])
        resp = patient_client.post("/api/reviews/clinic", json={
            "clinic_id": "clinic-001",
            "star_rating": 4,
        })
        assert resp.status_code == 409

    def test_create_clinic_review_as_therapist_forbidden(self, client):
        resp = client.post("/api/reviews/clinic", json={
            "clinic_id": "clinic-001",
            "star_rating": 4,
        })
        assert resp.status_code == 403

    def test_create_clinic_review_missing_star_rating(self, patient_client):
        resp = patient_client.post("/api/reviews/clinic", json={
            "clinic_id": "clinic-001",
        })
        assert resp.status_code == 422

    def test_create_clinic_review_no_auth(self, client):
        resp = client._tc.post("/api/reviews/clinic", json={
            "clinic_id": "clinic-001",
            "star_rating": 4,
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# List Clinic Reviews
# ---------------------------------------------------------------------------

class TestListClinicReviews:
    def test_list_clinic_reviews(self, client):
        client._mock_supabase.set_table_data("clinic_reviews", [SAMPLE_CLINIC_REVIEW])
        resp = client.get("/api/reviews/clinic/clinic-001")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert "pagination" in body

    def test_list_clinic_reviews_empty(self, client):
        client._mock_supabase.set_table_data("clinic_reviews", [])
        resp = client.get("/api/reviews/clinic/clinic-001")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_clinic_reviews_no_auth(self, client):
        resp = client._tc.get("/api/reviews/clinic/clinic-001")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Respond to Review
# ---------------------------------------------------------------------------

class TestRespondToReview:
    def test_respond_success(self, client):
        """Therapist responds to a review on their profile."""
        client._mock_supabase.set_table_data("reviews", [
            {**SAMPLE_REVIEW, "therapist_response": "Obrigado!"},
        ])
        resp = client.post("/api/reviews/review-001/respond", json={
            "response_text": "Obrigado pela avaliação!",
        })
        assert resp.status_code == 200

    def test_respond_as_patient_forbidden(self, patient_client):
        resp = patient_client.post("/api/reviews/review-001/respond", json={
            "response_text": "Tentativa",
        })
        assert resp.status_code == 403

    def test_respond_missing_text(self, client):
        resp = client.post("/api/reviews/review-001/respond", json={})
        assert resp.status_code == 422

    def test_respond_no_auth(self, client):
        resp = client._tc.post("/api/reviews/review-001/respond", json={
            "response_text": "No auth",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Flag Review
# ---------------------------------------------------------------------------

class TestFlagReview:
    def test_flag_review_as_therapist(self, client):
        client._mock_supabase.set_table_data("reviews", [
            {**SAMPLE_REVIEW, "is_flagged": True, "flag_reason": "Conteúdo ofensivo"},
        ])
        resp = client.post("/api/reviews/review-001/flag", json={
            "reason": "Conteúdo ofensivo e inapropriado",
        })
        assert resp.status_code == 200

    def test_flag_review_as_clinic_admin(self, clinic_admin_client):
        clinic_admin_client._mock_supabase.set_table_data("reviews", [
            {**SAMPLE_REVIEW, "is_flagged": True},
        ])
        resp = clinic_admin_client.post("/api/reviews/review-001/flag", json={
            "reason": "Avaliação falsa e tendenciosa",
        })
        assert resp.status_code == 200

    def test_flag_review_as_admin(self, admin_client):
        admin_client._mock_supabase.set_table_data("reviews", [
            {**SAMPLE_REVIEW, "is_flagged": True},
        ])
        resp = admin_client.post("/api/reviews/review-001/flag", json={
            "reason": "Violação de termos de uso",
        })
        assert resp.status_code == 200

    def test_flag_review_as_patient_forbidden(self, patient_client):
        resp = patient_client.post("/api/reviews/review-001/flag", json={
            "reason": "Paciente não pode flaggar",
        })
        assert resp.status_code == 403

    def test_flag_review_short_reason(self, client):
        resp = client.post("/api/reviews/review-001/flag", json={
            "reason": "abc",
        })
        assert resp.status_code == 422

    def test_flag_review_missing_reason(self, client):
        resp = client.post("/api/reviews/review-001/flag", json={})
        assert resp.status_code == 422

    def test_flag_review_no_auth(self, client):
        resp = client._tc.post("/api/reviews/review-001/flag", json={
            "reason": "No auth attempt",
        })
        assert resp.status_code == 401
