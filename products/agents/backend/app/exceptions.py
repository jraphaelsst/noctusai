"""Product-local ``HTTPException`` handler override.

**The defect this closes.** The seed's global handler
(``noctusai_lib.primitives.exceptions.http_exception_handler``) always
overwrites the response body with ``{"error": {"code": <status-derived>,
"message": str(exc.detail)}}`` — even when ``exc.detail`` is ALREADY the
structured ``{"detail": ..., "code": ...}`` dict the seed's own
``noctusai_lib.api.auth.session.require_scopes`` raises (``scope_missing``
/ ``role_missing`` / ``product_required`` / ``user_required``). The
specific machine ``code`` is silently flattened into a stringified blob
inside ``message`` and lost — confirmed empirically (2026-09-14, this
slice) by hitting a ``require_scopes``-gated route through a real
``TestClient`` and reading the wire body; the seed's own unit tests for
``require_scopes`` never exercise this because they assert on the raised
``HTTPException.detail`` directly, before it ever reaches the app-level
handler (``seed/lib/backend/tests/api/auth/test_seed1_token_scopes.py``).

**Scope of the fix.** Contract §0 (``projects/julia-agents-academia-
CONTRACT.md``) requires EVERY error response from this product to be
exactly ``{"detail": "<pt-BR message>", "code": "<machine_code>"}`` — no
``"error"`` wrapper. Changing the seed's global envelope shape is a
platform-wide, cross-product change out of this slice's scope (an
unknown number of existing consumers may assert on the CURRENT
``{"error": {...}}`` shape) — this override is scoped to THIS product via
``app.add_exception_handler(HTTPException, ...)``, a sanctioned FastAPI
override seam, not a monkeypatch of the seed's own handler function.

**Flagged to the tech-lead** (delivery note ``drift-found:``): the
underlying seed defect affects every OTHER ``require_scopes`` consumer
too (e.g. the SW1 bridge, contract §E.6) — worth a seed-level fix in a
follow-up slice once the blast radius across the fleet is assessed.
"""
from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from noctusai_lib.primitives.exceptions import (
    http_exception_handler as seed_http_exception_handler,
)


async def agents_http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Contract §0 error envelope for a structured ``detail``; falls back
    to the seed's generic status-derived envelope otherwise (FastAPI's
    own validation-adjacent exceptions, or any plain-string ``detail``)."""
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "detail" in detail:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": detail["detail"], "code": detail["code"]},
        )
    return await seed_http_exception_handler(request, exc)


__all__ = ["agents_http_exception_handler"]
