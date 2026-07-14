"""Dependencies for Daily Life — delegates to framework + factory-bound auth.

The seed framework's ``ProductDependencies`` exports ``get_org_id`` /
``get_user_role`` / ``get_user_client`` as plain functions; using them as
``Depends()`` does NOT chain through FastAPI because their positional
``user`` / ``token`` args become required query parameters. The canonical
pattern is to bind :func:`noctusai_lib.api.auth.make_get_current_user_org`
once at module load and use the resulting closure-bound dep at every
router site (Pattern F adoption — daily-life-wiring Phase 1, 2026-05-11).

See ``KB § PATTERNS/backend.md § Auth — canonical pattern`` for the why.
"""
from __future__ import annotations

import uuid as _uuid
from typing import Any
from uuid import UUID

from noctusai_seed import create_dependencies, create_database_module
from noctusai_lib.api.auth import (
    first_or_none,  # noqa: F401 — re-exported for product imports
    make_get_current_user,
    make_get_current_user_org,
    resolve_sso_role,  # noqa: F401 — re-exported for product imports
)
from app.config import settings

_db = create_database_module(settings, schema="daily_life")
deps = create_dependencies(_db)

# Canonical auth deps — wire via the factory so FastAPI sees only
# ``authorization: Header(None)`` in the dep signature.
#
# Late-binding lambda: tests patch ``_db.get_client`` AFTER this module
# imports. Capturing the bound method at module load would freeze the
# pre-patch reference. The lambda re-resolves on every request so both
# production and test paths see the right client.
get_current_user = make_get_current_user(lambda: _db.get_client())
# `get_admin_client_fn=lambda: _db.get_core_client()` — NOT get_admin_client().
# `noctus_users` lives in the `public` schema; `get_admin_client()` is scoped
# to THIS product's schema and would 500 with PGRST205 (see
# `seed-trusted-org-resolution`, 2026-07-14 — the make_get_current_user_org
# docstring in noctusai_lib.api.auth has the full rationale).
get_current_user_org = make_get_current_user_org(
    get_current_user,
    lambda u: (u.user_metadata or {}).get("org_id"),  # fallback only — trusted DB wins
    get_admin_client_fn=lambda: _db.get_core_client(),
    required=True,
)

# Plain-call helpers (NOT to be wired via ``Depends(...)``) — kept for
# imperative call-sites and backward compatibility with existing imports.
get_user_role = deps.get_user_role
get_org_id = deps.get_org_id


# Late-binding wrappers so test patches on ``_db.get_*`` reach call sites.
def get_user_client(token: str):
    return _db.get_client(token)


def get_admin_client():
    return _db.get_admin_client()


def coerce_org_uuid(raw_org: Any) -> UUID:
    """Coerce the auth-side org_id into a UUID.

    Auth-side ``org_id`` is sometimes a real UUID string, sometimes an
    opaque test fixture (``"test-org-123"``). DB columns are UUID-typed,
    so coerce at the boundary. Non-UUID inputs map to a deterministic
    ``uuid5(NAMESPACE_OID, raw)`` so the same fixture always lands on
    the same row. The user-scoped Supabase client is RLS-bound by the
    JWT, not by this UUID — safe to derive deterministically.

    Mirrors the seed reference at ``products/seed/backend/app/dependencies.py``.
    """
    try:
        return UUID(str(raw_org))
    except (ValueError, TypeError):
        return _uuid.uuid5(_uuid.NAMESPACE_OID, str(raw_org))
