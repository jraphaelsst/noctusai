"""``create_me_router(deps)`` — ``GET /api/me/access``.

Round 2 (2026-10-06). Auto-mounted on EVERY product by ``create_product_app``
(registry key ``"me"``, appended automatically) so no product can forget the
read the seed frontend depends on:

* ``GET /api/me/access`` — auth required, deliberately NOT license-gated: it is
  how the SPA asks "may I be here?" (after login / SSO) and must answer
  ``has_access=false`` instead of 403 (the SPA then routes to ``/sem-acesso``).

Identity resolves through the ONE effective-org resolver
(:mod:`noctusai_lib.api.auth.effective_org`). (``/api/me/context`` existed only
to feed the act-as banner; it was removed with act-as-org on 2026-10-07.)

KB § PATTERNS/backend/tenancy-license-gate.md
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.api.auth.effective_org import resolve_effective_org
from noctusai_lib.domain.licensing import enforce_license, get_license_gate

logger = logging.getLogger(__name__)


def _org_dto(core_client: Any, org_id: Optional[str]) -> Optional[dict]:
    """``{"id", "nome"}`` for an org id (``None`` when no id / no row)."""
    if not org_id:
        return None
    result = (
        core_client.table("organizations")
        .select("id, nome")
        .eq("id", str(org_id))
        .limit(1)
        .execute()
    )
    rows = result.data or []
    nome = rows[0].get("nome") if rows else None
    return {"id": str(org_id), "nome": nome}


def create_me_router(deps) -> APIRouter:
    router = APIRouter(prefix="/api/me", tags=["me"])

    @router.get("/access")
    async def me_access(auth=Depends(deps.get_current_user_ungated)) -> dict:
        user, _token = auth
        core = deps.get_core_client()
        try:
            eff = resolve_effective_org(core, user.id)
        except Exception:
            logger.error("me_access_lookup_error user_id=%s", user.id, exc_info=True)
            raise HTTPException(
                status_code=503, detail="Falha ao resolver organizacao do usuario"
            )
        gate = get_license_gate()
        slug = gate.product_slug if gate else None
        has_access = False
        if eff is not None and eff.org_id:
            try:
                enforce_license(eff.org_id, eff.org_role, allow_customer=True)
                has_access = True
            except HTTPException as exc:
                if exc.status_code != 403:
                    raise
        return {
            "has_access": has_access,
            "product_slug": slug,
            "org": _org_dto(core, eff.org_id) if eff is not None else None,
        }

    return router


__all__ = ["create_me_router"]
