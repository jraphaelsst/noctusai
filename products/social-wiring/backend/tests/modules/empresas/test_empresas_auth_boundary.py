"""`/api/empresas/...` — strict `== 401`, never `in (401, 404)`.

A permissive tuple is a false-green: it passes when the route doesn't exist
at all, and it passes when validation runs before auth. Only the exact code
proves the guard fired.
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`

NAMED `test_empresas_auth_boundary`, not `test_auth_boundary`: the test
directories have no `__init__.py`, so pytest derives a module name from the
basename alone and a second `test_auth_boundary.py` (already `card_hub`'s)
collides at COLLECTION time — same reasoning `imovel_hub`'s identically-
named file documents.

`GET/POST /api/clientes/{cliente_id}/empresas` are mounted in `card_hub`'s
OWN router and already covered by `card_hub/test_auth_boundary.py`'s
enumeration — this file covers only the SEPARATE `app.modules.empresas`
registration (`/api/empresas/*`).
"""
from __future__ import annotations

from uuid import uuid4

_EMPRESA_ID = str(uuid4())
_DOCUMENTO_ID = str(uuid4())


def test_every_empresas_route_requires_auth(anon_client):
    """Enumerates mounted routes rather than a hand list — guards against a
    future route landing without `Depends(get_current_user_org)`."""
    from app.modules.empresas import register

    paths = {
        (method.lower(), route.path)
        for router in register().routers
        for route in router.routes
        for method in getattr(route, "methods", set())
        if method.lower() in {"get", "post", "patch", "delete", "put"}
    }
    assert paths, "no empresas routes are registered — the router isn't wired"

    for method, path in sorted(paths):
        concrete = path.replace("{empresa_id}", _EMPRESA_ID).replace(
            "{documento_id}", _DOCUMENTO_ID
        )
        kwargs = {}
        # The upload route (`POST .../documentos`) is multipart — sending it
        # JSON would hit FastAPI's own body-shape rejection before auth
        # even runs, which is a false-green this file exists to refuse.
        # Every OTHER POST here takes no body at all.
        resp = getattr(anon_client, method)(concrete, **kwargs)
        assert resp.status_code == 401, (
            f"{method.upper()} {concrete} -> {resp.status_code} "
            "(every empresas route must require auth)"
        )
