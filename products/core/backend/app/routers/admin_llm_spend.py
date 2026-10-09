"""Per-org LLM-spend status endpoint — Phase 18 (X4).

  - GET /api/admin/llm-spend/{org_id}    → status dict from compute_budget_status
  - PUT /api/admin/llm-spend/{org_id}/budget {monthly_brl: float}
        → upsert org_settings.monthly_llm_budget_brl

READ (owner decision 2026-10-09, "org admins see their own"): a platform
admin reads any org; an org owner/admin reads ONLY their own org. The seed's
`<LLMSpendBadge/>` polls this from every product layout for exactly that
audience (`useIsOrgAdmin`), so a platform-admin-only gate 403-toasted every
org admin fleet-wide. The PUT stays platform-admin only.
"""
from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response

from noctusai_lib.api.auth.mfa.gate import require_admin_assurance
from noctusai_lib.api.auth.platform import resolve_platform_admin_role
from noctusai_lib.api.auth.session.scopes import resolve_org_role
from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.integrations.llm.budget import compute_status
from noctusai_lib.primitives.roles import PRODUCT_ADMIN_ROLES

from app.database import get_admin_client
from app.dependencies import get_current_admin
from app.schemas.admin_llm_spend import BudgetUpdate
from app.services.trusted_auth import get_trusted_auth, get_trusted_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/llm-spend", tags=["Admin · LLM Spend"])

_ACESSO_NEGADO = {
    "detail": "Restrito aos administradores desta organização",
    "code": "org_admin_required",
}


def _normalizar_org(org_id: str) -> Optional[str]:
    try:
        return str(UUID(org_id))
    except (ValueError, AttributeError, TypeError):
        return None


async def require_spend_reader(
    org_id: str,
    request: Request,
    response: Response,
    ctx: AuthContext = Depends(get_trusted_auth),
    db: Any = Depends(get_trusted_db),
) -> str:
    """The NORMALIZED org id the caller may read spend for; 401 without a
    valid bearer (`get_trusted_auth`), 403 otherwise.

    Every role and org fact comes from the trusted `public.noctus_users` row,
    never `user_metadata` (a user can rewrite theirs). `PRODUCT_ADMIN_ROLES`
    is the same owner/admin set the FE gate (`isProductAdmin` /
    `isOrgAdmin`) uses, so the badge only ever fetches for callers this lets
    through. A malformed path id is a 403, never a 500.

    Assurance-gated like every admin gate (the old `get_current_admin` was
    too): the admin-MFA policy decides, `off` = no-op. Org owners/admins are
    in that tier by the policy's own owner decision (`ADMIN_TIER_ROLES`)."""
    alvo = _normalizar_org(org_id)
    if alvo is None:
        raise HTTPException(status_code=403, detail=_ACESSO_NEGADO)
    if resolve_platform_admin_role(db, ctx.user_id) == "admin":
        papel = "admin"
    else:
        papel = resolve_org_role(db, ctx.user_id)
        mesma_org = bool(ctx.org_id) and _normalizar_org(str(ctx.org_id)) == alvo
        if not mesma_org or papel not in PRODUCT_ADMIN_ROLES:
            raise HTTPException(status_code=403, detail=_ACESSO_NEGADO)
    await require_admin_assurance(
        request, response, caller_kind=ctx.caller_kind, aal=ctx.aal,
        user_id=ctx.user_id, org_id=ctx.org_id, role=papel,
    )
    return alvo


def get_spend_calculator() -> Callable[[str], Awaitable[dict]]:
    """DI seam for the spend computation (tests override this dependency)."""
    return compute_status


@router.get("/{org_id}")
async def get_spend_status(
    org_id: str = Depends(require_spend_reader),
    calcular: Callable[[str], Awaitable[dict]] = Depends(get_spend_calculator),
):
    """Return `{spent_brl, budget_brl, used_pct, status, soft_pct, hard_pct}`
    for the AUTHORIZED (normalized) org id."""
    status = await calcular(org_id)
    return {"data": {**status, "org_id": org_id}}


@router.put("/{org_id}/budget")
async def update_budget(
    org_id: str,
    body: BudgetUpdate,
    authorization: Optional[str] = Header(None),
):
    """Upsert `org_settings.monthly_llm_budget_brl` for the org. Pass 0 to
    clear (returns guard to fail-open / unlimited)."""
    await get_current_admin(authorization)
    db = get_admin_client()
    try:
        db.table("org_settings").upsert(
            {
                "org_id": org_id,
                "key": "monthly_llm_budget_brl",
                "value": str(body.monthly_brl),
            },
            on_conflict="org_id,key",
        ).execute()
    except Exception as e:
        logger.error("admin_llm_spend.update_budget failed for org=%s: %s", org_id, e)
        raise HTTPException(status_code=500, detail="Erro ao atualizar orçamento")
    return {"data": {"org_id": org_id, "monthly_brl": body.monthly_brl, "ok": True}}
