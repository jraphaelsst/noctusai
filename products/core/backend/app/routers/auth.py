"""
Auth Router — Login, Signup, Session for NoctusAI.

POST  /api/auth/signup   — Register new user + org
POST  /api/auth/login    — Email/password login
GET   /api/auth/me       — Get current user profile + org
POST  /api/auth/logout   — Invalidate session
"""
import anyio
import logging
from typing import Optional, Literal
from fastapi import APIRouter, Header, HTTPException, Request, Query

from supabase import create_client
from app.config import settings
from app.database import get_admin_client
from app.dependencies import get_current_user
from app.rate_limit import limiter
from app.services import login_mfa, org_provisioning
from app.schemas.products import PRODUCT_PUBLIC_KEYS as _PUBLIC_PRODUCT_KEYS
from app.schemas.auth import SignupRequest, LoginRequest, ProfileUpdate, PasswordChange, RefreshRequest
from noctusai_lib.api.auth import auth_provider_unavailable, is_authoritative_token_rejection
from noctusai_lib.api.auth.org_selection import make_org_selection_store
from noctusai_lib.config.product_urls import resolve_product_url

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])

# The slug rule + org insert live in ONE place (signup, OAuth signup, a removed member's
# personal org): app.services.org_provisioning. Re-exported for the signup tests.
_make_org_slug = org_provisioning.make_org_slug


@router.post("/signup")
@limiter.limit("10/minute")
async def signup(request: Request, body: SignupRequest):
    """Register a new user and create their organization.

    Self-serve billing: with `plan_price_id`, the chosen price is validated
    (sellable, audience fits `org_type`) before anything is created, and the
    response tells the client to continue to checkout.

    Website signup gate (contract §6, §10): when the website's
    `signup_enabled` switch is off, refuse BEFORE any user is created.
    Invites (`/invite/:token`) are a separate flow and are unaffected.
    """
    from app.services import website_settings_service

    try:
        _version, website_data = website_settings_service.get_current()
    except website_settings_service.WebsiteDefaultsMissing:
        # The website subsystem has no rows AND no FE-built defaults file —
        # it has never been configured on this deploy (or this is a test
        # that predates the website slice). Signup stays open: the gate is
        # only meaningful once an admin has something to toggle, and
        # blocking every signup because a DIFFERENT feature isn't wired
        # would be the wrong kind of "fail loud" here — `get_current()`
        # already fails loud for the website's OWN endpoints.
        website_data = {"signup_enabled": True}
    if not website_data.get("signup_enabled", True):
        # `{"detail": <code>, "code": <code>}` — the seed's escape hatch for
        # the LITERAL `{"detail": "signup_closed"}` shape the website
        # contract specifies (`noctusai_lib.primitives.exceptions.
        # http_exception_handler`); every other HTTPException here still
        # gets the platform's historical `{"error": {"code","message"}}`.
        raise HTTPException(status_code=403, detail={"detail": "signup_closed", "code": "signup_closed"})

    db = get_admin_client()

    chosen_price = None
    if body.plan_price_id:
        from app.services.billing_subscriptions import BillingError, validate_price_for_org_type

        try:
            chosen_price = validate_price_for_org_type(db, body.plan_price_id, body.org_type)["price"]
        except BillingError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    # 1. Create Supabase auth user
    try:
        auth_response = (await anyio.to_thread.run_sync(lambda: db.auth.admin.create_user({
            "email": body.email,
            "password": body.password,
            "email_confirm": True,
        })))
        user = auth_response.user
        if not user:
            raise HTTPException(status_code=400, detail="Erro ao criar usuário")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Erro no cadastro: {str(e)}")

    # 2. Create organization with org_type, number_of_users, and prefixed slug.
    #    Slug format: 'indv_<base>' for individuals, 'comp_<base>' for companies.
    org = (await anyio.to_thread.run_sync(lambda: org_provisioning.create_owned_org(
        db, owner_id=user.id, nome=body.empresa.strip(), slug_base=body.empresa.strip(),
        org_type=body.org_type, category="normal", number_of_users=body.number_of_users,
    )))

    # 3. Create user profile linked to org
    profile_data = {
        "id": user.id,
        "email": body.email,
        "nome": body.nome.strip().title(),
        "org_id": org["id"],
        "role": "user",
        "org_role": "owner",  # Org creator is owner of their org
    }
    (await anyio.to_thread.run_sync(db.table("noctus_users").insert(profile_data).execute))

    # 4. Sync org_id to auth user_metadata so product backends can read it
    try:
        (await anyio.to_thread.run_sync(lambda: db.auth.admin.update_user_by_id(user.id, {"user_metadata": {"org_id": org["id"]}})))
    except Exception as e:
        logger.warning(
            "auth: user_metadata sync failed for user_id=%s (%s); request continues",
            user.id, e,
        )

    # Log signup with user_id (UUID), not email — emails are LGPD personal data.
    logger.info("auth: new signup user_id=%s org_id=%s", user.id, org["id"])

    # Audit log and welcome email (best-effort)
    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=user.id, org_id=org["id"],
            action="signup", resource_type="user", resource_id=user.id,
            request=request,
        )
    except Exception as exc:
        logger.warning("auth: signup audit log failed for user_id=%s (%s); request continues", user.id, exc)
    try:
        from app.services.email_service import send_welcome_email
        send_welcome_email(to=body.email, user_name=body.nome.strip().title(), org_name=org["nome"])
    except Exception as exc:
        # Log user_id (UUID), NOT body.email — emails are LGPD personal data
        # and shouldn't persist in operator log streams. Same rule as the
        # surrounding audit-log warnings (which all use user_id=%s).
        logger.warning("auth: welcome email send failed for user_id=%s (%s); request continues", user.id, exc)

    data = {"user_id": user.id, "org_id": org["id"]}
    if chosen_price is not None:
        data["next_step"] = {"action": "subscribe", "plan_price_id": chosen_price["id"]}
    return {"data": data}


@router.post("/login")
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest):
    """Login with email/password. Returns Supabase session."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    try:
        response = (await anyio.to_thread.run_sync(lambda: client.auth.sign_in_with_password({
            "email": body.email,
            "password": body.password,
        })))
        if not response.session:
            raise HTTPException(status_code=401, detail="Credenciais inválidas")

        # Audit log (best-effort)
        try:
            from app.services import audit_service
            await audit_service.log(
                user_id=str(response.user.id), org_id=None,
                action="login", resource_type="user", resource_id=str(response.user.id),
                request=request,
            )
        except Exception as exc:
            logger.warning("auth: login audit log failed for user_id=%s (%s); login proceeds", response.user.id, exc)

        # Enforce concurrent session cap (best-effort)
        try:
            admin_db = get_admin_client()
            (await anyio.to_thread.run_sync(admin_db.rpc("enforce_session_cap", {"p_user_id": str(response.user.id)}).execute))
        except Exception as exc:
            logger.warning("auth: enforce_session_cap RPC failed for user_id=%s (%s); login proceeds", response.user.id, exc)

        # MFA discovery (platform-admin-mfa M5). With verified factors the
        # tokens below are the aal1 session: the SPA must challenge via
        # POST /api/auth/mfa/verify before treating the user as signed in.
        mfa_factors = await login_mfa.verified_factors(request, response.session.access_token)

        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
            "user": {
                "id": response.user.id,
                "email": response.user.email,
            },
            "mfa_required": bool(mfa_factors),
            "mfa_factors": mfa_factors,
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail="Email ou senha incorretos")


@router.get("/me")
async def get_me(authorization: Optional[str] = Header(None)):
    """Get current user profile with organization and licensed products."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    # Get noctus user profile
    profile_result = (await anyio.to_thread.run_sync(db.table("noctus_users").select("*").eq("id", user.id).single().execute))
    if not profile_result.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    profile = profile_result.data
    org_id = profile.get("org_id")

    # Get organization
    org_result = (await anyio.to_thread.run_sync(db.table("organizations").select("*").eq("id", org_id).single().execute))

    # has_access = the SSO admission rule (S4 multi-org): ANY active membership whose org holds a
    # live license, minus orgs where the user is BLOCKED from the product (D5) -- not only the
    # profile org, or the card locks a product /api/sso/token would admit. One license + one block
    # lookup per membership org (a user belongs to a handful), never per product.
    from app.dependencies import get_licensed_product_ids
    from app.services import product_admission
    from app.services.team_memberships import blocked_product_ids

    def _admission_inputs():
        memberships = product_admission.ordered_memberships(db, user.id, org_id)
        orgs = {str(m["org_id"]) for m in memberships if m.get("org_id")}
        licensed = {o: {str(p) for p in get_licensed_product_ids(db, o)} for o in orgs}
        blocked = {o: blocked_product_ids(db, user.id, o) for o in orgs}
        return memberships, licensed, blocked

    memberships, licensed_by_org, blocked_by_org = await anyio.to_thread.run_sync(_admission_inputs)

    # Get all products (for the marketplace view).
    #
    # Platform admins ALSO see inactive products, so they can reactivate one
    # straight from the dashboard card instead of having to open the admin
    # panel. Everyone else sees only active products — an inactive product is
    # one we have agreed not to work on, and it must not appear in a normal
    # user's marketplace.
    #
    # `role` comes from the profile already loaded above (the same field the
    # frontend derives `isAdmin` from), so this costs no extra query and
    # cannot disagree with the client's own view of who is an admin.
    is_platform_admin = profile.get("role") == "admin"
    products_query = db.table("products").select("*")
    if not is_platform_admin:
        products_query = products_query.eq("ativo", True)
    all_products = products_query.order("nome").execute()

    # Resolve url_base through the seed-side resolver so each product's
    # frontend URL adapts to the deploy environment (env-driven) without
    # rewriting public.products rows. Empty / missing resolution surfaces
    # as a logged warning; the row keeps its DB url_base as the dashboard
    # tile's last-resort destination — the dashboard must render even when
    # one product's URL config is gappy.
    products_with_access = []
    for product in (all_products.data or []):
        try:
            resolved_url = resolve_product_url(
                product["slug"],
                db_url_base=product.get("url_base"),
            )
        except ValueError as exc:
            logger.warning(
                "url_base resolution failed for product slug=%s: %s",
                product.get("slug"), exc,
            )
            resolved_url = product.get("url_base") or ""
        # RESPONSE is the public allowlist only; the wide row above exists solely
        # so the admission rule can read `aceita_clientes`. Operational
        # columns (house_port, sso_callback_verified_at, db_schema, ...) never leave.
        products_with_access.append({
            **{k: product[k] for k in _PUBLIC_PRODUCT_KEYS if k in product},
            "url_base": resolved_url,
            # The switcher must not offer what /api/sso/token will refuse, nor lock
            # what it would admit (SEC-2 customer roles included, per membership).
            "has_access": product_admission.admitting_membership(
                memberships, product,
                is_licensed=lambda o, pid=str(product["id"]): pid in licensed_by_org.get(o, ()),
                is_blocked=lambda o, pid=str(product["id"]): pid in blocked_by_org.get(o, ()),
            ) is not None,
        })

    return {
        "user": profile,
        "organization": org_result.data if org_result.data else None,
        "products": products_with_access,
    }


@router.post("/change-password")
@limiter.limit("5/minute")
async def change_password(
    request: Request,
    body: PasswordChange,
    authorization: Optional[str] = Header(None),
):
    """Change the current user's password."""
    user, token = await get_current_user(authorization)

    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="A senha deve ter no mínimo 8 caracteres")

    db = get_admin_client()
    try:
        (await anyio.to_thread.run_sync(lambda: db.auth.admin.update_user_by_id(user.id, {"password": body.new_password})))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Revoke every OTHER session of this user. GoTrue's admin sign_out takes the
    # session's access-token JWT (NOT the user id -- passing the id never worked and
    # the old broad except hid that). The password itself IS already changed, so a
    # failed revocation does not roll the change back; but it is surfaced to the
    # caller (`other_sessions_revoked: false`) and logged at ERROR, never swallowed.
    other_sessions_revoked = True
    try:
        (await anyio.to_thread.run_sync(lambda: db.auth.admin.sign_out(token, scope="others")))
    except Exception:
        other_sessions_revoked = False
        logger.error(
            "auth: could not revoke other sessions after password change user_id=%s",
            user.id, exc_info=True,
        )

    # Audit log (best-effort)
    try:
        from app.services import audit_service
        await audit_service.log(
            user_id=str(user.id), org_id=None,
            action="password_change", resource_type="user", resource_id=str(user.id),
            request=request,
        )
    except Exception as exc:
        logger.warning("auth: password-change audit log failed for user_id=%s (%s)", user.id, exc)

    return {
        "ok": True,
        "message": "Senha atualizada com sucesso",
        "other_sessions_revoked": other_sessions_revoked,
    }


@router.post("/refresh")
@limiter.limit("10/minute")
async def refresh_token(request: Request, body: RefreshRequest):
    """Exchange a refresh token for a new access token."""
    client = create_client(settings.supabase_url, settings.supabase_anon_key)
    try:
        response = (await anyio.to_thread.run_sync(lambda: client.auth.refresh_session(body.refresh_token)))
        if not response.session:
            raise HTTPException(status_code=401, detail="Refresh token inválido")

        # Update last_active_at (best-effort)
        if response.user:
            try:
                admin_db = get_admin_client()
                (await anyio.to_thread.run_sync(admin_db.table("noctus_users").update(
                    {"last_active_at": "now()"}
                ).eq("id", str(response.user.id)).execute))
            except Exception as exc:
                logger.warning("auth: last_active_at update failed for user_id=%s (%s); refresh proceeds", response.user.id, exc)

            # Audit log (best-effort)
            try:
                from app.services import audit_service
                await audit_service.log(
                    user_id=str(response.user.id), org_id=None,
                    action="token_refresh", resource_type="user",
                    resource_id=str(response.user.id),
                    request=request,
                )
            except Exception as exc:
                logger.warning("auth: token-refresh audit log failed for user_id=%s (%s)", response.user.id, exc)

        return {
            "access_token": response.session.access_token,
            "refresh_token": response.session.refresh_token,
        }
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — classified, never swallowed
        # 401 ONLY when Supabase Auth rejected the refresh token (invalid /
        # revoked / reused). A transport failure or an Auth 5xx/429 is 503 +
        # Retry-After: the core SPA logs the user out on a refresh 401, so
        # answering 401 for "could not reach Supabase" turned a blip into a
        # forced re-login (2026-10-03).
        if is_authoritative_token_rejection(exc):
            raise HTTPException(status_code=401, detail="Falha ao renovar token") from exc
        raise auth_provider_unavailable(exc) from exc


@router.patch("/profile")
async def update_profile(
    body: ProfileUpdate,
    authorization: Optional[str] = Header(None),
):
    """Update the current user's profile (name, avatar)."""
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    update_data = {k: v for k, v in body.model_dump(mode="json").items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    result = (await anyio.to_thread.run_sync(db.table("noctus_users").update(update_data).eq("id", user.id).execute))
    if not result.data:
        raise HTTPException(status_code=404, detail="Perfil não encontrado")

    return {"data": result.data[0]}


@router.post("/logout")
async def logout(
    authorization: Optional[str] = Header(None),
    scope: Literal["global", "local"] = Query("local"),
):
    """Revoke the caller's GoTrue session upstream.

    ``scope="global"`` (sent EXPLICITLY by the "Sair" control): owner decision
    2026-10-09, logging out of core ends the user's sessions on every product and
    every other device. ``scope="local"`` (the DEFAULT since 2026-10-24: a caller that does not say
    "Sair" -- an expiry handler, a stale bundle in a forgotten tab -- can only
    ever end its own session, never every product's) ends ONLY the session this access token
    belongs to (core's own) -- used when core ends its session for a reason the
    user did not ask for, e.g. its inactivity timer. 🔴 2026-10-23 prod: core's
    30-min inactivity timer, ticking in a forgotten background core tab while the
    user worked in social.noctusai.com, called the GLOBAL logout and signed the
    user out of every product mid-session. A timeout must never be global.

    GoTrue's admin sign_out takes the caller's access-token JWT. A revocation that
    fails is an error response -- never ``ok: true`` over a session still alive.
    """
    user, token = await get_current_user(authorization)
    try:
        (await anyio.to_thread.run_sync(lambda: get_admin_client().auth.admin.sign_out(token, scope=scope)))
    except Exception as exc:
        logger.error("auth: %s sign_out failed user_id=%s", scope, user.id, exc_info=True)
        if is_authoritative_token_rejection(exc):
            # Supabase already considers this token dead -- the session is gone.
            raise HTTPException(status_code=401, detail="Sessão inválida") from exc
        raise HTTPException(status_code=502, detail="Não foi possível encerrar as sessões") from exc

    # The verified-token cache (30 s) would otherwise keep accepting this just-revoked token.
    from noctusai_lib.api.auth.token_cache import discard_token_everywhere
    discard_token_everywhere(token)

    if scope == "local":
        # Only core's own session ended: the user's product sessions and their org
        # selections stay untouched (the selection rows bound to this session_id go
        # inert on their own).
        return {"ok": True}

    # Core's cached per-product SSO sessions would otherwise keep handing out the
    # (now revoked) tokens for up to the cache TTL.
    from app.routers.sso import invalidate_sso_cache_for_user
    invalidate_sso_cache_for_user(getattr(user, "email", None) or "")

    # Platform org picker: logging out of core ends ALL of the user's live selections
    # (ended_by='logout') -- the next login starts clean. The sign-out itself is
    # best-effort, but a selection that could not be ended is logged LOUDLY: the
    # revocation triggers and the session_id binding still keep a stale row inert
    # (a new login never matches it), yet it must be visible.
    try:
        make_org_selection_store(get_admin_client, force_real=True).end(user.id, None, "logout")
    except Exception:
        logger.error("auth: could not end org selections on logout user_id=%s", user.id, exc_info=True)
    return {"ok": True}
