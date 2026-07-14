"""
Shared dependencies for FastAPI routers — seed framework + ERP extensions.

Standard deps (get_current_user, get_user_role, get_user_client, get_admin_client)
come from the seed framework. ERP-specific deps (get_org_id with required param,
log_action) are defined here.

Canonical auth pattern (PF retro §e row 1 — formalized 2026-05-11):
The :func:`noctusai_lib.api.auth.make_get_current_user_org` factory binds the
``(user, token, org_id)`` triple resolution at module load. Routers consume the
resulting closure-bound dep via ``Depends(get_current_user_org)`` instead of
the imperative ``Header(authorization) + await get_current_user(authorization)``
shape — see ``KB § PATTERNS/backend.md § Auth — canonical pattern`` (the
original reference adopter was the retired ``youtube-crawler`` product,
consolidated into ``social-wiring`` 2026-05-16).
"""
import logging
from typing import Optional

from fastapi import HTTPException
from noctusai_seed import create_database_module, create_dependencies
from noctusai_lib.domain.action_log import log_action as _shared_log_action
from noctusai_lib.api.auth import (
    first_or_none,  # noqa: F401 — re-exported for product imports
    make_get_current_user,
    make_get_current_user_org,
    make_require_role,
    make_resolve_platform_role,
)
from app.config import settings

_db = create_database_module(settings, schema="erp")
deps = create_dependencies(_db)

get_user_role = deps.get_user_role
get_user_client = deps.get_user_client
get_admin_client = deps.get_admin_client

logger = logging.getLogger(__name__)


def get_org_id(user, *, required: bool = False) -> Optional[str]:
    """Extract org_id from user metadata.

    org_id is set in auth.users.raw_user_meta_data during signup (core)
    and user creation (ERP profiles router). Available on every request
    without extra DB queries.

    By default returns None if missing (backwards-compatible).
    Pass required=True in endpoints where org_id is strictly needed.
    """
    org_id = (user.user_metadata or {}).get("org_id")
    if not org_id and required:
        raise HTTPException(status_code=400, detail="Organizacao nao encontrada no perfil do usuario")
    return org_id or None


def resolve_org_id_db(user_id: str) -> Optional[str]:
    """Single source of truth for a caller's org: the DB, not the JWT.

    Reads ``public.noctus_users`` — the SAME row RLS resolves via
    ``current_org_id()`` — so the app's notion of org can never drift from
    what RLS enforces. Unlike :func:`get_org_id` (which reads the JWT
    ``user_metadata`` and goes stale until the user re-authenticates), this
    reflects a provisioning change immediately.

    Uses the CORE client — ``noctus_users`` lives in the ``public`` schema, NOT
    the product's ``erp`` schema. The erp-scoped admin client would resolve
    ``.table("noctus_users")`` to ``erp.noctus_users`` and PGRST205 → 500
    (regression shipped + caught in prod 2026-07-07; the schema-agnostic mock
    hid it). ``get_core_client`` targets ``public`` with the service role
    (bypasses RLS), reading the single PK row.
    Returns None for an unprovisioned user (no noctus_users row / null org).
    """
    core = _db.get_core_client()
    res = (
        core.table("noctus_users")
        .select("org_id")
        .eq("id", user_id)
        .limit(1)
        .execute()
    )
    if res.data and res.data[0].get("org_id"):
        return res.data[0]["org_id"]
    return None


# Canonical auth deps — wire via the factory so FastAPI sees only
# ``authorization: Header(None)`` in the dep signature.
#
# Late-binding lambda: the conftest patches ``_db.get_client`` AFTER this
# module imports. Capturing the bound method at module load
# (``make_get_current_user(_db.get_client)``) would freeze the pre-patch
# reference. The lambda re-resolves on every request so both production
# and test paths see the right client.
get_current_user = make_get_current_user(lambda: _db.get_client())
# `get_admin_client_fn=lambda: _db.get_core_client()` — same client
# `resolve_org_id_db` above already uses. `noctus_users` lives in the
# `public` schema; the erp-scoped admin client would 500 with PGRST205
# (the exact regression `resolve_org_id_db`'s docstring documents,
# 2026-07-07). See `seed-trusted-org-resolution` (2026-07-14) — the
# make_get_current_user_org docstring in noctusai_lib.api.auth has the
# full trust-model rationale.
get_current_user_org = make_get_current_user_org(
    get_current_user,
    lambda u: get_org_id(u),  # fallback only — trusted DB wins
    get_admin_client_fn=lambda: _db.get_core_client(),
    required=True,
    missing_status=400,
    missing_detail="Organizacao nao encontrada no perfil do usuario",
)

# Trusted-first platform-admin cascade (``role-cascade-trusted``, 2026-07-14)
# — same ``get_core_client`` client `get_current_user_org` already uses;
# `noctus_users` lives in `public`, not `erp`. See
# `noctusai_lib.api.auth.make_resolve_platform_role`'s docstring for the
# full trust-model rationale (mirrors `make_get_current_user_org`'s).
resolve_platform_role = make_resolve_platform_role(lambda: _db.get_core_client())


def log_action(user_id: str, tipo_acao: str, tipo_entidade: str,
               entidade_id: Optional[str] = None, descricao: str = "", detalhes: Optional[dict] = None):
    """Server-side action logging. Always runs with service role."""
    _shared_log_action(
        get_admin_client(), "user_actions_log", "usuario_id",
        user_id, tipo_acao, tipo_entidade, entidade_id, descricao, detalhes,
    )


# ---------------------------------------------------------------------------
# Role resolution + `require_role` factory wiring
# ---------------------------------------------------------------------------
# Phase 3 (erp-wiring 2026-05-11) — Pattern F continuation. Replaces the
# bespoke `vista_showcase.require_admin` SSO-aware gate and the inline
# `metas_digest` role check with seed `make_require_role` composition.
#
# ERP's role resolution differs from the seed default because it preserves
# *both* historical metadata keys (`erp_role` first, `noctus_role` second)
# while still letting the platform-admin cascade short-circuit to
# "platform_admin" for cross-product SSO admins. The seed primitive only
# consumes the resolver — composition stays in product code.
#
# `role-cascade-trusted` (2026-07-14): closed the role-spoof hole AND added
# the missing ERP-scoped elevation tier. Resolution order is now:
#   1. Trusted platform-admin cascade (`public.noctus_users`, via
#      `resolve_platform_role`) — a Noctus platform admin is admin in
#      EVERY product, including ERP. Trusted DB, never spoofable
#      `user_metadata`.
#   2. Trusted ERP-scoped elevation (`public.has_role(user.id,
#      'admin'::erp.app_role)`, backed by `erp.user_roles`) — an ERP admin
#      explicitly granted THIS user 'admin' WITHIN ERP (see
#      `POST /api/profiles/{user_id}/roles`). Elevate-only + product-scoped
#      by construction: it is consulted ONLY after step 1 has already
#      returned (so it can never demote a platform admin), and it reads
#      `erp.user_roles` — a table no other product's role resolver touches
#      (so it can never cascade elsewhere).
#   3. `erp.user_roles` base row (`corretor` / `coordenador` / `dev`) when
#      one exists — the ERP-native role vocabulary, trusted DB.
#   4. `user_metadata.erp_role` / `.noctus_role` — legacy, spoofable,
#      transition-only fallback (warned). `"user"` sentinel default
#      otherwise; downstream `require_role(*allowed)` will 403.
#
# Both DB legs (2 + 3) fail CLOSED on a genuine error — the exception
# propagates rather than silently falling through to the spoofable
# metadata fallback, mirroring `make_resolve_platform_role`'s documented
# trust model for the exact same reason: falling back in the error branch
# would reopen the hole this change closes, in the one place a regression
# would hide silently.


def get_erp_user_role(user) -> str:
    """Resolve ERP-tier role for a user — trusted-first, product-scoped override.

    See the module-level comment above for the full resolution order + the
    fail-closed rationale on the two DB legs.
    """
    platform_role = resolve_platform_role(user)
    if platform_role == "platform_admin":
        return platform_role

    # `public.has_role` lives in the `public` schema (NOT `erp`) — the
    # erp-scoped admin client would resolve it against the wrong schema
    # and 500 with PGRST205 (the same class of regression documented on
    # `resolve_org_id_db` above). Use the core client, same as
    # `resolve_platform_role`.
    core = _db.get_core_client()
    try:
        elevated = core.rpc(
            "has_role", {"_user_id": user.id, "_role": "admin"}
        ).execute()
    except Exception:
        logger.error(
            "erp_has_role_lookup_error user_id=%s — failing closed "
            "(NOT treating as elevated)",
            user.id, exc_info=True,
        )
        raise
    if elevated.data:
        return "admin"

    admin = get_admin_client()  # erp-scoped — erp.user_roles lives here
    try:
        base_row = (
            admin.table("user_roles")
            .select("role")
            .eq("user_id", user.id)
            .limit(1)
            .execute()
        )
    except Exception:
        logger.error(
            "erp_user_roles_lookup_error user_id=%s — failing closed",
            user.id, exc_info=True,
        )
        raise
    if base_row.data:
        return base_row.data[0]["role"]

    metadata = user.user_metadata or {}
    fallback = metadata.get("erp_role") or metadata.get("noctus_role")
    if fallback:
        logger.warning(
            "erp_role_lookup_empty user_id=%s — no erp.user_roles row, "
            "falling back to user_metadata resolver (role=%r)",
            user.id, fallback,
        )
    return fallback or "user"


# Canonical `require_role(*allowed)` factory — bound once at module load to
# this product's `get_current_user` (Supabase-client-aware) and ERP role
# resolver. Routers consume via `Depends(require_role("admin", "owner"))`.
require_role = make_require_role(get_current_user, get_erp_user_role)
