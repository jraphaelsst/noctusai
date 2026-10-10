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


# ---------------------------------------------------------------------------
# Non-admin reads project an explicit column allowlist (no operational leak)
# ---------------------------------------------------------------------------

_FULL_ROW = {
    "id": "prod-1", "nome": "ERP", "slug": "erp", "descricao": "d", "icone": "Building2",
    "url_base": "https://erp.noctusai.com", "cor": "#111111", "ativo": True,
    "deploy_scope": "live", "logout_behavior": "redirect", "created_at": "2026-01-01",
    "house_port": 8001, "sso_callback_verified_at": "2026-10-01T00:00:00Z",
    "db_schema": "erp", "aceita_clientes": False,
}
_LEAKS = ("house_port", "sso_callback_verified_at", "db_schema", "aceita_clientes")
_FE_FIELDS = ("id", "nome", "slug", "descricao", "icone", "url_base", "cor",
              "ativo", "deploy_scope", "logout_behavior", "created_at")


def _project_selects(mock_sb):
    """Make the test double honour `.select("a, b")` column lists like PostgREST
    (MockSupabaseClient returns whole rows). Wraps the double's own `table`; the
    app code under test is untouched. Returns the list of recorded select args."""
    recorded: list[str] = []
    orig_table = mock_sb.table

    class _Proj:
        def __init__(self, builder):
            self._b = builder

        def select(self, cols="*", *a, **kw):
            recorded.append(cols)
            b = self._b.select(cols, *a, **kw)
            if cols.strip() == "*":
                return b
            keep = {c.strip() for c in cols.split(",")}
            orig_exec = b.execute

            def execute(*ea, **ekw):
                r = orig_exec(*ea, **ekw)
                if isinstance(r.data, list):
                    r.data = [{k: v for k, v in row.items() if k in keep} for row in r.data]
                elif isinstance(r.data, dict):
                    r.data = {k: v for k, v in r.data.items() if k in keep}
                return r

            b.execute = execute
            return b

        def __getattr__(self, name):
            return getattr(self._b, name)

    mock_sb.table = lambda name, *a, **kw: _Proj(orig_table(name, *a, **kw)) if name == "products" else orig_table(name, *a, **kw)
    return recorded


class TestNonAdminColumnProjection:
    def test_constant_excludes_leaks_and_covers_fe(self):
        from app.schemas.products import PRODUCT_PUBLIC_COLUMNS
        cols = {c.strip() for c in PRODUCT_PUBLIC_COLUMNS.split(",")}
        assert not cols & set(_LEAKS)
        assert set(_FE_FIELDS) <= cols

    def test_list_hides_operational_columns(self, client):
        client.mock_supabase.set_table_data("products", [dict(_FULL_ROW)])
        _project_selects(client.mock_supabase)
        row = client.get("/api/products").json()["data"][0]
        for k in _LEAKS:
            assert k not in row
        for k in _FE_FIELDS:
            assert k in row

    def test_detail_hides_operational_columns(self, client):
        client.mock_supabase.set_table_data("products", dict(_FULL_ROW))
        _project_selects(client.mock_supabase)
        row = client.get("/api/products/prod-1").json()["data"]
        for k in _LEAKS:
            assert k not in row
        for k in _FE_FIELDS:
            assert k in row

    def test_admin_list_keeps_full_row(self, admin_client):
        admin_client.mock_supabase.set_table_data("products", [dict(_FULL_ROW)])
        _project_selects(admin_client.mock_supabase)
        row = admin_client.get("/api/products?include_inactive=true").json()["data"][0]
        assert row["house_port"] == 8001
