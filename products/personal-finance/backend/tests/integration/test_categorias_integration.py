"""Integration tests for Categorias — CRUD cycles and tree building."""
import pytest


class TestCategoriasCRUDCycle:
    def test_full_crud_cycle(self, integration_client):
        c = integration_client

        # Create
        resp = c.post("/api/categorias", json={
            "nome": "Alimentacao",
            "tipo": "despesa",
            "icone": "utensils",
            "cor": "#ef4444",
        })
        assert resp.status_code == 200
        cat = resp.json()["data"]
        cat_id = cat["id"]

        # Read single
        resp = c.get(f"/api/categorias/{cat_id}")
        assert resp.status_code == 200

        # List
        resp = c.get("/api/categorias")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1

        # Update
        resp = c.patch(f"/api/categorias/{cat_id}", json={"nome": "Alimentacao e Bebidas"})
        assert resp.status_code == 200

        # Delete
        resp = c.delete(f"/api/categorias/{cat_id}")
        assert resp.status_code == 200


class TestCategoriasTree:
    def test_tree_with_parent_and_children(self, integration_client):
        c = integration_client

        # Create parent
        resp = c.post("/api/categorias", json={
            "nome": "Moradia",
            "tipo": "despesa",
        })
        parent_id = resp.json()["data"]["id"]

        # Create children
        c.post("/api/categorias", json={
            "nome": "Aluguel",
            "tipo": "despesa",
            "categoria_pai_id": parent_id,
        })
        c.post("/api/categorias", json={
            "nome": "Condominio",
            "tipo": "despesa",
            "categoria_pai_id": parent_id,
        })

        resp = c.get("/api/categorias/arvore")
        assert resp.status_code == 200
        tree = resp.json()["data"]
        # Parent should have 2 subcategorias
        parent = next((n for n in tree if n["id"] == parent_id), None)
        assert parent is not None
        assert len(parent["subcategorias"]) == 2


class TestCategoriasValidation:
    def test_invalid_tipo_rejected(self, integration_client):
        resp = integration_client.post("/api/categorias", json={
            "nome": "Invalida",
            "tipo": "invalido",
        })
        assert resp.status_code == 422

    def test_empty_nome_rejected(self, integration_client):
        resp = integration_client.post("/api/categorias", json={
            "nome": "",
            "tipo": "despesa",
        })
        assert resp.status_code == 422
