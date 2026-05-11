"""
Tests for the Mood Router.

Covers: create mood entry (patient only), list with date filters,
analytics endpoint, and auth/permission checks.
"""
import pytest

SAMPLE_MOOD_ENTRY = {
    "id": "mood-001",
    "patient_id": "test-user-123",
    "rating": 7,
    "emocoes": ["calma", "esperança"],
    "nota": "Dia bom no geral",
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_ANALYTICS = {
    "avg_rating": 6.5,
    "emotion_frequency": {"calma": 5, "ansiedade": 3},
    "trend": "improving",
    "total_entries": 10,
}


class TestCreateMoodEntry:
    """POST /api/mood"""

    def test_create_mood_entry(self, patient_client):
        """Patient creates a mood entry."""
        patient_client._mock_supabase.set_table_data("mood_entries", [SAMPLE_MOOD_ENTRY])
        resp = patient_client.post("/api/mood", json={
            "rating": 7,
            "emocoes": ["calma", "esperança"],
            "nota": "Dia bom",
        })
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_create_mood_therapist_forbidden(self, client):
        """Therapist cannot create mood entries."""
        resp = client.post("/api/mood", json={
            "rating": 7,
        })
        assert resp.status_code == 403

    def test_create_mood_admin_forbidden(self, admin_client):
        """Admin cannot create mood entries."""
        resp = admin_client.post("/api/mood", json={
            "rating": 7,
        })
        assert resp.status_code == 403

    def test_create_mood_401(self, patient_client):
        """No auth returns 401."""
        resp = patient_client._tc.post("/api/mood", json={
            "rating": 7,
        })
        assert resp.status_code == 401


class TestListMoodEntries:
    """GET /api/mood"""

    def test_list_entries(self, patient_client):
        """Patient lists their mood entries."""
        patient_client._mock_supabase.set_table_data("mood_entries", [SAMPLE_MOOD_ENTRY])
        resp = patient_client.get("/api/mood")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_list_entries_with_date_range(self, patient_client):
        """Patient lists entries with date filters."""
        patient_client._mock_supabase.set_table_data("mood_entries", [SAMPLE_MOOD_ENTRY])
        resp = patient_client.get(
            "/api/mood",
            params={"data_inicio": "2026-04-01", "data_fim": "2026-04-30"},
        )
        assert resp.status_code == 200

    def test_list_entries_therapist_forbidden(self, client):
        """Therapist cannot list patient mood entries."""
        resp = client.get("/api/mood")
        assert resp.status_code == 403


class TestMoodAnalytics:
    """GET /api/mood/analytics"""

    def test_analytics(self, patient_client):
        """Patient gets mood analytics."""
        patient_client._mock_supabase.set_table_data("mood_entries", [
            {"rating": 7, "emocoes": ["calma"], "created_at": "2026-04-01T10:00:00Z"},
            {"rating": 5, "emocoes": ["ansiedade"], "created_at": "2026-03-20T10:00:00Z"},
        ])
        resp = patient_client.get("/api/mood/analytics")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_analytics_with_date_range(self, patient_client):
        """Patient gets analytics for a specific period."""
        patient_client._mock_supabase.set_table_data("mood_entries", [])
        resp = patient_client.get(
            "/api/mood/analytics",
            params={"data_inicio": "2026-03-01", "data_fim": "2026-04-01"},
        )
        assert resp.status_code == 200

    def test_analytics_therapist_forbidden(self, client):
        """Therapist cannot access patient mood analytics."""
        resp = client.get("/api/mood/analytics")
        assert resp.status_code == 403

    def test_analytics_admin_forbidden(self, admin_client):
        """Admin cannot access patient mood analytics."""
        resp = admin_client.get("/api/mood/analytics")
        assert resp.status_code == 403
