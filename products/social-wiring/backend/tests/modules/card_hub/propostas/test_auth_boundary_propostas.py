"""Proposta routes — strict `== 401`, never a permissive tuple.
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`"""
from __future__ import annotations

from uuid import uuid4

_CLIENTE_ID = str(uuid4())
_PROPOSTA_ID = str(uuid4())

_BASE = "/api/clientes/{cliente_id}/propostas"
_ROUTES: tuple[tuple[str, str, dict], ...] = (
    ("get", _BASE, {}),
    ("post", _BASE, {"imovel_codigo": "ONE1"}),
    ("get", _BASE + "/{proposta_id}", {}),
    ("patch", _BASE + "/{proposta_id}", {"observacoes": "x"}),
    ("post", _BASE + "/{proposta_id}/enviar", {}),
    ("post", _BASE + "/{proposta_id}/recusar", {"motivo": "caro"}),
    ("post", _BASE + "/{proposta_id}/aceitar", {}),
    ("post", _BASE + "/{proposta_id}/pos-aceite", {}),
    ("delete", _BASE + "/{proposta_id}", {}),
)


def test_every_proposta_route_requires_auth(anon_client):
    for method, path, body in _ROUTES:
        concrete = path.replace("{cliente_id}", _CLIENTE_ID).replace("{proposta_id}", _PROPOSTA_ID)
        kwargs = {"json": body} if method in {"post", "patch"} else {}
        resp = getattr(anon_client, method)(concrete, **kwargs)
        assert resp.status_code == 401, f"{method.upper()} {concrete} -> {resp.status_code}"


def test_the_routes_are_actually_mounted():
    from app.modules.card_hub import register

    mounted = {
        (method.lower(), route.path)
        for router in register().routers
        for route in router.routes
        for method in getattr(route, "methods", set())
    }
    for method, path, _body in _ROUTES:
        assert (method, path.replace("{cliente_id}", "{cliente_id}")) in mounted, path
