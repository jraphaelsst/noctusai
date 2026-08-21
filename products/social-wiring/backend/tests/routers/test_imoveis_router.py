"""`/api/imoveis` — auth boundary + route-ordering.

**Strict `== 401`, never `in (401, 404)`.** A permissive tuple is a
false-green: it passes when the route doesn't exist at all, and it passes
when validation runs before auth (which leaks whether a resource exists to
an unauthenticated caller). Only the exact code proves the guard fired.
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`

The route-ordering test is the other one worth reading. `/{codigo}` is a
bare path segment, so FastAPI — which matches in declaration order — will
happily route `/api/imoveis/sync` into `get_imovel(codigo="sync")` if the
parameterized route is declared first. That failure is invisible in review
and only shows up as "the sync button 404s".
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import (  # type: ignore[attr-defined]
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)


# `anon_client` now lives in tests/conftest.py — it was needed by a
# second auth-boundary suite (campanhas) and a per-suite copy is how one
# of them quietly drifts into passing.


UNAUTHENTICATED_ROUTES = [
    ("get", "/api/imoveis"),
    ("get", "/api/imoveis/filtros"),
    ("get", "/api/imoveis/caracteristicas"),
    ("get", "/api/imoveis/ONE10640"),
    ("post", "/api/imoveis/sync"),
]


@pytest.mark.parametrize("method,path", UNAUTHENTICATED_ROUTES)
def test_unauthenticated_requests_are_strictly_401(anon_client, method, path):
    resp = getattr(anon_client, method)(path)
    assert resp.status_code == 401, f"{method.upper()} {path} → {resp.status_code}: {resp.text}"


def test_every_imoveis_route_requires_auth(anon_client):
    """Guards against a future route being added without a dependency.

    Enumerates the mounted routes rather than a hand-written list — a
    hand-written list is exactly what goes stale when someone adds
    `/api/imoveis/export` and forgets `Depends(get_current_user_org)`.
    """
    from app.main import app

    paths = {
        (method.lower(), route.path)
        for route in app.routes
        if getattr(route, "path", "").startswith("/api/imoveis")
        for method in getattr(route, "methods", set())
        if method.lower() in {"get", "post", "patch", "delete"}
    }
    assert paths, "no /api/imoveis routes are mounted — the router isn't wired"

    for method, path in sorted(paths):
        # Substitute a concrete value for any path parameter.
        concrete = path.replace("{codigo}", "ONE10640")
        resp = getattr(anon_client, method)(concrete)
        assert resp.status_code == 401, (
            f"{method.upper()} {concrete} → {resp.status_code} "
            "(every /api/imoveis route must require auth)"
        )


def test_router_is_mounted(anon_client):
    from app.main import app

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/imoveis" in paths
    assert "/api/imoveis/sync" in paths
    assert "/api/imoveis/{codigo}" in paths


def test_static_routes_are_declared_before_the_catch_all():
    """`/{codigo}` must come LAST or it shadows `/sync` and `/filtros`.

    FastAPI matches in declaration order, and "sync" is a perfectly valid
    `codigo`. Declared wrong, POST /api/imoveis/sync would 405 and
    GET /api/imoveis/filtros would look up an imóvel called "filtros" —
    both of which read as data bugs, not routing bugs.
    """
    from app.routers.imoveis_router import router

    # `router.routes` carries the full prefixed path, e.g. `/api/imoveis/sync`.
    paths = [getattr(r, "path", "") for r in router.routes]
    catch_all = next(i for i, p in enumerate(paths) if "{codigo}" in p)
    for static in ("/api/imoveis/filtros", "/api/imoveis/caracteristicas", "/api/imoveis/sync"):
        assert static in paths, f"{static} is not declared at all"
        assert paths.index(static) < catch_all, (
            f"{static} is declared after /{{codigo}} and will be shadowed"
        )
