"""
NoctusAI Core — Auth dependencies (framework-deep + core-specific extensions).

Refactored by `projects/core-seed-wiring-v2/` Phase 2 (2026-04-23):
- `get_current_user` / `get_user_client` / `get_admin_client` — inherited from
  `noctusai_seed.create_dependencies()`; byte-identical behavior to the prior
  local implementations.
- `create_sso_token` / `verify_sso_token` — still local this phase; promoted
  to `noctusai_lib.auth` in Phase 4 (ground for future identity-source products).
- Core-specific extensions (`get_current_admin`, `get_current_user_with_permissions`,
  `get_org_id`, `check_org_license`, `get_licensed_product_ids`) — composed on
  top of framework primitives. Same pattern therapy + erp + pf use.

Historical re-exports (`get_supabase_client`, `get_admin_client` from the
database module) preserved for backward compatibility with `tests/conftest.py`
patches. Removing them would require a test-patch sweep; out of scope here.
"""
import logging
import re
from datetime import datetime as dt, timezone
from typing import Optional, Tuple, List

from fastapi import Header, HTTPException

from noctusai_seed import create_database_module, create_dependencies

logger = logging.getLogger(__name__)
from noctusai_lib.api.auth import (
    create_sso_token_factory,
    verify_sso_token_factory,
)

from app.config import settings
from app.database import get_supabase_client, get_admin_client  # noqa: F401 — test-patch compat

# ── Framework inheritance ──────────────────────────────────────────────
# Core uses the "public" schema — noctus_users, organizations, licenses, etc.
# Same settings + same schema as app/database.py; no shared singleton to keep
# module decoupled (both are cheap — DatabaseModule doesn't open connections).
_db = create_database_module(settings, schema="public")
deps = create_dependencies(_db)

# Re-expose framework auth primitives (identical behavior to the former local
# implementations; hits Supabase Auth via `admin.auth.get_user(token)`).
get_current_user = deps.get_current_user
get_user_client = deps.get_user_client


def _parse_timestamp(value: str) -> dt:
    """Parse Supabase timestamp to datetime. Handles '2026-04-09 00:00:00+00' format."""
    ts = str(value).replace("Z", "+00:00").replace(" ", "T")
    ts = re.sub(r'([+-]\d{2})$', r'\1:00', ts)
    return dt.fromisoformat(ts)


# ── Core-specific auth extensions ──────────────────────────────────────

async def get_current_admin(authorization: Optional[str] = Header(None)) -> Tuple:
    """Extract user and verify they have platform admin role.

    Core-specific: checks `noctus_users.role == 'admin'` — the platform-level
    admin flag (not the per-org role). Consumer products would use
    `resolve_sso_role()` instead.
    """
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = db.table("noctus_users").select("role").eq("id", user.id).single().execute()
    if not profile.data or profile.data.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")
    return user, token


async def get_current_user_with_permissions(
    authorization: Optional[str] = Header(None),
) -> Tuple:
    """Authenticate user and return (user, token, permissions_list).

    Resolves the user's org role, looks up the role's permissions in the
    `roles` table (org-specific first, then system fallback), and returns
    the full permission list alongside the standard auth tuple.
    """
    user, token = await get_current_user(authorization)
    db = get_admin_client()

    profile = (
        db.table("noctus_users")
        .select("org_id, org_role")
        .eq("id", user.id)
        .single()
        .execute()
    )
    if not profile.data:
        return user, token, []

    org_id = profile.data.get("org_id")
    role_slug = profile.data.get("org_role", "member")

    permissions: List[str] = []
    role_record = (
        db.table("roles")
        .select("permissions")
        .eq("slug", role_slug)
        .eq("org_id", org_id)
        .execute()
    )

    if not role_record.data:
        role_record = (
            db.table("roles")
            .select("permissions")
            .eq("slug", role_slug)
            .is_("org_id", "null")
            .execute()
        )

    if role_record.data:
        permissions = role_record.data[0].get("permissions", [])

    return user, token, permissions


async def get_org_id(user) -> str:
    """Extract org_id from noctus_users table for the given user.

    Core's source of truth is the `noctus_users` table (not user_metadata,
    which is a cache populated by `/api/sso/session`). Raises 404 if missing.
    """
    db = get_admin_client()
    profile = db.table("noctus_users").select("org_id").eq("id", user.id).single().execute()
    if not profile.data or not profile.data.get("org_id"):
        raise HTTPException(status_code=404, detail="Perfil ou organização não encontrada")
    return profile.data["org_id"]


def check_org_license(db, org_id: str, product_id: str) -> bool:
    """Check if an org has a valid, non-expired license for a product.

    A license is valid when:
    - status = 'active'
    - fim IS NULL (permanent) OR fim > now()
    """
    result = db.table("licenses").select("id, fim").eq(
        "org_id", org_id
    ).eq("product_id", product_id).eq("status", "active").execute()

    if not result.data:
        return False

    now = dt.now(timezone.utc)
    for lic in result.data:
        fim = lic.get("fim")
        if fim is None:
            return True
        try:
            if _parse_timestamp(fim) > now:
                return True
        except (ValueError, TypeError) as exc:
            logger.warning(
                "dependencies: license id=%s has unparseable fim=%r (%s); "
                "skipping in license-validity check",
                lic.get("id"), fim, exc,
            )
            continue

    return False


def get_licensed_product_ids(db, org_id: str) -> list:
    """Get list of product IDs the org has valid licenses for.

    Filters out expired licenses (fim is not null AND fim <= now()).
    """
    result = db.table("licenses").select(
        "product_id, fim"
    ).eq("org_id", org_id).eq("status", "active").execute()

    if not result.data:
        return []

    now = dt.now(timezone.utc)
    valid_ids = []
    for lic in result.data:
        fim = lic.get("fim")
        if fim is None:
            valid_ids.append(lic["product_id"])
        else:
            try:
                if _parse_timestamp(fim) > now:
                    valid_ids.append(lic["product_id"])
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "dependencies: license id=%s has unparseable fim=%r (%s); "
                    "skipping in licensed-product-ids list",
                    lic.get("id"), fim, exc,
                )
                continue
    return valid_ids


# ── SSO JWT primitives (promoted to noctusai_lib.auth in Phase 4) ──────
# Core composes the library factories with its own settings. Behavior
# byte-identical to the prior local implementation; the primitives now
# live in seed for any future identity-source product to reuse.
create_sso_token = create_sso_token_factory(settings)
verify_sso_token = verify_sso_token_factory(settings)
