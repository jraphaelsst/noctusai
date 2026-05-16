"""
Dependencies for Social Wiring.

The seed framework's ``ProductDependencies`` exports ``get_org_id`` /
``get_user_role`` / ``get_user_client`` as plain functions; using them as
``Depends()`` does NOT chain through FastAPI because their positional
``user`` / ``token`` args become required query parameters (loc:
``['query', 'user']``). The canonical pattern is to bind
:func:`noctusai_lib.api.auth.make_get_current_user_org` once at module
load and use the resulting closure-bound dep at every router site.

See ``KB § PATTERNS/backend.md § Auth — canonical pattern`` for the why.
"""
import uuid as _uuid
from types import SimpleNamespace
from typing import Any
from uuid import UUID

from noctusai_seed import create_database_module, create_dependencies
from noctusai_lib.api.auth import (
    first_or_none,  # noqa: F401 — re-exported for product imports
    make_get_current_user,
    make_get_current_user_org,
    resolve_sso_role,  # noqa: F401 — re-exported for product imports
)
from app.config import settings
from app.sqlite_client import SQLiteClient

_sqlite_client = SQLiteClient(settings.sqlite_path)
_db = None
_deps = None
_use_sqlite = settings.database_backend.lower() == "sqlite"
if not _use_sqlite:
    _db = create_database_module(settings, schema="social_wiring")
    _deps = create_dependencies(_db)

# Canonical auth deps — wire via the factory so FastAPI sees only
# ``authorization: Header(None)`` in the dep signature.
#
# Late-binding lambda: the conftest patches ``_db.get_client`` AFTER
# this module imports. Capturing the bound method at module load
# (``make_get_current_user(get_supabase_client)``) would freeze the
# pre-patch reference. The lambda re-resolves on every request so
# both production and test paths see the right client.
if _use_sqlite:
    async def get_current_user():
        return SimpleNamespace(
            id=settings.local_dev_user_id,
            email="local-dev@noctusai.local",
            user_metadata={"org_id": settings.local_dev_org_id},
        )

    async def get_current_user_org():
        user = await get_current_user()
        return user, "local-dev-token", settings.local_dev_org_id
else:
    get_current_user = make_get_current_user(lambda: _db.get_client())
    get_current_user_org = make_get_current_user_org(
        get_current_user,
        lambda u: (u.user_metadata or {}).get("org_id"),
        required=True,
    )

# Plain-call helpers (NOT to be wired via ``Depends(...)``) — kept for
# imperative call-sites and for backward compatibility with existing
# imports. Will emit ``DeprecationWarning`` after Phase 2 lands the
# seed-side warning.
get_user_role = _deps.get_user_role if _deps is not None else (lambda *_args, **_kwargs: "owner")
get_org_id = _deps.get_org_id if _deps is not None else (lambda *_args, **_kwargs: settings.local_dev_org_id)
# Late-binding wrappers so test patches on ``_db.get_*`` reach call sites.
def get_user_client(token: str):
    if _use_sqlite:
        return _sqlite_client
    return _db.get_client(token)


def get_admin_client():
    if _use_sqlite:
        return _sqlite_client
    return _db.get_admin_client()


# Auth-side org_id is sometimes a UUID string, sometimes an opaque
# fixture string (`"test-org-123"`). DB columns are UUID-typed; coerce
# here so call sites don't repeat the try/except. Lifted to this module
# at the N=3 recurrence trigger (upload_router + settings_router +
# videos_router each had a private copy). The user-scoped supabase
# client is RLS-bound by the JWT, not by this UUID — safe to derive a
# deterministic UUID via uuid5 for non-UUID fixture inputs.
def coerce_org_uuid(raw_org: Any) -> UUID:
    """Coerce the auth-side org_id (string or UUID) into a UUID."""
    try:
        return UUID(str(raw_org))
    except (ValueError, TypeError):
        return _uuid.uuid5(_uuid.NAMESPACE_OID, str(raw_org))
