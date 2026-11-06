"""Platform admin: the MFA-to-mint-tokens switch and the service accounts a token can belong to.

GET  /api/admin/tokens/settings          -> {"data": {"mfa_required": bool}}
PUT  /api/admin/tokens/settings          -> same; platform admins only
GET  /api/admin/tokens/service-accounts  -> {"data": [{id, slug, name, description}]}

Minting / rotating / revoking / listing tokens themselves is the seed router
(``/api/settings/api-tokens`` -- see ``app.auth_context``).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.api.schemas import StrictHttpModel

from app.services import api_tokens
from app.services.trusted_auth import get_trusted_db, require_platform_admin_dep

router = APIRouter(prefix="/api/admin/tokens", tags=["Admin · Tokens"], include_in_schema=False)


class TokenSettingsBody(StrictHttpModel):
    mfa_required: bool


@router.get("/settings")
async def get_token_settings(
    _: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    return {"data": {"mfa_required": await run_blocking(api_tokens.read_mfa_required, db)}}


@router.put("/settings")
async def put_token_settings(
    body: TokenSettingsBody,
    ctx: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    required = await run_blocking(
        api_tokens.write_mfa_required, db, body.mfa_required, str(ctx.user_id) if ctx.user_id else None
    )
    return {"data": {"mfa_required": required}}


@router.get("/service-accounts")
async def get_service_accounts(
    _: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    return {"data": await run_blocking(api_tokens.list_service_accounts, db)}
