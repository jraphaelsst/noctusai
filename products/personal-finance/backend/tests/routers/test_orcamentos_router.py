"""Tests for orcamentos (budgets) router."""
import pytest


SAMPLE_ORCAMENTO = {
    "id": "orc-001",
    "org_id": "test-org-123",
    "nome": "Orcamento Mensal",
    "metodo": "50_30_20",
    "periodo": "mensal",
    "ativo": True,
    "created_at": "2026-01-01T10:00:00",
}

SAMPLE_ORCAMENTO_ITEM = {
    "id": "item-001",
    "orcamento_id": "orc-001",
    "categoria_id": "cat-001",
    "valor_planejado": 1500.00,
    "valor_gasto": 800.00,
    "periodo_mes": "2026-02",
    "categoria": {"id": "cat-001", "nome": "Alimentacao", "icone": "utensils", "cor": "#ef4444"},
}


class TestListarOrcamentos:
    def test_returns_budgets_list(self, client):
        client._mock_supabase.set_table_data("orcamentos", [SAMPLE_ORCAMENTO])
        response = client.get("/api/orcamentos")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_returns_total_count(self, client):
        client._mock_supabase.set_table_data("orcamentos", [SAMPLE_ORCAMENTO])
        response = client.get("/api/orcamentos")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/orcamentos")
        assert response.status_code == 401


class TestObterOrcamento:
    def test_returns_single_budget(self, client):
        client._mock_supabase.set_table_data("orcamentos", [SAMPLE_ORCAMENTO])
        response = client.get("/api/orcamentos/orc-001")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/orcamentos/orc-001")
        assert response.status_code == 401


class TestObterProgresso:
    def test_returns_progress(self, client):
        client._mock_supabase.set_table_data("orcamento_itens", [SAMPLE_ORCAMENTO_ITEM])
        response = client.get("/api/orcamentos/orc-001/progresso?periodo_mes=2026-02")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_periodo_mes(self, client):
        response = client.get("/api/orcamentos/orc-001/progresso")
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.get("/api/orcamentos/orc-001/progresso?periodo_mes=2026-02")
        assert response.status_code == 401


class TestListarItens:
    def test_returns_items(self, client):
        client._mock_supabase.set_table_data("orcamento_itens", [SAMPLE_ORCAMENTO_ITEM])
        response = client.get("/api/orcamentos/orc-001/itens")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_filter_by_periodo_mes(self, client):
        client._mock_supabase.set_table_data("orcamento_itens", [SAMPLE_ORCAMENTO_ITEM])
        response = client.get("/api/orcamentos/orc-001/itens?periodo_mes=2026-02")
        assert response.status_code == 200

    def test_requires_auth(self, client):
        response = client._tc.get("/api/orcamentos/orc-001/itens")
        assert response.status_code == 401


class TestCriarOrcamento:
    def test_creates_budget(self, client):
        client._mock_supabase.set_table_data("orcamentos", [SAMPLE_ORCAMENTO])
        response = client.post("/api/orcamentos", json={
            "nome": "Orcamento Mensal",
            "metodo": "50_30_20",
            "periodo": "mensal",
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_creates_budget_with_items(self, client):
        client._mock_supabase.set_table_data("orcamentos", [SAMPLE_ORCAMENTO])
        client._mock_supabase.set_table_data("orcamento_itens", [SAMPLE_ORCAMENTO_ITEM])
        response = client.post("/api/orcamentos", json={
            "nome": "Orcamento Mensal",
            "metodo": "zero_based",
            "itens": [
                {
                    "categoria_id": "cat-001",
                    "valor_planejado": 1500.00,
                    "periodo_mes": "2026-02",
                }
            ],
        })
        assert response.status_code == 200

    def test_requires_nome(self, client):
        response = client.post("/api/orcamentos", json={
            "metodo": "50_30_20",
        })
        assert response.status_code == 422

    def test_validates_metodo(self, client):
        response = client.post("/api/orcamentos", json={
            "nome": "Teste",
            "metodo": "invalido",
        })
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/orcamentos", json={
            "nome": "Orcamento Mensal",
        })
        assert response.status_code == 401


class TestAtualizarOrcamento:
    def test_updates_budget(self, client):
        updated = {**SAMPLE_ORCAMENTO, "nome": "Orcamento Atualizado"}
        client._mock_supabase.set_table_data("orcamentos", [updated])
        response = client.patch("/api/orcamentos/orc-001", json={"nome": "Orcamento Atualizado"})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_empty_update_returns_400(self, client):
        response = client.patch("/api/orcamentos/orc-001", json={})
        assert response.status_code == 400

    def test_requires_auth(self, client):
        response = client._tc.patch("/api/orcamentos/orc-001", json={"nome": "Teste"})
        assert response.status_code == 401


class TestExcluirOrcamento:
    def test_deletes_budget(self, client):
        client._mock_supabase.set_table_data("orcamentos", [{"id": "orc-001", "org_id": "test-org-123"}])
        response = client.delete("/api/orcamentos/orc-001")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "excluido" in data["message"]

    def test_requires_auth(self, client):
        response = client._tc.delete("/api/orcamentos/orc-001")
        assert response.status_code == 401


class TestCriarItem:
    def test_creates_budget_item(self, client):
        client._mock_supabase.set_table_data("orcamento_itens", [SAMPLE_ORCAMENTO_ITEM])
        response = client.post("/api/orcamentos/orc-001/itens", json={
            "categoria_id": "cat-001",
            "valor_planejado": 1500.00,
            "periodo_mes": "2026-02",
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_categoria_id(self, client):
        response = client.post("/api/orcamentos/orc-001/itens", json={
            "valor_planejado": 1500.00,
            "periodo_mes": "2026-02",
        })
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/orcamentos/orc-001/itens", json={
            "categoria_id": "cat-001",
            "valor_planejado": 1500.00,
            "periodo_mes": "2026-02",
        })
        assert response.status_code == 401


class TestAtualizarItem:
    def test_updates_item(self, client):
        updated = {**SAMPLE_ORCAMENTO_ITEM, "valor_planejado": 2000.00}
        client._mock_supabase.set_table_data("orcamento_itens", [updated])
        response = client.patch("/api/orcamentos/itens/item-001", json={"valor_planejado": 2000.00})
        assert response.status_code == 200

    def test_requires_auth(self, client):
        response = client._tc.patch("/api/orcamentos/itens/item-001", json={"valor_planejado": 2000.00})
        assert response.status_code == 401


class TestExcluirItem:
    def test_deletes_item(self, client):
        client._mock_supabase.set_table_data("orcamento_itens", [SAMPLE_ORCAMENTO_ITEM])
        response = client.delete("/api/orcamentos/itens/item-001")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True

    def test_returns_404_when_not_found(self, client):
        client._mock_supabase.set_table_data("orcamento_itens", [])
        response = client.delete("/api/orcamentos/itens/nonexistent")
        assert response.status_code == 404
        body = response.json()
        assert body["error"]["code"] == "NOT_FOUND"
        assert "Item" in body["error"]["message"] or "item" in body["error"]["message"]

    def test_actually_removes_row_from_shared_list(self, client):
        client._mock_supabase.set_table_data("orcamento_itens", [SAMPLE_ORCAMENTO_ITEM])
        response = client.delete("/api/orcamentos/itens/item-001")
        assert response.status_code == 200
        # MockFilterBuilder mutates the shared list in place on .delete().
        builder = client._mock_supabase.table("orcamento_itens")
        assert all(row.get("id") != "item-001" for row in builder._data)

    def test_requires_auth(self, client):
        response = client._tc.delete("/api/orcamentos/itens/item-001")
        assert response.status_code == 401
