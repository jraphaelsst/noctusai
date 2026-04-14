"""Tests for the Focus Sessions router — /api/foco endpoints."""
from datetime import datetime

SAMPLE_SESSION = {
    "id": "sess-1",
    "user_id": "test-user-123",
    "tipo": "pomodoro",
    "duracao_minutos": 25,
    "tarefa_id": None,
    "nota": None,
    "inicio": "2026-04-13T10:00:00",
    "fim": None,
    "created_at": "2026-04-13T10:00:00Z",
}

SAMPLE_SESSION_DEEP = {
    "id": "sess-2",
    "user_id": "test-user-123",
    "tipo": "deep_work",
    "duracao_minutos": 90,
    "tarefa_id": "task-1",
    "nota": "Foco total",
    "inicio": "2026-04-13T14:00:00",
    "fim": "2026-04-13T15:30:00",
    "created_at": "2026-04-13T14:00:00Z",
}


# ---------------------------------------------------------------------------
# List sessions
# ---------------------------------------------------------------------------

class TestListFocusSessions:
    def test_list_sessions(self, client):
        client.mock_supabase.set_table_data("sessoes_foco", [SAMPLE_SESSION, SAMPLE_SESSION_DEEP])
        resp = client.get("/api/foco")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 2

    def test_list_sessions_no_auth(self, client):
        resp = client.raw().get("/api/foco")
        assert resp.status_code == 401

    def test_list_sessions_filter_tipo(self, client):
        client.mock_supabase.set_table_data("sessoes_foco", [SAMPLE_SESSION])
        resp = client.get("/api/foco", params={"tipo": "pomodoro"})
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_sessions_pagination(self, client):
        client.mock_supabase.set_table_data("sessoes_foco", [SAMPLE_SESSION])
        resp = client.get("/api/foco", params={"page": 2, "page_size": 5})
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page"] == 2
        assert body["pagination"]["page_size"] == 5

    def test_list_sessions_empty(self, client):
        client.mock_supabase.set_table_data("sessoes_foco", [])
        resp = client.get("/api/foco")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ---------------------------------------------------------------------------
# Create session
# ---------------------------------------------------------------------------

class TestCreateFocusSession:
    def test_create_session(self, client):
        client.mock_supabase.set_table_data("sessoes_foco", [SAMPLE_SESSION])
        resp = client.post("/api/foco", json={
            "tipo": "pomodoro",
            "duracao_minutos": 25,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["tipo"] == "pomodoro"
        assert body["data"]["duracao_minutos"] == 25

    def test_create_session_with_tarefa(self, client):
        session = {**SAMPLE_SESSION_DEEP}
        client.mock_supabase.set_table_data("sessoes_foco", [session])
        resp = client.post("/api/foco", json={
            "tipo": "deep_work",
            "duracao_minutos": 90,
            "tarefa_id": "task-1",
            "nota": "Foco total",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["tarefa_id"] == "task-1"

    def test_create_session_invalid_tipo(self, client):
        resp = client.post("/api/foco", json={
            "tipo": "invalido",
            "duracao_minutos": 25,
        })
        assert resp.status_code == 422

    def test_create_session_missing_duracao(self, client):
        resp = client.post("/api/foco", json={"tipo": "pomodoro"})
        assert resp.status_code == 422

    def test_create_session_duracao_zero(self, client):
        resp = client.post("/api/foco", json={
            "tipo": "pomodoro",
            "duracao_minutos": 0,
        })
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Update session
# ---------------------------------------------------------------------------

class TestUpdateFocusSession:
    def test_update_session_nota(self, client):
        updated = {**SAMPLE_SESSION, "nota": "Boa sessao"}
        client.mock_supabase.set_table_data("sessoes_foco", [updated])
        resp = client.patch("/api/foco/sess-1", json={"nota": "Boa sessao"})
        assert resp.status_code == 200
        assert resp.json()["data"]["nota"] == "Boa sessao"

    def test_update_session_not_found(self, client):
        client.mock_supabase.set_table_data("sessoes_foco", [])
        resp = client.patch("/api/foco/nonexistent", json={"nota": "Nada"})
        assert resp.status_code == 404

    def test_update_session_no_fields(self, client):
        resp = client.patch("/api/foco/sess-1", json={})
        assert resp.status_code == 400
        assert "nenhum campo" in resp.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# Delete session
# ---------------------------------------------------------------------------

class TestDeleteFocusSession:
    def test_delete_session(self, client):
        client.mock_supabase.set_table_data("sessoes_foco", [SAMPLE_SESSION])
        resp = client.delete("/api/foco/sess-1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert "removida" in resp.json()["message"].lower()

    def test_delete_session_not_found(self, client):
        client.mock_supabase.set_table_data("sessoes_foco", [])
        resp = client.delete("/api/foco/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestFocusStats:
    def test_stats(self, client):
        sessions = [
            {**SAMPLE_SESSION, "id": "s1", "tipo": "pomodoro", "duracao_minutos": 25},
            {**SAMPLE_SESSION, "id": "s2", "tipo": "pomodoro", "duracao_minutos": 25},
            {**SAMPLE_SESSION_DEEP, "id": "s3", "tipo": "deep_work", "duracao_minutos": 90},
        ]
        client.mock_supabase.set_table_data("sessoes_foco", sessions)
        resp = client.get("/api/foco/stats")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_sessoes"] == 3
        assert data["total_minutos"] == 140
        assert data["por_tipo"]["pomodoro"] == 2
        assert data["por_tipo"]["deep_work"] == 1

    def test_stats_empty(self, client):
        client.mock_supabase.set_table_data("sessoes_foco", [])
        resp = client.get("/api/foco/stats")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_sessoes"] == 0
        assert data["total_minutos"] == 0
        assert data["por_tipo"] == {}

    def test_stats_no_auth(self, client):
        resp = client.raw().get("/api/foco/stats")
        assert resp.status_code == 401
