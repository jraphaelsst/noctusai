"""
Dependencies for Personal Finance.

The seed framework's ``ProductDependencies`` exports ``get_org_id`` /
``get_user_role`` / ``get_user_client`` as plain functions; using them as
``Depends()`` does NOT chain through FastAPI because their positional
``user`` / ``token`` args become required query parameters (loc:
``['query', 'user']``). The canonical pattern is to bind
:func:`noctusai_lib.api.auth.make_get_current_user_org` once at module
load and use the resulting closure-bound dep at every router site.

PF was the originator of ``make_get_current_user_org`` (per memory
``feedback_auth_factory_pattern``) but until 2026-05-11 still shipped the
inline async wrapper. This migration (``pf-auth-factory-migration``)
lifts PF onto the canonical factory shape, mirroring the original
reference adopter (retired ``youtube-crawler`` product, consolidated
into ``social-wiring`` 2026-05-16).

See ``KB § PATTERNS/backend.md § Auth — canonical pattern`` for the why.
"""
from noctusai_seed import create_dependencies, create_database_module
from noctusai_lib.api.auth import (
    first_or_none,  # noqa: F401 — re-exported for product imports
    make_get_current_user,
    make_get_current_user_org,
    resolve_sso_role,  # noqa: F401 — re-exported for product imports
)
from app.config import settings

_db = create_database_module(settings, schema="personal-finance")
deps = create_dependencies(_db)

# Canonical auth deps — wire via the factory so FastAPI sees only
# ``authorization: Header(None)`` in the dep signature.
#
# Late-binding lambda: the conftest patches ``_db.get_client`` AFTER
# this module imports. Capturing the bound method at module load
# (``make_get_current_user(get_supabase_client)``) would freeze the
# pre-patch reference. The lambda re-resolves on every request so
# both production and test paths see the right client.
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
# imperative call-sites and for backward compatibility with existing
# imports.
get_user_role = deps.get_user_role
get_admin_client = deps.get_admin_client


# Late-binding wrapper so test patches on ``_db.get_client`` reach call sites.
def get_user_client(token: str):
    return _db.get_client(token)
