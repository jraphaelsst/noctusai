"""
Tests for the Dashboard BI Router.

Covers: resumo, sessoes, receita, cancelamentos (therapist only),
and auth/permission checks.
"""
import pytest

SAMPLE_APPOINTMENTS = [
    {
        "id": "appt-001",
        "therapist_id": "test-user-123",
        "patient_id": "patient-001",
        "status": "completed",
        "session_price_applied": 250.00,
        "scheduled_start": "2026-03-15T09:00:00Z",
    },
    {
        "id": "appt-002",
        "therapist_id": "test-user-123",
        "patient_id": "patient-002",
        "status": "completed",
        "session_price_applied": 250.00,
        "scheduled_start": "2026-03-22T09:00:00Z",
    },
]


class TestDashboardSummary:
    """GET /api/bi/resumo"""

    def test_dashboard_summary(self, client):
        """Therapist gets dashboard summary."""
        client._mock_supabase.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        client._mock_supabase.set_table_data("reviews", [
            {"rating": 5, "therapist_id": "test-user-123"},
        ])
        resp = client.get("/api/bi/resumo")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_dashboard_summary_patient_forbidden(self, patient_client):
        """Patient cannot access BI dashboard."""
        resp = patient_client.get("/api/bi/resumo")
        assert resp.status_code == 403

    def test_dashboard_summary_admin_forbidden(self, admin_client):
        """Admin cannot access therapist BI dashboard."""
        resp = admin_client.get("/api/bi/resumo")
        assert resp.status_code == 403

    def test_dashboard_summary_401(self, client):
        """No auth returns 401."""
        resp = client._tc.get("/api/bi/resumo")
        assert resp.status_code == 401


class TestSessionMetrics:
    """GET /api/bi/sessoes"""

    def test_session_metrics(self, client):
        """Therapist gets session metrics."""
        client._mock_supabase.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        resp = client.get("/api/bi/sessoes")
        assert resp.status_code == 200

    def test_session_metrics_with_period(self, client):
        """Therapist gets session metrics for a specific period."""
        client._mock_supabase.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        resp = client.get("/api/bi/sessoes", params={
            "periodo": "semanal",
            "data_inicio": "2026-03-01",
            "data_fim": "2026-04-01",
        })
        assert resp.status_code == 200

    def test_session_metrics_patient_forbidden(self, patient_client):
        """Patient cannot access session metrics."""
        resp = patient_client.get("/api/bi/sessoes")
        assert resp.status_code == 403


class TestRevenueMetrics:
    """GET /api/bi/receita"""

    def test_revenue_metrics(self, client):
        """Therapist gets revenue metrics."""
        client._mock_supabase.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        resp = client.get("/api/bi/receita")
        assert resp.status_code == 200

    def test_revenue_metrics_with_period(self, client):
        """Therapist gets revenue for a specific period."""
        client._mock_supabase.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        resp = client.get("/api/bi/receita", params={
            "periodo": "trimestral",
            "data_inicio": "2026-01-01",
            "data_fim": "2026-04-01",
        })
        assert resp.status_code == 200

    def test_revenue_metrics_patient_forbidden(self, patient_client):
        """Patient cannot access revenue metrics."""
        resp = patient_client.get("/api/bi/receita")
        assert resp.status_code == 403


class TestCancellationRates:
    """GET /api/bi/cancelamentos"""

    def test_cancellation_rates(self, client):
        """Therapist gets cancellation rates."""
        client._mock_supabase.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        resp = client.get("/api/bi/cancelamentos")
        assert resp.status_code == 200

    def test_cancellation_rates_with_period(self, client):
        """Therapist gets cancellation rates for a specific period."""
        client._mock_supabase.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        resp = client.get("/api/bi/cancelamentos", params={
            "periodo": "mensal",
        })
        assert resp.status_code == 200

    def test_cancellation_rates_patient_forbidden(self, patient_client):
        """Patient cannot access cancellation rates."""
        resp = patient_client.get("/api/bi/cancelamentos")
        assert resp.status_code == 403

    def test_cancellation_rates_clinic_admin_forbidden(self, clinic_admin_client):
        """Clinic admin cannot access individual therapist cancellation rates."""
        resp = clinic_admin_client.get("/api/bi/cancelamentos")
        assert resp.status_code == 403
