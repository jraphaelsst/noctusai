"""`/api/imoveis/{codigo}/...` — strict `== 401`, never `in (401, 404)`.

A permissive tuple is a false-green: it passes when the route doesn't exist
at all, and it passes when validation runs before auth. Only the exact code
proves the guard fired.
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`

NAMED `test_imovel_auth_boundary`, not `test_auth_boundary`: the test
directories have no `__init__.py`, so pytest derives a module name from the
basename alone and two files called `test_auth_boundary.py` collide at
COLLECTION time — an error, not a failure, and one that only appears in a
full-suite run. The alternative (adding `__init__.py` under `tests/`) would
change package semantics for every existing suite to save a prefix here.
"""
from __future__ import annotations

from uuid import uuid4

_CODIGO = "AP1234"
_DOCUMENTO_ID = str(uuid4())


def test_every_imovel_hub_route_requires_auth(anon_client):
    """Enumerates mounted routes rather than a hand list — guards against a
    future route landing without `Depends(get_current_user_org)`."""
    from app.modules.imovel_hub import register

    paths = {
        (method.lower(), route.path)
        for router in register().routers
        for route in router.routes
        for method in getattr(route, "methods", set())
        if method.lower() in {"get", "post", "patch", "delete", "put"}
    }
    assert paths, "no imovel_hub routes are registered — the router isn't wired"

    for method, path in sorted(paths):
        concrete = path.replace("{codigo}", _CODIGO).replace(
            "{documento_id}", _DOCUMENTO_ID
        )
        kwargs = {}
        # Only PATCH takes a JSON body here. A multipart upload route must
        # NOT be sent JSON (FastAPI would reject the body shape and hand back
        # a 422 — exactly the false-green this file exists to refuse), and
        # `TestClient.delete()` has no `json` parameter at all, which is why
        # the DELETE route carries its `motivo` as a query param.
        if method == "patch":
            kwargs["json"] = {}
        resp = getattr(anon_client, method)(concrete, **kwargs)
        assert resp.status_code == 401, (
            f"{method.upper()} {concrete} -> {resp.status_code} "
            "(every imovel_hub route must require auth)"
        )
