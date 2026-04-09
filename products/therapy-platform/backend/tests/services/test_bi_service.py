"""
Tests for the BI Service.

Covers: dashboard summary, sessions by period, revenue by period,
cancellation rates.
"""
import pytest

from tests.conftest import MockSupabaseClient
from app.services import bi_service


SAMPLE_APPOINTMENTS = [
    {
        "id": "appt-001",
        "therapist_id": "therapist-001",
        "patient_id": "patient-001",
        "status": "completed",
        "session_price_applied": 250.00,
        "scheduled_start": "2026-03-15T09:00:00Z",
    },
    {
        "id": "appt-002",
        "therapist_id": "therapist-001",
        "patient_id": "patient-002",
        "status": "completed",
        "session_price_applied": 300.00,
        "scheduled_start": "2026-03-22T09:00:00Z",
    },
    {
        "id": "appt-003",
        "therapist_id": "therapist-001",
        "patient_id": "patient-001",
        "status": "cancelled",
        "session_price_applied": 250.00,
        "scheduled_start": "2026-03-25T09:00:00Z",
    },
    {
        "id": "appt-004",
        "therapist_id": "therapist-001",
        "patient_id": "patient-003",
        "status": "no_show",
        "session_price_applied": 250.00,
        "scheduled_start": "2026-03-28T09:00:00Z",
    },
]

SAMPLE_REVIEWS = [
    {"rating": 5, "therapist_id": "therapist-001"},
    {"rating": 4, "therapist_id": "therapist-001"},
    {"rating": 5, "therapist_id": "therapist-001"},
]


class TestDashboardResumo:
    @pytest.mark.asyncio
    async def test_dashboard_resumo(self):
        db = MockSupabaseClient()
        db.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        db.set_table_data("reviews", SAMPLE_REVIEWS)
        result = await bi_service.get_dashboard_resumo(
            therapist_id="therapist-001",
            db=db,
        )
        assert "total_sessions" in result
        assert "total_revenue" in result
        assert "active_patients" in result
        assert "avg_rating" in result

    @pytest.mark.asyncio
    async def test_dashboard_resumo_with_revenue(self):
        db = MockSupabaseClient()
        db.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        db.set_table_data("reviews", [])
        result = await bi_service.get_dashboard_resumo(
            therapist_id="therapist-001",
            db=db,
        )
        assert result["total_revenue"] >= 0

    @pytest.mark.asyncio
    async def test_dashboard_resumo_no_data(self):
        db = MockSupabaseClient()
        db.set_table_data("appointments", [])
        db.set_table_data("reviews", [])
        result = await bi_service.get_dashboard_resumo(
            therapist_id="therapist-001",
            db=db,
        )
        assert result["total_sessions"] == 0
        assert result["total_revenue"] == 0.0
        assert result["active_patients"] == 0
        assert result["avg_rating"] is None

    @pytest.mark.asyncio
    async def test_dashboard_avg_rating(self):
        db = MockSupabaseClient()
        db.set_table_data("appointments", [])
        db.set_table_data("reviews", SAMPLE_REVIEWS)
        result = await bi_service.get_dashboard_resumo(
            therapist_id="therapist-001",
            db=db,
        )
        # (5 + 4 + 5) / 3 = 4.67
        assert result["avg_rating"] == 4.67


class TestSessoesPorPeriodo:
    @pytest.mark.asyncio
    async def test_sessoes_por_periodo(self):
        db = MockSupabaseClient()
        db.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        result = await bi_service.get_sessoes_por_periodo(
            therapist_id="therapist-001",
            db=db,
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_sessoes_por_periodo_empty(self):
        db = MockSupabaseClient()
        db.set_table_data("appointments", [])
        result = await bi_service.get_sessoes_por_periodo(
            therapist_id="therapist-001",
            db=db,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_sessoes_por_periodo_with_dates(self):
        db = MockSupabaseClient()
        db.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        result = await bi_service.get_sessoes_por_periodo(
            therapist_id="therapist-001",
            db=db,
            inicio="2026-03-01",
            fim="2026-04-01",
        )
        assert isinstance(result, list)


class TestReceitaPorPeriodo:
    @pytest.mark.asyncio
    async def test_receita_por_periodo(self):
        db = MockSupabaseClient()
        db.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        result = await bi_service.get_receita_por_periodo(
            therapist_id="therapist-001",
            db=db,
        )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_receita_por_periodo_empty(self):
        db = MockSupabaseClient()
        db.set_table_data("appointments", [])
        result = await bi_service.get_receita_por_periodo(
            therapist_id="therapist-001",
            db=db,
        )
        assert result == []

    @pytest.mark.asyncio
    async def test_receita_por_periodo_with_dates(self):
        db = MockSupabaseClient()
        db.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        result = await bi_service.get_receita_por_periodo(
            therapist_id="therapist-001",
            db=db,
            inicio="2026-01-01",
            fim="2026-04-01",
        )
        assert isinstance(result, list)


class TestTaxaCancelamento:
    @pytest.mark.asyncio
    async def test_cancellation_rates(self):
        db = MockSupabaseClient()
        db.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        result = await bi_service.get_taxa_cancelamento(
            therapist_id="therapist-001",
            db=db,
        )
        assert "total_appointments" in result
        assert "cancelled" in result
        assert "late_cancelled" in result
        assert "no_show" in result
        assert "completed" in result
        assert "cancellation_rate" in result
        assert "no_show_rate" in result

    @pytest.mark.asyncio
    async def test_cancellation_rates_no_data(self):
        db = MockSupabaseClient()
        db.set_table_data("appointments", [])
        result = await bi_service.get_taxa_cancelamento(
            therapist_id="therapist-001",
            db=db,
        )
        assert result["total_appointments"] == 0
        assert result["cancellation_rate"] == 0.0
        assert result["no_show_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_cancellation_rate_calculation(self):
        """Verify cancellation_rate = (cancelled + late_cancelled) / total."""
        db = MockSupabaseClient()
        db.set_table_data("appointments", SAMPLE_APPOINTMENTS)
        result = await bi_service.get_taxa_cancelamento(
            therapist_id="therapist-001",
            db=db,
        )
        total = result["total_appointments"]
        if total > 0:
            expected_rate = (result["cancelled"] + result["late_cancelled"]) / total
            assert abs(result["cancellation_rate"] - round(expected_rate, 4)) < 0.001
