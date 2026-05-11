"""
Tests for the Homework Router.

Covers: assign (therapist), submit (patient), review (therapist),
list filtered by role, get single, and auth/permission checks.
"""
import pytest

SAMPLE_HOMEWORK = {
    "id": "hw-001",
    "therapist_id": "test-user-123",
    "patient_id": "patient-001",
    "titulo": "Registro de pensamentos automáticos",
    "descricao": "Anotar 3 pensamentos automáticos por dia",
    "data_limite": "2026-04-15",
    "status": "pendente",
    "created_at": "2026-04-01T10:00:00Z",
}

SAMPLE_HOMEWORK_SUBMITTED = {
    **SAMPLE_HOMEWORK,
    "id": "hw-002",
    "status": "concluido",
    "resposta_paciente": "Consegui registrar 3 pensamentos por dia.",
}


class TestAssignHomework:
    """POST /api/homework"""

    def test_assign_homework(self, client):
        """Therapist assigns homework to a patient."""
        client._mock_supabase.set_table_data("homework_assignments", [SAMPLE_HOMEWORK])
        resp = client.post("/api/homework", json={
            "patient_id": "patient-001",
            "titulo": "Registro de pensamentos",
            "descricao": "Anotar 3 pensamentos automáticos por dia",
        })
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_assign_homework_patient_forbidden(self, patient_client):
        """Patient cannot assign homework."""
        resp = patient_client.post("/api/homework", json={
            "patient_id": "patient-001",
            "titulo": "Teste",
            "descricao": "Teste",
        })
        assert resp.status_code == 403

    def test_assign_homework_401(self, client):
        """No auth returns 401.

        Body MUST be a complete + valid `HomeworkAssignCreate` so the
        request reaches the auth dependency (otherwise Pydantic 422
        short-circuits before auth fires — see KB §
        `PATTERNS/testing.md` 401-before-422 ordering).
        """
        resp = client._tc.post("/api/homework", json={
            "patient_id": "patient-001",
            "titulo": "Teste",
            "descricao": "Anotar 3 pensamentos automáticos por dia",
        })
        assert resp.status_code == 401


class TestListHomework:
    """GET /api/homework"""

    def test_list_homework_therapist(self, client):
        """Therapist lists homework they assigned."""
        client._mock_supabase.set_table_data("homework_assignments", [SAMPLE_HOMEWORK])
        resp = client.get("/api/homework")
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_list_homework_patient(self, patient_client):
        """Patient lists homework assigned to them."""
        patient_client._mock_supabase.set_table_data("homework_assignments", [SAMPLE_HOMEWORK])
        resp = patient_client.get("/api/homework")
        assert resp.status_code == 200

    def test_list_homework_with_status_filter(self, client):
        """Therapist filters homework by status."""
        client._mock_supabase.set_table_data("homework_assignments", [SAMPLE_HOMEWORK])
        resp = client.get("/api/homework", params={"status": "pendente"})
        assert resp.status_code == 200


class TestGetHomework:
    """GET /api/homework/{homework_id}"""

    def test_get_homework_therapist(self, client):
        """Therapist gets a homework they assigned."""
        client._mock_supabase.set_table_data("homework_assignments", [SAMPLE_HOMEWORK])
        resp = client.get("/api/homework/hw-001")
        assert resp.status_code == 200
        assert "data" in resp.json()

    def test_get_homework_not_found(self, client):
        """Non-existent homework returns 404."""
        client._mock_supabase.set_table_data("homework_assignments", [])
        resp = client.get("/api/homework/nonexistent")
        assert resp.status_code == 404

    def test_get_homework_not_owner(self, client):
        """Therapist cannot view another therapist's homework."""
        other_hw = {**SAMPLE_HOMEWORK, "therapist_id": "other-therapist-999"}
        client._mock_supabase.set_table_data("homework_assignments", [other_hw])
        resp = client.get("/api/homework/hw-001")
        assert resp.status_code == 403


class TestSubmitHomework:
    """POST /api/homework/{homework_id}/submit"""

    def test_submit_homework(self, patient_client):
        """Patient submits a homework response."""
        hw = {**SAMPLE_HOMEWORK, "patient_id": "test-user-123"}
        patient_client._mock_supabase.set_table_data("homework_assignments", [hw])
        resp = patient_client.post("/api/homework/hw-001/submit", json={
            "resposta_paciente": "Consegui registrar os pensamentos.",
        })
        assert resp.status_code == 200

    def test_submit_homework_therapist_forbidden(self, client):
        """Therapist cannot submit homework."""
        resp = client.post("/api/homework/hw-001/submit", json={
            "resposta_paciente": "Teste",
        })
        assert resp.status_code == 403

    def test_submit_homework_not_found(self, patient_client):
        """Non-existent homework returns 404."""
        patient_client._mock_supabase.set_table_data("homework_assignments", [])
        resp = patient_client.post("/api/homework/nonexistent/submit", json={
            "resposta_paciente": "Teste",
        })
        assert resp.status_code == 404

    def test_submit_homework_not_assignee(self, patient_client):
        """Patient cannot submit another patient's homework."""
        other_hw = {**SAMPLE_HOMEWORK, "patient_id": "other-patient-999"}
        patient_client._mock_supabase.set_table_data("homework_assignments", [other_hw])
        resp = patient_client.post("/api/homework/hw-001/submit", json={
            "resposta_paciente": "Teste",
        })
        assert resp.status_code == 403


class TestReviewHomework:
    """POST /api/homework/{homework_id}/review"""

    def test_review_homework(self, client):
        """Therapist reviews submitted homework."""
        completed_hw = {**SAMPLE_HOMEWORK, "status": "concluido"}
        client._mock_supabase.set_table_data("homework_assignments", [completed_hw])
        resp = client.post("/api/homework/hw-001/review", json={
            "feedback_terapeuta": "Excelente trabalho!",
        })
        assert resp.status_code == 200

    def test_review_homework_patient_forbidden(self, patient_client):
        """Patient cannot review homework."""
        resp = patient_client.post("/api/homework/hw-001/review", json={
            "feedback_terapeuta": "Teste",
        })
        assert resp.status_code == 403

    def test_review_homework_not_found(self, client):
        """Non-existent homework returns 404."""
        client._mock_supabase.set_table_data("homework_assignments", [])
        resp = client.post("/api/homework/nonexistent/review", json={
            "feedback_terapeuta": "Teste",
        })
        assert resp.status_code == 404

    def test_review_homework_not_owner(self, client):
        """Therapist cannot review another therapist's homework."""
        other_hw = {**SAMPLE_HOMEWORK, "therapist_id": "other-therapist-999"}
        client._mock_supabase.set_table_data("homework_assignments", [other_hw])
        resp = client.post("/api/homework/hw-001/review", json={
            "feedback_terapeuta": "Teste",
        })
        assert resp.status_code == 403
