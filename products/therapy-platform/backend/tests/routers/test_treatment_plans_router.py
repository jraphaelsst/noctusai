"""
Tests for the Treatment Plans Router.

Covers: create plan (therapist only), list by patient, get with goals,
update, goal CRUD, and auth/permission checks.
"""
import pytest

SAMPLE_PLAN = {
    "id": "plan-001",
    "patient_id": "patient-001",
    "therapist_id": "test-user-123",
    "titulo": "Plano para manejo de ansiedade",
    "descricao": "Abordagem TCC com foco em reestruturação cognitiva",
    "data_inicio": "2026-04-01",
    "data_revisao": "2026-07-01",
    "status": "ativo",
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_GOAL = {
    "id": "goal-001",
    "treatment_plan_id": "plan-001",
    "descricao": "Praticar respiração diafragmática diariamente",
    "prazo": "2026-05-01",
    "status": "pendente",
}


class TestCreateTreatmentPlan:
    """POST /api/treatment-plans"""

    def test_create_plan(self, client):
        """Therapist creates a treatment plan."""
        client._mock_supabase.set_table_data("treatment_plans", [SAMPLE_PLAN])
        resp = client.post("/api/treatment-plans", json={
            "patient_id": "patient-001",
            "titulo": "Plano para manejo de ansiedade",
            "data_inicio": "2026-04-01",
        })
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_create_plan_patient_forbidden(self, patient_client):
        """Patient cannot create treatment plans."""
        resp = patient_client.post("/api/treatment-plans", json={
            "patient_id": "patient-001",
            "titulo": "Plano",
            "data_inicio": "2026-04-01",
        })
        assert resp.status_code == 403

    def test_create_plan_401(self, client):
        """No auth returns 401."""
        resp = client._tc.post("/api/treatment-plans", json={
            "titulo": "Plano",
        })
        assert resp.status_code == 401


class TestListPlansByPatient:
    """GET /api/treatment-plans/paciente/{patient_id}"""

    def test_list_plans(self, client):
        """Therapist lists plans for a patient."""
        client._mock_supabase.set_table_data("treatment_plans", [SAMPLE_PLAN])
        resp = client.get("/api/treatment-plans/paciente/patient-001")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_plans_patient_role(self, patient_client):
        """Patient can list their own treatment plans."""
        patient_client._mock_supabase.set_table_data("treatment_plans", [SAMPLE_PLAN])
        resp = patient_client.get("/api/treatment-plans/paciente/patient-001")
        assert resp.status_code == 200


class TestGetTreatmentPlan:
    """GET /api/treatment-plans/{plan_id}"""

    def test_get_plan(self, client):
        """Therapist gets a treatment plan with goals."""
        client._mock_supabase.set_table_data("treatment_plans", [SAMPLE_PLAN])
        client._mock_supabase.set_table_data("treatment_plan_goals", [SAMPLE_GOAL])
        resp = client.get("/api/treatment-plans/plan-001")
        assert resp.status_code == 200
        assert "data" in resp.json()


class TestUpdateTreatmentPlan:
    """PATCH /api/treatment-plans/{plan_id}"""

    def test_update_plan(self, client):
        """Therapist updates their own plan."""
        client._mock_supabase.set_table_data("treatment_plans", [SAMPLE_PLAN])
        resp = client.patch("/api/treatment-plans/plan-001", json={
            "titulo": "Plano atualizado",
        })
        assert resp.status_code == 200

    def test_update_plan_not_found(self, client):
        """Non-existent plan returns 404."""
        client._mock_supabase.set_table_data("treatment_plans", [])
        resp = client.patch("/api/treatment-plans/nonexistent", json={
            "titulo": "Teste",
        })
        assert resp.status_code == 404

    def test_update_plan_not_owner(self, client):
        """Therapist cannot update another therapist's plan."""
        other_plan = {**SAMPLE_PLAN, "therapist_id": "other-therapist-999"}
        client._mock_supabase.set_table_data("treatment_plans", [other_plan])
        resp = client.patch("/api/treatment-plans/plan-001", json={
            "titulo": "Teste",
        })
        assert resp.status_code == 403

    def test_update_plan_patient_forbidden(self, patient_client):
        """Patient cannot update treatment plans."""
        resp = patient_client.patch("/api/treatment-plans/plan-001", json={
            "titulo": "Teste",
        })
        assert resp.status_code == 403


class TestGoalCRUD:
    """POST/PATCH/DELETE /api/treatment-plans/{plan_id}/metas"""

    def test_add_goal(self, client):
        """Therapist adds a goal to their plan."""
        client._mock_supabase.set_table_data("treatment_plans", [SAMPLE_PLAN])
        client._mock_supabase.set_table_data("treatment_plan_goals", [SAMPLE_GOAL])
        resp = client.post("/api/treatment-plans/plan-001/metas", json={
            "descricao": "Praticar respiração diafragmática",
        })
        assert resp.status_code == 200

    def test_add_goal_plan_not_found(self, client):
        """Adding goal to non-existent plan returns 404."""
        client._mock_supabase.set_table_data("treatment_plans", [])
        resp = client.post("/api/treatment-plans/nonexistent/metas", json={
            "descricao": "Meta teste",
        })
        assert resp.status_code == 404

    def test_add_goal_patient_forbidden(self, patient_client):
        """Patient cannot add goals."""
        resp = patient_client.post("/api/treatment-plans/plan-001/metas", json={
            "descricao": "Meta",
        })
        assert resp.status_code == 403

    def test_update_goal(self, client):
        """Therapist updates a goal."""
        client._mock_supabase.set_table_data("treatment_plan_goals", [SAMPLE_GOAL])
        client._mock_supabase.set_table_data("treatment_plans", [SAMPLE_PLAN])
        client._mock_supabase.set_table_data("treatment_plan_goals", [SAMPLE_GOAL])
        resp = client.patch("/api/treatment-plans/metas/goal-001", json={
            "status": "em_andamento",
        })
        assert resp.status_code == 200

    def test_update_goal_not_found(self, client):
        """Non-existent goal returns 404."""
        client._mock_supabase.set_table_data("treatment_plan_goals", [])
        resp = client.patch("/api/treatment-plans/metas/nonexistent", json={
            "status": "em_andamento",
        })
        assert resp.status_code == 404

    def test_delete_goal(self, client):
        """Therapist deletes a goal."""
        client._mock_supabase.set_table_data("treatment_plan_goals", [SAMPLE_GOAL])
        client._mock_supabase.set_table_data("treatment_plans", [SAMPLE_PLAN])
        client._mock_supabase.set_table_data("treatment_plan_goals", [SAMPLE_GOAL])
        resp = client.delete("/api/treatment-plans/metas/goal-001")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    def test_delete_goal_not_found(self, client):
        """Non-existent goal returns 404."""
        client._mock_supabase.set_table_data("treatment_plan_goals", [])
        resp = client.delete("/api/treatment-plans/metas/nonexistent")
        assert resp.status_code == 404

    def test_delete_goal_patient_forbidden(self, patient_client):
        """Patient cannot delete goals."""
        resp = patient_client.delete("/api/treatment-plans/metas/goal-001")
        assert resp.status_code == 403
