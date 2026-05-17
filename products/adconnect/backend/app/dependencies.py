"""
Shared dependencies for FastAPI routers — seed framework + AdConnect extensions.

Standard deps (``get_current_user``, ``get_user_role``, ``get_admin_client``)
come from the seed framework. AdConnect-specific role resolution lifts the
SSO-aware ``resolve_sso_role`` first, then falls through to the product-native
``user_metadata.role`` (the historical "customer" / "admin" / "owner"
vocabulary used by distributor / brand-admin routers).

Canonical auth pattern (PF retro §e row 1 — formalized 2026-05-11):
The :func:`noctusai_lib.api.auth.make_get_current_user_org` factory binds the
``(user, token, org_id)`` triple resolution at module load. Routers consume the
resulting closure-bound dep via ``Depends(get_current_user_org)`` instead of
the imperative ``Header(authorization) + await get_current_user(authorization)``
shape — see ``KB § PATTERNS/backend.md § Auth — canonical pattern`` (the
original reference adopter was the retired ``youtube-crawler`` product,
consolidated into ``social-wiring`` 2026-05-16).

Migration history: AdConnect's MVP (2026-05-10, commit ``f2987c8``) shipped a
dict-wrapper bridge at ``app/auth_deps.py`` to bound Phase 1's blast-radius
across the seven downstream routers that read ``user["sub"]`` /
``user["role"]`` / ``user["distributorId"]`` / ``user["org_id"]``. This module
replaces the bridge — routers now read those fields from the Supabase
``user.user_metadata`` directly, mirroring the canonical pattern across
ERP / PF / youtube-crawler.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException
from noctusai_seed import create_dependencies
from noctusai_lib.api.auth import (
    first_or_none,  # noqa: F401 — re-exported for product imports
    make_get_current_user,
    make_get_current_user_org,
    make_require_role,
    resolve_sso_role,
)

# Reuse the singleton ``DatabaseModule`` from ``app.database`` rather than
# constructing a second instance. The conftest patches
# ``app.database._db.get_client`` directly + at the
# ``noctusai_seed.database.DatabaseModule`` class level; reusing the same
# instance ensures every auth-dep call path resolves through the patched
# methods (the canonical pattern at ERP/PF patches at the class level only,
# but AdConnect's conftest predates that convention and explicitly relies
# on both the module-attr and class-level patches landing on the same
# underlying ``_db``).
from . import database as _database_module

_db = _database_module._db
deps = create_dependencies(_db)

get_user_role = deps.get_user_role
get_admin_client = deps.get_admin_client


def get_org_id(user: Any) -> Optional[str]:
    """Extract the brand ``org_id`` from the Supabase user metadata.

    The brand ``org_id`` is set in ``auth.users.raw_user_meta_data`` during
    signup (core) + SSO sync (the AdConnect SSO callback mirrors the
    distributor's brand-org assignment into ``user_metadata.org_id``).

    Returns ``None`` when missing; callers decide whether to fall back to
    a single-instance default or 4xx. The canonical
    :func:`make_get_current_user_org` wrapper raises 403 when ``required=True``
    and the metadata is absent.
    """
    metadata = getattr(user, "user_metadata", None) or {}
    return metadata.get("org_id") or None


def resolve_role(user: Any) -> str:
    """Resolve the caller's role for AdConnect.

    Resolution order:
      1. :func:`resolve_sso_role(user)` — owner / admin ``org_role`` or
         ``noctus_role=admin`` returns ``"platform_admin"``.
      2. ``user.user_metadata.role`` — product-native vocabulary
         (``customer`` / ``admin`` / ``owner``).
      3. Fallback → ``"customer"`` — the historical default for
         distributor users.
    """
    sso = resolve_sso_role(user)
    if sso:
        return sso
    metadata = getattr(user, "user_metadata", None) or {}
    return metadata.get("role") or "customer"


# Canonical auth deps — wire via the factory so FastAPI sees only
# ``authorization: Header(None)`` in the dep signature.
#
# Late-binding lambda: the conftest patches ``_db.get_client`` AFTER this
# module imports. Capturing the bound method at module load
# (``make_get_current_user(_db.get_client)``) would freeze the pre-patch
# reference. The lambda re-resolves on every request so both production
# and test paths see the right client.
get_current_user = make_get_current_user(lambda: _db.get_client())
get_current_user_org = make_get_current_user_org(
    get_current_user,
    get_org_id,
    required=False,  # AdConnect has a single-instance brand default;
    # routers fall back to ``DEFAULT_ORG_ID`` when the
    # metadata is absent (matches MVP-era behavior).
)
require_role = make_require_role(get_current_user, resolve_role)


# Late-binding wrapper so test patches on ``_db.get_client`` reach call sites.
def get_user_client(token: str):
    return _db.get_client(token)


__all__ = [
    "first_or_none",
    "get_admin_client",
    "get_current_user",
    "get_current_user_org",
    "get_org_id",
    "get_user_client",
    "get_user_role",
    "require_role",
    "resolve_role",
    "resolve_sso_role",
]
