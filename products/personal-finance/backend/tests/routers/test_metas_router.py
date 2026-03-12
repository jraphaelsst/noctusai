"""Tests for metas (financial goals) router."""
import pytest


SAMPLE_META = {
    "id": "meta-001",
    "org_id": "test-org-123",
    "nome": "Fundo de Emergencia",
    "tipo": "fundo_emergencia",
    "valor_alvo": 30000.00,
    "valor_atual": 15000.00,
    "data_alvo": "2026-12-31",
    "conta_vinculada_id": "conta-002",
    "prioridade": "alta",
    "status": "ativa",
    "icone": "shield",
    "cor": "#22c55e",
    "created_at": "2026-01-01T10:00:00",
}

SAMPLE_META_2 = {
    "id": "meta-002",
    "org_id": "test-org-123",
    "nome": "Viagem Europa",
    "tipo": "poupanca",
    "valor_alvo": 20000.00,
    "valor_atual": 5000.00,
    "data_alvo": "2027-06-30",
    "conta_vinculada_id": None,
    "prioridade": "media",
    "status": "ativa",
    "icone": "plane",
    "cor": "#3b82f6",
    "created_at": "2026-01-15T10:00:00",
}

SAMPLE_CONTRIBUICAO = {
    "id": "contrib-001",
    "meta_id": "meta-001",
    "valor": 500.00,
    "data": "2026-02-15",
    "fonte": "manual",
    "transacao_id": None,
    "notas": "Aporte mensal",
}


class TestListarMetas:
    def test_returns_goals_list(self, client):
        client._mock_supabase.set_table_data("metas", [SAMPLE_META, SAMPLE_META_2])
        response = client.get("/api/metas")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_returns_total_count(self, client):
        client._mock_supabase.set_table_data("metas", [SAMPLE_META])
        response = client.get("/api/metas")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("metas", [SAMPLE_META])
        response = client.get("/api/metas?status=ativa")
        assert response.status_code == 200

    def test_requires_auth(self, client):
        response = client._tc.get("/api/metas")
        assert response.status_code == 401


class TestObterMeta:
    def test_returns_single_goal(self, client):
        client._mock_supabase.set_table_data("metas", [SAMPLE_META])
        response = client.get("/api/metas/meta-001")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/metas/meta-001")
        assert response.status_code == 401


class TestObterProgresso:
    def test_returns_progress_data(self, client):
        client._mock_supabase.set_table_data("metas", [SAMPLE_META])
        client._mock_supabase.set_table_data("meta_contribuicoes", [SAMPLE_CONTRIBUICAO])
        response = client.get("/api/metas/meta-001/progresso")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/metas/meta-001/progresso")
        assert response.status_code == 401


class TestCriarMeta:
    def test_creates_goal(self, client):
        client._mock_supabase.set_table_data("metas", [SAMPLE_META])
        response = client.post("/api/metas", json={
            "nome": "Fundo de Emergencia",
            "tipo": "fundo_emergencia",
            "valor_alvo": 30000.00,
            "prioridade": "alta",
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_creates_goal_with_date(self, client):
        client._mock_supabase.set_table_data("metas", [SAMPLE_META])
        response = client.post("/api/metas", json={
            "nome": "Viagem",
            "tipo": "poupanca",
            "valor_alvo": 20000.00,
            "data_alvo": "2027-06-30",
        })
        assert response.status_code == 200

    def test_requires_nome(self, client):
        response = client.post("/api/metas", json={
            "tipo": "poupanca",
            "valor_alvo": 10000.00,
        })
        assert response.status_code == 422

    def test_requires_tipo(self, client):
        response = client.post("/api/metas", json={
            "nome": "Meta",
            "valor_alvo": 10000.00,
        })
        assert response.status_code == 422

    def test_validates_tipo(self, client):
        response = client.post("/api/metas", json={
            "nome": "Meta",
            "tipo": "invalido",
            "valor_alvo": 10000.00,
        })
        assert response.status_code == 422

    def test_valor_alvo_must_be_positive(self, client):
        response = client.post("/api/metas", json={
            "nome": "Meta",
            "tipo": "poupanca",
            "valor_alvo": -1000.00,
        })
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/metas", json={
            "nome": "Meta",
            "tipo": "poupanca",
            "valor_alvo": 10000.00,
        })
        assert response.status_code == 401


class TestAtualizarMeta:
    def test_updates_goal(self, client):
        updated = {**SAMPLE_META, "nome": "Fundo Atualizado"}
        client._mock_supabase.set_table_data("metas", [updated])
        response = client.patch("/api/metas/meta-001", json={"nome": "Fundo Atualizado"})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_updates_status(self, client):
        updated = {**SAMPLE_META, "status": "concluida"}
        client._mock_supabase.set_table_data("metas", [updated])
        response = client.patch("/api/metas/meta-001", json={"status": "concluida"})
        assert response.status_code == 200

    def test_empty_update_returns_400(self, client):
        response = client.patch("/api/metas/meta-001", json={})
        assert response.status_code == 400

    def test_requires_auth(self, client):
        response = client._tc.patch("/api/metas/meta-001", json={"nome": "Teste"})
        assert response.status_code == 401


class TestExcluirMeta:
    def test_deletes_goal(self, client):
        client._mock_supabase.set_table_data("metas", [{"id": "meta-001", "org_id": "test-org-123"}])
        response = client.delete("/api/metas/meta-001")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "excluida" in data["message"]

    def test_requires_auth(self, client):
        response = client._tc.delete("/api/metas/meta-001")
        assert response.status_code == 401


class TestAdicionarContribuicao:
    def test_adds_contribution(self, client):
        client._mock_supabase.set_table_data("meta_contribuicoes", [SAMPLE_CONTRIBUICAO])
        client._mock_supabase.set_table_data("metas", [SAMPLE_META])
        response = client.post("/api/metas/meta-001/contribuicao", json={
            "valor": 500.00,
            "data": "2026-02-15",
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_contribution_with_notes(self, client):
        client._mock_supabase.set_table_data("meta_contribuicoes", [SAMPLE_CONTRIBUICAO])
        client._mock_supabase.set_table_data("metas", [SAMPLE_META])
        response = client.post("/api/metas/meta-001/contribuicao", json={
            "valor": 1000.00,
            "data": "2026-02-20",
            "fonte": "manual",
            "notas": "Bonus recebido",
        })
        assert response.status_code == 200

    def test_valor_must_be_positive(self, client):
        response = client.post("/api/metas/meta-001/contribuicao", json={
            "valor": -100.00,
            "data": "2026-02-15",
        })
        assert response.status_code == 422

    def test_requires_data(self, client):
        response = client.post("/api/metas/meta-001/contribuicao", json={
            "valor": 500.00,
        })
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/metas/meta-001/contribuicao", json={
            "valor": 500.00,
            "data": "2026-02-15",
        })
        assert response.status_code == 401
