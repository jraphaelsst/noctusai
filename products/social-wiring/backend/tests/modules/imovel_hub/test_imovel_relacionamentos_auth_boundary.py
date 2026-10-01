"""Strict `== 401` for every route this slice adds — never `in (401, 404)`.

Enumerates the mounted routers of `imovel_hub.register()` (not a hand list), so
a future route cannot land without the guard. Named distinctly from
`test_imovel_auth_boundary` (see its note on pytest basename collisions).
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`
"""
from __future__ import annotations

from uuid import uuid4

_ID = str(uuid4())
_NOVAS = (
    "/atendimento-imoveis", "/interesses", "/propriedades", "/resumo",
    "/proprietarios", "/interessados", "/similares",
)


def _rotas_novas():
    from app.modules.imovel_hub import register

    return sorted(
        {
            (method.lower(), route.path)
            for router in register().routers
            for route in router.routes
            for method in getattr(route, "methods", set())
            if method.lower() in {"get", "post", "put", "patch", "delete"}
            and any(trecho in route.path for trecho in _NOVAS)
        }
    )


def test_the_new_routes_are_actually_mounted():
    rotas = _rotas_novas()
    # 4 + 3 + 6 + 1 + 3 (cliente/empresa propriedades are 3 each) … at least:
    assert len(rotas) >= 17, rotas
    metodos = {m for m, _ in rotas}
    assert {"get", "post", "put", "delete"} <= metodos


def test_every_new_route_requires_auth_strictly(anon_client):
    for method, path in _rotas_novas():
        concreto = (
            path.replace("{cliente_id}", _ID)
            .replace("{empresa_id}", _ID)
            .replace("{codigo}", "ONE1")
            .replace("{item_id}", _ID)
            .replace("{interesse_id}", _ID)
            .replace("{propriedade_id}", _ID)
        )
        assert "{" not in concreto, f"unhandled path param in {path}"
        kwargs = {"json": {"codigo": "ONE1"}} if method in {"post", "put"} else {}
        resp = getattr(anon_client, method)(concreto, **kwargs)
        assert resp.status_code == 401, f"{method.upper()} {concreto} -> {resp.status_code}"
