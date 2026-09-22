"""`/api/matriculas/*` — strict `== 401`, never `in (401, 404|422)`.

A permissive tuple is a false-green: it passes when the route doesn't exist
at all, and it passes when validation runs before auth. Only the exact code
proves the guard fired.
→ `KB § PATTERNS/compliance/auth-boundary-false-green.md`

Enumerates the MOUNTED routes rather than a hand list, so a future route
landing without `Depends(get_current_user_org)` fails here — and pins the
routes migration 109 added, so the enumeration cannot silently pass over an
empty or partial router.

Named `test_matriculas_auth_boundary`, not `test_auth_boundary`: the test
directories have no `__init__.py`, so two files with the same basename
collide at collection time.
"""
from __future__ import annotations

from uuid import uuid4

_IDS = {
    "{extracao_id}": str(uuid4()),
    "{contrato_id}": str(uuid4()),
    "{ato_id}": str(uuid4()),
    "{codigo}": "AP1234",
}
_PDF = {"file": ("matricula.pdf", b"%PDF-1.0 fake", "application/pdf")}

_ROTAS_109 = {
    ("post", "/api/matriculas/extracoes/de-documento"),
    ("get", "/api/matriculas/extracoes/{extracao_id}/atos"),
    ("get", "/api/matriculas/extracoes/{extracao_id}/fontes"),
    ("put", "/api/matriculas/extracoes/{extracao_id}/fontes"),
    ("get", "/api/matriculas/contratos/{contrato_id}/atos"),
    ("put", "/api/matriculas/contratos/{contrato_id}/atos"),
}

_ROTAS_115 = {
    ("put", "/api/matriculas/atos/{ato_id}/detalhes"),
    ("get", "/api/matriculas/imoveis/{codigo}/titulo-aquisitivo"),
    ("put", "/api/matriculas/imoveis/{codigo}/titulo-aquisitivo"),
    ("get", "/api/matriculas/imoveis/{codigo}/onus-credor"),
    ("put", "/api/matriculas/imoveis/{codigo}/onus-credor"),
    ("get", "/api/matriculas/imoveis/{codigo}/antigos-proprietarios"),
}

_ROTAS_152 = {
    ("put", "/api/matriculas/imoveis/{codigo}/ultima-transferencia"),
}


def test_every_matriculas_route_requires_auth(anon_client):
    from app.modules.matriculas import register

    paths = {
        (method.lower(), route.path)
        for router in register().routers
        for route in router.routes
        for method in getattr(route, "methods", set())
        if method.lower() in {"get", "post", "patch", "delete", "put"}
    }
    assert _ROTAS_109 <= paths, f"missing 109 routes: {_ROTAS_109 - paths}"
    assert _ROTAS_115 <= paths, f"missing 115 routes: {_ROTAS_115 - paths}"
    assert _ROTAS_152 <= paths, f"missing 152 routes: {_ROTAS_152 - paths}"

    for method, path in sorted(paths):
        concrete = path
        for marcador, valor in _IDS.items():
            concrete = concrete.replace(marcador, valor)
        kwargs = {}
        # A well-formed body on every write, so a 422 from body validation
        # can never stand in for the 401 this asserts.
        if path.endswith("/extrair"):
            kwargs["files"] = _PDF
        elif method in {"post", "put", "patch"}:
            kwargs["json"] = {}
        resp = getattr(anon_client, method)(concrete, **kwargs)
        assert resp.status_code == 401, (
            f"{method.upper()} {concrete} -> {resp.status_code} "
            "(every matriculas route must require auth)"
        )
