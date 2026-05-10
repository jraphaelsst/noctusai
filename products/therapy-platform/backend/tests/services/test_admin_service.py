"""
Service-level tests for admin Phase 2 additions.

Covers ``list_appointments_for_admin`` (DTO shape), ``admin_dashboard_metrics``
(aggregation math), and ``suspend_entity`` (404 + invalid-type branches).
"""
import pytest

from tests.conftest import MockSupabaseClient
from app.services import admin_service


SAMPLE_APPOINTMENT_ROW = {
    "id": "appt-001",
    "patient_id": "patient-001",
    "therapist_id": "therapist-001",
    "clinic_id": "clinic-001",
    "scheduled_start": "2026-05-10T15:00:00Z",
    "scheduled_end": "2026-05-10T16:00:00Z",
    "status": "waiting",
    "patient_origin": "platform_assigned",
    "session_price_applied": 150.0,
    "created_at": "2026-05-01T10:00:00Z",
}


def _client():
    return MockSupabaseClient(validate_schema=False, schema="therapy")


@pytest.mark.asyncio
class TestListAppointmentsForAdmin:
    async def test_returns_dto_shape(self):
        db = _client()
        db.set_table_data("appointments", [SAMPLE_APPOINTMENT_ROW])
        db.set_table_data("clinics", [
            {"id": "clinic-001", "name": "Clínica Alpha"},
        ])
        data, total = await admin_service.list_appointments_for_admin(
            db, page=1, page_size=20,
        )
        assert total == 1
        assert len(data) == 1
        row = data[0]
        assert row["id"] == "appt-001"
        assert row["clinic_name"] == "Clínica Alpha"
        # Identity resolver returns "" for unknown ids in the mock; the
        # key must still be present so the frontend doesn't crash.
        assert "patient_name" in row
        assert "therapist_name" in row
        assert row["status"] == "waiting"
        assert row["scheduled_start"] == "2026-05-10T15:00:00Z"

    async def test_clinic_name_missing_when_clinic_id_null(self):
        db = _client()
        row = {**SAMPLE_APPOINTMENT_ROW, "clinic_id": None}
        db.set_table_data("appointments", [row])
        db.set_table_data("clinics", [])
        data, total = await admin_service.list_appointments_for_admin(
            db, page=1, page_size=20,
        )
        assert total == 1
        assert data[0]["clinic_name"] is None

    async def test_empty_result(self):
        db = _client()
        db.set_table_data("appointments", [])
        db.set_table_data("clinics", [])
        data, total = await admin_service.list_appointments_for_admin(
            db, page=1, page_size=20,
        )
        assert data == []
        assert total == 0


@pytest.mark.asyncio
class TestAdminDashboardMetrics:
    async def test_metrics_shape(self):
        db = _client()
        db.set_table_data("therapist_profiles", [
            {"user_id": "t1", "is_approved": False, "is_active": True},
        ])
        db.set_table_data("clinics", [
            {"id": "c1", "is_approved": False, "is_active": True},
            {"id": "c2", "is_approved": False, "is_active": True},
        ])
        db.set_table_data("appointments", [])
        db.set_table_data("transactions", [
            {"gross_amount": "200.00", "platform_fee_amount": "20.00", "status": "captured"},
        ])
        metrics = await admin_service.admin_dashboard_metrics(db)
        # MockSelectBuilder doesn't apply read-side filters — counts reflect
        # ALL rows in the table. The service code still issues the correct
        # PostgREST predicates against a real DB.
        assert "pending_therapists" in metrics
        assert "pending_clinics" in metrics
        assert "sessions_today" in metrics
        assert "total_revenue" in metrics
        assert "platform_fees" in metrics
        assert metrics["total_revenue"] == 200.0
        assert metrics["platform_fees"] == 20.0


@pytest.mark.asyncio
class TestSuspendEntity:
    async def test_suspend_therapist_sets_is_active_false(self):
        db = _client()
        db.set_table_data("therapist_profiles", [
            {"user_id": "t1", "is_active": True, "is_approved": True},
        ])
        result = await admin_service.suspend_entity(
            entity_type="therapist",
            entity_id="t1",
            admin_id="admin-1",
            db=db,
        )
        assert result["is_active"] is False

    async def test_suspend_clinic_sets_is_active_false(self):
        db = _client()
        db.set_table_data("clinics", [
            {"id": "c1", "is_active": True, "is_approved": True},
        ])
        result = await admin_service.suspend_entity(
            entity_type="clinic",
            entity_id="c1",
            admin_id="admin-1",
            db=db,
        )
        assert result["is_active"] is False

    async def test_suspend_invalid_type_raises(self):
        db = _client()
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await admin_service.suspend_entity(
                entity_type="widget",
                entity_id="x",
                admin_id="admin-1",
                db=db,
            )
        assert exc.value.status_code == 400

    async def test_suspend_nonexistent_raises_404(self):
        db = _client()
        db.set_table_data("therapist_profiles", [])
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            await admin_service.suspend_entity(
                entity_type="therapist",
                entity_id="missing",
                admin_id="admin-1",
                db=db,
            )
        assert exc.value.status_code == 404
