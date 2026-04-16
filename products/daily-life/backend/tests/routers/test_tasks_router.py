"""Tests for the Tasks router — /api/tasks endpoints."""
from datetime import date, timedelta

from noctusai_lib.testing import MockSupabaseResponse

TOMORROW = (date.today() + timedelta(days=1)).isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()

SAMPLE_TASK = {
    "id": "task-1",
    "user_id": "test-user-123",
    "org_id": "test-org-123",
    "titulo": "Comprar leite",
    "descricao": "Leite integral",
    "prioridade": "alta",
    "prioridade_ordem": 3,
    "categoria": "compras",
    "data_vencimento": TOMORROW,
    "status": "pendente",
}

SAMPLE_TASK_2 = {
    "id": "task-2",
    "user_id": "test-user-123",
    "org_id": "test-org-123",
    "titulo": "Estudar Python",
    "descricao": None,
    "prioridade": "media",
    "prioridade_ordem": 2,
    "categoria": "trabalho",
    "data_vencimento": None,
    "status": "em_progresso",
}


# ---------------------------------------------------------------------------
# List tasks
# ---------------------------------------------------------------------------

class TestListTasks:
    def test_list_tasks(self, client):
        client.mock_supabase.set_table_data("tarefas", [SAMPLE_TASK, SAMPLE_TASK_2])
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 2
        assert body["pagination"]["page"] == 1
        assert body["pagination"]["page_size"] == 20

    def test_list_tasks_no_auth(self, client):
        resp = client.raw().get("/api/tasks")
        assert resp.status_code == 401

    def test_list_tasks_filter_status(self, client):
        client.mock_supabase.set_table_data("tarefas", [SAMPLE_TASK])
        resp = client.get("/api/tasks", params={"status": "pendente"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["status"] == "pendente"

    def test_list_tasks_filter_prioridade(self, client):
        client.mock_supabase.set_table_data("tarefas", [SAMPLE_TASK])
        resp = client.get("/api/tasks", params={"prioridade": "alta"})
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_tasks_filter_categoria(self, client):
        client.mock_supabase.set_table_data("tarefas", [SAMPLE_TASK_2])
        resp = client.get("/api/tasks", params={"categoria": "trabalho"})
        assert resp.status_code == 200
        assert resp.json()["data"][0]["categoria"] == "trabalho"

    def test_list_tasks_pagination(self, client):
        client.mock_supabase.set_table_data("tarefas", [SAMPLE_TASK])
        resp = client.get("/api/tasks", params={"page": 2, "page_size": 5})
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page"] == 2
        assert body["pagination"]["page_size"] == 5

    def test_list_tasks_empty(self, client):
        client.mock_supabase.set_table_data("tarefas", [])
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
        assert resp.json()["pagination"]["total"] == 0


# ---------------------------------------------------------------------------
# Create task
# ---------------------------------------------------------------------------

class TestCreateTask:
    def test_create_task(self, client):
        client.mock_supabase.set_table_data("tarefas", [SAMPLE_TASK])
        resp = client.post("/api/tasks", json={
            "titulo": "Comprar leite",
            "descricao": "Leite integral",
            "prioridade": "alta",
            "categoria": "compras",
            "data_vencimento": TOMORROW,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["titulo"] == "Comprar leite"
        assert body["data"]["prioridade"] == "alta"
        assert body["data"]["prioridade_ordem"] == 3

    def test_create_task_default_prioridade(self, client):
        task_with_default = {**SAMPLE_TASK, "prioridade": "media", "prioridade_ordem": 2}
        client.mock_supabase.set_table_data("tarefas", [task_with_default])
        resp = client.post("/api/tasks", json={"titulo": "Tarefa simples"})
        assert resp.status_code == 200

    def test_create_task_validates_prioridade(self, client):
        resp = client.post("/api/tasks", json={
            "titulo": "Test",
            "prioridade": "invalida",
        })
        assert resp.status_code == 422

    def test_create_task_validates_titulo_empty(self, client):
        resp = client.post("/api/tasks", json={"titulo": ""})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Get single task
# ---------------------------------------------------------------------------

class TestGetTask:
    def test_get_task(self, client):
        client.mock_supabase.set_table_data("tarefas", [SAMPLE_TASK])
        resp = client.get("/api/tasks/task-1")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["id"] == "task-1"
        assert body["data"]["titulo"] == "Comprar leite"

    def test_get_task_not_found(self, client):
        client.mock_supabase.set_table_data("tarefas", [])
        resp = client.get("/api/tasks/nonexistent")
        assert resp.status_code == 404
        assert "nao encontrada" in resp.json()["error"]["message"].lower()


# ---------------------------------------------------------------------------
# Update task
# ---------------------------------------------------------------------------

class TestUpdateTask:
    def test_update_task(self, client):
        updated = {**SAMPLE_TASK, "titulo": "Comprar leite desnatado"}
        client.mock_supabase.set_table_data("tarefas", [updated])
        resp = client.patch("/api/tasks/task-1", json={"titulo": "Comprar leite desnatado"})
        assert resp.status_code == 200
        assert resp.json()["data"]["titulo"] == "Comprar leite desnatado"

    def test_update_task_status(self, client):
        updated = {**SAMPLE_TASK, "status": "concluida"}
        client.mock_supabase.set_table_data("tarefas", [updated])
        resp = client.patch("/api/tasks/task-1", json={"status": "concluida"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "concluida"

    def test_update_task_not_found(self, client):
        client.mock_supabase.set_table_data("tarefas", [])
        resp = client.patch("/api/tasks/nonexistent", json={"titulo": "Nada"})
        assert resp.status_code == 404

    def test_update_task_no_fields(self, client):
        resp = client.patch("/api/tasks/task-1", json={})
        assert resp.status_code == 400
        assert "nenhum campo" in resp.json()["error"]["message"].lower()

    def test_update_task_invalid_status(self, client):
        resp = client.patch("/api/tasks/task-1", json={"status": "invalido"})
        assert resp.status_code == 422

    def test_update_task_prioridade_updates_ordem(self, client):
        updated = {**SAMPLE_TASK, "prioridade": "baixa", "prioridade_ordem": 1}
        client.mock_supabase.set_table_data("tarefas", [updated])
        resp = client.patch("/api/tasks/task-1", json={"prioridade": "baixa"})
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Delete task
# ---------------------------------------------------------------------------

class TestDeleteTask:
    def test_delete_task(self, client):
        client.mock_supabase.set_table_data("tarefas", [SAMPLE_TASK])
        resp = client.delete("/api/tasks/task-1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert "removida" in resp.json()["message"].lower()

    def test_delete_task_not_found(self, client):
        client.mock_supabase.set_table_data("tarefas", [])
        resp = client.delete("/api/tasks/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

class TestTaskStats:
    def test_task_stats(self, client):
        tasks = [
            {**SAMPLE_TASK, "id": "t1", "status": "pendente"},
            {**SAMPLE_TASK, "id": "t2", "status": "pendente"},
            {**SAMPLE_TASK, "id": "t3", "status": "concluida"},
            {**SAMPLE_TASK, "id": "t4", "status": "em_progresso"},
        ]
        client.mock_supabase.set_table_data("tarefas", tasks)
        resp = client.get("/api/tasks/stats/resumo")
        assert resp.status_code == 200
        stats = resp.json()["data"]
        assert stats["total"] == 4
        assert stats["pendente"] == 2
        assert stats["concluida"] == 1
        assert stats["em_progresso"] == 1
        assert stats["cancelada"] == 0

    def test_task_stats_empty(self, client):
        client.mock_supabase.set_table_data("tarefas", [])
        resp = client.get("/api/tasks/stats/resumo")
        assert resp.status_code == 200
        stats = resp.json()["data"]
        assert stats["total"] == 0

    def test_task_stats_no_auth(self, client):
        resp = client.raw().get("/api/tasks/stats/resumo")
        assert resp.status_code == 401
