"""`/api/edicao-fotos/...` — strict `== 401` unauthenticated, and the
contract §1 role matrix as `403`s.

The 401 sweep ENUMERATES the mounted routes from `register()` rather than a
hand list, so a future route landing without the auth dependency fails here.
The role matrix below is asserted complete against the same enumeration.
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`
"""
from __future__ import annotations

from uuid import uuid4

import pytest

from app.modules.edicao_fotos import register

_ID = str(uuid4())


def _routes() -> set[tuple[str, str]]:
    return {
        (method.lower(), route.path)
        for router in register().routers
        for route in router.routes
        for method in getattr(route, "methods", set())
        if method.lower() in {"get", "post", "put", "patch", "delete"}
    }


def _concrete(path: str) -> str:
    return path.replace("{lote_id}", _ID).replace("{foto_id}", _ID).replace("{user_id}", _ID)


def test_module_is_mounted_on_the_app() -> None:
    from app.main import app

    mounted = {getattr(r, "path", "") for r in app.routes}
    assert {path for _m, path in _routes()} <= mounted


def test_every_route_requires_auth(anon_client) -> None:
    routes = _routes()
    assert len(routes) == 19, sorted(routes)
    for method, path in sorted(routes):
        # No body at all: a JSON body on the multipart route (or a missing
        # one on a JSON route) must not be what decides the status.
        resp = getattr(anon_client, method)(_concrete(path))
        assert resp.status_code == 401, f"{method.upper()} {path} -> {resp.status_code}"


# (method, path, body, forbidden user) — one row per route.
_FORBIDDEN = [
    ("get", "/api/edicao-fotos/capacidades", None, "viewer"),
    ("get", "/api/edicao-fotos/configuracoes", None, "viewer"),
    ("put", "/api/edicao-fotos/configuracoes", {}, "corretor"),
    ("get", "/api/edicao-fotos/configuracoes/plataforma", None, "admin"),
    ("put", "/api/edicao-fotos/configuracoes/plataforma", {}, "admin"),
    ("get", "/api/edicao-fotos/curadores", None, "admin"),
    ("post", "/api/edicao-fotos/curadores", {"user_id": _ID}, "admin"),
    ("delete", "/api/edicao-fotos/curadores/{user_id}", None, "curador"),
    ("get", "/api/edicao-fotos/modelos", None, "viewer"),
    ("get", "/api/edicao-fotos/lotes", None, "viewer"),
    ("post", "/api/edicao-fotos/lotes", {"nome": "x"}, "viewer"),
    ("get", "/api/edicao-fotos/lotes/{lote_id}", None, "viewer"),
    ("post", "/api/edicao-fotos/lotes/{lote_id}/fotos", "files", "curador"),
    ("post", "/api/edicao-fotos/lotes/{lote_id}/vista", {"codigo": "CA1"}, "viewer"),
    ("post", "/api/edicao-fotos/lotes/{lote_id}/submeter", None, "viewer"),
    ("post", "/api/edicao-fotos/lotes/{lote_id}/fotos/{foto_id}/retentar", None, "viewer"),
    ("get", "/api/edicao-fotos/lotes/{lote_id}/zip", None, "viewer"),
    ("get", "/api/edicao-fotos/revisao/{lote_id}", None, "viewer"),
    ("post", "/api/edicao-fotos/revisao/{lote_id}/fotos/{foto_id}/decisao",
     {"decisao": "aprovar"}, "curador"),
]


def test_role_matrix_covers_every_route() -> None:
    assert {(m, p) for m, p, _b, _u in _FORBIDDEN} == _routes()


@pytest.mark.parametrize("method,path,body,user", _FORBIDDEN, ids=lambda v: str(v))
def test_role_matrix_denies(edicao, method, path, body, user) -> None:
    edicao.as_user(user)
    kwargs = {}
    if body == "files":
        kwargs["files"] = [("fotos", ("a.jpg", b"x", "image/jpeg"))]
    elif body is not None:
        kwargs["json"] = body
    resp = getattr(edicao.http, method)(_concrete(path), **kwargs)
    assert resp.status_code == 403, f"{method.upper()} {path} as {user} -> {resp.status_code} {resp.text}"
    assert resp.json()["code"] in {
        "sem_acesso_edicao_fotos",
        "restrito_admin_organizacao",
        "restrito_admin_plataforma",
    }


def test_product_token_caller_is_refused(edicao) -> None:
    """A caller with no user id (product token) never reaches the surface."""
    from types import SimpleNamespace

    from app.dependencies import get_current_user_org

    edicao.app.dependency_overrides[get_current_user_org] = lambda: (
        SimpleNamespace(id=None, user_metadata={}), "pk_token", "test-org-123"
    )
    resp = edicao.http.get("/api/edicao-fotos/lotes")
    assert resp.status_code == 403
    assert resp.json()["code"] == "usuario_obrigatorio"
