"""
Auth-boundary tests for the /api/clients router.

Every protected endpoint MUST return exactly 401 (not 404/422) when
called without a valid auth token. Strict == 401 per KB § PATTERNS/
compliance/auth-boundary-false-green.md.

The public capture endpoint is tested separately (test_crm_router.py).
"""
import pytest


PROTECTED_CALLS = [
    ("GET",  "/api/clients"),
    ("POST", "/api/clients"),
    ("GET",  "/api/clients/some-id"),
    ("PATCH", "/api/clients/some-id"),
    ("POST", "/api/clients/some-id/archive"),
]


class TestClientsRouterAuth:
    """Every /api/clients endpoint requires authentication."""

    def test_list_clients_without_auth_returns_401(self, client):
        resp = client.raw().get("/api/clients")
        assert resp.status_code == 401

    def test_create_client_without_auth_returns_401(self, client):
        resp = client.raw().post("/api/clients", json={"name": "x"})
        assert resp.status_code == 401

    def test_get_client_without_auth_returns_401(self, client):
        resp = client.raw().get("/api/clients/some-id")
        assert resp.status_code == 401

    def test_update_client_without_auth_returns_401(self, client):
        resp = client.raw().patch("/api/clients/some-id", json={"name": "x"})
        assert resp.status_code == 401

    def test_archive_client_without_auth_returns_401(self, client):
        resp = client.raw().post("/api/clients/some-id/archive")
        assert resp.status_code == 401


class TestClientsRouterValidation:
    """Pydantic validation fires before the service layer."""

    def test_create_with_empty_name_returns_422(self, client):
        resp = client.post("/api/clients", json={"name": ""})
        assert resp.status_code == 422

    def test_create_with_due_date_out_of_range_returns_422(self, client):
        resp = client.post("/api/clients", json={"name": "Valid", "due_date": 32})
        assert resp.status_code == 422

    def test_create_with_negative_monthly_value_returns_422(self, client):
        resp = client.post("/api/clients", json={"name": "Valid", "monthly_value": -1})
        assert resp.status_code == 422

    def test_create_with_extra_field_returns_422(self, client):
        """extra='forbid' on StrictHttpModel — unknown fields → 422."""
        resp = client.post("/api/clients", json={"name": "Valid", "unknown_field": "x"})
        assert resp.status_code == 422

    def test_list_with_invalid_page_size_returns_422(self, client):
        resp = client.get("/api/clients?page_size=999")
        assert resp.status_code == 422
