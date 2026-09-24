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
_EXTRA_ID = str(uuid4())
_PARTE_ID = str(uuid4())
_ROTEIRO_ID = str(uuid4())
_VISITA_ID = str(uuid4())
_CONTRATO_ID = str(uuid4())
_VERSAO_ID = str(uuid4())
#: Migration 108 — negociação estruturada (parcelas/favorecidos/
#: intermediários), mounted via `negociacao_estruturada_router.router`.
_PARCELA_ID = str(uuid4())
_FAVORECIDO_ID = str(uuid4())
_INTERMEDIARIO_ID = str(uuid4())
#: Migration 167 — the empresas/PJ-due-diligence link (slice D).
_EMPRESA_ID = str(uuid4())
#: Migration 170 — Certidões matriz per-card custom rows.
_LINHA_ID = str(uuid4())

#: Multipart-upload routes — their last path segment is a literal (no
#: trailing id), same shape `.../financiamento/documentos` and
#: `.../documentos` already have. A JSON body sent here would target the
#: wrong content-type for a route expecting `File(...)`/`Form(...)`; auth
#: fires first regardless (see the loop below), but matching the real
#: request shape keeps this test honest about what each route expects.
_MULTIPART_UPLOAD_LAST_SEGMENTS = {"documentos", "contratos", "versoes"}


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
            .replace("{extra_id}", _EXTRA_ID)
            .replace("{parte_id}", _PARTE_ID)
            .replace("{roteiro_id}", _ROTEIRO_ID)
            .replace("{visita_id}", _VISITA_ID)
            .replace("{contrato_id}", _CONTRATO_ID)
            .replace("{versao_id}", _VERSAO_ID)
            .replace("{parcela_id}", _PARCELA_ID)
            .replace("{favorecido_id}", _FAVORECIDO_ID)
            .replace("{intermediario_id}", _INTERMEDIARIO_ID)
            .replace("{empresa_id}", _EMPRESA_ID)
            .replace("{linha_id}", _LINHA_ID)
        )
        kwargs = {}
        # Checked on the LAST segment only (not the last two, which is what
        # the original single-string "documentos" check did): a multipart
        # upload route always TERMINATES in its literal segment name (no
        # trailing id), while e.g. `PATCH .../contratos/{contrato_id}` has
        # "contratos" as its second-to-last segment and must still get a
        # JSON body.
        last_segment = concrete.rstrip("/").split("/")[-1]
        if (
            method in ("post", "patch", "put")
            and last_segment not in _MULTIPART_UPLOAD_LAST_SEGMENTS
        ):
            kwargs["json"] = {}
        resp = getattr(anon_client, method)(concrete, **kwargs)
        assert resp.status_code == 401, (
            f"{method.upper()} {concrete} -> {resp.status_code} "
            "(every card_hub route must require auth)"
        )
