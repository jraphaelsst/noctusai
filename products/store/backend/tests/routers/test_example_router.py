"""
Tests for the example router skeleton.

These tests verify the **canonical shape** every scaffolded product
inherits — the auth dep is wired correctly, the routes are reachable,
and request validation kicks in. They DO NOT exercise list/create
business logic because the placeholder service raises NotImplementedError
on purpose (TODO markers for the new product to fill in).

Every assertion pins ``response.status_code`` per the keeper-detector
rule (``check_test_status_assertion``) so a 4xx/5xx wouldn't slip past
a substring-only body check.
"""
import pytest


class TestExampleRouterAuth:
    """The canonical Depends(get_current_user_org) shape rejects unauth'd."""

    def test_list_without_auth_returns_401(self, client):
        resp = client.raw().get("/api/example")
        assert resp.status_code == 401

    def test_create_without_auth_returns_401(self, client):
        resp = client.raw().post("/api/example", json={"title": "x"})
        assert resp.status_code == 401


class TestExampleRouterValidation:
    """Pydantic validation fires before the placeholder service."""

    def test_create_with_empty_title_returns_422(self, client):
        # Auth'd but title violates min_length=1 — Pydantic rejects.
        resp = client.post("/api/example", json={"title": ""})
        assert resp.status_code == 422

    def test_create_with_oversized_title_returns_422(self, client):
        # title max_length=200 in schemas/example.py.
        resp = client.post("/api/example", json={"title": "x" * 201})
        assert resp.status_code == 422

    def test_list_with_invalid_limit_returns_422(self, client):
        # limit le=200 — Query validator rejects 999.
        resp = client.get("/api/example?limit=999")
        assert resp.status_code == 422


# NOTE: The full CRUD *body* logic (list/get/create/update/soft-delete)
# is exercised at the service level in
# ``tests/services/test_example_service.py`` — data-seeded
# ``MockSupabaseClient`` + ``inserted_payloads``/``updated_payloads``
# assertions, no monkeypatching. These router tests pin the canonical
# auth + validation contract every scaffolded product inherits; the
# service tests pin the page-scoped-CRUD behavior. Together they are the
# product-internal-wiring reference. (Router body tests via the `client`
# fixture would need the fixture's mock seeded with `seed.examples`
# rows; the service-level tests cover the same logic more directly.)
# TODO(new-product): rename `example` → your domain in both files.
