"""Auth boundary for /api/campanhas.

Strict `== 401`, never `in (401, 404)`. A 404 would mean the route is
absent and the test would pass for the wrong reason; a 422 would mean
validation ran BEFORE auth, leaking the endpoint's shape to an anonymous
caller. → KB § PATTERNS/compliance/auth-boundary-false-green.md

Uses the `anon_client` fixture and the enumerate-the-router pattern from
`test_imoveis_router.py` — a hand-written route list is exactly what goes
stale when someone adds an endpoint and forgets the dependency.
"""
from __future__ import annotations

import pytest

UNAUTHENTICATED_ROUTES = [
    ("post", "/api/campanhas/solicitacoes"),
    ("get", "/api/campanhas/solicitacoes"),
    ("get", "/api/campanhas/solicitacoes/ONE10640"),
]


@pytest.mark.parametrize("method,path", UNAUTHENTICATED_ROUTES)
def test_unauthenticated_requests_are_strictly_401(anon_client, method, path):
    resp = getattr(anon_client, method)(path)
    assert resp.status_code == 401, (
        f"{method.upper()} {path} → {resp.status_code}: {resp.text}"
    )


def test_post_rejects_before_validating_the_body(anon_client):
    """An INVALID body must still 401, not 422.

    A 422 would prove validation ran first, which tells an anonymous caller
    what the endpoint expects.
    """
    resp = anon_client.post("/api/campanhas/solicitacoes", json={})
    assert resp.status_code == 401, resp.text


def test_every_campanhas_route_requires_auth(anon_client):
    """Guards against a future route landing without a dependency."""
    from app.main import app

    paths = sorted(
        {
            r.path
            for r in app.routes
            if hasattr(r, "path") and r.path.startswith("/api/campanhas")
        }
    )
    assert paths, "no /api/campanhas routes mounted — the router is not wired"

    for path in paths:
        route = next(r for r in app.routes if getattr(r, "path", None) == path)
        for method in sorted(getattr(route, "methods", set()) - {"HEAD", "OPTIONS"}):
            probe = path.replace("{codigo}", "ONE10640")
            resp = getattr(anon_client, method.lower())(probe)
            assert resp.status_code == 401, (
                f"{method} {probe} → {resp.status_code}: {resp.text}"
            )


def test_collection_and_single_routes_are_distinct(app_routes_paths):
    """`/solicitacoes` must not be shadowed by `/solicitacoes/{codigo}`.

    FastAPI matches in declaration order and a bare segment is a valid
    código, so a mis-ordered router would swallow the collection GET.
    """
    assert "/api/campanhas/solicitacoes" in app_routes_paths
    assert "/api/campanhas/solicitacoes/{codigo}" in app_routes_paths


@pytest.fixture
def app_routes_paths():
    from app.main import app

    return {r.path for r in app.routes if hasattr(r, "path")}
