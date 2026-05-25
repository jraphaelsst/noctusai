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
        # First execute: slug duplicate check → empty (no conflict)
        # Second execute: insert result
        mock_sb.set_table_responses("products", [
            [],
            [
                {
                    "id": "new-prod",
                    "nome": "New Product",
                    "slug": "new-prod",
                    "url_base": "http://localhost:3000",
                    "ativo": True,
                }
            ],
        ])

        resp = admin_client.post("/api/products", json={
            "nome": "New Product",
            "slug": "new-prod",
            "icone": "Box",  # required + non-empty (product-icon rule)
            "url_base": "http://localhost:3000",
        })
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["nome"] == "New Product"

    def test_create_product_forbidden_for_non_admin(self, client):
        resp = client.post("/api/products", json={
            "nome": "New Product",
            "slug": "new-prod",
            "icone": "Box",
            "url_base": "http://localhost:3000",
        })
        assert resp.status_code == 403

    def test_create_product_missing_required_fields(self, admin_client):
        resp = admin_client.post("/api/products", json={
            "nome": "Product Without URL",
        })
        assert resp.status_code == 422

    def test_create_product_rejects_empty_icone(self, admin_client):
        # A product must ship a real icon — icone is required + non-empty.
        resp = admin_client.post("/api/products", json={
            "nome": "No Icon",
            "slug": "no-icon",
            "icone": "",
            "url_base": "http://localhost:3000",
        })
        assert resp.status_code == 422

    def test_create_product_rejects_missing_icone(self, admin_client):
        resp = admin_client.post("/api/products", json={
            "nome": "No Icon",
            "slug": "no-icon",
            "url_base": "http://localhost:3000",
        })
        assert resp.status_code == 422

    def test_create_product_unauthenticated(self, unauth_client):
        resp = unauth_client.post("/api/products", json={
            "nome": "Test",
            "slug": "test",
            "icone": "Box",
            "url_base": "http://localhost:3000",
        })
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/products?include_inactive=true  (admin-only — the admin panel path)
# ---------------------------------------------------------------------------

class TestListProductsIncludeInactive:
    def test_include_inactive_requires_admin(self, client):
        """A non-admin asking for inactive rows is rejected by the admin gate."""
        resp = client.get("/api/products?include_inactive=true")
        assert resp.status_code == 403

    def test_include_inactive_unauthenticated(self, unauth_client):
        resp = unauth_client.get("/api/products?include_inactive=true")
        assert resp.status_code == 401

    def test_include_inactive_as_admin_returns_all_rows(self, admin_client):
        """Admin gets ALL rows (incl. ativo=False) so deactivated products
        stay visible + reactivatable — the admin-panel listing."""
        mock_sb = admin_client.mock_supabase
        mock_sb.set_table_data("products", [
            {"id": "prod-1", "nome": "Active", "slug": "a", "ativo": True},
            {"id": "prod-2", "nome": "Inactive", "slug": "b", "ativo": False},
        ])
        resp = admin_client.get("/api/products?include_inactive=true")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data) == 2
        assert any(p["ativo"] is False for p in data)

    def test_default_listing_still_works_for_regular_user(self, client):
        """Default (no param) stays the public catalog — any authed user."""
        mock_sb = client.mock_supabase
        mock_sb.set_table_data("products", [
            {"id": "prod-1", "nome": "Active", "slug": "a", "ativo": True},
        ])
        resp = client.get("/api/products")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 1
