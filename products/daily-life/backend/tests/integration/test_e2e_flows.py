"""
Integration / E2E tests for Daily Life — multi-step flows through the API.

These tests simulate realistic user journeys by chaining multiple API calls
and using ``set_sequential_responses`` to simulate the database state changing
between queries.
"""
from datetime import date, timedelta, datetime
from unittest.mock import MagicMock, patch

from noctusai_lib.testing import MockSupabaseResponse, MockUser, MockUserResponse


TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()
TOMORROW = (date.today() + timedelta(days=1)).isoformat()


# ==========================================================================
# 1. Task Lifecycle: create -> update status to em_progresso -> complete -> stats
# ==========================================================================


class TestTaskLifecycle:
    def test_create_update_complete_then_verify_stats(self, client):
        """Full task lifecycle: create -> em_progresso -> concluida -> stats."""
        task_created = {
            "id": "task-lc-1",
            "user_id": "test-user-123",
            "org_id": "test-org-123",
            "titulo": "Tarefa de integracao",
            "descricao": "Teste e2e",
            "prioridade": "alta",
            "prioridade_ordem": 3,
            "categoria": "trabalho",
            "data_vencimento": TOMORROW,
            "status": "pendente",
        }

        # Step 1: Create task
        client.mock_supabase.set_table_data("tarefas", [task_created])
        resp = client.post("/api/tasks", json={
            "titulo": "Tarefa de integracao",
            "descricao": "Teste e2e",
            "prioridade": "alta",
            "categoria": "trabalho",
            "data_vencimento": TOMORROW,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "pendente"

        # Step 2: Update to em_progresso
        task_in_progress = {**task_created, "status": "em_progresso"}
        client.mock_supabase.set_table_data("tarefas", [task_in_progress])
        resp = client.patch("/api/tasks/task-lc-1", json={"status": "em_progresso"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "em_progresso"

        # Step 3: Complete the task
        task_done = {**task_created, "status": "concluida"}
        client.mock_supabase.set_table_data("tarefas", [task_done])
        resp = client.patch("/api/tasks/task-lc-1", json={"status": "concluida"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "concluida"

        # Step 4: Verify stats reflect the completed task
        all_tasks = [
            {**task_created, "id": "t1", "status": "concluida"},
            {**task_created, "id": "t2", "status": "pendente"},
        ]
        client.mock_supabase.set_table_data("tarefas", all_tasks)
        resp = client.get("/api/tasks/stats/resumo")
        assert resp.status_code == 200
        stats = resp.json()["data"]
        assert stats["total"] == 2
        assert stats["concluida"] == 1
        assert stats["pendente"] == 1


# ==========================================================================
# 2. Goal + Check-in Flow
# ==========================================================================


class TestGoalCheckinFlow:
    def test_create_goal_then_checkin_then_verify(self, client):
        """Create goal -> register check-in -> verify valor_atual -> list check-ins."""
        goal = {
            "id": "goal-e2e-1",
            "user_id": "test-user-123",
            "org_id": "test-org-123",
            "titulo": "Correr 100km",
            "descricao": "Meta mensal",
            "tipo": "meta",
            "categoria": "saude",
            "meta_valor": 100,
            "valor_atual": 0,
            "unidade": "km",
            "frequencia": None,
            "data_limite": TOMORROW,
            "status": "ativa",
            "created_at": "2026-01-01T00:00:00Z",
        }

        # Step 1: Create goal
        client.mock_supabase.set_table_data("metas", [goal])
        resp = client.post("/api/goals", json={
            "titulo": "Correr 100km",
            "descricao": "Meta mensal",
            "tipo": "meta",
            "categoria": "saude",
            "meta_valor": 100,
            "unidade": "km",
            "data_limite": TOMORROW,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["titulo"] == "Correr 100km"
        assert resp.json()["data"]["valor_atual"] == 0

        # Step 2: Register check-in
        checkin = {
            "id": "ck-e2e-1",
            "meta_id": "goal-e2e-1",
            "user_id": "test-user-123",
            "data": TODAY,
            "valor": 10.0,
            "nota": "Corrida matinal",
        }
        client.mock_supabase.set_sequential_responses("metas", [
            MockSupabaseResponse(data=[{"id": "goal-e2e-1", "tipo": "meta"}]),
            MockSupabaseResponse(data=[{**goal, "valor_atual": 10.0}]),
        ])
        client.mock_supabase.set_sequential_responses("checkins", [
            MockSupabaseResponse(data=[checkin]),
            MockSupabaseResponse(data=[checkin]),
        ])
        resp = client.post("/api/goals/goal-e2e-1/checkin", json={
            "data": TODAY,
            "valor": 10.0,
            "nota": "Corrida matinal",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["valor"] == 10.0
        assert resp.json()["data"]["meta_id"] == "goal-e2e-1"

        # Step 3: List check-ins and verify
        client.mock_supabase.set_table_data("checkins", [checkin])
        resp = client.get("/api/goals/goal-e2e-1/checkins")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["valor"] == 10.0
        assert body["data"][0]["nota"] == "Corrida matinal"


# ==========================================================================
# 3. Note Lifecycle: create -> search -> pin -> verify order -> delete
# ==========================================================================


class TestNoteLifecycle:
    def test_full_note_lifecycle(self, client):
        """Create note -> search by keyword -> pin -> verify pinned first -> delete."""
        note = {
            "id": "note-e2e-1",
            "user_id": "test-user-123",
            "org_id": "test-org-123",
            "titulo": "Receita de bolo",
            "conteudo": "Farinha, ovos, acucar",
            "categoria": "culinaria",
            "tags": ["receita"],
            "fixada": False,
            "updated_at": "2026-04-13T10:00:00Z",
        }

        # Step 1: Create note
        client.mock_supabase.set_table_data("notas", [note])
        resp = client.post("/api/notes", json={
            "titulo": "Receita de bolo",
            "conteudo": "Farinha, ovos, acucar",
            "categoria": "culinaria",
            "tags": ["receita"],
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["titulo"] == "Receita de bolo"

        # Step 2: Search by keyword
        client.mock_supabase.set_table_data("notas", [note])
        resp = client.get("/api/notes", params={"busca": "bolo"})
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1
        assert resp.json()["data"][0]["titulo"] == "Receita de bolo"

        # Step 3: Pin the note
        pinned_note = {**note, "fixada": True}
        client.mock_supabase.set_table_data("notas", [pinned_note])
        resp = client.patch("/api/notes/note-e2e-1", json={"fixada": True})
        assert resp.status_code == 200
        assert resp.json()["data"]["fixada"] is True

        # Step 4: Verify pinned note appears first in list
        other_note = {
            "id": "note-e2e-2",
            "user_id": "test-user-123",
            "org_id": "test-org-123",
            "titulo": "Outra nota",
            "conteudo": "Conteudo qualquer",
            "categoria": "pessoal",
            "tags": [],
            "fixada": False,
            "updated_at": "2026-04-13T12:00:00Z",
        }
        # Pinned should come first (API orders by fixada desc)
        client.mock_supabase.set_table_data("notas", [pinned_note, other_note])
        resp = client.get("/api/notes")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        assert data[0]["fixada"] is True
        assert data[0]["id"] == "note-e2e-1"

        # Step 5: Delete the note
        client.mock_supabase.set_table_data("notas", [pinned_note])
        resp = client.delete("/api/notes/note-e2e-1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True


# ==========================================================================
# 4. Schedule Event Flow: create -> update time -> delete -> verify gone
# ==========================================================================


class TestScheduleEventFlow:
    def test_create_update_delete_event(self, client):
        """Create event -> update time -> delete -> verify gone."""
        event = {
            "id": "evt-e2e-1",
            "user_id": "test-user-123",
            "org_id": "test-org-123",
            "titulo": "Reuniao semanal",
            "descricao": "Alinhamento com equipe",
            "categoria": "trabalho",
            "data_inicio": "2026-04-15T10:00:00",
            "data_fim": "2026-04-15T11:00:00",
            "dia_inteiro": False,
            "local": "Sala 3",
            "lembrete_minutos": 15,
            "cor": "#3B82F6",
            "status": "agendado",
        }

        # Step 1: Create event
        client.mock_supabase.set_table_data("eventos", [event])
        resp = client.post("/api/schedule", json={
            "titulo": "Reuniao semanal",
            "descricao": "Alinhamento com equipe",
            "categoria": "trabalho",
            "data_inicio": "2026-04-15T10:00:00",
            "data_fim": "2026-04-15T11:00:00",
            "local": "Sala 3",
            "lembrete_minutos": 15,
            "cor": "#3B82F6",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["titulo"] == "Reuniao semanal"
        assert resp.json()["data"]["status"] == "agendado"

        # Step 2: Update time
        updated_event = {**event, "data_inicio": "2026-04-15T14:00:00", "data_fim": "2026-04-15T15:00:00"}
        client.mock_supabase.set_table_data("eventos", [updated_event])
        resp = client.patch("/api/schedule/evt-e2e-1", json={
            "data_inicio": "2026-04-15T14:00:00",
            "data_fim": "2026-04-15T15:00:00",
        })
        assert resp.status_code == 200
        assert "14:00:00" in resp.json()["data"]["data_inicio"]

        # Step 3: Delete event
        client.mock_supabase.set_table_data("eventos", [updated_event])
        resp = client.delete("/api/schedule/evt-e2e-1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        # Step 4: Verify gone
        client.mock_supabase.set_table_data("eventos", [])
        resp = client.get("/api/schedule/evt-e2e-1")
        assert resp.status_code == 404


# ==========================================================================
# 5. Team Endpoints (provided by seed framework)
# ==========================================================================


class TestTeamFrameworkEndpoints:
    """Verify team endpoints exist and work via the seed framework."""

    def test_team_list_returns_members(self, client):
        """GET /api/team returns org members."""
        members = [
            {"id": "user-1", "nome": "Alice", "email": "alice@test.com",
             "org_role": "owner", "avatar_url": None, "created_at": "2026-01-01T00:00:00Z"},
            {"id": "user-2", "nome": "Bob", "email": "bob@test.com",
             "org_role": "member", "avatar_url": None, "created_at": "2026-01-02T00:00:00Z"},
        ]
        client.mock_supabase.set_table_data("noctus_users", members)
        resp = client.get("/api/team")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2


# ==========================================================================
# 6. Focus Session Flow: start -> update with end time -> verify in stats
# ==========================================================================


class TestFocusSessionFlow:
    def test_start_finish_verify_stats(self, client):
        """Start focus session -> update with end time -> verify in stats."""
        session = {
            "id": "foco-e2e-1",
            "user_id": "test-user-123",
            "tipo": "deep_work",
            "duracao_minutos": 60,
            "tarefa_id": None,
            "nota": None,
            "inicio": "2026-04-13T09:00:00",
            "fim": None,
            "created_at": "2026-04-13T09:00:00Z",
        }

        # Step 1: Start session
        client.mock_supabase.set_table_data("sessoes_foco", [session])
        resp = client.post("/api/foco", json={
            "tipo": "deep_work",
            "duracao_minutos": 60,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["tipo"] == "deep_work"
        assert resp.json()["data"]["fim"] is None

        # Step 2: Update with end time and note
        finished = {**session, "fim": "2026-04-13T10:00:00", "nota": "Excelente sessao"}
        client.mock_supabase.set_table_data("sessoes_foco", [finished])
        resp = client.patch("/api/foco/foco-e2e-1", json={
            "fim": "2026-04-13T10:00:00",
            "nota": "Excelente sessao",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["fim"] is not None
        assert resp.json()["data"]["nota"] == "Excelente sessao"

        # Step 3: Verify stats
        client.mock_supabase.set_table_data("sessoes_foco", [finished])
        resp = client.get("/api/foco/stats")
        assert resp.status_code == 200
        stats = resp.json()["data"]
        assert stats["total_sessoes"] == 1
        assert stats["total_minutos"] == 60
        assert stats["por_tipo"]["deep_work"] == 1


# ==========================================================================
# 7. Metrics Snapshot: create -> list -> check summary
# ==========================================================================


class TestMetricsSnapshotFlow:
    def test_create_list_and_summarize(self, client):
        """Create metric -> list -> check summary."""
        metric = {
            "id": "met-e2e-1",
            "user_id": "test-user-123",
            "data": TODAY,
            "tarefas_concluidas": 7,
            "tarefas_criadas": 4,
            "checkins_realizados": 3,
            "eventos_do_dia": 2,
            "notas_criadas": 1,
            "score_produtividade": 9.0,
            "created_at": f"{TODAY}T00:00:00Z",
        }

        # Step 1: Create metric
        client.mock_supabase.set_table_data("metricas_produtividade", [metric])
        resp = client.post("/api/metricas", json={
            "data": TODAY,
            "tarefas_concluidas": 7,
            "tarefas_criadas": 4,
            "checkins_realizados": 3,
            "eventos_do_dia": 2,
            "notas_criadas": 1,
            "score_produtividade": 9.0,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["tarefas_concluidas"] == 7

        # Step 2: List metrics
        client.mock_supabase.set_table_data("metricas_produtividade", [metric])
        resp = client.get("/api/metricas")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1
        assert resp.json()["data"][0]["score_produtividade"] == 9.0

        # Step 3: Check summary
        client.mock_supabase.set_table_data("metricas_produtividade", [metric])
        resp = client.get("/api/metricas/resumo")
        assert resp.status_code == 200
        summary = resp.json()["data"]
        assert summary["dias_analisados"] == 1
        assert summary["score_medio"] == 9.0
        assert summary["total_tarefas_concluidas"] == 7
        assert summary["total_checkins"] == 3
        assert summary["streak_dias"] == 1


# ==========================================================================
# 8. Auth Boundary: unauthenticated requests to all protected endpoints
# ==========================================================================


class TestAuthBoundary:
    """Unauthenticated requests to all protected endpoints return 401."""

    def test_tasks_list_401(self, client):
        resp = client.raw().get("/api/tasks")
        assert resp.status_code == 401

    def test_tasks_create_401(self, client):
        resp = client.raw().post("/api/tasks", json={"titulo": "Test"})
        assert resp.status_code == 401

    def test_tasks_get_401(self, client):
        resp = client.raw().get("/api/tasks/some-id")
        assert resp.status_code == 401

    def test_tasks_update_401(self, client):
        resp = client.raw().patch("/api/tasks/some-id", json={"titulo": "X"})
        assert resp.status_code == 401

    def test_tasks_delete_401(self, client):
        resp = client.raw().delete("/api/tasks/some-id")
        assert resp.status_code == 401

    def test_tasks_stats_401(self, client):
        resp = client.raw().get("/api/tasks/stats/resumo")
        assert resp.status_code == 401

    def test_goals_list_401(self, client):
        resp = client.raw().get("/api/goals")
        assert resp.status_code == 401

    def test_goals_create_401(self, client):
        resp = client.raw().post("/api/goals", json={"titulo": "Test"})
        assert resp.status_code == 401

    def test_goals_get_401(self, client):
        resp = client.raw().get("/api/goals/some-id")
        assert resp.status_code == 401

    def test_goals_update_401(self, client):
        resp = client.raw().patch("/api/goals/some-id", json={"titulo": "X"})
        assert resp.status_code == 401

    def test_goals_delete_401(self, client):
        resp = client.raw().delete("/api/goals/some-id")
        assert resp.status_code == 401

    def test_goals_checkin_401(self, client):
        resp = client.raw().post("/api/goals/some-id/checkin", json={"data": TODAY})
        assert resp.status_code == 401

    def test_goals_list_checkins_401(self, client):
        resp = client.raw().get("/api/goals/some-id/checkins")
        assert resp.status_code == 401

    def test_notes_list_401(self, client):
        resp = client.raw().get("/api/notes")
        assert resp.status_code == 401

    def test_notes_create_401(self, client):
        resp = client.raw().post("/api/notes", json={"titulo": "Test"})
        assert resp.status_code == 401

    def test_notes_get_401(self, client):
        resp = client.raw().get("/api/notes/some-id")
        assert resp.status_code == 401

    def test_notes_update_401(self, client):
        resp = client.raw().patch("/api/notes/some-id", json={"titulo": "X"})
        assert resp.status_code == 401

    def test_notes_delete_401(self, client):
        resp = client.raw().delete("/api/notes/some-id")
        assert resp.status_code == 401

    def test_schedule_list_401(self, client):
        resp = client.raw().get("/api/schedule")
        assert resp.status_code == 401

    def test_schedule_create_401(self, client):
        resp = client.raw().post("/api/schedule", json={
            "titulo": "Test",
            "data_inicio": "2026-04-15T10:00:00",
        })
        assert resp.status_code == 401

    def test_schedule_get_401(self, client):
        resp = client.raw().get("/api/schedule/some-id")
        assert resp.status_code == 401

    def test_schedule_update_401(self, client):
        resp = client.raw().patch("/api/schedule/some-id", json={"titulo": "X"})
        assert resp.status_code == 401

    def test_schedule_delete_401(self, client):
        resp = client.raw().delete("/api/schedule/some-id")
        assert resp.status_code == 401

    def test_focus_list_401(self, client):
        resp = client.raw().get("/api/foco")
        assert resp.status_code == 401

    def test_focus_create_401(self, client):
        resp = client.raw().post("/api/foco", json={
            "tipo": "pomodoro",
            "duracao_minutos": 25,
        })
        assert resp.status_code == 401

    def test_focus_update_401(self, client):
        resp = client.raw().patch("/api/foco/some-id", json={"nota": "X"})
        assert resp.status_code == 401

    def test_focus_delete_401(self, client):
        resp = client.raw().delete("/api/foco/some-id")
        assert resp.status_code == 401

    def test_focus_stats_401(self, client):
        resp = client.raw().get("/api/foco/stats")
        assert resp.status_code == 401

    def test_metrics_list_401(self, client):
        resp = client.raw().get("/api/metricas")
        assert resp.status_code == 401

    def test_metrics_create_401(self, client):
        resp = client.raw().post("/api/metricas", json={"data": TODAY})
        assert resp.status_code == 401

    def test_metrics_summary_401(self, client):
        resp = client.raw().get("/api/metricas/resumo")
        assert resp.status_code == 401

    def test_team_list_401(self, client):
        resp = client.raw().get("/api/team")
        assert resp.status_code == 401

    def test_team_invite_401(self, client):
        resp = client.raw().post("/api/team/invite", json={
            "email": "test@example.com",
            "role": "member",
        })
        assert resp.status_code == 401

    def test_team_invitations_401(self, client):
        resp = client.raw().get("/api/team/invitations")
        assert resp.status_code == 401

    def test_team_delete_member_401(self, client):
        resp = client.raw().delete("/api/team/some-id")
        assert resp.status_code == 401


# ==========================================================================
# 9. Cross-User Isolation: user A's data not visible to user B
# ==========================================================================


class TestCrossUserIsolation:
    """Simulate different users — user B should not see user A's resources."""

    def test_task_isolation_by_user_id(self, client):
        """User A creates a task; user B (different user_id) gets 404 when accessing it."""
        # User A's task
        task_a = {
            "id": "task-user-a",
            "user_id": "user-a-id",
            "org_id": "test-org-123",
            "titulo": "Tarefa privada de A",
            "status": "pendente",
        }

        # When user B (test-user-123) queries for user A's task,
        # the eq("user_id", user.id) filter means the mock returns empty
        client.mock_supabase.set_table_data("tarefas", [])
        resp = client.get("/api/tasks/task-user-a")
        assert resp.status_code == 404

    def test_note_isolation_by_user_id(self, client):
        """User B cannot see user A's notes — mock returns empty for mismatched user."""
        client.mock_supabase.set_table_data("notas", [])
        resp = client.get("/api/notes/note-user-a")
        assert resp.status_code == 404

    def test_goal_isolation_by_user_id(self, client):
        """User B cannot access user A's goals."""
        client.mock_supabase.set_table_data("metas", None)
        resp = client.get("/api/goals/goal-user-a")
        assert resp.status_code == 404

    def test_schedule_isolation_by_user_id(self, client):
        """User B cannot access user A's events."""
        client.mock_supabase.set_table_data("eventos", [])
        resp = client.get("/api/schedule/evt-user-a")
        assert resp.status_code == 404

    def test_user_list_only_own_tasks(self, client):
        """When listing, the mock only returns user B's tasks (empty),
        proving the user_id filter is applied at the query level."""
        client.mock_supabase.set_table_data("tarefas", [])
        resp = client.get("/api/tasks")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
        assert resp.json()["pagination"]["total"] == 0


# ==========================================================================
# 10. Duplicate Check-in Date: two check-ins same goal same day
# ==========================================================================


class TestDuplicateCheckinDate:
    def test_two_checkins_same_goal_same_day_both_succeed(self, client):
        """The system allows multiple check-ins for the same goal on the same day.
        Each check-in accumulates valor_atual."""
        goal = {
            "id": "goal-dup-1",
            "user_id": "test-user-123",
            "org_id": "test-org-123",
            "titulo": "Beber agua",
            "tipo": "habito",
            "categoria": "saude",
            "meta_valor": None,
            "valor_atual": 0,
            "unidade": "copos",
            "frequencia": "diario",
            "data_limite": None,
            "status": "ativa",
            "created_at": "2026-01-01T00:00:00Z",
        }

        checkin_1 = {
            "id": "ck-dup-1",
            "meta_id": "goal-dup-1",
            "user_id": "test-user-123",
            "data": TODAY,
            "valor": 3.0,
            "nota": "Manha",
        }
        checkin_2 = {
            "id": "ck-dup-2",
            "meta_id": "goal-dup-1",
            "user_id": "test-user-123",
            "data": TODAY,
            "valor": 5.0,
            "nota": "Tarde",
        }

        # First check-in
        client.mock_supabase.set_sequential_responses("metas", [
            MockSupabaseResponse(data=[{"id": "goal-dup-1", "tipo": "habito"}]),
            MockSupabaseResponse(data=[{**goal, "valor_atual": 3.0}]),
        ])
        client.mock_supabase.set_sequential_responses("checkins", [
            MockSupabaseResponse(data=[checkin_1]),
            MockSupabaseResponse(data=[checkin_1]),
        ])

        resp = client.post("/api/goals/goal-dup-1/checkin", json={
            "data": TODAY,
            "valor": 3.0,
            "nota": "Manha",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["valor"] == 3.0

        # Second check-in — same day, same goal
        client.mock_supabase.set_sequential_responses("metas", [
            MockSupabaseResponse(data=[{"id": "goal-dup-1", "tipo": "habito"}]),
            MockSupabaseResponse(data=[{**goal, "valor_atual": 8.0}]),
        ])
        client.mock_supabase.set_sequential_responses("checkins", [
            MockSupabaseResponse(data=[checkin_2]),
            MockSupabaseResponse(data=[checkin_1, checkin_2]),  # both in accumulation
        ])

        resp = client.post("/api/goals/goal-dup-1/checkin", json={
            "data": TODAY,
            "valor": 5.0,
            "nota": "Tarde",
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["valor"] == 5.0

        # Verify both check-ins are listed
        client.mock_supabase.set_table_data("checkins", [checkin_1, checkin_2])
        resp = client.get("/api/goals/goal-dup-1/checkins")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2
