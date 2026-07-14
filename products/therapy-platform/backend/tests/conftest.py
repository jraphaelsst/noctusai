"""
Pytest fixtures for the Therapy Platform backend.

Uses shared mock infrastructure from noctusai_lib.testing. Re-exports
all shared classes for backwards compatibility (tests import from conftest).

Key difference from ERP/PF: no org_id. Instead, users have roles
(platform_admin, clinic_admin, therapist, patient) and optional clinic_id.
"""
# MOCK-SELECT-PREDICATE-FIX follow-up: pre-populate Supabase env vars BEFORE
# `app.main` is imported by `noctusai_lib.testing.pytest_plugin` at session
# start. Without these defaults, BackgroundTask paths that call
# `app.database.get_core_client()` / `get_admin_client()` (e.g. `ai_pipeline.
# on_observation_change`, `process_session_end`) try to instantiate a real
# Supabase client and crash on "supabase_url is required", surfacing as test
# failures even though the test-fixture mock SHOULD have been used. The
# per-fixture `patch(...)` patches on `DatabaseModule.<method>` don't reach
# the bound-method bindings captured at module-import time. Setting these
# placeholder env vars lets `make_supabase_client` succeed; the actual data
# IO still routes through the mock via `patcher4/5/6` in
# `_make_client_context`. Tests asserting real network IO live under
# `tests/realdb/` and use their own env probe.
import os as _os
_os.environ.setdefault("SUPABASE_URL", "http://test.local")
# Supabase client validates the key as a JWT regex: header.body.signature
# (`^[A-Za-z0-9-_=]+\.[A-Za-z0-9-_=]+\.?[A-Za-z0-9-_.+/=]*$`). Plain "test"
# fails with "Invalid API key" at module-import. Use a minimal valid-shape
# placeholder. NO real secrets — this never reaches a real Supabase.
_FAKE_JWT = "aaa.bbb.ccc"
_os.environ.setdefault("SUPABASE_ANON_KEY", _FAKE_JWT)
_os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", _FAKE_JWT)

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

from noctusai_lib.testing import (
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

# Note: `app.main` is auto-imported at session start by
# `noctusai_lib.testing.pytest_plugin` (registered via the `pytest11`
# entry point in seed-lib's pyproject.toml). That triggers
# `create_product_app(consent_features=...)`, which loads the consent
# catalog for unit tests that import services directly. No per-product
# bootstrap line needed here.

# Re-export all shared classes so existing test imports
# (e.g. `from tests.conftest import MockSupabaseClient`) keep working.
__all__ = [
    "MockSupabaseResponse",
    "MockSelectBuilder",
    "MockFilterBuilder",
    "MockQueryBuilder",
    "MockRequestBuilder",
    "MockSupabaseClient",
    "MockUser",
    "MockUserResponse",
    "AuthClient",
]


def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: tests that require a live Supabase instance")


def _make_client_context(role="therapist", clinic_id=None):
    """Create an AuthClient with mocked auth for a given role.

    Returns a context manager that keeps patches alive for the duration
    of the test.
    """
    # `validate_schema` intentionally False — therapy has ~20 known
    # column-level schema-drift points tracked by
    # `products/therapy-platform/projects/therapy-audio-lifecycle-schema-reconciliation/`.
    # Flipping column validation on surfaces all of them (appointment_id on
    # session_audio_segments / session_interruptions; patient_id/therapist_id
    # on session_records; user_id on therapist_settings; rating vs star_rating
    # on reviews; therapist_id on whatsapp_messages; etc.). Those belong in the
    # reconciliation project, not in the mock-supabase close. Once that project
    # lands, flip this to validate_schema=True.
    #
    # `strict_unknown_tables=True` is **orthogonal** to validate_schema (added
    # 2026-05-11 by `therapy-platform-drift-sweep`). It raises
    # `MockUnknownTableError` if a test exercises a table absent from the
    # migration-derived schema cache — guards against regressing the 11
    # phantom-table references the sweep eliminated. Works regardless of
    # `validate_schema`. See `noctusai_lib.testing.mocks.MockRequestBuilder.
    # _check_table_known`.
    mock_sb = MockSupabaseClient(
        validate_schema=False,
        schema="therapy",
        strict_unknown_tables=True,
    )
    mock_user = MockUser(role=role, clinic_id=clinic_id)
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(mock_user))

    # `role-cascade-trusted` (2026-07-14): `get_user_role` now resolves the
    # platform-admin cascade from `public.noctus_users` FIRST (see
    # `noctusai_lib.api.auth.make_resolve_platform_role`), via a REAL
    # `get_core_client()` — i.e. a client scoped to the `public` schema, NOT
    # `therapy`. Reusing `mock_sb` (bound to `schema="therapy"`) for
    # `get_core_client` was already semantically wrong (the seed's
    # `DatabaseModule.get_core_client()` always targets `public` in
    # production) but nothing exercised it until now: with
    # `strict_unknown_tables=True`, `.table("noctus_users")` against a
    # `schema="therapy"` mock raises `MockUnknownTableError` (`public.
    # noctus_users` is a known table; `therapy.noctus_users` isn't — it
    # doesn't exist). A DEDICATED `schema="public"` mock — with no seeded
    # rows, so every lookup returns "no row" — fixes the schema mismatch;
    # `get_user_role` falls through to the `user_metadata` path every
    # fixture here already sets via `MockUser(role=...)`, so no test's
    # asserted role changes.
    mock_core = MockSupabaseClient(
        validate_schema=False,
        schema="public",
        strict_unknown_tables=True,
    )

    patcher1 = patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb)
    patcher2 = patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_core)
    patcher3 = patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb)
    # MOCK-SELECT-PREDICATE-FIX follow-up: `app.database` captures
    # `db.get_client / get_core_client / get_admin_client` as BOUND METHODS
    # at module-import time (triggered by `pytest_plugin`'s `app.main` probe
    # at session start). Class-level patches above do NOT propagate to those
    # captured bindings — the original `DatabaseModule.<method>` reference
    # is frozen into the bound. Patch the module-level callables directly so
    # the BackgroundTask path in routers (which calls `get_core_client()` /
    # `get_admin_client()` from `app.database` / `app.dependencies`) lands on
    # the test's mock instead of attempting to instantiate a real Supabase
    # client and crashing on missing `SUPABASE_URL`.
    patcher4 = patch("app.database.get_core_client", return_value=mock_core)
    patcher5 = patch("app.database.get_admin_client", return_value=mock_sb)
    patcher6 = patch("app.database.get_supabase_client", return_value=mock_sb)
    patcher1.start()
    patcher2.start()
    patcher3.start()
    patcher4.start()
    patcher5.start()
    patcher6.start()

    from app.main import app
    # Per-fixture re-bind of the seed's consent module to THIS test's mock_sb.
    # See KB § PATTERNS/testing.md § Consent-guard product conftest pattern.
    bind_consent_module_to_mock(mock_sb)
    tc = TestClient(app)
    client = AuthClient(tc, mock_sb)
    return client, (patcher1, patcher2, patcher3, patcher4, patcher5, patcher6)


@pytest.fixture
def client():
    """Default test client — therapist role."""
    c, patchers = _make_client_context(role="therapist")
    yield c
    for p in patchers:
        p.stop()


@pytest.fixture
def patient_client():
    """Test client — patient role."""
    c, patchers = _make_client_context(role="patient")
    yield c
    for p in patchers:
        p.stop()


@pytest.fixture
def clinic_admin_client():
    """Test client — clinic admin role with clinic_id."""
    c, patchers = _make_client_context(role="clinic_admin", clinic_id="test-clinic-123")
    yield c
    for p in patchers:
        p.stop()


@pytest.fixture
def admin_client():
    """Test client — platform admin role."""
    c, patchers = _make_client_context(role="platform_admin")
    yield c
    for p in patchers:
        p.stop()
