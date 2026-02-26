"""
SSO Router — Generate and validate SSO tokens for cross-product authentication.

POST  /api/sso/token           — Generate SSO token for a product
POST  /api/sso/validate        — Validate SSO token (called by products)
GET   /api/sso/launch/{slug}   — Redirect to product with SSO token
POST  /api/sso/session         — Exchange SSO token for a Supabase session
"""
from __future__ import annotations

import logging
import threading
import time
from typing import Dict, Optional, Tuple

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from app.database import get_admin_client, supabase_admin
from app.dependencies import get_current_user, create_sso_token, verify_sso_token

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/sso", tags=["SSO"])

# ---------------------------------------------------------------------------
# SSO session cache (shared across all products)
# ---------------------------------------------------------------------------

_CACHE_TTL = 55  # seconds — below Supabase's 60s rate limit


class _SSOSessionCache:
    """In-memory cache for SSO sessions, keyed by email with TTL."""

    def __init__(self):
        self._store: Dict[str, Tuple[dict, float]] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._global_lock = threading.Lock()

    def get(self, email: str) -> Optional[dict]:
        entry = self._store.get(email)
        if entry is None:
            return None
        data, created_at = entry
        if time.monotonic() - created_at > _CACHE_TTL:
            self._store.pop(email, None)
            return None
        return data

    def set(self, email: str, data: dict) -> None:
        self._store[email] = (data, time.monotonic())

    def get_lock(self, email: str) -> threading.Lock:
        with self._global_lock:
            if email not in self._locks:
                self._locks[email] = threading.Lock()
            return self._locks[email]

    def clear(self) -> None:
        self._store.clear()
        with self._global_lock:
            self._locks.clear()


_session_cache = _SSOSessionCache()


class _RateLimitError(Exception):
    """Internal signal for Supabase rate limit — caught by the endpoint."""
    pass


class SSOTokenRequest(BaseModel):
    product_slug: str


class SSOValidateRequest(BaseModel):
    token: str


@router.post("/token")
async def generate_sso_token(body: SSOTokenRequest, authorization: Optional[str] = Header(None)):
    """Generate a short-lived SSO token to access a product."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Get user profile
    profile = db.table("noctus_users").select("*").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    org_id = profile.data["org_id"]
    role = profile.data.get("role", "user")

    # Check if org has access to product
    product = db.table("products").select("id, slug").eq("slug", body.product_slug).single().execute()
    if not product.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    license_check = db.table("licenses").select("id").eq(
        "org_id", org_id
    ).eq("product_id", product.data["id"]).eq("status", "active").execute()

    if not license_check.data:
        raise HTTPException(status_code=403, detail="Organização não tem acesso a este produto")

    # Generate SSO token
    sso_token = create_sso_token(
        user_id=user.id,
        org_id=org_id,
        product_slug=body.product_slug,
        email=user.email,
        role=role,
    )

    logger.info(f"SSO token generated for user={user.id} product={body.product_slug}")
    return {"sso_token": sso_token, "product_slug": body.product_slug}


@router.post("/validate")
async def validate_sso_token(body: SSOValidateRequest):
    """Validate an SSO token. Called by products to verify user access."""
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
async def launch_product(product_slug: str, authorization: Optional[str] = Header(None)):
    """Generate SSO token and redirect to the product URL."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Get user profile
    profile = db.table("noctus_users").select("org_id, role").eq("id", user.id).single().execute()
    if not profile.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    org_id = profile.data["org_id"]
    role = profile.data.get("role", "user")

    # Get product
    product = db.table("products").select("*").eq("slug", product_slug).single().execute()
    if not product.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")

    # Check license
    license_check = db.table("licenses").select("id").eq(
        "org_id", org_id
    ).eq("product_id", product.data["id"]).eq("status", "active").execute()

    if not license_check.data:
        raise HTTPException(status_code=403, detail="Sem acesso a este produto")

    # Generate SSO token
    sso_token = create_sso_token(
        user_id=user.id,
        org_id=org_id,
        product_slug=product_slug,
        email=user.email,
        role=role,
    )

    # Redirect to product with token
    redirect_url = f"{product.data['url_base']}/sso?token={sso_token}"
    return RedirectResponse(url=redirect_url, status_code=302)


# ---------------------------------------------------------------------------
# POST /api/sso/session — Exchange SSO token for a Supabase session
# ---------------------------------------------------------------------------

class SSOSessionRequest(BaseModel):
    token: str


class SSOSessionResponse(BaseModel):
    access_token: str
    refresh_token: str
    user_id: str
    email: str


def _is_rate_limit_error(exc: Exception) -> bool:
    """Check if an exception is a Supabase rate limit error."""
    msg = str(exc).lower()
    return "rate" in msg and "limit" in msg or "429" in msg or "60 seconds" in msg


def _generate_session(email: str) -> dict:
    """Generate a Supabase session for the given user.

    Uses a per-email cache to avoid hitting Supabase's 60s rate limit.
    A per-email lock prevents concurrent duplicate calls.
    """
    if not supabase_admin:
        logger.error("supabase_admin não inicializado — verifique SUPABASE_SERVICE_ROLE_KEY")
        raise HTTPException(status_code=500, detail="Configuração do servidor incompleta")

    # Fast path: check cache before acquiring lock
    cached = _session_cache.get(email)
    if cached:
        logger.debug("SSO cache hit para email=%s", email)
        return cached

    lock = _session_cache.get_lock(email)
    with lock:
        # Double-check after acquiring lock (another thread may have populated)
        cached = _session_cache.get(email)
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

            session_response = supabase_admin.auth.verify_otp({
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

            _session_cache.set(email, result)
            logger.info("SSO sessão gerada e cacheada para email=%s", email)
            return result

        except HTTPException:
            raise
        except Exception as exc:
            if _is_rate_limit_error(exc):
                # Last resort: maybe cache was populated by a concurrent request
                cached = _session_cache.get(email)
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


@router.post("/session", response_model=SSOSessionResponse)
async def sso_session(body: SSOSessionRequest):
    """Exchange an SSO token for a Supabase session.

    Called by product frontends directly. The Core is the sole owner of
    session generation — no product backend participates in SSO.

    Flow:
    1. Decode JWT using shared jwt_secret (via verify_sso_token)
    2. Extract email from payload (user already exists — same Supabase project)
    3. Generate a Supabase session (access_token + refresh_token), with caching
    4. Return tokens to the frontend
    """
    payload = verify_sso_token(body.token)
    email = payload.get("email")

    if not email:
        raise HTTPException(status_code=400, detail="Token SSO sem email")

    logger.info("SSO session para email=%s, org=%s", email, payload.get("org_id"))

    try:
        session = _generate_session(email)
    except _RateLimitError:
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
