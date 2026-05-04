"""Tests for the Goals & Habits router — /api/goals endpoints."""
from datetime import date, timedelta

from noctusai_lib.testing import MockSupabaseResponse

TOMORROW = (date.today() + timedelta(days=1)).isoformat()
TODAY = date.today().isoformat()

SAMPLE_GOAL = {
    "id": "goal-1",
    "user_id": "test-user-123",
    "org_id": "test-org-123",
    "titulo": "Ler 12 livros",
    "descricao": "Um livro por mes",
    "tipo": "meta",
    "categoria": "educacao",
    "meta_valor": 12,
    "valor_atual": 3,
    "unidade": "livros",
    "frequencia": None,
    "data_limite": TOMORROW,
    "status": "ativa",
    "created_at": "2026-01-01T00:00:00Z",
}

SAMPLE_HABIT = {
    "id": "habit-1",
    "user_id": "test-user-123",
    "org_id": "test-org-123",
    "titulo": "Meditar",
    "descricao": "10 minutos por dia",
    "tipo": "habito",
    "categoria": "saude",
    "meta_valor": None,
    "valor_atual": 15,
    "unidade": "dias",
    "frequencia": "diario",
    "data_limite": None,
    "status": "ativa",
    "created_at": "2026-01-01T00:00:00Z",
}

SAMPLE_CHECKIN = {
    "id": "checkin-1",
    "meta_id": "habit-1",
    "user_id": "test-user-123",
    "data": TODAY,
    "valor": 1.0,
    "nota": "Sessao matinal",
}


# ---------------------------------------------------------------------------
# List goals
# ---------------------------------------------------------------------------

class TestListGoals:
    def test_list_goals(self, client):
        client.mock_supabase.set_table_data("metas", [SAMPLE_GOAL, SAMPLE_HABIT])
        resp = client.get("/api/goals")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 2
        assert body["pagination"]["page"] == 1

    def test_list_goals_no_auth(self, client):
        resp = client.raw().get("/api/goals")
        assert resp.status_code == 401

    def test_list_goals_filter_tipo(self, client):
        client.mock_supabase.set_table_data("metas", [SAMPLE_HABIT])
        resp = client.get("/api/goals", params={"tipo": "habito"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 1
        assert data[0]["tipo"] == "habito"

    def test_list_goals_filter_status(self, client):
        client.mock_supabase.set_table_data("metas", [SAMPLE_GOAL])
        resp = client.get("/api/goals", params={"status": "ativa"})
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_goals_pagination(self, client):
        client.mock_supabase.set_table_data("metas", [SAMPLE_GOAL])
        resp = client.get("/api/goals", params={"page": 2, "page_size": 10})
        assert resp.status_code == 200
        body = resp.json()
        assert body["pagination"]["page"] == 2
        assert body["pagination"]["page_size"] == 10


# ---------------------------------------------------------------------------
# Create goal / habit
# ---------------------------------------------------------------------------

class TestCreateGoal:
    def test_create_goal(self, client):
        client.mock_supabase.set_table_data("metas", [SAMPLE_GOAL])
        resp = client.post("/api/goals", json={
            "titulo": "Ler 12 livros",
            "descricao": "Um livro por mes",
            "tipo": "meta",
            "categoria": "educacao",
            "meta_valor": 12,
            "unidade": "livros",
            "data_limite": TOMORROW,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["titulo"] == "Ler 12 livros"
        assert body["data"]["tipo"] == "meta"
        assert body["data"]["status"] == "ativa"

    def test_create_habit(self, client):
        client.mock_supabase.set_table_data("metas", [SAMPLE_HABIT])
        resp = client.post("/api/goals", json={
            "titulo": "Meditar",
            "tipo": "habito",
            "frequencia": "diario",
            "categoria": "saude",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["tipo"] == "habito"
        assert data["frequencia"] == "diario"

    def test_create_goal_default_tipo(self, client):
        client.mock_supabase.set_table_data("metas", [SAMPLE_GOAL])
        resp = client.post("/api/goals", json={"titulo": "Meta simples"})
        assert resp.status_code == 200

    def test_create_goal_invalid_tipo(self, client):
        resp = client.post("/api/goals", json={"titulo": "Test", "tipo": "invalido"})
        assert resp.status_code == 422

    def test_create_goal_invalid_frequencia(self, client):
        resp = client.post("/api/goals", json={
            "titulo": "Test",
            "frequencia": "quinzenal",
        })
        assert resp.status_code == 422

    def test_create_goal_empty_titulo(self, client):
        resp = client.post("/api/goals", json={"titulo": ""})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Get single goal (NOT implemented — router has no GET /{goal_id})
# ---------------------------------------------------------------------------

class TestGetGoal:
    def test_get_goal(self, client):
        """GET /api/goals/{id} returns a single goal."""
        client.mock_supabase.set_table_data("metas", SAMPLE_GOAL)
        resp = client.get("/api/goals/goal-1")
        assert resp.status_code == 200
        assert resp.json()["data"]["id"] == "goal-1"

    def test_get_goal_not_found(self, client):
        """GET /api/goals/{id} returns 404 when not found."""
        client.mock_supabase.set_table_data("metas", None)
        resp = client.get("/api/goals/goal-999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update goal
# ---------------------------------------------------------------------------

class TestUpdateGoal:
    def test_update_goal(self, client):
        updated = {**SAMPLE_GOAL, "titulo": "Ler 24 livros", "meta_valor": 24}
        client.mock_supabase.set_table_data("metas", [updated])
        resp = client.patch("/api/goals/goal-1", json={
            "titulo": "Ler 24 livros",
            "meta_valor": 24,
        })
        assert resp.status_code == 200
        assert resp.json()["data"]["titulo"] == "Ler 24 livros"

    def test_update_goal_status(self, client):
        updated = {**SAMPLE_GOAL, "status": "concluida"}
        client.mock_supabase.set_table_data("metas", [updated])
        resp = client.patch("/api/goals/goal-1", json={"status": "concluida"})
        assert resp.status_code == 200
        assert resp.json()["data"]["status"] == "concluida"

    def test_update_goal_not_found(self, client):
        client.mock_supabase.set_table_data("metas", [])
        resp = client.patch("/api/goals/nonexistent", json={"titulo": "Nada"})
        assert resp.status_code == 404

    def test_update_goal_no_fields(self, client):
        resp = client.patch("/api/goals/goal-1", json={})
        assert resp.status_code == 400
        assert "nenhum campo" in resp.json()["error"]["message"].lower()

    def test_update_goal_invalid_status(self, client):
        resp = client.patch("/api/goals/goal-1", json={"status": "invalido"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Delete goal
# ---------------------------------------------------------------------------

class TestDeleteGoal:
    def test_delete_goal(self, client):
        client.mock_supabase.set_table_data("metas", [SAMPLE_GOAL])
        resp = client.delete("/api/goals/goal-1")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert "removida" in resp.json()["message"].lower()

    def test_delete_goal_not_found(self, client):
        client.mock_supabase.set_table_data("metas", [])
        resp = client.delete("/api/goals/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Checkin endpoints
# ---------------------------------------------------------------------------

class TestCheckin:
    def test_checkin(self, client):
        """POST /api/goals/{id}/checkin — wired to seed accumulate_contribution.

        Flow (post-seed-wiring):
            1. SELECT meta_valor + valor_atual from metas (verify).
            2. INSERT checkin row.
            3. seed.accumulate_contribution(target, current, increment).
            4. UPDATE metas SET valor_atual=transition.new_current.
        """
        client.mock_supabase.set_sequential_responses("metas", [
            # 1) verify goal + read state for seed math.
            MockSupabaseResponse(data=[{
                "id": "habit-1",
                "tipo": "habito",
                "meta_valor": 30,
                "valor_atual": 14,
            }]),
            # 4) update valor_atual on metas (.update().eq().execute()).
            MockSupabaseResponse(data=[SAMPLE_HABIT]),
        ])
        client.mock_supabase.set_table_data("checkins", [SAMPLE_CHECKIN])
        resp = client.post("/api/goals/habit-1/checkin", json={
            "data": TODAY,
            "valor": 1.0,
            "nota": "Sessao matinal",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["meta_id"] == "habit-1"
        assert body["data"]["valor"] == 1.0
        assert body["data"]["nota"] == "Sessao matinal"

        # Seed math: 14 + 1.0 = 15.0 — assert via the recorded update payload.
        update_payloads = client.mock_supabase.table("metas").updated_payloads
        assert update_payloads, "expected one update on metas"
        assert update_payloads[-1]["valor_atual"] == 15.0

    def test_checkin_with_null_target_habit(self, client):
        """A pure check-yes/no habit has meta_valor=None — the seed treats
        target=0 as the boundary case. Accumulation still records the new
        valor_atual; no completion / milestone is fired.
        """
        client.mock_supabase.set_sequential_responses("metas", [
            MockSupabaseResponse(data=[{
                "id": "habit-1",
                "tipo": "habito",
                "meta_valor": None,
                "valor_atual": 5,
            }]),
            MockSupabaseResponse(data=[SAMPLE_HABIT]),
        ])
        client.mock_supabase.set_table_data("checkins", [SAMPLE_CHECKIN])
        resp = client.post("/api/goals/habit-1/checkin", json={
            "data": TODAY,
            "valor": 1.0,
        })
        assert resp.status_code == 200

        # 5 + 1 = 6, target=0 → no milestone.
        update_payloads = client.mock_supabase.table("metas").updated_payloads
        assert update_payloads[-1]["valor_atual"] == 6.0

    def test_checkin_milestone_crossing_logged(self, client, caplog):
        """Crossing a 25/50/75/100 milestone fires a logger.info — wired today
        as the audit-trail surface; future gamification + push-notification
        consumers will pick this up. See metas-domain-seed-absorption proposal
        § 2.3 (crossed_threshold_pct shipped ahead of consumer).
        """
        import logging

        client.mock_supabase.set_sequential_responses("metas", [
            # current=20, target=100 → crossing 25% with +5.
            MockSupabaseResponse(data=[{
                "id": "habit-1",
                "tipo": "habito",
                "meta_valor": 100,
                "valor_atual": 20,
            }]),
            MockSupabaseResponse(data=[SAMPLE_HABIT]),
        ])
        client.mock_supabase.set_table_data("checkins", [SAMPLE_CHECKIN])

        with caplog.at_level(logging.INFO, logger="app.services.goals_service"):
            resp = client.post("/api/goals/habit-1/checkin", json={
                "data": TODAY,
                "valor": 5.0,
            })
        assert resp.status_code == 200

        # 20 + 5 = 25 — exactly hits the 25% milestone.
        update_payloads = client.mock_supabase.table("metas").updated_payloads
        assert update_payloads[-1]["valor_atual"] == 25.0

        milestone_logs = [r for r in caplog.records if "goal_milestone_crossed" in r.getMessage()]
        assert len(milestone_logs) == 1, (
            f"expected 1 milestone log; got {[r.getMessage() for r in caplog.records]}"
        )
        assert "pct=25" in milestone_logs[0].getMessage()

    def test_checkin_goal_not_found(self, client):
        client.mock_supabase.set_table_data("metas", [])
        resp = client.post("/api/goals/nonexistent/checkin", json={
            "data": TODAY,
        })
        assert resp.status_code == 404

    def test_checkin_no_auth(self, client):
        resp = client.raw().post("/api/goals/habit-1/checkin", json={
            "data": TODAY,
        })
        assert resp.status_code == 401

    def test_list_checkins(self, client):
        client.mock_supabase.set_table_data("checkins", [SAMPLE_CHECKIN])
        resp = client.get("/api/goals/habit-1/checkins")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 1
        assert body["data"][0]["meta_id"] == "habit-1"
        assert body["pagination"]["total"] == 1

    def test_list_checkins_pagination(self, client):
        client.mock_supabase.set_table_data("checkins", [SAMPLE_CHECKIN])
        resp = client.get("/api/goals/habit-1/checkins", params={"page": 1, "page_size": 5})
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page_size"] == 5

    def test_list_checkins_no_auth(self, client):
        resp = client.raw().get("/api/goals/habit-1/checkins")
        assert resp.status_code == 401

    def test_list_checkins_empty(self, client):
        client.mock_supabase.set_table_data("checkins", [])
        resp = client.get("/api/goals/habit-1/checkins")
        assert resp.status_code == 200
        assert resp.json()["data"] == []
