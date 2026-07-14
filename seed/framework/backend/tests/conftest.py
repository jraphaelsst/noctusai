"""Shared fixtures for seed framework unit tests.

The framework has no DB, no Supabase, no network — every factory under
`noctusai_seed/` is a pure function of its inputs. Fixtures here provide
the minimum plausible `deps` / `settings` / `product_name` so tests can
instantiate routers and inspect their surface without integration harness.

-----------------------------------------------------------------------------
Parallel-worktree venv shadowing (defensive — mirrors seed/lib/backend/tests/conftest.py)
-----------------------------------------------------------------------------
Fix-on-contact (`role-cascade-trusted`, 2026-07-14): this conftest only
inserted `sys.path` entries — it never purged a shadowing editable finder.
When the shared host venv carries an editable install of `noctusai_lib` /
`noctusai_seed` pointing at ANOTHER worktree, that meta-path finder wins
over the `sys.path` insertion below regardless of order (editable-install
finders are consulted before `sys.path`-based resolution for an
already-registered package), so this suite silently exercised whatever
`noctusai_lib` happened to be installed, not this worktree's — surfaced
while adding `make_resolve_platform_role` here (a fresh worktree-only
symbol failed to import with `ImportError` pointing at the OTHER
worktree's `seed/lib/backend/noctusai_lib/api/auth/__init__.py`). Mirrors
the exact fix `seed-trusted-org-resolution` (2026-07-14) already applied to
`products/seed/backend/tests/conftest.py` + `therapy-platform`'s — this
conftest was the one product/package-family conftest left unfixed.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make sibling lib + framework importable regardless of cwd.
_FRAMEWORK = Path(__file__).resolve().parents[1]  # <repo>/seed/framework/backend
# Fix-on-contact: was `_FRAMEWORK.parents[0] / "lib"` == <repo>/seed/framework/lib
# — a path that doesn't exist (`noctusai_lib` actually lives at
# <repo>/seed/lib/backend). The stale sys.path entry silently never resolved
# `noctusai_lib`; this only stayed invisible because the shared venv's
# editable-install finder happened to fill the gap for whichever worktree
# owned it. Surfaced by the same purge-helper fix above.
_LIB = _FRAMEWORK.parents[1] / "lib" / "backend"  # <repo>/seed/lib/backend
for p in (_LIB, _FRAMEWORK):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location(
    "_bootstrap_conftest_helpers",
    _LIB / "noctusai_lib" / "testing" / "conftest_helpers.py",
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_mod.purge_shadowing_editable_finders(_LIB)


@pytest.fixture
def product_name() -> str:
    return "Test Product"


@pytest.fixture
def version() -> str:
    return "9.9.9"


@pytest.fixture
def fake_settings():
    """Minimum settings surface the team / notificacoes routers read."""

    class _FakeSettings:
        cors_origins = "http://localhost:3000"
        cors_origins_list = ["http://localhost:3000"]
        debug = True
        is_production = False
        sentry_dsn = None
        product_slug = "test"
        supabase_url = "http://localhost:54321"
        supabase_anon_key = "anon"
        supabase_service_role_key = "service"

    return _FakeSettings()


@pytest.fixture
def fake_deps():
    """A `ProductDependencies`-shaped mock. Routers only call methods;
    they never reach into private attributes."""
    deps = MagicMock()
    deps.get_current_user = MagicMock()
    deps.get_user_role = MagicMock(return_value="owner")
    deps.get_org_id = MagicMock(return_value="org-123")
    deps.get_admin_client = MagicMock()
    deps.get_core_client = MagicMock()
    deps.get_user_client = MagicMock()
    # Team router reads `deps._db.schema` (the public accessor promoted
    # from `_schema` as part of the Phase 0 proposal). Mirror that shape
    # so router execution paths don't blow up; wiring is what we assert.
    deps._db = MagicMock()
    deps._db.schema = "test"
    return deps
