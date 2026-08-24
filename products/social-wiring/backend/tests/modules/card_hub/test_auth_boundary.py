"""`/api/clientes/...` (card_hub surface) — strict `== 401`, never
`in (401, 404)`. A permissive tuple is a false-green: it passes when the
route doesn't exist at all, and it passes when validation runs before
auth. Only the exact code proves the guard fired.
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`
"""
from __future__ import annotations

from uuid import uuid4

import pytest

_CLIENTE_ID = str(uuid4())
_TAG_ID = str(uuid4())
_NOTA_ID = str(uuid4())
_CHECKLIST_ID = str(uuid4())
_ITEM_ID = str(uuid4())
_DOCUMENTO_ID = str(uuid4())
_PARTE_ID = str(uuid4())


def test_every_card_hub_route_requires_auth(anon_client):
    """Enumerates mounted routes rather than a hand list — guards against a
    future route landing without `Depends(get_current_user_org)`."""
    from app.modules.card_hub import register

    paths = {
        (method.lower(), route.path)
        for router in register().routers
        for route in router.routes
        for method in getattr(route, "methods", set())
        if method.lower() in {"get", "post", "patch", "delete", "put"}
    }
    assert paths, "no card_hub routes are registered — the router isn't wired"

    for method, path in sorted(paths):
        concrete = (
            path.replace("{cliente_id}", _CLIENTE_ID)
            .replace("{tag_id}", _TAG_ID)
            .replace("{nota_id}", _NOTA_ID)
            .replace("{checklist_id}", _CHECKLIST_ID)
            .replace("{item_id}", _ITEM_ID)
            .replace("{documento_id}", _DOCUMENTO_ID)
            .replace("{parte_id}", _PARTE_ID)
        )
        kwargs = {}
        if method in ("post", "patch", "put") and "documentos" not in concrete.split("/")[-2:]:
            kwargs["json"] = {}
        resp = getattr(anon_client, method)(concrete, **kwargs)
        assert resp.status_code == 401, (
            f"{method.upper()} {concrete} -> {resp.status_code} "
            "(every card_hub route must require auth)"
        )
