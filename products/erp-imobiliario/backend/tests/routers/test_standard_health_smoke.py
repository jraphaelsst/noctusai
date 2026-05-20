"""Mount-smoke tests for the seed `health` standard router on ERP.

Per PROJECT §6 Phase 7 (mirrors PF lessons §d.4): every standard router
ERP mounts via `app/main.py § standard_routers=[...]` ships a per-product
smoke file that asserts the 5-test pattern: (a) route exists, (b) auth
gate, (c) happy-path 200, (d) wrong-org isolation (where applicable —
`health` is unauthenticated and product-scoped not org-scoped, so this
slot pins the product-id contract instead), (e) response shape.

`health` is unauthenticated by seed contract; this file uses
`client.raw()` to ensure the auth header doesn't mask anything.

Status-code assertions follow the `status-code-assertion-rule`
(`KB § PATTERNS/testing.md`).
"""


class TestHealthStandardRouterMountSmoke:
    """`GET /api/health` — seed `health` router (unauthenticated probe)."""

    def test_route_exists(self, client):
        """(a) /api/health is mounted — not 404."""
        resp = client.raw().get("/api/health")
        assert resp.status_code != 404

    def test_is_unauthenticated(self, client):
        """(b) Auth-gate: `health` is by-design unauthenticated. The raw
        client (no Authorization header) MUST still return 200, not 401.
        This pins the seed contract — if a future change accidentally
        adds auth to `health`, Kubernetes/Cloudflare probes break."""
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200

    def test_happy_path_returns_ok(self, client):
        """(c) Happy path: returns 200 with `status=="ok"`."""
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"

    def test_product_identifier_is_erp(self, client):
        """(d) Isolation analogue — `health` isn't org-scoped, but it
        IS product-scoped. The product field MUST be ERP's exact
        product name (matches `create_product_app(name=...)` in
        `app/main.py:42`). A regression here means a seed-side mount
        leaked another product's name into our health endpoint."""
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200
        assert resp.json()["product"] == "ERP Imobiliario"

    def test_response_shape_contract(self, client):
        """(e) Shape: response carries `status`, `version`, `product` —
        the contract `_create_health_router` builds in seed."""
        resp = client.raw().get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert {"status", "version", "product"}.issubset(body.keys())
