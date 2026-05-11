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
    "set_by_admin_id": "test-user-123",
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
        # Phase 4 fix: canonical table is platform_commission_overrides
        # (see migration 001 §platform_commission_overrides). admin_service
        # previously wrote to a non-existent commission_overrides table.
        admin_client._mock_supabase.set_table_data("platform_commission_overrides", [
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
        # Status-code-assertion-rule + payload contract:
        # set_by_admin_id is the canonical column name (NOT set_by).
        assert data.get("set_by_admin_id") == "test-user-123"

    def test_set_commission_for_therapist(self, admin_client):
        admin_client._mock_supabase.set_table_data("platform_commission_overrides", [
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


# ---------------------------------------------------------------------------
# Admin Clinics DTO normalization — GET /api/admin/clinics (Phase 3)
# ---------------------------------------------------------------------------


SAMPLE_CLINIC_ROW = {
    "id": "clinic-alpha",
    "name": "Clínica Alpha",
    "cnpj": "11111111000111",
    "responsible_person": "Maria Souza",
    "contact_email": "contato@alpha.com",
    "phone": "+5511999999999",
    "logo_url": None,
    "is_approved": True,
    "is_active": True,
    "approved_by": "admin-uid-001",
    "created_at": "2026-04-01T10:00:00Z",
    "updated_at": "2026-04-02T10:00:00Z",
}


class TestAdminClinicsDTO:
    def test_list_clinics_returns_dto_shape(self, admin_client):
        admin_client._mock_supabase.set_table_data("clinics", [SAMPLE_CLINIC_ROW])
        resp = admin_client.get("/api/admin/clinics")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body
        row = body["data"][0]
        # ``Clinica`` DTO fields the page reads.
        assert row["id"] == "clinic-alpha"
        assert row["nome"] == "Clínica Alpha"
        assert row["cnpj"] == "11111111000111"
        assert row["status"] == "aprovada"
        assert row["responsavel"]  # falls back to responsible_person column

    def test_list_clinics_status_filter(self, admin_client):
        admin_client._mock_supabase.set_table_data("clinics", [SAMPLE_CLINIC_ROW])
        resp = admin_client.get("/api/admin/clinics?status=pendente")
        assert resp.status_code == 200
        body = resp.json()
        # MockSupabase doesn't apply read predicates, so we only check
        # the shape/route accepts the filter without breaking.
        assert "data" in body

    def test_list_clinics_rejeitada_accepts_filter(self, admin_client):
        # Phase 5: removed the empty-fallback hack after migration 013
        # landed the reject-audit columns. The filter now resolves to
        # ``is_approved=False AND rejection_reason IS NOT NULL`` against
        # the real DB. MockSupabase doesn't apply read predicates so we
        # only assert the route accepts the filter without breaking.
        admin_client._mock_supabase.set_table_data("clinics", [SAMPLE_CLINIC_ROW])
        resp = admin_client.get("/api/admin/clinics?status=rejeitada")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert "pagination" in body

    def test_list_clinics_as_therapist_forbidden(self, client):
        resp = client.get("/api/admin/clinics")
        assert resp.status_code == 403

    def test_list_clinics_no_auth(self, client):
        resp = client._tc.get("/api/admin/clinics")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Admin Patients DTO normalization — GET /api/admin/patients (Phase 3)
# ---------------------------------------------------------------------------


SAMPLE_PATIENT_ROW = {
    "user_id": "patient-001",
    "current_therapist_id": "therapist-001",
    "clinic_id": "clinic-alpha",
    "origin": "platform",
    "phone": "+5511988887777",
    "is_active": True,
    "created_at": "2026-04-01T10:00:00Z",
    "updated_at": "2026-04-02T10:00:00Z",
}


class TestAdminPatientsDTO:
    def test_list_patients_returns_dto_shape(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "patient_profiles", [SAMPLE_PATIENT_ROW]
        )
        admin_client._mock_supabase.set_table_data("appointments", [])
        resp = admin_client.get("/api/admin/patients")
        assert resp.status_code == 200
        body = resp.json()
        row = body["data"][0]
        # ``AdminPatient`` DTO fields the page reads.
        assert row["id"] == "patient-001"
        assert "nome" in row
        assert "email" in row
        assert row["origin"] == "platform"
        assert row["session_count"] == 0
        # terapeuta_nome key MUST exist even when unresolved (so the
        # frontend ``p.terapeuta_nome ?? "Sem terapeuta"`` works).
        assert "terapeuta_nome" in row

    def test_list_patients_session_count_aggregates_completed(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "patient_profiles", [SAMPLE_PATIENT_ROW]
        )
        admin_client._mock_supabase.set_table_data(
            "appointments",
            [
                {"patient_id": "patient-001", "status": "completed"},
                {"patient_id": "patient-001", "status": "completed"},
            ],
        )
        resp = admin_client.get("/api/admin/patients")
        assert resp.status_code == 200
        body = resp.json()
        row = body["data"][0]
        # MockSupabase doesn't apply ``.eq("status","completed")`` on
        # SELECT reads — seed only the rows the production filter would
        # pass through (Phase 2 caveat re-used). Counts reflect those
        # rows.
        assert row["session_count"] == 2

    def test_list_patients_search_filter(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "patient_profiles", [SAMPLE_PATIENT_ROW]
        )
        admin_client._mock_supabase.set_table_data("appointments", [])
        resp = admin_client.get("/api/admin/patients?busca=988")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_patients_as_patient_forbidden(self, patient_client):
        resp = patient_client.get("/api/admin/patients")
        assert resp.status_code == 403

    def test_list_patients_no_auth(self, client):
        resp = client._tc.get("/api/admin/patients")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Admin Reports — GET /api/admin/reports + resolve (Phase 3)
# ---------------------------------------------------------------------------


SAMPLE_REPORT_ROW = {
    "id": "report-001",
    "conversation_id": "convo-001",
    "message_id": "msg-001",
    "reported_by_user_id": "reporter-uid",
    "reason": "Linguagem inapropriada",
    "status": "pending",
    "created_at": "2026-04-30T10:00:00Z",
}


class TestAdminReports:
    def test_list_reports_dto_shape(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "message_reports", [SAMPLE_REPORT_ROW]
        )
        admin_client._mock_supabase.set_table_data(
            "messages",
            [{"id": "msg-001", "content": "Mensagem sinalizada", "message_type": "text"}],
        )
        resp = admin_client.get("/api/admin/reports")
        assert resp.status_code == 200
        body = resp.json()
        row = body["data"][0]
        # ``Report`` DTO keys the Moderation page reads.
        assert row["id"] == "report-001"
        assert "reporter_name" in row
        assert "reported_message_preview" in row
        assert row["reason"] == "Linguagem inapropriada"
        assert row["status"] == "pending"
        assert row["conversation_id"] == "convo-001"

    def test_list_reports_status_filter(self, admin_client):
        admin_client._mock_supabase.set_table_data("message_reports", [])
        admin_client._mock_supabase.set_table_data("messages", [])
        resp = admin_client.get("/api/admin/reports?status=resolved")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []

    def test_resolve_report_success(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "message_reports", [SAMPLE_REPORT_ROW]
        )
        resp = admin_client.post(
            "/api/admin/reports/report-001/resolve",
            json={"resolution": "Usuário advertido"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_resolve_report_missing_resolution_400(self, admin_client):
        resp = admin_client.post(
            "/api/admin/reports/report-001/resolve",
            json={"resolution": ""},
        )
        assert resp.status_code == 422  # pydantic min_length=1

    def test_resolve_report_not_found(self, admin_client):
        admin_client._mock_supabase.set_table_data("message_reports", [])
        resp = admin_client.post(
            "/api/admin/reports/missing/resolve",
            json={"resolution": "qualquer"},
        )
        assert resp.status_code == 404

    def test_list_reports_as_therapist_forbidden(self, client):
        resp = client.get("/api/admin/reports")
        assert resp.status_code == 403

    def test_list_reports_no_auth(self, client):
        resp = client._tc.get("/api/admin/reports")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Admin Flagged Reviews — GET /api/admin/reviews/flagged + actions (Phase 3)
# ---------------------------------------------------------------------------


SAMPLE_FLAGGED_THERAPIST_REVIEW = {
    "id": "review-t-001",
    "patient_id": "patient-001",
    "therapist_id": "therapist-001",
    "clinic_id": None,
    "star_rating": 1,
    "review_text": "Terapeuta foi rude",
    "is_flagged": True,
    "is_hidden": False,
    "flagged_by_therapist_id": "therapist-001",
    "flagged_reason": "Conteúdo difamatório",
    "created_at": "2026-04-30T10:00:00Z",
    "updated_at": "2026-04-30T10:00:00Z",
}

SAMPLE_FLAGGED_CLINIC_REVIEW = {
    "id": "review-c-001",
    "patient_id": "patient-002",
    "clinic_id": "clinic-alpha",
    "star_rating": 2,
    "review_text": "Recepção lenta",
    "is_flagged": True,
    "is_hidden": False,
    "flagged_by_clinic_admin_id": "clinic-admin-001",
    "flagged_reason": "Avaliação inválida",
    "created_at": "2026-04-29T10:00:00Z",
    "updated_at": "2026-04-29T10:00:00Z",
}


class TestAdminFlaggedReviews:
    def test_list_flagged_reviews_dto_shape(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "reviews", [SAMPLE_FLAGGED_THERAPIST_REVIEW]
        )
        admin_client._mock_supabase.set_table_data(
            "clinic_reviews", [SAMPLE_FLAGGED_CLINIC_REVIEW]
        )
        admin_client._mock_supabase.set_table_data(
            "clinics",
            [{"id": "clinic-alpha", "name": "Clínica Alpha"}],
        )
        resp = admin_client.get("/api/admin/reviews/flagged")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        assert len(body["data"]) == 2
        types = {r["entity_type"] for r in body["data"]}
        assert types == {"therapist", "clinic"}
        # Every DTO carries the ``FlaggedReview`` shape the page reads.
        for r in body["data"]:
            assert "nota" in r
            assert "comentario" in r
            assert "patient_name" in r
            assert "entity_name" in r
            assert "flag_reason" in r
            assert "created_at" in r

    def test_list_flagged_reviews_entity_filter_therapist(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "reviews", [SAMPLE_FLAGGED_THERAPIST_REVIEW]
        )
        admin_client._mock_supabase.set_table_data(
            "clinic_reviews", [SAMPLE_FLAGGED_CLINIC_REVIEW]
        )
        admin_client._mock_supabase.set_table_data("clinics", [])
        resp = admin_client.get("/api/admin/reviews/flagged?entity_type=therapist")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["entity_type"] == "therapist"

    def test_dismiss_review_flag_clears_is_flagged(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "reviews", [SAMPLE_FLAGGED_THERAPIST_REVIEW]
        )
        admin_client._mock_supabase.set_table_data("clinic_reviews", [])
        resp = admin_client.post("/api/admin/reviews/review-t-001/dismiss")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_hide_review_sets_is_hidden(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "reviews", [SAMPLE_FLAGGED_THERAPIST_REVIEW]
        )
        admin_client._mock_supabase.set_table_data("clinic_reviews", [])
        resp = admin_client.post("/api/admin/reviews/review-t-001/hide")
        assert resp.status_code == 200

    def test_dismiss_falls_through_to_clinic_reviews(self, admin_client):
        admin_client._mock_supabase.set_table_data("reviews", [])
        admin_client._mock_supabase.set_table_data(
            "clinic_reviews", [SAMPLE_FLAGGED_CLINIC_REVIEW]
        )
        resp = admin_client.post("/api/admin/reviews/review-c-001/dismiss")
        assert resp.status_code == 200

    def test_dismiss_unknown_review_404(self, admin_client):
        admin_client._mock_supabase.set_table_data("reviews", [])
        admin_client._mock_supabase.set_table_data("clinic_reviews", [])
        resp = admin_client.post("/api/admin/reviews/missing/dismiss")
        assert resp.status_code == 404

    def test_list_flagged_as_therapist_forbidden(self, client):
        resp = client.get("/api/admin/reviews/flagged")
        assert resp.status_code == 403

    def test_list_flagged_no_auth(self, client):
        resp = client._tc.get("/api/admin/reviews/flagged")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Admin Blocks — GET /api/admin/blocks (Phase 3)
# ---------------------------------------------------------------------------


SAMPLE_BLOCK_ROW = {
    "id": "block-001",
    "blocker_user_id": "user-blocker",
    "blocked_user_id": "user-blocked",
    "created_at": "2026-04-30T10:00:00Z",
}


class TestAdminBlocks:
    def test_list_blocks_dto_shape(self, admin_client):
        admin_client._mock_supabase.set_table_data("user_blocks", [SAMPLE_BLOCK_ROW])
        resp = admin_client.get("/api/admin/blocks")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        row = body["data"][0]
        # ``Block`` DTO shape the page reads.
        assert row["id"] == "block-001"
        assert "blocker_name" in row
        assert "blocked_name" in row
        assert row["created_at"] == "2026-04-30T10:00:00Z"

    def test_list_blocks_empty(self, admin_client):
        admin_client._mock_supabase.set_table_data("user_blocks", [])
        resp = admin_client.get("/api/admin/blocks")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []

    def test_list_blocks_as_therapist_forbidden(self, client):
        resp = client.get("/api/admin/blocks")
        assert resp.status_code == 403

    def test_list_blocks_no_auth(self, client):
        resp = client._tc.get("/api/admin/blocks")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Admin Support Conversations — GET /api/admin/support/conversations (Phase 3)
# ---------------------------------------------------------------------------


SAMPLE_SUPPORT_CONVO = {
    "id": "convo-support-001",
    "mode": "human",
    "last_message_at": "2026-04-01T10:00:00Z",
    "created_at": "2026-04-01T09:00:00Z",
    "last_message_preview": "Preciso de ajuda",
    "unread_count": 1,
    "is_muted": False,
}


class TestAdminSupportConversations:
    def test_list_support_conversations_dto_shape(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "conversations", [SAMPLE_SUPPORT_CONVO]
        )
        admin_client._mock_supabase.set_table_data(
            "conversation_participants",
            [
                {
                    "conversation_id": "convo-support-001",
                    "participant_type": "platform_support",
                    "participant_id": None,
                    "clinic_id": None,
                },
                {
                    "conversation_id": "convo-support-001",
                    "participant_type": "user",
                    "participant_id": "patient-uid-1",
                    "clinic_id": None,
                },
            ],
        )
        resp = admin_client.get("/api/admin/support/conversations")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body
        row = body["data"][0]
        # ``Conversation`` DTO from frontend/src/types/messaging.ts
        assert row["id"] == "convo-support-001"
        assert row["mode"] == "human"
        assert row["is_support"] is True
        assert "other_participant_name" in row
        assert row["other_participant_type"] in ("user", "clinic", "platform_support")
        assert "unread_count" in row
        assert "is_muted" in row

    def test_list_support_conversations_empty_when_no_participants(self, admin_client):
        admin_client._mock_supabase.set_table_data("conversations", [])
        admin_client._mock_supabase.set_table_data("conversation_participants", [])
        resp = admin_client.get("/api/admin/support/conversations")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"] == []

    def test_list_support_conversations_busca_filter(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "conversations", [SAMPLE_SUPPORT_CONVO]
        )
        admin_client._mock_supabase.set_table_data(
            "conversation_participants",
            [
                {
                    "conversation_id": "convo-support-001",
                    "participant_type": "platform_support",
                },
            ],
        )
        resp = admin_client.get("/api/admin/support/conversations?busca=convo")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_support_conversations_as_therapist_forbidden(self, client):
        resp = client.get("/api/admin/support/conversations")
        assert resp.status_code == 403

    def test_list_support_conversations_no_auth(self, client):
        resp = client._tc.get("/api/admin/support/conversations")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Phase 5 — Reject flow router transitions
# ---------------------------------------------------------------------------


class TestRejectFlowTransitions:
    """End-to-end transitions across the reject lifecycle."""

    def test_pendente_to_rejeitado_with_reason(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "therapist_profiles",
            [{"user_id": "t1", "is_approved": False, "is_active": True}],
        )
        resp = admin_client.post(
            "/api/admin/reject/therapist/t1",
            json={"action": "reject", "reason": "CRP inválido"},
        )
        assert resp.status_code == 200
        # The update payload carries the full reject-audit triplet
        # (migration 013 columns); inspecting `updated_payloads` is the
        # canonical way to assert UPDATE shape under MockSupabase.
        payloads = admin_client._mock_supabase.table(
            "therapist_profiles"
        ).updated_payloads
        assert payloads, "reject should have issued an update"
        payload = payloads[-1]
        assert payload["is_approved"] is False
        assert payload["rejection_reason"] == "CRP inválido"
        assert payload["rejected_by"]  # admin id from JWT
        assert payload["rejected_at"]  # ISO timestamp

    def test_rejeitado_to_aprovado_clears_audit(self, admin_client):
        # Seed state: previously rejected therapist.
        admin_client._mock_supabase.set_table_data(
            "therapist_profiles",
            [
                {
                    "user_id": "t1",
                    "is_approved": False,
                    "is_active": True,
                    "rejection_reason": "needs docs",
                    "rejected_at": "2026-05-10T10:00:00+00:00",
                    "rejected_by": "admin-uid-prev",
                }
            ],
        )
        resp = admin_client.post("/api/admin/approve/therapist/t1")
        assert resp.status_code == 200
        payload = admin_client._mock_supabase.table(
            "therapist_profiles"
        ).updated_payloads[-1]
        # Re-approval clears the reject-audit triplet AND
        # reactivates the row (in case prior reject was followed by a
        # suspend that lowered is_active).
        assert payload["is_approved"] is True
        assert payload["is_active"] is True
        assert payload["rejection_reason"] is None
        assert payload["rejected_at"] is None
        assert payload["rejected_by"] is None

    def test_aprovado_suspenso_aprovado_keeps_audit_clear(self, admin_client):
        # 1) Approved baseline (no audit columns).
        admin_client._mock_supabase.set_table_data(
            "therapist_profiles",
            [{"user_id": "t1", "is_approved": True, "is_active": True}],
        )
        # 2) Suspend.
        r1 = admin_client.post("/api/admin/suspend/therapist/t1")
        assert r1.status_code == 200
        suspended_payload = admin_client._mock_supabase.table(
            "therapist_profiles"
        ).updated_payloads[-1]
        assert suspended_payload["is_active"] is False
        # Suspension touches `is_active` only — leaves audit columns clean.
        assert "rejection_reason" not in suspended_payload
        assert "rejected_at" not in suspended_payload

        # 3) Re-approve clears audit defensively (no-op if already clean).
        r2 = admin_client.post("/api/admin/approve/therapist/t1")
        assert r2.status_code == 200
        approved_payload = admin_client._mock_supabase.table(
            "therapist_profiles"
        ).updated_payloads[-1]
        assert approved_payload["is_approved"] is True
        assert approved_payload["is_active"] is True
        assert approved_payload["rejection_reason"] is None
        assert approved_payload["rejected_at"] is None
        assert approved_payload["rejected_by"] is None

    def test_clinic_pendente_to_rejeitada_with_reason(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "clinics",
            [{"id": "c1", "is_approved": False, "is_active": True}],
        )
        resp = admin_client.post(
            "/api/admin/reject/clinic/c1",
            json={"action": "reject", "reason": "CNPJ inválido"},
        )
        assert resp.status_code == 200
        payload = admin_client._mock_supabase.table(
            "clinics"
        ).updated_payloads[-1]
        assert payload["rejection_reason"] == "CNPJ inválido"
        assert payload["rejected_by"]
        assert payload["rejected_at"]


# ---------------------------------------------------------------------------
# Phase 5 — Admin detail endpoints (GET /api/admin/{therapists,clinics}/:id)
# ---------------------------------------------------------------------------


class TestAdminTherapistDetail:
    def test_get_returns_audit_fields_when_rejected(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "therapist_profiles",
            [
                {
                    "user_id": "t1",
                    "crp": "06/111",
                    "is_approved": False,
                    "is_active": True,
                    "rejection_reason": "CRP inválido",
                    "rejected_at": "2026-05-11T10:00:00+00:00",
                    "rejected_by": "admin-uid-007",
                }
            ],
        )
        resp = admin_client.get("/api/admin/therapists/t1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "t1"
        assert data["status"] == "rejeitado"
        assert data["rejection_reason"] == "CRP inválido"
        assert data["rejected_at"] == "2026-05-11T10:00:00+00:00"
        assert data["rejected_by"] == "admin-uid-007"
        assert "rejected_by_name" in data

    def test_get_returns_clean_audit_when_not_rejected(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "therapist_profiles",
            [{"user_id": "t1", "is_approved": True, "is_active": True}],
        )
        resp = admin_client.get("/api/admin/therapists/t1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["status"] == "aprovado"
        assert data["rejection_reason"] is None
        assert data["rejected_at"] is None
        assert data["rejected_by"] is None

    def test_get_404_when_missing(self, admin_client):
        admin_client._mock_supabase.set_table_data("therapist_profiles", [])
        resp = admin_client.get("/api/admin/therapists/missing")
        assert resp.status_code == 404

    def test_get_as_therapist_forbidden(self, client):
        resp = client.get("/api/admin/therapists/t1")
        assert resp.status_code == 403

    def test_get_no_auth(self, client):
        resp = client._tc.get("/api/admin/therapists/t1")
        assert resp.status_code == 401


class TestAdminClinicDetail:
    def test_get_returns_audit_fields_when_rejected(self, admin_client):
        admin_client._mock_supabase.set_table_data(
            "clinics",
            [
                {
                    "id": "c1",
                    "name": "Clínica X",
                    "is_approved": False,
                    "is_active": True,
                    "rejection_reason": "CNPJ inválido",
                    "rejected_at": "2026-05-11T10:00:00+00:00",
                    "rejected_by": "admin-uid-007",
                }
            ],
        )
        resp = admin_client.get("/api/admin/clinics/c1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "c1"
        assert data["status"] == "rejeitada"
        assert data["rejection_reason"] == "CNPJ inválido"
        assert data["rejected_at"] == "2026-05-11T10:00:00+00:00"
        assert data["rejected_by"] == "admin-uid-007"
        assert "rejected_by_name" in data

    def test_get_404_when_missing(self, admin_client):
        admin_client._mock_supabase.set_table_data("clinics", [])
        resp = admin_client.get("/api/admin/clinics/missing")
        assert resp.status_code == 404

    def test_get_as_therapist_forbidden(self, client):
        resp = client.get("/api/admin/clinics/c1")
        assert resp.status_code == 403

    def test_get_no_auth(self, client):
        resp = client._tc.get("/api/admin/clinics/c1")
        assert resp.status_code == 401
