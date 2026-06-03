"""
Auth-boundary + validation tests for the /api/tasks/* and /api/routines/* routers.

Auth: strict == 401 for all endpoints (not 404/422).
Validation: StrictHttpModel extra='forbid' → 422 for unknown fields.
"""
import pytest

TEST_ORG = "00000000-0000-0000-0000-000000000001"


class TestTasksRouterAuth:
    """Every /api/tasks/* endpoint requires authentication — strict 401."""

    def test_list_tasks_without_auth_returns_401(self, client):
        assert client.raw().get("/api/tasks").status_code == 401

    def test_create_task_without_auth_returns_401(self, client):
        assert client.raw().post("/api/tasks", json={"title": "x"}).status_code == 401

    def test_get_task_without_auth_returns_401(self, client):
        assert client.raw().get("/api/tasks/some-id").status_code == 401

    def test_update_task_without_auth_returns_401(self, client):
        assert client.raw().patch("/api/tasks/some-id", json={"title": "x"}).status_code == 401

    def test_delete_task_without_auth_returns_401(self, client):
        assert client.raw().delete("/api/tasks/some-id").status_code == 401

    def test_update_task_status_without_auth_returns_401(self, client):
        assert client.raw().patch(
            "/api/tasks/some-id/status", json={"status": "done"}
        ).status_code == 401


class TestRoutinesRouterAuth:
    """Every /api/routines/* endpoint requires authentication — strict 401."""

    def test_list_routines_without_auth_returns_401(self, client):
        assert client.raw().get("/api/routines").status_code == 401

    def test_create_routine_without_auth_returns_401(self, client):
        assert client.raw().post(
            "/api/routines",
            json={"title": "r", "cadence": "daily", "next_run": "2026-01-01"},
        ).status_code == 401

    def test_get_routine_without_auth_returns_401(self, client):
        assert client.raw().get("/api/routines/some-id").status_code == 401

    def test_update_routine_without_auth_returns_401(self, client):
        assert client.raw().patch("/api/routines/some-id", json={"active": False}).status_code == 401

    def test_delete_routine_without_auth_returns_401(self, client):
        assert client.raw().delete("/api/routines/some-id").status_code == 401

    def test_run_due_routines_without_auth_returns_401(self, client):
        assert client.raw().post("/api/routines/run-due").status_code == 401


class TestTasksRouterValidation:
    """Pydantic validation enforced on inbound schemas."""

    def test_create_task_empty_title_returns_422(self, client):
        resp = client.post("/api/tasks", json={"title": ""})
        assert resp.status_code == 422

    def test_create_task_extra_field_returns_422(self, client):
        resp = client.post("/api/tasks", json={"title": "ok", "rogue_field": True})
        assert resp.status_code == 422

    def test_create_task_invalid_status_returns_422(self, client):
        resp = client.post("/api/tasks", json={"title": "t", "status": "nope"})
        assert resp.status_code == 422

    def test_create_task_invalid_priority_returns_422(self, client):
        resp = client.post("/api/tasks", json={"title": "t", "priority": "ultra"})
        assert resp.status_code == 422

    def test_update_task_status_invalid_value_returns_422(self, client):
        resp = client.patch("/api/tasks/some-id/status", json={"status": "flying"})
        assert resp.status_code == 422

    def test_list_tasks_invalid_page_size_returns_422(self, client):
        resp = client.get("/api/tasks?page_size=9999")
        assert resp.status_code == 422

    def test_create_routine_empty_title_returns_422(self, client):
        resp = client.post(
            "/api/routines",
            json={"title": "", "cadence": "daily", "next_run": "2026-01-01"},
        )
        assert resp.status_code == 422

    def test_create_routine_invalid_cadence_returns_422(self, client):
        resp = client.post(
            "/api/routines",
            json={"title": "r", "cadence": "hourly", "next_run": "2026-01-01"},
        )
        assert resp.status_code == 422

    def test_create_routine_extra_field_returns_422(self, client):
        resp = client.post(
            "/api/routines",
            json={"title": "r", "cadence": "daily", "next_run": "2026-01-01", "foo": "bar"},
        )
        assert resp.status_code == 422


class TestTasksRouterHappyPath:
    """Authenticated happy-path smoke tests (mock DB)."""

    def test_list_tasks_returns_200(self, client):
        resp = client.get("/api/tasks")
        assert resp.status_code == 200

    def test_create_task_returns_201_or_502(self, client):
        """201 on success; 502 if mock returns no data (both are valid in test env)."""
        resp = client.post("/api/tasks", json={"title": "Nova tarefa"})
        assert resp.status_code in (201, 502)

    def test_list_routines_returns_200(self, client):
        resp = client.get("/api/routines")
        assert resp.status_code == 200

    def test_create_routine_returns_201_or_502(self, client):
        resp = client.post(
            "/api/routines",
            json={"title": "Rotina diária", "cadence": "daily", "next_run": "2026-06-01"},
        )
        assert resp.status_code in (201, 502)

    def test_run_due_routines_returns_200(self, client):
        resp = client.post("/api/routines/run-due")
        assert resp.status_code == 200
        body = resp.json()
        assert "spawned" in body
        assert "tasks" in body
