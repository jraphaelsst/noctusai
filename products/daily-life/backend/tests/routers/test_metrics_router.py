"""Tests for the Productivity Metrics router — /api/metrics endpoints."""
from datetime import date, timedelta

TODAY = date.today().isoformat()
YESTERDAY = (date.today() - timedelta(days=1)).isoformat()

SAMPLE_METRIC = {
    "id": "met-1",
    "user_id": "test-user-123",
    "data": TODAY,
    "tarefas_concluidas": 5,
    "tarefas_criadas": 3,
    "checkins_realizados": 2,
    "eventos_do_dia": 1,
    "notas_criadas": 1,
    "score_produtividade": 8.5,
    "created_at": "2026-04-13T00:00:00Z",
}

SAMPLE_METRIC_2 = {
    "id": "met-2",
    "user_id": "test-user-123",
    "data": YESTERDAY,
    "tarefas_concluidas": 3,
    "tarefas_criadas": 2,
    "checkins_realizados": 1,
    "eventos_do_dia": 2,
    "notas_criadas": 0,
    "score_produtividade": 6.0,
    "created_at": "2026-04-12T00:00:00Z",
}

SAMPLE_METRIC_ZERO = {
    "id": "met-3",
    "user_id": "test-user-123",
    "data": (date.today() - timedelta(days=2)).isoformat(),
    "tarefas_concluidas": 0,
    "tarefas_criadas": 0,
    "checkins_realizados": 0,
    "eventos_do_dia": 0,
    "notas_criadas": 0,
    "score_produtividade": None,
    "created_at": "2026-04-11T00:00:00Z",
}


# ---------------------------------------------------------------------------
# List metrics
# ---------------------------------------------------------------------------

class TestListMetrics:
    def test_list_metrics(self, client):
        client.mock_supabase.set_table_data("metricas_produtividade", [SAMPLE_METRIC, SAMPLE_METRIC_2])
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["data"]) == 2
        assert body["pagination"]["total"] == 2

    def test_list_metrics_no_auth(self, client):
        resp = client.raw().get("/api/metrics")
        assert resp.status_code == 401

    def test_list_metrics_date_filter(self, client):
        client.mock_supabase.set_table_data("metricas_produtividade", [SAMPLE_METRIC])
        resp = client.get("/api/metrics", params={
            "data_inicio": TODAY,
            "data_fim": TODAY,
        })
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1

    def test_list_metrics_pagination(self, client):
        client.mock_supabase.set_table_data("metricas_produtividade", [SAMPLE_METRIC])
        resp = client.get("/api/metrics", params={"page": 1, "page_size": 10})
        assert resp.status_code == 200
        assert resp.json()["pagination"]["page_size"] == 10

    def test_list_metrics_empty(self, client):
        client.mock_supabase.set_table_data("metricas_produtividade", [])
        resp = client.get("/api/metrics")
        assert resp.status_code == 200
        assert resp.json()["data"] == []


# ---------------------------------------------------------------------------
# Create metric
# ---------------------------------------------------------------------------

class TestCreateMetric:
    def test_create_metric(self, client):
        client.mock_supabase.set_table_data("metricas_produtividade", [SAMPLE_METRIC])
        resp = client.post("/api/metrics", json={
            "data": TODAY,
            "tarefas_concluidas": 5,
            "tarefas_criadas": 3,
            "checkins_realizados": 2,
            "eventos_do_dia": 1,
            "notas_criadas": 1,
            "score_produtividade": 8.5,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["tarefas_concluidas"] == 5
        assert body["data"]["score_produtividade"] == 8.5

    def test_create_metric_minimal(self, client):
        metric = {**SAMPLE_METRIC, "tarefas_concluidas": 0, "score_produtividade": None}
        client.mock_supabase.set_table_data("metricas_produtividade", [metric])
        resp = client.post("/api/metrics", json={"data": TODAY})
        assert resp.status_code == 200

    def test_create_metric_no_auth(self, client):
        resp = client.raw().post("/api/metrics", json={"data": TODAY})
        assert resp.status_code == 401

    def test_create_metric_missing_data(self, client):
        resp = client.post("/api/metrics", json={})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

class TestMetricsSummary:
    def test_resumo(self, client):
        # Ordered desc by data: SAMPLE_METRIC (today, 5 tarefas), SAMPLE_METRIC_2 (yesterday, 3 tarefas)
        client.mock_supabase.set_table_data("metricas_produtividade", [SAMPLE_METRIC, SAMPLE_METRIC_2])
        resp = client.get("/api/metrics/resumo")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["dias_analisados"] == 2
        assert data["score_medio"] == 7.25  # (8.5 + 6.0) / 2
        assert data["total_tarefas_concluidas"] == 8  # 5 + 3
        assert data["total_checkins"] == 3  # 2 + 1
        assert data["streak_dias"] == 2  # both days have tarefas_concluidas > 0

    def test_resumo_with_streak_break(self, client):
        # SAMPLE_METRIC (today, 5 tasks), SAMPLE_METRIC_ZERO (no activity) — streak = 1
        client.mock_supabase.set_table_data("metricas_produtividade", [SAMPLE_METRIC, SAMPLE_METRIC_ZERO])
        resp = client.get("/api/metrics/resumo")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["streak_dias"] == 1

    def test_resumo_empty(self, client):
        client.mock_supabase.set_table_data("metricas_produtividade", [])
        resp = client.get("/api/metrics/resumo")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["dias_analisados"] == 0
        assert data["score_medio"] is None
        assert data["total_tarefas_concluidas"] == 0
        assert data["streak_dias"] == 0

    def test_resumo_no_auth(self, client):
        resp = client.raw().get("/api/metrics/resumo")
        assert resp.status_code == 401

    def test_resumo_custom_dias(self, client):
        client.mock_supabase.set_table_data("metricas_produtividade", [SAMPLE_METRIC])
        resp = client.get("/api/metrics/resumo", params={"dias": 7})
        assert resp.status_code == 200
        assert resp.json()["data"]["dias_analisados"] == 1
