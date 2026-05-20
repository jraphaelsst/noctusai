"""Verify the ``media_creation`` module's ``register()`` seam wires the
expected routes into the social-wiring seed-factory app.

Catches drift in: prefix conventions, ModuleRegistration return shape,
the fact that the module exists at all.
"""
from __future__ import annotations


class TestModuleRegistration:
    def test_register_exposes_expected_route_prefixes(self, client):
        # Hit a few endpoints unauthenticated to confirm they're mounted
        # (auth rejection proves the route exists; 404 would prove it
        # doesn't). Use the raw client so the auth header is skipped.
        for path in [
            "/api/media-creation/brand-kits",
            "/api/media-creation/posts",
        ]:
            resp = client.raw().get(path)
            assert resp.status_code in (
                401,
                403,
            ), f"{path}: unexpected status {resp.status_code} — route may not be mounted"

    def test_authenticated_brand_kits_list_returns_200(self, client):
        resp = client.get("/api/media-creation/brand-kits")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "data" in body
