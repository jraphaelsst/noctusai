"""
Public SSO entry router -- the product identity behind core's central login.

GET /api/sso/produto/{slug} -- {slug, nome, icone, landing_url} of an ACTIVE catalog product.

Contract: products/core/CONTRACTS/sso-entry.md (slice S3 of
project-history/plans/sso-session-lifecycle-2026-11.md). Lives in its own file so it never
collides with ``routers/sso.py`` (the token/redeem surface).

The return target is a catalog SLUG, never a URL: the URL is resolved here, server-side
(``resolve_launch_base`` + the same-site guard), so the login page has no URL parameter to abuse.
"""
import logging

import anyio
from fastapi import HTTPException, Request
from noctusai_lib.api.access_tiers import access_tier, make_router

from app.database import get_admin_client
from app.rate_limit import limiter
from app.schemas.sso import SSOProdutoPublic
from app.sso_regime import LaunchNotSameSite, ProductUrlUnresolvable, assert_launch_same_site, resolve_launch_base, site_of

logger = logging.getLogger(__name__)
router = make_router(
    tier="public",
    reason="login page shows which product the visitor is entering; four catalog fields, ativo rows only",
    category="auth",
    prefix="/api/sso",
    tags=["SSO"],
)

_NOT_FOUND = "Produto não encontrado"


def _rows(data) -> list[dict]:
    if isinstance(data, dict):
        return [data]
    return [r for r in (data or []) if isinstance(r, dict)]


@router.get("/produto/{slug}", response_model=SSOProdutoPublic)
@access_tier('public', reason='login page shows which product the visitor is entering; four catalog fields, ativo rows only', category='auth')
@limiter.limit("60/minute")
async def get_produto_publico(request: Request, slug: str):
    """Public identity of an ACTIVE product. Unknown and inactive are both 404 (indistinguishable)."""
    return await anyio.to_thread.run_sync(_produto_publico_sync, slug)


def _produto_publico_sync(slug: str) -> SSOProdutoPublic:
    db = get_admin_client()
    rows = _rows(
        db.table("products").select("slug, nome, icone, url_base, ativo, deploy_scope")
        .eq("slug", slug).eq("ativo", True).limit(1).execute().data
    )
    # `ativo` is re-checked here: the query already filters, and a catalog row that is not a
    # literal True must never be served whatever the data layer returned.
    if not rows or rows[0].get("ativo") is not True:
        raise HTTPException(status_code=404, detail=_NOT_FOUND)
    product = rows[0]

    try:
        base = resolve_launch_base(slug, product)
    except ProductUrlUnresolvable:
        logger.error("sso_produto: no launch URL resolvable for product=%s", slug)
        raise HTTPException(
            status_code=409,
            detail="Produto sem URL de acesso configurada — contate o suporte NoctusAI",
        )
    try:
        assert_launch_same_site(base)
    except LaunchNotSameSite as exc:
        logger.error("sso_produto_cross_site product=%s base_site=%s: %s", slug, site_of(base), exc)
        raise HTTPException(
            status_code=409,
            detail="O endereço de acesso do produto não pertence ao mesmo site do NoctusAI — contate o suporte NoctusAI",
        )

    return SSOProdutoPublic(slug=slug, nome=product.get("nome") or slug, icone=product.get("icone"), landing_url=base)
