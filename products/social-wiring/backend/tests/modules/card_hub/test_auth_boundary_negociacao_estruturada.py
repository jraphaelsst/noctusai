"""`/api/clientes/{cliente_id}/negociacao/{parcelas,favorecidos,
intermediarios,estruturada}` — migration 108's routes, strict `== 401`, never
`in (401, 404|422)`. A permissive tuple is a false-green: it passes when the
route doesn't exist at all, and it passes when validation runs before auth.
Only the exact code proves the guard fired.
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`

A DEDICATED file rather than folding these into `test_auth_boundary.py`
directly: this migration's engineer does not own that shared file's full
surface, and a new file cannot collide with a sibling dispatch also touching
card_hub tests. `test_auth_boundary.py`'s OWN generic sweep (which enumerates
`register().routers` and therefore already walks these routes too) got its
id-placeholder map extended in the same commit so it keeps passing — see
that file's diff.
"""
from __future__ import annotations

from uuid import uuid4

_CLIENTE_ID = str(uuid4())
_PARCELA_ID = str(uuid4())
_FAVORECIDO_ID = str(uuid4())
_INTERMEDIARIO_ID = str(uuid4())

_ROUTES: tuple[tuple[str, str], ...] = (
    ("get", "/api/clientes/{cliente_id}/negociacao/estruturada"),
    # Migration 114 — the deal's contract clauses.
    ("put", "/api/clientes/{cliente_id}/negociacao/termos"),
    ("post", "/api/clientes/{cliente_id}/negociacao/parcelas"),
    ("patch", "/api/clientes/{cliente_id}/negociacao/parcelas/{parcela_id}"),
    ("delete", "/api/clientes/{cliente_id}/negociacao/parcelas/{parcela_id}"),
    ("post", "/api/clientes/{cliente_id}/negociacao/parcelas/dividir-saldo"),
    ("post", "/api/clientes/{cliente_id}/negociacao/favorecidos"),
    ("patch", "/api/clientes/{cliente_id}/negociacao/favorecidos/{favorecido_id}"),
    ("delete", "/api/clientes/{cliente_id}/negociacao/favorecidos/{favorecido_id}"),
    ("post", "/api/clientes/{cliente_id}/negociacao/intermediarios"),
    ("patch", "/api/clientes/{cliente_id}/negociacao/intermediarios/{intermediario_id}"),
    ("delete", "/api/clientes/{cliente_id}/negociacao/intermediarios/{intermediario_id}"),
)


def test_every_negociacao_estruturada_route_requires_auth(anon_client):
    for method, path in _ROUTES:
        concrete = (
            path.replace("{cliente_id}", _CLIENTE_ID)
            .replace("{parcela_id}", _PARCELA_ID)
            .replace("{favorecido_id}", _FAVORECIDO_ID)
            .replace("{intermediario_id}", _INTERMEDIARIO_ID)
        )
        kwargs = {}
        if method in ("post", "patch"):
            kwargs["json"] = {}
        resp = getattr(anon_client, method)(concrete, **kwargs)
        assert resp.status_code == 401, (
            f"{method.upper()} {concrete} -> {resp.status_code} "
            "(every negociação estruturada route must require auth)"
        )


def test_the_new_router_is_actually_mounted():
    """Guards against the dedicated sweep above silently testing zero
    routes if `router.include_router(...)` were ever removed — every path
    in `_ROUTES` must resolve to a REAL mounted route, concrete-id 401s
    notwithstanding."""
    from app.modules.card_hub import register

    mounted = {
        (method.lower(), route.path)
        for router in register().routers
        for route in router.routes
        for method in getattr(route, "methods", set())
    }
    for method, path in _ROUTES:
        assert (method, path) in mounted, f"{method.upper()} {path} is not mounted"
