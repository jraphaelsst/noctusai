"""Aditivo routes (migration 190) — strict `== 401`, never `in (401, 404|422)`.
A permissive tuple passes when the route is absent or when validation runs
before auth; only the exact code proves the guard fired.
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`
"""
from __future__ import annotations

from uuid import uuid4

_IDS = {
    "{cliente_id}": str(uuid4()),
    "{contrato_id}": str(uuid4()),
    "{aditivo_id}": str(uuid4()),
    "{versao_id}": str(uuid4()),
}

_BASE = "/api/clientes/{cliente_id}/contratos/{contrato_id}/aditivos"
_ROUTES: tuple[tuple[str, str], ...] = (
    ("get", _BASE),
    ("post", _BASE),
    ("patch", _BASE + "/{aditivo_id}"),
    ("get", _BASE + "/{aditivo_id}/geracao"),
    ("post", _BASE + "/{aditivo_id}/gerar"),
    ("get", _BASE + "/{aditivo_id}/versoes"),
    ("get", _BASE + "/{aditivo_id}/versoes/{versao_id}/url"),
    ("post", _BASE + "/{aditivo_id}/versoes/{versao_id}/revisao-juridica"),
)


def _concreto(path: str) -> str:
    for chave, valor in _IDS.items():
        path = path.replace(chave, valor)
    return path


def test_every_aditivo_route_requires_auth(anon_client):
    for method, path in _ROUTES:
        concrete = _concreto(path)
        kwargs = {"json": {}} if method in ("post", "patch") else {}
        resp = getattr(anon_client, method)(concrete, **kwargs)
        assert resp.status_code == 401, (
            f"{method.upper()} {concrete} -> {resp.status_code} (every aditivo route must require auth)"
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
