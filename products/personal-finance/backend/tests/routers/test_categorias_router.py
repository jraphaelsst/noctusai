"""Tests for categorias (categories) router."""
import pytest


SAMPLE_CATEGORIA = {
    "id": "cat-001",
    "org_id": "test-org-123",
    "nome": "Alimentacao",
    "tipo": "despesa",
    "categoria_pai_id": None,
    "icone": "utensils",
    "cor": "#ef4444",
    "tipo_orcamento": "necessidade",
    "ordem": 1,
    "is_sistema": False,
    "created_at": "2026-01-01T10:00:00",
}

SAMPLE_SUBCATEGORIA = {
    "id": "cat-002",
    "org_id": "test-org-123",
    "nome": "Restaurantes",
    "tipo": "despesa",
    "categoria_pai_id": "cat-001",
    "icone": "pizza",
    "cor": "#f97316",
    "tipo_orcamento": "desejo",
    "ordem": 2,
    "is_sistema": False,
    "created_at": "2026-01-01T10:00:00",
}

SAMPLE_RECEITA_CAT = {
    "id": "cat-003",
    "org_id": "test-org-123",
    "nome": "Salario",
    "tipo": "receita",
    "categoria_pai_id": None,
    "icone": "wallet",
    "cor": "#22c55e",
    "tipo_orcamento": None,
    "ordem": 0,
    "is_sistema": True,
    "created_at": "2026-01-01T10:00:00",
}


class TestListarCategorias:
    def test_returns_categories_list(self, client):
        client._mock_supabase.set_table_data("categorias", [SAMPLE_CATEGORIA, SAMPLE_RECEITA_CAT])
        response = client.get("/api/categorias")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_returns_total_count(self, client):
        client._mock_supabase.set_table_data("categorias", [SAMPLE_CATEGORIA])
        response = client.get("/api/categorias")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data

    def test_filter_by_tipo(self, client):
        client._mock_supabase.set_table_data("categorias", [SAMPLE_CATEGORIA])
        response = client.get("/api/categorias?tipo=despesa")
        assert response.status_code == 200

    def test_requires_auth(self, client):
        response = client._tc.get("/api/categorias")
        assert response.status_code == 401


class TestCategoriasArvore:
    def test_returns_tree_structure(self, client):
        client._mock_supabase.set_table_data("categorias", [SAMPLE_CATEGORIA, SAMPLE_SUBCATEGORIA])
        response = client.get("/api/categorias/arvore")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert isinstance(data["data"], list)

    def test_filter_arvore_by_tipo(self, client):
        client._mock_supabase.set_table_data("categorias", [SAMPLE_CATEGORIA])
        response = client.get("/api/categorias/arvore?tipo=despesa")
        assert response.status_code == 200

    def test_requires_auth(self, client):
        response = client._tc.get("/api/categorias/arvore")
        assert response.status_code == 401


class TestObterCategoria:
    def test_returns_single_category(self, client):
        client._mock_supabase.set_table_data("categorias", [SAMPLE_CATEGORIA])
        response = client.get("/api/categorias/cat-001")
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_requires_auth(self, client):
        response = client._tc.get("/api/categorias/cat-001")
        assert response.status_code == 401


class TestCriarCategoria:
    def test_creates_category(self, client):
        client._mock_supabase.set_table_data("categorias", [SAMPLE_CATEGORIA])
        response = client.post("/api/categorias", json={
            "nome": "Alimentacao",
            "tipo": "despesa",
            "icone": "utensils",
            "cor": "#ef4444",
        })
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_creates_subcategory(self, client):
        client._mock_supabase.set_table_data("categorias", [SAMPLE_SUBCATEGORIA])
        response = client.post("/api/categorias", json={
            "nome": "Restaurantes",
            "tipo": "despesa",
            "categoria_pai_id": "cat-001",
        })
        assert response.status_code == 200

    def test_requires_nome(self, client):
        response = client.post("/api/categorias", json={
            "tipo": "despesa",
        })
        assert response.status_code == 422

    def test_validates_tipo(self, client):
        response = client.post("/api/categorias", json={
            "nome": "Teste",
            "tipo": "invalido",
        })
        assert response.status_code == 422

    def test_requires_auth(self, client):
        response = client._tc.post("/api/categorias", json={
            "nome": "Alimentacao",
            "tipo": "despesa",
        })
        assert response.status_code == 401


class TestAtualizarCategoria:
    def test_updates_category(self, client):
        updated = {**SAMPLE_CATEGORIA, "nome": "Alimentacao e Bebidas"}
        client._mock_supabase.set_table_data("categorias", [updated])
        response = client.patch("/api/categorias/cat-001", json={"nome": "Alimentacao e Bebidas"})
        assert response.status_code == 200
        data = response.json()
        assert "data" in data

    def test_empty_update_returns_400(self, client):
        response = client.patch("/api/categorias/cat-001", json={})
        assert response.status_code == 400

    def test_requires_auth(self, client):
        response = client._tc.patch("/api/categorias/cat-001", json={"nome": "Teste"})
        assert response.status_code == 401


class TestExcluirCategoria:
    def test_deletes_category(self, client):
        client._mock_supabase.set_table_data("categorias", [{"id": "cat-001"}])
        response = client.delete("/api/categorias/cat-001")
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "excluida" in data["message"]

    def test_requires_auth(self, client):
        response = client._tc.delete("/api/categorias/cat-001")
        assert response.status_code == 401
