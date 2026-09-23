"""F5 contract-generation routes — strict `== 401`, never `in (401, 404|422)`.
A permissive tuple passes when the route is absent or when validation runs
before auth; only the exact code proves the guard fired.
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`
"""
from __future__ import annotations

from uuid import uuid4

_CLIENTE_ID = str(uuid4())
_CONTRATO_ID = str(uuid4())

_ROUTES: tuple[tuple[str, str], ...] = (
    ("get", "/api/clientes/{cliente_id}/contratos/{contrato_id}/geracao"),
    ("post", "/api/clientes/{cliente_id}/contratos/{contrato_id}/gerar"),
    ("post", "/api/clientes/{cliente_id}/contratos/gerar"),
    # Owner decision D2 (migration 156) — the extraction validation gate.
    ("get", "/api/clientes/{cliente_id}/contratos/{contrato_id}/validacao-extracao"),
    ("post", "/api/clientes/{cliente_id}/contratos/{contrato_id}/validacao-extracao/decisoes"),
    # S2 — the card's "Proveniência" tab.
    ("get", "/api/clientes/{cliente_id}/contratos/{contrato_id}/proveniencia"),
    # S2 — the static FE-hint catalog, a SEPARATE router (`proveniencia_router`,
    # `/api/proveniencia`) — see `card_hub/proveniencia/router.py`.
    ("get", "/api/proveniencia/registro"),
)


def test_every_contrato_gerador_route_requires_auth(anon_client):
    for method, path in _ROUTES:
        concrete = path.replace("{cliente_id}", _CLIENTE_ID).replace("{contrato_id}", _CONTRATO_ID)
        kwargs = {"json": {}} if method == "post" else {}
        resp = getattr(anon_client, method)(concrete, **kwargs)
        assert resp.status_code == 401, (
            f"{method.upper()} {concrete} -> {resp.status_code} "
            "(every contract-generation route must require auth)"
        )


def test_the_routes_are_actually_mounted():
    """Guards the sweep above against silently testing zero routes."""
    from app.modules.card_hub import register

    mounted = {
        (method.lower(), route.path)
        for router in register().routers
        for route in router.routes
        for method in getattr(route, "methods", set())
    }
    for method, path in _ROUTES:
        assert (method, path) in mounted, f"{method.upper()} {path} is not mounted"
