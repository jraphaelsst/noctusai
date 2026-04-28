"""Shared fixtures for seed framework unit tests.

The framework has no DB, no Supabase, no network — every factory under
`noctusai_seed/` is a pure function of its inputs. Fixtures here provide
the minimum plausible `deps` / `settings` / `product_name` so tests can
instantiate routers and inspect their surface without integration harness.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make sibling lib + framework importable regardless of cwd.
_FRAMEWORK = Path(__file__).resolve().parents[1]
_LIB = _FRAMEWORK.parents[0] / "lib"
for p in (_LIB, _FRAMEWORK):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


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
