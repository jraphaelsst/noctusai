"""``create_me_router(deps)`` — ``/api/me/access`` + ``/api/me/context``.

Round 2 (2026-10-06). Auto-mounted on EVERY product by ``create_product_app``
(registry key ``"me"``, appended automatically) so no product can forget the
two reads the seed frontend depends on:

* ``GET /api/me/access`` — auth required, deliberately NOT license-gated: it is
  how the SPA asks "may I be here?" (after login / SSO) and must answer
  ``has_access=false`` instead of 403. Reads the EFFECTIVE org (act-as aware).
* ``GET /api/me/context`` — auth required AND license-gated like any route
  (``make_get_current_user_org`` with the default ``enforce_license=True``):
  which org the request is for, the caller's home org, and the live act-as
  session if any (drives the "Você está acessando como X" AppShell banner).

Both resolve identity through the ONE effective-org resolver
(:mod:`noctusai_lib.api.auth.effective_org`).

KB § PATTERNS/backend/tenancy-license-and-act-as.md
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from noctusai_lib.api.auth import make_get_current_user_org
from noctusai_lib.api.auth.effective_org import (
    EffectiveOrg,
    live_act_as_session,
    resolve_effective_org,
)
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


def _acting_dto(core_client: Any, user_id: Any, eff: EffectiveOrg) -> Optional[dict]:
    if not eff.acting:
        return None
    session = live_act_as_session(core_client, user_id)
    org = _org_dto(core_client, eff.org_id) or {}
    started_at = session.get("started_at") if session else None
    return {
        "session_id": str(eff.acting_session_id),
        "org_id": str(eff.org_id),
        "org_nome": org.get("nome"),
        "started_at": started_at,
    }


def create_me_router(deps) -> APIRouter:
    router = APIRouter(prefix="/api/me", tags=["me"])

    # Same resolver, full enforcement — /context is license-gated like any route.
    get_current_user_org = make_get_current_user_org(
        deps.get_current_user,
        lambda u: None,  # retired positional slot — never consulted
        get_admin_client_fn=lambda: deps.get_core_client(),
        allow_customer=True,
    )

    @router.get("/access")
    async def me_access(auth=Depends(deps.get_current_user)) -> dict:
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
            "acting": _acting_dto(core, user.id, eff) if eff is not None else None,
        }

    @router.get("/context")
    async def me_context(auth=Depends(get_current_user_org)) -> dict:
        user, _token, org_id = auth
        core = deps.get_core_client()
        eff = resolve_effective_org(core, user.id)
        return {
            "org": _org_dto(core, org_id),
            "home_org": _org_dto(core, eff.home_org_id if eff else org_id),
            "acting": _acting_dto(core, user.id, eff) if eff else None,
        }

    return router


__all__ = ["create_me_router"]
