"""`/api/certidoes/...` — strict `== 401`, never `in (401, 404, 422)`.

A permissive tuple is a false-green: it passes when the route doesn't exist
at all, and it passes when validation runs before auth. Only the exact code
proves the guard fired.
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`

Mirrors `tests/modules/imovel_hub/test_imovel_auth_boundary.py`: routes are
ENUMERATED from `app.modules.certidoes.register()` rather than hand-listed,
so a future route landing without `Depends(get_current_user_org)` is caught
even if nobody remembers to add it here.

NAMED `test_certidoes_auth_boundary`, not `test_auth_boundary` — the test
directories have no `__init__.py`, so pytest derives a module name from the
basename alone and two files called `test_auth_boundary.py` collide at
COLLECTION time.

🔴 The certidões router is NOT yet wired into `app/main.py`'s `MODULES`
(pre-integration slice — see `app/modules/certidoes/__init__.py`'s own
docstring). `tests/modules/test_certidoes_router.py` mounts it onto the
shared `app.main.app` object IN-MEMORY at collection time; this file does
the SAME mount so it is independently runnable (`pytest
tests/modules/test_certidoes_auth_boundary.py` alone) rather than silently
depending on that other file having been collected first. Including the
same `APIRouter` instance twice in one session (the common case, both files
collected together) is a harmless no-op duplication of `app.routes` — every
duplicate entry answers identically, because it is the same route object.
"""
from __future__ import annotations

from uuid import uuid4

from app.main import app as _app
from app.modules.certidoes.routers import certidoes as _certidoes_router_mod

_app.include_router(_certidoes_router_mod.router)

_CONSULTA_ID = "consulta-001"
_RESULTADO_ID = "resultado-001"
_PARTE_ID = str(uuid4())
_CLIENTE_ID = str(uuid4())


def test_every_certidoes_route_requires_auth(anon_client):
    """Enumerates mounted routes rather than a hand list — guards against a
    future route landing without `Depends(get_current_user_org)`."""
    from app.modules.certidoes import register

    paths = {
        (method.lower(), route.path)
        for router in register().routers
        for route in router.routes
        for method in getattr(route, "methods", set())
        if method.lower() in {"get", "post", "patch", "delete", "put"}
    }
    assert paths, "no certidoes routes are registered — the router isn't wired"

    for method, path in sorted(paths):
        concrete = (
            path.replace("{consulta_id}", _CONSULTA_ID)
            .replace("{resultado_id}", _RESULTADO_ID)
            .replace("{atendimento_parte_id}", _PARTE_ID)
            .replace("{cliente_id}", _CLIENTE_ID)
        )
        kwargs = {}
        # PATCH and the two POST-with-a-JSON-body routes need a body;
        # `/resultados/{id}/upload` is a multipart UploadFile route and must
        # NOT be sent JSON (FastAPI would reject the body shape and hand
        # back a 422 — exactly the false-green this file exists to refuse).
        if method in ("patch", "post") and "/upload" not in concrete:
            kwargs["json"] = {}
        resp = getattr(anon_client, method)(concrete, **kwargs)
        assert resp.status_code == 401, (
            f"{method.upper()} {concrete} -> {resp.status_code} "
            "(every certidoes route must require auth)"
        )
