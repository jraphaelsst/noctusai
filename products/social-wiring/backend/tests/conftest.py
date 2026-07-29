"""
Pytest configuration and shared fixtures for Social Wiring backend tests.

The seed product uses the framework (noctusai_seed), so patches target
the framework's database module rather than product-level modules.
"""
import os as _os
import sys as _sys
from pathlib import Path as _Path

from cryptography.fernet import Fernet as _Fernet

# SEC-3 (erp-httponly-cookie-session-2026-07 roadmap) test-only key —
# `SocialWiringSettings.redis_url` defaults to a real, reachable local
# Redis, so `noctusai_seed.auth_router.get_session_store(settings)`
# (shared by `app.dependencies.get_auth_context` AND the promoted
# `/api/auth/{login,me,logout}` router — see `app/dependencies.py`'s
# `_get_session_store` docstring) calls
# `make_session_store(require_encryption=True)`, which REFUSES to boot
# a Redis-backed session store without
# `settings.redis_session_encryption_key` set — fail-loudly-on-
# misconfiguration is the intended SEC-3 behavior, NOT something to
# bypass. Setting a per-session-run Fernet key here (BEFORE
# `app.config`/`app.main` is first imported by any fixture/test) lets
# the suite exercise the REAL Redis-backed + encrypted session store
# (dev-prod parity — the roadmap's Slice 4 note warns "Fake store hides
# the exchange"; a live local Redis is already required by several
# OTHER redis-backed routers this suite exercises, so this doesn't add
# a new external dependency). `setdefault` so a real
# `REDIS_SESSION_ENCRYPTION_KEY` already exported in the environment
# wins.
_os.environ.setdefault(
    "REDIS_SESSION_ENCRYPTION_KEY", _Fernet.generate_key().decode()
)

_REPO = _Path(__file__).resolve().parents[4]
_LIB = _REPO / "seed" / "lib" / "backend"
_FRAMEWORK = _REPO / "seed" / "framework" / "backend"
# Add BOTH seed source roots to sys.path FIRST. `purge_shadowing_editable_finders`
# (called below) drops the `noctusai_seed` editable finder too (its mapping
# points at seed/framework/backend, outside `_LIB`), so without
# `_FRAMEWORK` on the path `import noctusai_seed` fails at collection. The
# `_LIB`-only shim the W0.3 scaffold/reference carried predates the
# separate-finders layout — this restores framework resolution by path.
# (Cross-product test-infra follow-up: fold `noctusai_seed` path-restore
# into the shared shim — out of this product's scope.)
for _p in (_FRAMEWORK, _LIB):
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


# NOTE: the former `settings_override` fixture (raw setattr on the
# `app.config.settings` singleton) was removed by
# `social-wiring-settings-di-rewrite` P4. Production now reads config via
# the `Depends(get_settings)` DI seam, so tests override through
# `override_settings` below (`app.dependency_overrides`) — no singleton
# mutation, honest DI. Per KB § PATTERNS/di-test-seam.md (Class-A).


@pytest.fixture
def override_settings():
    """Production DI-seam settings override (`app.dependency_overrides`).

    The honest replacement for ``settings_override`` / raw
    ``monkeypatch.setattr(settings, "X", ...)``: routers depend on
    ``Depends(get_settings)`` (``app.dependencies.get_settings``); this
    fixture installs an ``app.dependency_overrides[get_settings]`` that
    returns a ``model_copy``-updated settings object, then tears the
    override down automatically. No production singleton mutation, no
    self-monkeypatch — per ``KB § PATTERNS/di-test-seam.md`` (Class-A,
    Pydantic-settings-via-Depends).

    Usage::

        def test_x(client, override_settings):
            override_settings(encryption_key="", youtube_client_id="cid")
            ...

    Multiple calls in one test are additive (later override wins). The
    ``client`` fixture must be requested too (it builds + binds the app).
    """
    from app.config import settings as _settings
    from app.dependencies import get_settings
    from app.main import app

    _overrides: dict = {}
    _prev = app.dependency_overrides.get(get_settings)

    def _apply(**overrides):
        _overrides.update(overrides)
        stub = _settings.model_copy(update=dict(_overrides))
        app.dependency_overrides[get_settings] = lambda: stub
        return stub

    yield _apply

    # Restore the prior override state (usually absent).
    if _prev is None:
        app.dependency_overrides.pop(get_settings, None)
    else:
        app.dependency_overrides[get_settings] = _prev


@pytest.fixture
def override_upload_service():
    """Inject a fake :class:`UploadService` via the ``get_upload_service``
    DI seam (``app.dependency_overrides``).

    The honest replacement for ``patch.object(UploadService,
    "retry_failed_job", ...)``: the router resolves the service through
    ``Depends(get_upload_service)``; this fixture swaps it for a test
    double and tears the override down automatically. No self-monkeypatch
    of our own service method — per ``KB § PATTERNS/di-test-seam.md``
    (Class-B, service DI).
    """
    from app.main import app
    from app.modules.youtube.routers.upload import get_upload_service

    _prev = app.dependency_overrides.get(get_upload_service)

    def _apply(fake_service):
        app.dependency_overrides[get_upload_service] = lambda: fake_service
        return fake_service

    yield _apply

    if _prev is None:
        app.dependency_overrides.pop(get_upload_service, None)
    else:
        app.dependency_overrides[get_upload_service] = _prev


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(
        MockUser(org_id="test-org-123")
    ))

    # Canonical seed-level patch (mirrors products/personal-finance
    # conftest). Class-level patch on DatabaseModule covers every
    # DatabaseModule instance — both app.database._db and the separate
    # instance dependencies.py builds — so we never resolve
    # `app.database._db` at collection time (which broke the older
    # product-level-patch shape the W0.3 scaffold/reference carried).
    with patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb), \
         patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb):

        from app.main import app
        # Per-fixture re-bind of the seed's consent module to THIS test's
        # mock_sb. Idempotent — safe even if no consent features registered.
        # See KB § PATTERNS/testing.md § Consent-guard product conftest pattern.
        bind_consent_module_to_mock(mock_sb)

        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)


@pytest.fixture
def isolate_meta_config_db(monkeypatch):
    """Force ENV-ONLY resolution of Meta app-config by making the
    app-config store unbuildable (the exact degrade precondition
    ``test_app_config_store`` exercises).

    ``resolve_meta_ads_config`` / ``resolve_meta_app_creds`` read the Meta
    System-User token + ad-account + org DB-first (prod reads its config
    from the shared ``app_integration_config``). But UNIT tests that assert
    adapter-SELECTION fallback (system_user → user_oauth → Fake) or
    scheduler org-gating with explicit ``settings`` must NOT read the
    AMBIENT shared DB — whose real config would override the test's intent
    (surfaced once the real token was stored: 12 such tests flipped).

    Apply with ``@pytest.mark.usefixtures("isolate_meta_config_db")`` on the
    class, or ``pytestmark = pytest.mark.usefixtures("isolate_meta_config_db")``
    at module scope. Prod behavior unchanged. self-patch-ok: substitutes the
    store SOURCE to isolate from the real DB; the env-fallback path under
    test is untouched. See feedback_dev_env_deprioritized_verify_prod_via_shared_db.
    """
    from app.config import settings as _default_settings
    from app.services.credential_vault import EncryptionNotConfigured

    def _no_ambient_store():
        raise EncryptionNotConfigured("unit test: no ambient DB read")

    monkeypatch.setattr(
        "app.services.app_config_store.build_app_config_store", _no_ambient_store
    )
    # Also clear the ENV-DEFAULT Meta config on the settings singleton:
    # the developer's / CI's root `.env` may carry a real
    # META_SYSTEM_USER_TOKEN (it does in this repo), which resolves via the
    # env-fallback even with the DB isolated — a test asserting the
    # "no connection" path (default_settings, no explicit token) would then
    # get a LIVE adapter. Tests that WANT a token pass an explicit settings
    # object (unaffected) or patch the field themselves AFTER this fixture.
    for _field in ("meta_system_user_token", "meta_ad_account_id", "meta_ads_org_id"):
        # Clears AMBIENT ENVIRONMENT, not our logic. These three fields are
        # populated from the developer's / CI's root `.env`, which in this repo
        # carries a REAL META_SYSTEM_USER_TOKEN; a test asserting the "not
        # connected" path would otherwise resolve a LIVE adapter through the
        # env-fallback. The resolution code under test is untouched — only the
        # environment it reads is neutralised. Tests that need a value pass an
        # explicit settings object through the `cfg` DI seam instead.
        monkeypatch.setattr(  # self-patch-ok: neutralises ambient .env, not our logic
            _default_settings, _field, "", raising=False
        )
