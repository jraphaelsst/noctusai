"""
Pytest configuration and shared fixtures for Agentes backend tests.

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

# ── the suite must own its env (KB § PATTERNS/compliance/testing.md) ──────
#
# `ANTHROPIC_API_KEY` goes in `clear` because for this product its mere
# PRESENCE is a switch, not a value: `get_slot_pool()` (and every sibling
# agents runtime factory) hands back the REAL implementation when a key
# resolves, and `RealSlotPool` sweeps via `RealSweeper`, which spawns
# `/app/bin/julia-cli-slot` as a per-slot unix user. That path exists only
# inside the container, so on any developer machine the spawn fails, all
# three slots are quarantined at startup, and the three slot-pool tests in
# `test_main.py` fail on `assert [0, 1, 2] == []`.
#
# The repo's own `.env` carries a real 108-char ANTHROPIC_API_KEY and
# `env_bootstrap` loads it, so ANY process that bootstraps — the MCP
# server, `predeploy_check`, `gate_sweep`, a plain shell after `source` —
# inherits it. CI has no key, gets `FakeSlotPool`, and is green. That is
# the p-studio 2026-08-19 shape exactly: a suite reporting on the
# developer's shell rather than on the code, and green in CI either way.
#
# Measured 2026-09-20: 3 failed / 522 passed with the ambient key;
# 525 passed with it cleared.
#
# `APP_ENV` rides along because `is_deploy_context()` keys off it and would
# force the real pool regardless of the key. (Its other door,
# `PRODUCT_URL_<SLUG>`, is dynamic and stays owned by that helper.)
#
# 🔴 ASSIGNED EMPTY, NOT `clear`ed — this is the load-bearing detail.
# `clear` does `del os.environ[key]`, which makes the key ABSENT; the next
# `env_bootstrap` in the process (it runs with `override=False`, i.e.
# "an already-set var wins") then sees it absent and RELOADS it straight
# back out of `.env`. Assigning `""` leaves it present-but-empty, which
# `override=False` treats as already-set and will not overwrite — and
# `resolve_app_config_value` documents that "an empty-string env value
# counts as unset". So empty is both stable AND correctly falsy.
# Measured 2026-09-20: `clear` => still 3 failed; assign-empty => 525 passed.
#
# `SUPABASE_SERVICE_ROLE_KEY` rides along for the same reason (2026-09-21,
# Agent Studio): every store factory here returns its REAL Supabase store
# when the key resolves, and the developer `.env` carries the real key of the
# SHARED (prod) project. A binding that reaches a factory directly (the eval
# gate did) sent a test's reads to the live DB. Empty ⇒ every factory hands
# back its Fake — the suite can never touch the shared database.
_mod.own_test_env({"ANTHROPIC_API_KEY": "", "APP_ENV": "", "SUPABASE_SERVICE_ROLE_KEY": ""})

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


@pytest.fixture(autouse=True)
def _hermetic_config_stores():
    """Bind the app's credential store + runtime-settings service to Fakes
    for every test (explicit install seams, not patches) — with a local
    `.env` the factories would otherwise pick the REAL Supabase-backed
    stores and a unit test would read production config."""
    from noctusai_lib.security.app_config import CachedAppConfigStore, FakeAppConfigStore

    from app.config import settings
    from app.credentials import resolver
    from app.services import runtime_settings
    from app.stores.runtime_settings import FakeRuntimeSettingsStore

    resolver.install_config_store_handle(
        settings,
        resolver.ConfigStoreHandle(
            store=CachedAppConfigStore(FakeAppConfigStore(), ttl_seconds=0), persistent=True
        ),
    )
    runtime_settings.install_runtime_settings_service(
        runtime_settings.RuntimeSettingsService(FakeRuntimeSettingsStore(), settings, ttl_seconds=0)
    )
    yield
    resolver.reset_for_testing()
    runtime_settings.reset_for_testing()


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
