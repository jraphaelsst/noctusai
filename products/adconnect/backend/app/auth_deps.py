"""
AdConnect auth dependencies — Option A (distributor-as-noc-user).

Phase 1 of `adconnect-mvp-implementation`: replaces the previous custom-JWT
scaffold (HS256 bearer tokens, in-memory `store.users`, `app/security.py`
bcrypt helpers) with the seed framework's standard SSO surface.

Why this module still exists (rather than being removed outright):
seven downstream routers (admin, orders, financial, rewards, sellout,
distributors, auth itself) currently import `get_current_user` /
`require_role` from `..auth_deps`. Those routers stay mock-backed until
their respective phases (2-6) swap them. This module bridges the seed-side
auth dep into the dict-shaped contract those routers expect, so the auth
swap doesn't cascade into Phase 1's blast-radius. The module is a slated
removal at Phase 6 close, by which point the last mock-backed router has
been swapped. See `findings.md → mistakes-slips → "Brief vs reality on
auth_deps.py removal"` for the full triage.

The dict-shaped user this module yields has the keys downstream routers
read: `sub` (user id), `email`, `role` (resolved via SSO), `distributorId`
(the user's primary distributor membership, or None). `distributorId` is
populated lazily — this dep does NOT query the membership table on every
request; routers that need fine-grained membership info (Phase 2-6) will
move to the proper Supabase-backed deps directly.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, Header, HTTPException
from noctusai_lib.api.auth import (
    make_get_current_user,
    make_require_role,
    resolve_sso_role,
)

from . import database as _database


# ---------------------------------------------------------------------------
# Seed-backed primitives
# ---------------------------------------------------------------------------


def _get_supabase_client(*args, **kwargs):
    """Defer the lookup of the Supabase client factory until call time.

    Going through `_database._db.get_client(...)` resolves the
    `DatabaseModule.get_client` method via the class MRO at every call,
    so `tests/conftest.py`'s patch on
    `noctusai_seed.database.DatabaseModule.get_client` takes effect.
    Capturing the bound method at module-import time would freeze the
    pre-patch reference, defeating the test fixture.
    """
    return _database._db.get_client(*args, **kwargs)


# Product-bound: closes over AdConnect's Supabase client factory.
_seed_get_current_user = make_get_current_user(_get_supabase_client)


def _resolve_role(user) -> str:
    """SSO-aware role resolver.

    Resolution order:
      1. `resolve_sso_role(user)` — owner/admin org_role or noctus_role=admin
         → 'platform_admin'.
      2. `user.user_metadata.role` → product-native role.
      3. fallback → 'customer' (the historical default for distributor users).
    """
    sso = resolve_sso_role(user)
    if sso:
        return sso
    metadata = getattr(user, "user_metadata", None) or {}
    return metadata.get("role") or "customer"


_seed_require_role = make_require_role(_seed_get_current_user, _resolve_role)


# ---------------------------------------------------------------------------
# Dict-shaped wrapper (compat for downstream routers)
# ---------------------------------------------------------------------------


async def get_current_user(
    authorization: Optional[str] = Header(None),
) -> dict[str, Any]:
    """Yield a dict-shaped user record compatible with the legacy callers.

    Downstream routers (orders, rewards, financial, sellout, distributors,
    admin) currently read `user["role"]`, `user["sub"]`, `user["distributorId"]`,
    `user["org_id"]`. This wrapper preserves that surface while sourcing
    the underlying user via the seed's SSO-aware get_current_user. Once
    those routers are swapped to the Supabase-backed shape (Phases 2-6),
    they can move to `noctusai_lib.api.auth.make_get_current_user_org`
    directly.
    """
    user, _token = await _seed_get_current_user(authorization)
    metadata = getattr(user, "user_metadata", None) or {}
    return {
        "sub": getattr(user, "id", None),
        "email": getattr(user, "email", None),
        "role": _resolve_role(user),
        # Best-effort — the JWT may carry a `distributor_id` claim if the
        # SSO callback chose to mirror it. Routers that need authoritative
        # membership look up `adconnect.distributor_memberships` directly.
        "distributorId": metadata.get("distributor_id"),
        # Brand-org id — admin endpoints (Phase 6) scope by this. Sourced
        # from the SSO-synced user_metadata; absent metadata → caller falls
        # back to the product-default org.
        "org_id": metadata.get("org_id"),
        "_user": user,
    }


def require_role(*allowed_roles: str):
    """Factory: returns a Depends-able dep that 403s on role mismatch.

    Mirrors the previous `auth_deps.require_role` API. Internally re-uses
    the seed's `make_require_role`, then re-shapes the result into the
    legacy dict format.
    """
    seed_dep = _seed_require_role(*allowed_roles)

    async def _checker(
        authorization: Optional[str] = Header(None),
    ) -> dict[str, Any]:
        user, _token, role = await seed_dep(authorization)
        metadata = getattr(user, "user_metadata", None) or {}
        return {
            "sub": getattr(user, "id", None),
            "email": getattr(user, "email", None),
            "role": role,
            "distributorId": metadata.get("distributor_id"),
            "org_id": metadata.get("org_id"),
            "_user": user,
        }

    return _checker
