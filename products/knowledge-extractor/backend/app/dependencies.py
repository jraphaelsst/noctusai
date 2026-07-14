"""Dependencies for Knowledge Extractor — mirrors the seed canonical (auth factory).

The auth dep ``get_current_user_org`` is wired through
:func:`noctusai_lib.api.auth.make_get_current_user_org` (factory pattern) — using
the plain ``get_org_id`` through ``Depends(...)`` does NOT chain through FastAPI
because its positional ``user`` / ``token`` args become required query params.
See ``KB § PATTERNS/backend.md § Auth — canonical pattern``.
"""
from __future__ import annotations

import uuid as _uuid
from pathlib import Path
from typing import Any
from uuid import UUID

from noctusai_seed import (
    create_database_module,
    create_dependencies,
    select_get_current_user,
)
from noctusai_lib.api.auth import (
    first_or_none,  # noqa: F401 — re-exported for product imports
    make_get_current_user,
    make_get_current_user_org,
    resolve_sso_role,  # noqa: F401 — re-exported for product imports
)
from app.config import settings

_db = create_database_module(settings, schema="knowledge_extractor")
_deps = create_dependencies(_db)

# Canonical auth deps — wire via the factory so FastAPI sees only
# ``authorization: Header(None)`` in the dep signature. Late-binding lambdas
# so tests that patch ``_db.get_client`` after import still resolve correctly.
_prod_get_current_user = make_get_current_user(lambda: _db.get_client())
get_current_user = select_get_current_user(settings, _prod_get_current_user)
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

# Plain-call helpers (NOT to be wired via ``Depends(...)``).
get_user_role = _deps.get_user_role
get_org_id = _deps.get_org_id


def get_user_client(token: str):
    return _db.get_client(token)


def get_admin_client():
    return _db.get_admin_client()


def coerce_org_uuid(raw_org: Any) -> UUID:
    """Coerce the auth-side org_id into a UUID (deterministic for opaque fixtures)."""
    try:
        return UUID(str(raw_org))
    except (ValueError, TypeError):
        return _uuid.uuid5(_uuid.NAMESPACE_OID, str(raw_org))


def get_data_dir() -> Path:
    """The KE data directory (transcripts / summaries / methodology live here).

    A DI seam: router tests override this to a temp dir via
    ``app.dependency_overrides[get_data_dir]`` — never monkeypatching our code.
    """
    return settings.data_path
