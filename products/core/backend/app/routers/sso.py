"""
SSO Router — Generate and validate SSO tokens for cross-product authentication.

POST  /api/sso/token           — Generate SSO token for a product (+ server-built redirect_url)
POST  /api/sso/validate        — Validate SSO token (called by products)
GET   /api/sso/launch/{slug}   — Redirect to product with SSO token
POST  /api/sso/session         — Exchange SSO token for a Supabase session

Token transport / redemption strictness is MIXED and catalog-derived: see
``app.sso_regime`` (strict = fragment + mandatory product_slug; legacy = query,
slug optional, only for active dev-scope products on the old callback).
"""
import logging
import threading
import time
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from noctusai_lib.api.auth.session.types import AuthContext

from app.services.trusted_auth import require_platform_admin_dep
from fastapi.responses import JSONResponse, RedirectResponse
from supabase import create_client

from app.config import settings
from app.database import get_admin_client, supabase_admin
from app.dependencies import get_current_user, create_sso_token, verify_sso_token
from app.rate_limit import limiter
from app.sso_regime import ProductUrlUnresolvable, build_sso_launch_url, resolve_launch_base, sso_regime
from app.schemas.sso import SSOSessionRequest, SSOSessionResponse, SSOTokenRequest, SSOTokenResponse, SSOValidateRequest

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sso", tags=["SSO"])

# ---------------------------------------------------------------------------
# SSO session cache (shared across all products)
#
# compliance-audit-reconciliation Phase 6 (finding 9, 2026-04-22):
# previous TTL was 3500s (~58min). That preserved stale role / license /
# org-reassignment state for up to an hour after change. Reduced to 300s
# — above the Supabase 60s rate-limit between magic-link generations but
# tight enough that role revocations take effect quickly. Role/license
# change points also call `invalidate_sso_cache_for_user(email)` to
# flush on demand.
# ---------------------------------------------------------------------------
#
# Cache class promoted to `noctusai_lib.auth.SSOSessionCache` in
# `core-seed-wiring-v2` Phase 4 (2026-04-23). Core now composes the lib
# class rather than maintaining a local one — any future identity-source
# product gets the same cache with the same concurrency semantics.

from noctusai_lib.api.auth import SSOSessionCache
from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.primitives.roles import customer_may_access_product

# SEC-2 (2026-09-28): an end customer (org_role in CUSTOMER_ORG_ROLES) only
# ever SSOs into a product whose catalog row declares `aceita_clientes`.
_CUSTOMER_REFUSED = "Área restrita à equipe."

_CACHE_TTL = 300  # 5 min — above 60s Supabase rate limit, tight on staleness

class _ScopedSSOSessionCache(SSOSessionCache):
    """SSOSessionCache keyed per (email, org_id, product_slug), flushable per email.

    Why scoped: an email-only key handed the SAME session (same refresh token) to
    several product origins -- Supabase refresh-token reuse detection can then revoke
    the whole family -- and replayed a stale org_id/org_role in user_metadata for up
    to the TTL after an org switch. The cache exists only to dodge GoTrue's ~60s
    per-email magic-link cooldown, so entries are kept per scope and a flush by email
    removes every scope of that user.
    """

    _SEP = "\x1f"

    @classmethod
    def scoped_key(cls, email: str, org_id: str | None, product_slug: str | None) -> str:
        return cls._SEP.join((email, org_id or "", product_slug or ""))

    def invalidate(self, email: str) -> bool:
        prefix = email + self._SEP
        keys = [k for k in list(self._store) if k == email or k.startswith(prefix)]
        removed = False
        for k in keys:
            removed = super().invalidate(k) or removed
        return removed


_session_cache = _ScopedSSOSessionCache(ttl_seconds=_CACHE_TTL)


def invalidate_sso_cache_for_user(email: str) -> bool:
    """Public helper — flush a user's cached SSO session.

    Call on: role change, license revocation, org reassignment, user
    disable. Idempotent — returns True iff an entry existed.
    """
    if not email:
        return False
    removed = _session_cache.invalidate(email)
    if removed:
        logger.info("SSO cache invalidated for email=%s", email)
    return removed


def invalidate_sso_cache_for_org(db, org_id: str) -> int:
    """Flush every cached SSO session for an org. Returns invalidated count.

    Use when a change affects the whole org (license revoke, plan change,
    org reassignment). Silent-fails safely if the user query errors —
    the 5-min TTL will still expire the entry.
    """
    if not org_id:
        return 0
    try:
        result = (
            db.table("noctus_users")
            .select("email")
            .eq("org_id", org_id)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("SSO cache org-invalidate failed (org=%s): %s", org_id, exc)
        return 0

    count = 0
    for row in result.data or []:
        email = row.get("email")
        if email and _session_cache.invalidate(email):
            count += 1
    if count:
        logger.info("SSO cache invalidated for org=%s count=%d", org_id, count)
    return count


class _RateLimitError(Exception):
    """Internal signal for Supabase rate limit — caught by the endpoint."""
    pass


@router.post("/token", response_model=SSOTokenResponse)
@limiter.limit("20/minute")
async def generate_sso_token(request: Request, body: SSOTokenRequest, authorization: Optional[str] = Header(None)):
    """Generate a short-lived SSO token to access a product."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Get user profile
    profile = db.table("noctus_users").select("*").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    org_id = profile.data["org_id"]
    role = profile.data.get("role", "user")
    org_role = profile.data.get("org_role", "member")

    # Check if org has access to product (including expiry check)
    product = db.table("products").select("id, slug, aceita_clientes, url_base, ativo, deploy_scope").eq("slug", body.product_slug).single().execute()
    if not product.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    if not customer_may_access_product(org_role, product.data):
        raise HTTPException(status_code=403, detail=_CUSTOMER_REFUSED)
    if product.data.get("ativo") is not True:
        # An inactive (asleep) product is not launchable -- fail closed.
        raise HTTPException(status_code=403, detail="Organização não tem acesso a este produto")

    from app.dependencies import check_org_license
    if not check_org_license(db, org_id, product.data["id"]):
        raise HTTPException(status_code=403, detail="Organização não tem acesso a este produto")

    # Resolve the launch URL BEFORE minting: an unresolvable product is a typed
    # 409, never a token minted and then a 500.
    try:
        launch_base = resolve_launch_base(body.product_slug, product.data)
    except ProductUrlUnresolvable:
        logger.error("sso: no launch URL resolvable for product=%s", body.product_slug)
        raise HTTPException(
            status_code=409,
            detail="Produto sem URL de acesso configurada — contate o suporte NoctusAI",
        )

    # Generate SSO token
    sso_token = create_sso_token(
        user_id=user.id,
        org_id=org_id,
        product_slug=body.product_slug,
        email=user.email,
        role=role,
        org_role=org_role,
    )

    logger.info(f"SSO token generated for user={user.id} product={body.product_slug}")
    return SSOTokenResponse(
        sso_token=sso_token,
        product_slug=body.product_slug,
        redirect_url=build_sso_launch_url(body.product_slug, product.data, sso_token, base=launch_base),
    )


@router.post("/validate")
@limiter.limit("20/minute")
async def validate_sso_token(
    request: Request,
    body: SSOValidateRequest,
    _: AuthContext = Depends(require_platform_admin_dep),
):
    """Decode an SSO token WITHOUT consuming it — platform admins only.

    2026-10-09 (SSO roadmap follow-up): this was an unauthenticated,
    non-consuming token oracle with no audience binding. No product or frontend
    calls it (repo grep); n8n workflows could not be listed (API 401), so it is
    gated to platform admins rather than removed. Products redeem via
    POST /api/sso/session, which binds and consumes."""
    payload = verify_sso_token(body.token)
    return {
        "valid": True,
        "user_id": payload["sub"],
        "org_id": payload["org_id"],
        "product": payload["product"],
        "email": payload["email"],
        "role": payload["role"],
    }


@router.get("/launch/{product_slug}")
@limiter.limit("20/minute")
async def launch_product(request: Request, product_slug: str, authorization: Optional[str] = Header(None)):
    """Generate SSO token and redirect to the product URL."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Get user profile
    profile = db.table("noctus_users").select("org_id, role, org_role").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    org_id = profile.data["org_id"]
    role = profile.data.get("role", "user")
    org_role = profile.data.get("org_role", "member")

    # Get product
    product = db.table("products").select("*").eq("slug", product_slug).single().execute()
    if not product.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    if not customer_may_access_product(org_role, product.data):
        raise HTTPException(status_code=403, detail=_CUSTOMER_REFUSED)
    if product.data.get("ativo") is not True:
        raise HTTPException(status_code=403, detail="Sem acesso a este produto")

    # Check license (including expiry)
    from app.dependencies import check_org_license
    if not check_org_license(db, org_id, product.data["id"]):
        raise HTTPException(status_code=403, detail="Sem acesso a este produto")

    try:
        launch_base = resolve_launch_base(product_slug, product.data)
    except ProductUrlUnresolvable:
        logger.error("sso: no launch URL resolvable for product=%s", product_slug)
        raise HTTPException(
            status_code=409,
            detail="Produto sem URL de acesso configurada — contate o suporte NoctusAI",
        )

    # Generate SSO token
    sso_token = create_sso_token(
        user_id=user.id,
        org_id=org_id,
        product_slug=product_slug,
        email=user.email,
        role=role,
        org_role=org_role,
    )

    # Token transport per the catalog-derived regime (strict -> URL fragment,
    # legacy -> query), URL resolved through the seed `resolve_product_url`.
    redirect_url = build_sso_launch_url(product_slug, product.data, sso_token, base=launch_base)
    return RedirectResponse(url=redirect_url, status_code=302)


# ---------------------------------------------------------------------------
# POST /api/sso/session — Exchange SSO token for a Supabase session
# ---------------------------------------------------------------------------


def _enrich_sso_metadata(db, metadata: dict, org_id: str | None, product_slug: str | None) -> None:
    """Enrich SSO metadata dict with org, subscription plan, and license info.

    All queries are best-effort — failures are logged but never block session
    creation.  Fields are set to None when the corresponding record doesn't
    exist (e.g. no subscription yet).
    """
    # ── Org info ──────────────────────────────────────────────
    if org_id:
        try:
            org = db.table("organizations").select(
                "nome, logo_url"
            ).eq("id", org_id).single().execute()
            if org.data:
                metadata["org_name"] = org.data.get("nome")
                metadata["org_logo_url"] = org.data.get("logo_url")
        except Exception as exc:
            logger.debug("SSO enrich: org query failed: %s", exc)

    # ── Subscription + plan ───────────────────────────────────
    if org_id:
        try:
            sub = db.table("subscriptions").select(
                "status, expires_at, plans(slug, max_users, max_products, features)"
            ).eq("org_id", org_id).eq("status", "active").limit(1).execute()

            if not sub.data:
                # Try trial
                sub = db.table("subscriptions").select(
                    "status, expires_at, plans(slug, max_users, max_products, features)"
                ).eq("org_id", org_id).eq("status", "trial").limit(1).execute()

            if sub.data:
                row = sub.data[0]
                plan = row.get("plans") or {}
                metadata["subscription_status"] = row.get("status")
                metadata["subscription_expires_at"] = row.get("expires_at")
                metadata["plan_slug"] = plan.get("slug")
                metadata["plan_max_users"] = plan.get("max_users")
                metadata["plan_max_products"] = plan.get("max_products")
                metadata["plan_features"] = plan.get("features")
        except Exception as exc:
            logger.debug("SSO enrich: subscription query failed: %s", exc)

    # ── License expiry for this specific product ──────────────
    if org_id and product_slug:
        try:
            product = db.table("products").select("id").eq(
                "slug", product_slug
            ).limit(1).execute()
            if product.data:
                product_id = product.data[0]["id"]
                lic = db.table("licenses").select("fim").eq(
                    "org_id", org_id
                ).eq("product_id", product_id).eq(
                    "status", "active"
                ).limit(1).execute()
                if lic.data:
                    metadata["license_expires_at"] = lic.data[0].get("fim")
        except Exception as exc:
            logger.debug("SSO enrich: license query failed: %s", exc)


def _is_rate_limit_error(exc: Exception) -> bool:
    """Check if an exception is a Supabase rate limit error.

    Supabase GoTrue returns different error messages depending on the context:
    - "rate limit" / "429" / "60 seconds" for explicit rate limit responses
    - "User not allowed" when a magiclink/OTP is generated too quickly for the
      same email (undocumented ~60s cooldown per email)
    """
    msg = str(exc).lower()
    return (
        ("rate" in msg and "limit" in msg)
        or "429" in msg
        or "60 seconds" in msg
        or "user not allowed" in msg
    )


def _generate_session(email: str, org_id: str | None = None, product_slug: str | None = None) -> dict:
    """Generate a Supabase session for the given user.

    Uses a cache keyed (email, org_id, product_slug) to avoid hitting Supabase's
    60s rate limit without sharing one session across origins or orgs.
    A per-key lock prevents concurrent duplicate calls.
    """
    cache_key = _ScopedSSOSessionCache.scoped_key(email, org_id, product_slug)
    if not supabase_admin:
        logger.error("supabase_admin não inicializado — verifique SUPABASE_SERVICE_ROLE_KEY")
        raise HTTPException(status_code=500, detail="Configuração do servidor incompleta")

    # Fast path: check cache before acquiring lock
    cached = _session_cache.get(cache_key)
    if cached:
        logger.debug("SSO cache hit para email=%s", email)
        return cached

    lock = _session_cache.get_lock(cache_key)
    with lock:
        # Double-check after acquiring lock (another thread may have populated)
        cached = _session_cache.get(cache_key)
        if cached:
            logger.debug("SSO cache hit (post-lock) para email=%s", email)
            return cached

        try:
            logger.debug("Gerando link para email=%s", email)
            link_response = supabase_admin.auth.admin.generate_link({
                "type": "magiclink",
                "email": email,
            })

            email_otp = link_response.properties.email_otp
            if not email_otp:
                raise Exception("generate_link não retornou email_otp")

            # verify_otp ESTABLISHES a session, so supabase-py propagates the
            # new user token onto the calling client's PostgREST layer. Running
            # it on the shared service-role singleton (`supabase_admin`) would
            # downgrade every later get_admin_client() call from service_role
            # to authenticated — process-wide until restart — tripping RLS on
            # unrelated requests (42P17 recursion on noctus_users, broke
            # GET /api/auth/me 2026-05-23). Use a throwaway anon client, like
            # login/refresh/logout already do. generate_link above stays on the
            # admin singleton (admin API; it does not set a session).
            otp_client = create_client(settings.supabase_url, settings.supabase_anon_key)
            session_response = otp_client.auth.verify_otp({
                "email": email,
                "token": email_otp,
                "type": "magiclink",
            })

            session = session_response.session
            if not session:
                raise Exception("Nenhuma sessão retornada na verificação OTP")

            result = {
                "access_token": session.access_token,
                "refresh_token": session.refresh_token,
                "user_id": str(session_response.user.id),
                "email": email,
            }

            _session_cache.set(cache_key, result)
            logger.info("SSO sessão gerada e cacheada para email=%s", email)
            return result

        except HTTPException:
            raise
        except Exception as exc:
            if _is_rate_limit_error(exc):
                # Last resort: maybe cache was populated by a concurrent request
                cached = _session_cache.get(cache_key)
                if cached:
                    logger.info("Rate limited mas cache disponível para email=%s", email)
                    return cached

                logger.warning("Rate limit do Supabase para email=%s: %s", email, exc)
                raise _RateLimitError()

            logger.error("Erro ao gerar sessão Supabase para %s: %s: %s", email, type(exc).__name__, exc)
            raise HTTPException(
                status_code=500,
                detail=f"Erro ao gerar sessão: {type(exc).__name__}",
            )


def _claim_sso_jti(db, jti: str, user_id: str | None, product: str | None) -> None:
    """Record the jti as redeemed; refuse (401) when it already was.

    Fail-closed: any insert error other than a duplicate-key is a 500, never
    an implicit pass.
    """
    try:
        db.table("sso_token_redemptions").insert({
            "jti": jti, "user_id": user_id, "product": product or "",
        }).execute()
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        if "23505" in msg or "duplicate" in msg or "already exists" in msg:
            logger.warning("sso: replay refused for jti=%s", jti)
            raise HTTPException(status_code=401, detail="Token SSO já utilizado")
        logger.error("sso: could not record redemption jti=%s: %s", jti, exc)
        raise HTTPException(status_code=500, detail="Erro ao validar token SSO")


def _release_sso_jti(db, jti: str) -> None:
    """Undo a claim when no session was issued (so a retry is not burned)."""
    try:
        db.table("sso_token_redemptions").delete().eq("jti", jti).execute()
    except Exception as exc:  # noqa: BLE001
        logger.warning("sso: could not release jti=%s: %s", jti, exc)


@router.post("/session", response_model=SSOSessionResponse)
@limiter.limit("20/minute")
async def sso_session(request: Request, body: SSOSessionRequest):
    """Exchange an SSO token for a Supabase session.

    Called by product frontends directly. The Core is the sole owner of
    session generation — no product backend participates in SSO.

    Flow:
    1. Decode JWT using shared jwt_secret (via verify_sso_token)
    2. Extract email from payload (user already exists — same Supabase project)
    3. Sync NoctusAI role + org_id into user_metadata (so products know the role)
    4. Generate a Supabase session (access_token + refresh_token), with caching
    5. Return tokens to the frontend
    """
    payload = verify_sso_token(body.token)
    email = payload.get("email")

    if not email:
        raise HTTPException(status_code=400, detail="Token SSO sem email")

    user_id = payload.get("sub")
    noctus_role = payload.get("role", "user")
    org_role = payload.get("org_role", "member")
    org_id = payload.get("org_id")
    token_product = payload.get("product")

    # Audience binding: a token minted for product A cannot be redeemed as B.
    if body.product_slug is not None and body.product_slug != token_product:
        raise HTTPException(status_code=401, detail="Token SSO não é válido para este produto")

    db = get_admin_client()

    # The token's product row decides the regime (never the request). One
    # select serves the regime, the license check and the id lookup.
    product_row = (
        db.table("products").select("id, ativo, deploy_scope").eq("slug", token_product).limit(1).execute()
    )
    if not product_row.data:
        raise HTTPException(status_code=403, detail="Produto não encontrado")
    regime = sso_regime(product_row.data[0])

    # Strict: the redeemer must name itself. ALL binding/strictness 401s run
    # BEFORE `_claim_sso_jti`, so a rejected relay never burns a legitimate token.
    if regime == "strict" and body.product_slug is None:
        raise HTTPException(status_code=401, detail="Token SSO não é válido para este produto")

    # Re-check the license at redemption — a revoked license cannot redeem.
    from app.dependencies import check_org_license
    if not check_org_license(db, org_id, product_row.data[0]["id"]):
        raise HTTPException(status_code=403, detail="Organização não tem acesso a este produto")

    # Single use: claim the jti BEFORE issuing anything.
    jti = payload["jti"]
    _claim_sso_jti(db, jti, user_id, token_product)

    if regime == "legacy":
        # Drives the "legacy reaches zero" exit criterion (roadmap P2.1). Never the token.
        logger.warning(
            "sso_legacy_redeem jti=%s product=%s user_id=%s org_id=%s origin=%s slug_present=%s",
            jti, token_product, user_id, org_id,
            request.headers.get("origin"), body.product_slug is not None,
        )

    logger.info(
        "SSO session para email=%s, org=%s, role=%s, org_role=%s",
        email, org_id, noctus_role, org_role,
    )

    # Sync full SSO context into user_metadata so products are "aware"
    # of the user's role, org, subscription plan, and license status.
    # Supabase merges user_metadata (shallow), so existing fields are preserved.
    # This runs before _generate_session, so newly-created sessions include
    # the updated metadata.  Cached sessions (≤55s) have prior update's data.
    if supabase_admin and user_id:
        try:
            metadata_update: dict = {
                "noctus_role": noctus_role,
                "org_role": org_role,
            }
            if org_id:
                metadata_update["org_id"] = org_id

            # Enrich with org, subscription, and license context
            product_slug = payload.get("product")
            _enrich_sso_metadata(db, metadata_update, org_id, product_slug)

            supabase_admin.auth.admin.update_user_by_id(
                user_id, {"user_metadata": metadata_update}
            )
        except Exception as exc:
            logger.warning("Failed to sync metadata to user_metadata: %s", exc)

    try:
        session = _generate_session(email, org_id, payload.get("product"))
    except HTTPException:
        _release_sso_jti(db, jti)
        raise
    except _RateLimitError:
        # Nothing was issued — release the claim so the client's Retry-After
        # retry (same token) is not burned.
        _release_sso_jti(db, jti)
        logger.warning("sso: rate-limit hit for email=%s during session generation; returning 429", email)
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit — tente novamente em 60 segundos"},
            headers={"Retry-After": "60"},
        )

    return SSOSessionResponse(
        access_token=session["access_token"],
        refresh_token=session["refresh_token"],
        user_id=session["user_id"],
        email=session["email"],
    )
