"""
Tests for Products Router.

GET   /api/products
GET   /api/products/{id}
POST  /api/products       (admin only)
"""
import pytest


# ---------------------------------------------------------------------------
# GET /api/products
# ---------------------------------------------------------------------------

class TestListProducts:
    def test_list_products_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("products", [
            {"id": "prod-1", "nome": "ERP Imobiliario", "slug": "erp", "ativo": True},
            {"id": "prod-2", "nome": "CRM", "slug": "crm", "ativo": True},
        ])

        resp = client.get("/api/products")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 2

    def test_list_products_empty(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("products", [])

        resp = client.get("/api/products")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_list_products_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/products")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/products/{id}
# ---------------------------------------------------------------------------

class TestGetProduct:
    def test_get_product_success(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("products", {
            "id": "prod-1",
            "nome": "ERP Imobiliario",
            "slug": "erp",
            "url_base": "http://localhost:8080",
        })

        resp = client.get("/api/products/prod-1")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["id"] == "prod-1"

    def test_get_product_not_found(self, client):
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("products", None)

        resp = client.get("/api/products/nonexistent")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/products (admin only)
# ---------------------------------------------------------------------------

class TestCreateProduct:
    def test_create_product_as_admin(self, admin_client):
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("products", [
            {
                "id": "new-prod",
                "nome": "New Product",
                "slug": "new-prod",
                "url_base": "http://localhost:3000",
                "ativo": True,
            }
        ])

        resp = admin_client.post("/api/products", json={
            "nome": "New Product",
            "slug": "new-prod",
            "url_base": "http://localhost:3000",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["nome"] == "New Product"

    def test_create_product_forbidden_for_non_admin(self, client):
        resp = client.post("/api/products", json={
            "nome": "New Product",
            "slug": "new-prod",
            "url_base": "http://localhost:3000",
        })
        assert resp.status_code == 403

    def test_create_product_missing_required_fields(self, admin_client):
        resp = admin_client.post("/api/products", json={
            "nome": "Product Without URL",
        })
        assert resp.status_code == 422

    def test_create_product_unauthenticated(self, unauth_client):
        resp = unauth_client.post("/api/products", json={
            "nome": "Test",
            "slug": "test",
            "url_base": "http://localhost:3000",
        })
        assert resp.status_code == 401
