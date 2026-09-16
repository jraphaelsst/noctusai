"""
Pytest configuration and shared fixtures for Community backend tests.

The seed product uses the framework (noctusai_seed), so patches target
the framework's database module rather than product-level modules.
"""
import sys as _sys
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve().parents[4]
_LIB = _REPO / "seed" / "lib" / "backend"
_FRAMEWORK = _REPO / "seed" / "framework" / "backend"
# Inject BOTH seed package roots — this file previously added only `_LIB`,
# which left `noctusai_seed` unresolvable in a worktree once
# `purge_shadowing_editable_finders` drops the venv's editable finder
# pointing at a sibling checkout (every OTHER product's conftest.py
# already does this; found + fixed while verifying
# `seed-trusted-org-resolution`, 2026-07-14 — mirrors ERP-P7's reference
# fix, see `products/daily-life/backend/tests/conftest.py`).
for _p in (_LIB, _FRAMEWORK):
    if str(_p) not in _sys.path:
        _sys.path.insert(0, str(_p))
import importlib.util as _ilu  # noqa: E402
_spec = _ilu.spec_from_file_location(
    "_bootstrap_conftest_helpers",
    _LIB / "noctusai_lib" / "testing" / "conftest_helpers.py",
)
_mod = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
_mod.purge_shadowing_editable_finders(_LIB)
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

from noctusai_lib.testing import (  # noqa: F401 — re-exported for test imports
    MockSupabaseResponse,
    MockSelectBuilder,
    MockFilterBuilder,
    MockQueryBuilder,
    MockRequestBuilder,
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    AuthClient,
    bind_consent_module_to_mock,
)
from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401


def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: tests that require a live Supabase instance")


# ── Module 1 (Membros/Planos/Aplicações) shared test helpers ────────────
#
# The default `client` fixture's `MockUser(org_id="test-org-123")` — a
# non-UUID opaque string — round-trips through `coerce_org_uuid`'s
# `uuid5(NAMESPACE_OID, ...)` fallback deterministically, so every test
# that doesn't re-bind `auth.get_user` shares the same coerced org UUID.
from uuid import NAMESPACE_OID as _NAMESPACE_OID, uuid5 as _uuid5  # noqa: E402

TEST_USER_ID = "test-user-123"
TEST_ORG_ID = "test-org-123"
ORG_UUID = str(_uuid5(_NAMESPACE_OID, TEST_ORG_ID))


def seed_community_role(client, *, org_role: str | None = None, platform_role: str = "user") -> None:
    """Seed the trusted `public.noctus_users` row `get_community_role` reads.

    `org_role="admin"` also satisfies the seed's platform-admin cascade
    (`owner`/`admin` → `"platform_admin"`) — both paths converge on the
    same `"admin"` community-tier answer. `org_role="moderador"` (or any
    other value) falls through the cascade and is read back verbatim by
    `get_community_role`'s direct query, resolving to `"moderador"`.
    """
    client.mock_supabase.set_table_data(
        "noctus_users",
        [{
            "id": TEST_USER_ID,
            "org_id": TEST_ORG_ID,
            "role": platform_role,
            "org_role": org_role,
        }],
    )


def seed_public_license(client, *, org_id: str = ORG_UUID, slug: str = "community") -> None:
    """Seed `public.products` + `public.licenses` for the two PUBLIC routes
    (`resolve_public_org_id` — see `app/dependencies.py`)."""
    client.mock_supabase.set_table_data(
        "products", [{"id": "prod-community-1", "slug": slug}],
    )
    client.mock_supabase.set_table_data(
        "licenses",
        [{
            "id": "lic-1",
            "product_id": "prod-community-1",
            "org_id": org_id,
            "status": "active",
        }],
    )


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(
        MockUser(org_id="test-org-123")
    ))

    with patch("app.database._db.get_client", return_value=mock_sb), \
         patch("app.database._db.get_core_client", return_value=mock_sb), \
         patch("app.database._db.get_admin_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb):

        from app.main import app
        # Per-fixture re-bind of the seed's consent module to THIS test's
        # mock_sb. Idempotent — safe even if no consent features registered.
        # See KB § PATTERNS/testing.md § Consent-guard product conftest pattern.
        bind_consent_module_to_mock(mock_sb)

        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)
