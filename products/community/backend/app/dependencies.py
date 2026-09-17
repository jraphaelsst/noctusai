"""
Dependencies for Community.

This file is the canonical reference every new product inherits via
``scaffold_product``. The auth dep ``get_current_user_org`` is wired
through :func:`noctusai_lib.api.auth.make_get_current_user_org` (factory
pattern) — using the seed's plain ``get_org_id`` / ``get_user_role``
through ``Depends(...)`` does NOT chain through FastAPI because their
positional ``user`` / ``token`` args become required query parameters.

See ``KB § PATTERNS/backend.md § Auth — canonical pattern`` for the
full why and the deprecation warning that fires on the broken shape.
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any
from uuid import UUID

from fastapi import HTTPException

from noctusai_seed import (
    create_database_module,
    create_dependencies,
    select_get_current_user,
)
from noctusai_lib.api.auth import (
    first_or_none,  # noqa: F401 — re-exported for product imports
    make_get_current_user,
    make_get_current_user_org,
    make_resolve_platform_role,
    resolve_sso_role,  # noqa: F401 — re-exported for product imports
)
from app.config import settings

_db = create_database_module(settings, schema="community")
_deps = create_dependencies(_db)

# Canonical auth deps — wire via the factory so FastAPI sees only
# ``authorization: Header(None)`` in the dep signature.
#
# Late-binding lambdas: tests patch ``_db.get_client`` AFTER this module
# imports. Capturing the bound method at module load would freeze the
# pre-patch reference. The lambda re-resolves on every request so both
# production and test paths see the right client.
# Prod path (Supabase JWT validation). `select_get_current_user`
# transparently swaps in the already-shipped dev-auth dependency when
# `DATABASE_BACKEND=sqlite` AND the dev-auth double-gate is on — zero
# per-product code, parallel-never-modify (the prod path is returned
# untouched in every non-sqlite env). Inherited by every product
# through scaffold_product / propagation.
_prod_get_current_user = make_get_current_user(lambda: _db.get_client())
get_current_user = select_get_current_user(settings, _prod_get_current_user)
# `get_admin_client_fn=lambda: _db.get_core_client()` — NOT get_admin_client().
# `noctus_users` lives in the `public` schema; `get_admin_client()` is scoped
# to THIS product's schema and would 500 with PGRST205 (see
# `seed-trusted-org-resolution`, 2026-07-14 — the make_get_current_user_org
# docstring in noctusai_lib.api.auth has the full rationale + the prod
# incident this mirrors on the ERP side).
get_current_user_org = make_get_current_user_org(
    get_current_user,
    lambda u: (u.user_metadata or {}).get("org_id"),  # fallback only — trusted DB wins
    get_admin_client_fn=lambda: _db.get_core_client(),
    required=True,
)

# Plain-call helpers (NOT to be wired via ``Depends(...)``) — kept for
# imperative call-sites and for backward compatibility.
get_user_role = _deps.get_user_role
get_org_id = _deps.get_org_id


# Late-binding wrappers so test patches on ``_db.get_*`` reach call sites.
def get_user_client(token: str):
    return _db.get_client(token)


def get_admin_client():
    return _db.get_admin_client()


_ERROR_CODES = {
    400: "BAD_REQUEST", 401: "UNAUTHORIZED", 403: "FORBIDDEN",
    404: "NOT_FOUND", 409: "CONFLICT", 422: "VALIDATION_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def http_error(status_code: int, detail: str) -> HTTPException:
    """Build an ``HTTPException`` whose JSON body has a top-level ``detail``
    key — the contract's error shape (``{"detail": "..."}``).

    The seed's global handler (``noctusai_lib.primitives.exceptions.
    http_exception_handler``) reshapes a PLAIN-STRING-``detail``
    ``HTTPException`` into the platform-wide legacy envelope
    (``{"error": {"code", "message"}}``) — no top-level ``detail`` key at
    all. It passes a DICT ``detail`` containing BOTH ``"detail"`` and
    ``"code"`` keys through **verbatim** instead (documented on that
    handler as the escape hatch for exactly this case). Every explicit
    error this module/its routers raise goes through this helper rather
    than a bare ``HTTPException(status_code=..., detail="...")`` so the
    wire shape actually matches what the contract — and the frontend
    built against it in parallel — expect.

    Out of scope: FastAPI's OWN automatic request-body validation
    (missing/malformed fields) still surfaces via the seed's separate
    ``ValidationError`` handler in the same legacy envelope — that is
    platform-wide behavior this product does not override.
    """
    code = _ERROR_CODES.get(status_code, "HTTP_ERROR")
    return HTTPException(status_code=status_code, detail={"detail": detail, "code": code})


# ── Community role gate — admin / moderador (contract §Conventions) ─────
#
# Reuses the seed's trusted-first platform-admin cascade
# (``noctusai_lib.api.auth.make_resolve_platform_role``) — the same
# mechanism ``ProductDependencies.get_user_role`` composes for the
# "team" standard router — rather than inventing a parallel role store.
_resolve_platform_role = make_resolve_platform_role(lambda: _db.get_core_client())


def get_community_role(user: Any) -> str:
    """Resolve the caller's role for THIS product: ``"admin"`` or ``"moderador"``.

    Community defines its own two-tier vocabulary (contract-confirmed:
    "Manager roles: `admin` (everything) and `moderador` (moderation +
    content)"), distinct from the generic org-role vocabulary
    (``owner``/``admin``/``manager``/``member``) the seed's ``team``
    router (``noctusai_seed.routers._create_team_router``) uses for
    invites. A community manager is invited through that SAME router
    with ``role="admin"`` or ``role="moderador"`` in the invite body —
    an arbitrary string the seed's ``attach_user_to_org`` writes
    verbatim to the trusted ``public.noctus_users.org_role`` column.

    Resolution order:
    1. NoctusAI platform admin OR org owner/admin (the seed's
       trusted-first cascade, ``make_resolve_platform_role``) →
       ``"admin"`` — mirrors every other product's role-cascade-trusted
       convention: a platform/org admin is never locked out of a
       product's back office.
    2. Otherwise, read the trusted ``public.noctus_users.org_role`` for
       this user DIRECTLY (not through
       ``ProductDependencies.get_user_role``, which collapses any
       non-admin ``org_role`` to the metadata ``"role"`` key — a
       different, non-mirrored field — and would silently lose the
       "moderador" distinction). The literal value ``"admin"`` maps to
       ``"admin"``; anything else (including an absent row, a stale
       metadata-only member, or a value this product hasn't defined)
       degrades to ``"moderador"`` — the least-privileged of the two
       tiers, so an unrecognized value can read but never write.
    """
    if _resolve_platform_role(user) == "platform_admin":
        return "admin"
    core = _db.get_core_client()
    result = (
        core.table("noctus_users")
        .select("org_role")
        .eq("id", str(getattr(user, "id", "")))
        .limit(1)
        .execute()
    )
    rows = result.data or []
    org_role = rows[0].get("org_role") if rows else None
    return "admin" if org_role == "admin" else "moderador"


def require_admin(role: str, *, action: str) -> None:
    """403 unless ``role == "admin"`` — the contract's write gate.

    ``action`` is a pt-BR infinitive phrase so the message matches the
    contract's ``"Apenas administradores podem …"`` shape verbatim
    (e.g. ``action="criar planos"`` → "Apenas administradores podem
    criar planos.").
    """
    if role != "admin":
        raise http_error(403, f"Apenas administradores podem {action}.")


# ── Public-endpoint org resolution (contract §Aplicações, PUBLIC routes) ─
#
# Community is single-tenant by product decision (MASTER-PROMPT.md:
# "Single community (no multi-tenancy beyond the seed's org scoping)"),
# so its schema holds exactly one org's rows — but an anonymous request
# carries no JWT, hence no `current_org_id()`. Rather than hardcode an
# org id, this resolves the org the SAME way the platform already models
# "which org licenses this product": `public.products.slug` joined to
# `public.licenses` (status='active') — the exact table pair
# `snapshot_product_usage()` (products/core/backend/migrations/
# 001_noctusai_core.sql) already walks for per-product usage reporting.
# No new table, no invented mechanism.
_COMMUNITY_PRODUCT_SLUG = "community"


def resolve_public_org_id() -> UUID:
    """Resolve the single org licensed for this product, for anon routes.

    Raises:
        HTTPException(503): no product row, no active license, or more
            than one active license (a genuine misconfiguration for a
            single-tenant product) — surfaced loudly rather than
            guessing which org an anonymous submission belongs to.
    """
    core = _db.get_core_client()
    product = (
        core.table("products")
        .select("id")
        .eq("slug", _COMMUNITY_PRODUCT_SLUG)
        .limit(1)
        .execute()
    )
    product_rows = product.data or []
    if not product_rows:
        raise http_error(503, "Formulário de inscrição indisponível no momento.")
    product_id = product_rows[0]["id"]
    licenses = (
        core.table("licenses")
        .select("org_id")
        .eq("product_id", product_id)
        .eq("status", "active")
        .execute()
    )
    license_rows = licenses.data or []
    if len(license_rows) != 1:
        raise http_error(503, "Formulário de inscrição indisponível no momento.")
    return coerce_org_uuid(license_rows[0]["org_id"])


def coerce_org_uuid(raw_org: Any) -> UUID:
    """Coerce the auth-side org_id into a UUID.

    Auth-side ``org_id`` is sometimes a real UUID string, sometimes an
    opaque test fixture (``"test-org-123"``). DB columns are UUID-typed,
    so coerce at the boundary. Non-UUID inputs map to a deterministic
    ``uuid5(NAMESPACE_OID, raw)`` so the same fixture always lands on
    the same row. The user-scoped Supabase client is RLS-bound by the
    JWT, not by this UUID — safe to derive deterministically.

    Lifted to the seed at the N=3 recurrence trigger (youtube-crawler's
    upload + settings + videos routers each had a private copy before
    being lifted to a single helper). Now every new product inherits it.
    """
    try:
        return UUID(str(raw_org))
    except (ValueError, TypeError):
        return _uuid.uuid5(_uuid.NAMESPACE_OID, str(raw_org))


# ── Module 3: WhatsApp (community-m3-contract.md, D4) ─────────────────
#
# Community gets its OWN WAHA session on its OWN instance (D4) — a
# separate container from whatever other product's WAHA session exists.
# `get_whatsapp_client()` is the seed's Fake+Real+factory
# (`KB § PATTERNS/backend/seed-fake-real-adapter.md`): an unset
# `community_waha_base_url` returns `FakeWahaClient`, so this product
# boots and its tests pass with zero real WAHA credentials.


def actor_uuid(user: Any) -> UUID | None:
    """Coerce the ACTING user's id to a UUID for audit-trail columns
    (`proposto_por` / `confirmado_por` / `criada_por` / `resolvido_por`).

    Same test-fixture-compatible coercion `coerce_org_uuid` applies to
    `org_id` (a real Supabase auth user id IS a UUID in production; test
    fixtures use an opaque non-UUID label like `"test-user-123"`),
    applied here to the acting user instead of the org.
    """
    raw = getattr(user, "id", None)
    if not raw:
        return None
    return coerce_org_uuid(raw)


def get_community_waha_client():
    from noctusai_lib.integrations.whatsapp import get_whatsapp_client

    return get_whatsapp_client(
        base_url=settings.community_waha_base_url or None,
        api_key=settings.community_waha_api_key or None,
        session=settings.community_waha_session,
        external_base_url=settings.community_waha_external_base_url or None,
    )
