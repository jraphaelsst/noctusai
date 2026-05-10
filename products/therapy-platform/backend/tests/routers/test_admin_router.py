"""
Tests for the Admin Router — approvals, commissions, patient assignment, listing.
"""
import pytest


# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_PENDING_THERAPIST = {
    "user_id": "pending-therapist-001",
    "crp": "06/111111",
    "bio": "Aguardando aprovação",
    "is_approved": False,
    "is_active": True,
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_PENDING_CLINIC = {
    "id": "pending-clinic-001",
    "name": "Clínica Pendente",
    "cnpj": "11111111000111",
    "is_approved": False,
    "is_active": True,
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_APPROVED_THERAPIST = {
    **SAMPLE_PENDING_THERAPIST,
    "is_approved": True,
}

SAMPLE_COMMISSION_OVERRIDE = {
    "target_type": "clinic",
    "target_id": "clinic-001",
    "custom_commission_pct": 25.0,
    "set_by": "test-user-123",
}

SAMPLE_PATIENT = {
    "user_id": "patient-001",
    "current_therapist_id": None,
    "clinic_id": None,
    "is_active": True,
}


# ---------------------------------------------------------------------------
# List Pending Approvals
# ---------------------------------------------------------------------------

class TestListPending:
    def test_list_pending_as_admin(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "therapist_profiles", [SAMPLE_PENDING_THERAPIST]
        )
        admin_client._mock_supabase.set_table_data(
            "clinics", [SAMPLE_PENDING_CLINIC]
        )
        resp = admin_client.get("/api/admin/pending")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "therapists" in data
        assert "clinics" in data
        assert data["total"] == 2

    def test_list_pending_empty(self, admin_client):
        admin_client._mock_supabase.set_table_data("therapist_profiles", [])
        admin_client._mock_supabase.set_table_data("clinics", [])
        resp = admin_client.get("/api/admin/pending")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total"] == 0

    def test_list_pending_as_therapist_forbidden(self, client):
        resp = client.get("/api/admin/pending")
        assert resp.status_code == 403

    def test_list_pending_as_patient_forbidden(self, patient_client):
        resp = patient_client.get("/api/admin/pending")
        assert resp.status_code == 403

    def test_list_pending_as_clinic_admin_forbidden(self, clinic_admin_client):
        resp = clinic_admin_client.get("/api/admin/pending")
        assert resp.status_code == 403

    def test_list_pending_no_auth(self, client):
        resp = client._tc.get("/api/admin/pending")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Approve Entity
# ---------------------------------------------------------------------------

class TestApproveEntity:
    def test_approve_therapist(self, admin_client):
        admin_client._mock_supabase.set_table_data("therapist_profiles", [
            SAMPLE_APPROVED_THERAPIST,
        ])
        resp = admin_client.post("/api/admin/approve/therapist/pending-therapist-001")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_approved"] is True

    def test_approve_clinic(self, admin_client):
        admin_client._mock_supabase.set_table_data("clinics", [
            {**SAMPLE_PENDING_CLINIC, "is_approved": True},
        ])
        resp = admin_client.post("/api/admin/approve/clinic/pending-clinic-001")
        assert resp.status_code == 200

    def test_approve_invalid_entity_type(self, admin_client):
        admin_client._mock_supabase.set_table_data("therapist_profiles", [])
        resp = admin_client.post("/api/admin/approve/invalid/some-id")
        assert resp.status_code == 400

    def test_approve_nonexistent_therapist(self, admin_client):
        admin_client._mock_supabase.set_table_data("therapist_profiles", [])
        resp = admin_client.post("/api/admin/approve/therapist/nonexistent")
        assert resp.status_code == 404

    def test_approve_as_therapist_forbidden(self, client):
        resp = client.post("/api/admin/approve/therapist/pending-therapist-001")
        assert resp.status_code == 403

    def test_approve_no_auth(self, client):
        resp = client._tc.post("/api/admin/approve/therapist/pending-therapist-001")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Reject Entity
# ---------------------------------------------------------------------------

class TestRejectEntity:
    def test_reject_therapist_with_reason(self, admin_client):
        admin_client._mock_supabase.set_table_data("therapist_profiles", [
            {**SAMPLE_PENDING_THERAPIST, "rejection_reason": "CRP inválido"},
        ])
        resp = admin_client.post(
            "/api/admin/reject/therapist/pending-therapist-001",
            json={"action": "reject", "reason": "CRP inválido"},
        )
        assert resp.status_code == 200

    def test_reject_clinic_with_reason(self, admin_client):
        admin_client._mock_supabase.set_table_data("clinics", [
            {**SAMPLE_PENDING_CLINIC, "rejection_reason": "CNPJ inválido"},
        ])
        resp = admin_client.post(
            "/api/admin/reject/clinic/pending-clinic-001",
            json={"action": "reject", "reason": "CNPJ inválido"},
        )
        assert resp.status_code == 200

    def test_reject_without_reason(self, admin_client):
        resp = admin_client.post(
            "/api/admin/reject/therapist/pending-therapist-001",
            json={"action": "reject"},
        )
        assert resp.status_code == 422

    def test_reject_with_wrong_action(self, admin_client):
        resp = admin_client.post(
            "/api/admin/reject/therapist/pending-therapist-001",
            json={"action": "approve", "reason": "Trying wrong action"},
        )
        assert resp.status_code == 400

    def test_reject_as_therapist_forbidden(self, client):
        resp = client.post(
            "/api/admin/reject/therapist/pending-therapist-001",
            json={"action": "reject", "reason": "Attempt"},
        )
        assert resp.status_code == 403

    def test_reject_no_auth(self, client):
        resp = client._tc.post(
            "/api/admin/reject/therapist/pending-therapist-001",
            json={"action": "reject", "reason": "No auth"},
        )
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Set Commission Override
# ---------------------------------------------------------------------------

class TestSetCommission:
    def test_set_commission_success(self, admin_client):
        admin_client._mock_supabase.set_table_data("commission_overrides", [
            SAMPLE_COMMISSION_OVERRIDE,
        ])
        resp = admin_client.post("/api/admin/commissions", json={
            "target_type": "clinic",
            "target_id": "clinic-001",
            "custom_commission_pct": 25.0,
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["custom_commission_pct"] == 25.0

    def test_set_commission_for_therapist(self, admin_client):
        admin_client._mock_supabase.set_table_data("commission_overrides", [
            {**SAMPLE_COMMISSION_OVERRIDE, "target_type": "therapist", "target_id": "t-001"},
        ])
        resp = admin_client.post("/api/admin/commissions", json={
            "target_type": "therapist",
            "target_id": "t-001",
            "custom_commission_pct": 10.0,
        })
        assert resp.status_code == 200

    def test_set_commission_invalid_pct(self, admin_client):
        resp = admin_client.post("/api/admin/commissions", json={
            "target_type": "clinic",
            "target_id": "clinic-001",
            "custom_commission_pct": 150.0,
        })
        assert resp.status_code == 422

    def test_set_commission_negative_pct(self, admin_client):
        resp = admin_client.post("/api/admin/commissions", json={
            "target_type": "clinic",
            "target_id": "clinic-001",
            "custom_commission_pct": -5.0,
        })
        assert resp.status_code == 422

    def test_set_commission_as_therapist_forbidden(self, client):
        resp = client.post("/api/admin/commissions", json={
            "target_type": "clinic",
            "target_id": "clinic-001",
            "custom_commission_pct": 25.0,
        })
        assert resp.status_code == 403

    def test_set_commission_no_auth(self, client):
        resp = client._tc.post("/api/admin/commissions", json={
            "target_type": "clinic",
            "target_id": "clinic-001",
            "custom_commission_pct": 25.0,
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Assign Patient
# ---------------------------------------------------------------------------

class TestAssignPatient:
    def test_assign_patient_to_therapist(self, admin_client):
        admin_client._mock_supabase.set_table_data("patient_profiles", [
            {**SAMPLE_PATIENT, "current_therapist_id": "therapist-001"},
        ])
        admin_client._mock_supabase.set_table_data("therapist_profiles", [
            {"user_id": "therapist-001"},
        ])
        resp = admin_client.post("/api/admin/assign-patient", json={
            "patient_id": "patient-001",
            "therapist_id": "therapist-001",
        })
        assert resp.status_code == 200

    def test_assign_patient_to_clinic(self, admin_client):
        admin_client._mock_supabase.set_table_data("patient_profiles", [
            {**SAMPLE_PATIENT, "clinic_id": "clinic-001"},
        ])
        admin_client._mock_supabase.set_table_data("clinics", [
            {"id": "clinic-001"},
        ])
        resp = admin_client.post("/api/admin/assign-patient", json={
            "patient_id": "patient-001",
            "clinic_id": "clinic-001",
        })
        assert resp.status_code == 200

    def test_assign_patient_with_custom_price(self, admin_client):
        admin_client._mock_supabase.set_table_data("patient_profiles", [
            {**SAMPLE_PATIENT, "current_therapist_id": "therapist-001"},
        ])
        admin_client._mock_supabase.set_table_data("therapist_profiles", [
            {"user_id": "therapist-001"},
        ])
        admin_client._mock_supabase.set_table_data("patient_pricing", [
            {"patient_id": "patient-001", "therapist_id": "therapist-001", "custom_price": 150.0},
        ])
        resp = admin_client.post("/api/admin/assign-patient", json={
            "patient_id": "patient-001",
            "therapist_id": "therapist-001",
            "custom_price": 150.0,
        })
        assert resp.status_code == 200

    def test_assign_patient_missing_both_ids(self, admin_client):
        admin_client._mock_supabase.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        resp = admin_client.post("/api/admin/assign-patient", json={
            "patient_id": "patient-001",
        })
        assert resp.status_code == 400

    def test_assign_patient_nonexistent_patient(self, admin_client):
        admin_client._mock_supabase.set_table_data("patient_profiles", [])
        resp = admin_client.post("/api/admin/assign-patient", json={
            "patient_id": "nonexistent",
            "therapist_id": "therapist-001",
        })
        assert resp.status_code == 404

    def test_assign_patient_as_therapist_forbidden(self, client):
        resp = client.post("/api/admin/assign-patient", json={
            "patient_id": "patient-001",
            "therapist_id": "therapist-001",
        })
        assert resp.status_code == 403

    def test_assign_patient_no_auth(self, client):
        resp = client._tc.post("/api/admin/assign-patient", json={
            "patient_id": "patient-001",
            "therapist_id": "therapist-001",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Admin Listing
# ---------------------------------------------------------------------------

class TestAdminListing:
    def test_list_all_therapists(self, admin_client):
        admin_client._mock_supabase.set_table_data("therapist_profiles", [
            SAMPLE_PENDING_THERAPIST,
            SAMPLE_APPROVED_THERAPIST,
        ])
        resp = admin_client.get("/api/admin/therapists")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert "pagination" in body

    def test_list_all_therapists_pagination(self, admin_client):
        admin_client._mock_supabase.set_table_data("therapist_profiles", [])
        resp = admin_client.get("/api/admin/therapists?page=1&page_size=5")
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page_size"] == 5

    def test_list_all_clinics(self, admin_client):
        admin_client._mock_supabase.set_table_data("clinics", [SAMPLE_PENDING_CLINIC])
        resp = admin_client.get("/api/admin/clinics")
        assert resp.status_code == 200

    def test_list_all_patients(self, admin_client):
        admin_client._mock_supabase.set_table_data("patient_profiles", [SAMPLE_PATIENT])
        resp = admin_client.get("/api/admin/patients")
        assert resp.status_code == 200

    def test_list_all_therapists_as_therapist_forbidden(self, client):
        resp = client.get("/api/admin/therapists")
        assert resp.status_code == 403

    def test_list_all_clinics_as_patient_forbidden(self, patient_client):
        resp = patient_client.get("/api/admin/clinics")
        assert resp.status_code == 403

    def test_list_all_patients_no_auth(self, client):
        resp = client._tc.get("/api/admin/patients")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Admin Appointments — GET /api/admin/appointments
# ---------------------------------------------------------------------------


SAMPLE_APPOINTMENT = {
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


class TestAdminAppointments:
    def test_list_appointments_as_admin(self, admin_client):
        admin_client._mock_supabase.set_table_data("appointments", [SAMPLE_APPOINTMENT])
        admin_client._mock_supabase.set_table_data("clinics", [
            {"id": "clinic-001", "name": "Clínica Alpha"},
        ])
        resp = admin_client.get("/api/admin/appointments")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body
        assert len(body["data"]) == 1
        row = body["data"][0]
        assert row["id"] == "appt-001"
        assert row["clinic_name"] == "Clínica Alpha"
        # patient_name / therapist_name fall back to "" when the identity
        # resolver can't reach auth.admin in the mock; the keys must exist
        # so the frontend's `?.toLowerCase()` doesn't trip a TypeError.
        assert "patient_name" in row
        assert "therapist_name" in row

    def test_list_appointments_status_filter(self, admin_client):
        admin_client._mock_supabase.set_table_data("appointments", [])
        resp = admin_client.get("/api/admin/appointments?status=completed&page_size=5")
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page_size"] == 5

    def test_list_appointments_date_range(self, admin_client):
        admin_client._mock_supabase.set_table_data("appointments", [])
        resp = admin_client.get(
            "/api/admin/appointments?date_start=2026-05-01&date_end=2026-05-31"
        )
        assert resp.status_code == 200

    def test_list_appointments_as_therapist_forbidden(self, client):
        resp = client.get("/api/admin/appointments")
        assert resp.status_code == 403

    def test_list_appointments_as_patient_forbidden(self, patient_client):
        resp = patient_client.get("/api/admin/appointments")
        assert resp.status_code == 403

    def test_list_appointments_no_auth(self, client):
        resp = client._tc.get("/api/admin/appointments")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Admin Dashboard — GET /api/admin/dashboard
# ---------------------------------------------------------------------------


class TestAdminDashboard:
    def test_dashboard_as_admin(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "therapist_profiles", [SAMPLE_PENDING_THERAPIST]
        )
        admin_client._mock_supabase.set_table_data(
            "clinics", [SAMPLE_PENDING_CLINIC]
        )
        admin_client._mock_supabase.set_table_data("appointments", [])
        admin_client._mock_supabase.set_table_data("transactions", [
            {"gross_amount": "200.00", "platform_fee_amount": "20.00", "status": "captured"},
        ])
        resp = admin_client.get("/api/admin/dashboard")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        data = body["data"]
        assert "pending_therapists" in data
        assert "pending_clinics" in data
        assert "sessions_today" in data
        assert "total_revenue" in data
        assert data["total_revenue"] == 200.0

    def test_dashboard_therapist_forbidden(self, client):
        resp = client.get("/api/admin/dashboard")
        assert resp.status_code == 403

    def test_dashboard_no_auth(self, client):
        resp = client._tc.get("/api/admin/dashboard")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Suspend Entity — POST /api/admin/suspend/{type}/{id}
# ---------------------------------------------------------------------------


class TestSuspendEntity:
    def test_suspend_therapist(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "therapist_profiles", [SAMPLE_APPROVED_THERAPIST]
        )
        resp = admin_client.post(
            f"/api/admin/suspend/therapist/{SAMPLE_APPROVED_THERAPIST['user_id']}"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_suspend_clinic(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "clinics", [SAMPLE_PENDING_CLINIC]
        )
        resp = admin_client.post(
            f"/api/admin/suspend/clinic/{SAMPLE_PENDING_CLINIC['id']}"
        )
        assert resp.status_code == 200

    def test_suspend_invalid_entity_type(self, admin_client):
        resp = admin_client.post("/api/admin/suspend/widget/some-id")
        assert resp.status_code == 400
        body = resp.json()
        # Product wraps HTTPException details in the canonical error
        # envelope `{"error": {"code", "message"}}` via the seed-supplied
        # exception handler.
        assert body.get("error", {}).get("code") == "BAD_REQUEST"

    def test_suspend_nonexistent_entity(self, admin_client):
        admin_client._mock_supabase.set_table_data("therapist_profiles", [])
        resp = admin_client.post("/api/admin/suspend/therapist/missing-id")
        assert resp.status_code == 404

    def test_suspend_as_therapist_forbidden(self, client):
        resp = client.post("/api/admin/suspend/therapist/any-id")
        assert resp.status_code == 403

    def test_suspend_no_auth(self, client):
        resp = client._tc.post("/api/admin/suspend/clinic/any-id")
        assert resp.status_code == 401
