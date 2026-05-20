"""
Pytest configuration and shared fixtures for NoctusAI Core backend tests.
Uses mocking to avoid requiring a live Supabase instance.

All mock classes are imported from the shared testing package
(noctusai_lib.testing). Core-specific fixtures (client, admin_client,
unauth_client) and the _build_patches() helper remain here.
"""
import sys as _sys
from pathlib import Path as _Path

_REPO = _Path(__file__).resolve().parents[4]
_LIB = _REPO / "seed" / "lib" / "backend"
_FRAMEWORK = _REPO / "seed" / "framework" / "backend"
# Inject BOTH seed package roots: the purge helper drops sibling-worktree
# editable finders (correct behaviour), but the conftest must ALSO ensure
# THIS worktree's own seed source trees are importable via sys.path —
# otherwise `import noctusai_seed` fails with no fallback after the purge.
# Post-axis-swap fan-out (2026-05-20) mirroring ERP-P7's reference fix.
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
import contextlib
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: tests that require a live Supabase instance")


from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Shared mock imports (re-exported for backwards compat)
# ---------------------------------------------------------------------------

from noctusai_lib.testing import (  # noqa: F401
    MockSupabaseResponse,
    MockSelectBuilder,
    MockFilterBuilder,
    MockQueryBuilder,
    MockRequestBuilder,
    MockSupabaseClient as _SharedMockSupabaseClient,
    MockUser,
    MockUserResponse,
    AuthClient,
    bind_consent_module_to_mock,
)
from noctusai_lib.testing.fixtures import reset_rate_limiter  # noqa: F401


# ---------------------------------------------------------------------------
# Core-specific MockSupabaseClient — keeps `set_table_responses(...)` shim
# for backwards-compat (older tests pass raw dicts/lists; the seed-lib
# `set_sequential_responses` expects MockSupabaseResponse objects).
#
# The old "insert-data fallback" behavior previously implemented here as
# a custom MockRequestBuilder/MockQueryBuilder pair was REMOVED 2026-04-29
# after the seed-lib `MockRequestBuilder.insert(...)` was upgraded to
# return inserted rows in `result.data` directly (with auto-id). The
# parent class now does the right thing platform-wide; the override was
# a less-correct half-fix (didn't auto-add `id`, returned seeded rows
# when both seeded data + insert were present — divergent from real
# Supabase). Removed in `mcp-mock-supabase-insert-returns-row` project.
# ---------------------------------------------------------------------------

class MockSupabaseClient(_SharedMockSupabaseClient):
    """Core-compatible MockSupabaseClient — adds `set_table_responses(...)`
    wrapper. Insert-data return shape is now inherited from the parent
    (seed-lib MockRequestBuilder.insert returns inserted rows with auto-id).

    `set_table_responses(name, responses)` wraps raw data items into
    `MockSupabaseResponse` objects before delegating to the shared queue::

        mock_sb.set_table_responses("noctus_users", [
            {"org_id": "org-1"},   # first execute()
            [],                     # second execute()
        ])
    """

    def set_table_data(self, name, data):
        """Set mock data for a specific table. Delegates to the parent
        `_builder_for` so the seed-lib MockRequestBuilder is used (with
        insert→inserted-row return + auto-id fix from 2026-04-29)."""
        self._tables[name] = self._builder_for(name, data=data)

    def set_table_responses(self, name, responses):
        """Set a queue of mock responses for a specific table.

        Each call to ``.execute()`` on this table will return the next item
        from the queue wrapped in a ``MockSupabaseResponse``.  When the
        queue is exhausted, subsequent calls return empty data.

        ``responses`` should be a list of raw data values (dicts or lists).
        Each is normalised: a bare dict becomes ``[dict]``, a list stays
        as-is.
        """
        wrapped = []
        for item in responses:
            if isinstance(item, dict):
                wrapped.append(MockSupabaseResponse(data=[item]))
            elif isinstance(item, list):
                wrapped.append(MockSupabaseResponse(data=item))
            else:
                wrapped.append(MockSupabaseResponse(data=item))
        self.set_sequential_responses(name, wrapped)


# ---------------------------------------------------------------------------
# Core-specific UnauthClient (kept for backwards compat)
# ---------------------------------------------------------------------------

class UnauthClient:
    """TestClient wrapper that sends requests WITHOUT auth headers."""

    def __init__(self, tc: TestClient, mock_sb: MockSupabaseClient):
        self._tc = tc
        self._mock_supabase = mock_sb

    @property
    def mock_supabase(self) -> MockSupabaseClient:
        return self._mock_supabase

    def get(self, url, **kwargs):
        return self._tc.get(url, **kwargs)

    def post(self, url, **kwargs):
        return self._tc.post(url, **kwargs)

    def patch(self, url, **kwargs):
        return self._tc.patch(url, **kwargs)

    def delete(self, url, **kwargs):
        return self._tc.delete(url, **kwargs)

    def put(self, url, **kwargs):
        return self._tc.put(url, **kwargs)


# ---------------------------------------------------------------------------
# Helper: mock user that get_current_user returns
# ---------------------------------------------------------------------------

MOCK_USER = MockUser(id="test-user-123", email="test@example.com")
MOCK_ADMIN_USER = MockUser(id="admin-user-456", email="admin@example.com")


# ---------------------------------------------------------------------------
# Patch target helpers
# ---------------------------------------------------------------------------

def _build_patches(mock_sb, mock_get_user, mock_get_admin, mock_check_perm, mock_get_org_id=None):
    """Build the list of (target, replacement) tuples for all patches."""
    return [
        # Framework-class-level DATABASE patches (added in core-seed-wiring-v2 Phase 3).
        # Core now consumes the framework's /api/notificacoes router — its handler
        # calls `deps.get_core_client()` on the ProductDependencies instance
        # constructed inside create_product_app. Patching DatabaseModule methods
        # at the class level covers that instance AND `app.dependencies.deps`,
        # so the framework router's real `get_current_user` flows through the
        # mocked Supabase client (`admin.auth.get_user(token)` returns MOCK_USER).
        # Matches the ERP conftest pattern. We deliberately do NOT patch
        # `ProductDependencies.get_current_user` at the class level — the class
        # method would be called with `(self, authorization)` but the existing
        # mock signature accepts only `authorization=`, causing a TypeError.
        # Since the real `get_current_user` works end-to-end via the mocked
        # DatabaseModule, we keep auth logic real here.
        ("noctusai_seed.database.DatabaseModule.get_client", mock_sb),
        ("noctusai_seed.database.DatabaseModule.get_admin_client", mock_sb),
        ("noctusai_seed.database.DatabaseModule.get_core_client", mock_sb),
        # Database module
        ("app.database.get_supabase_client", mock_sb),
        ("app.database.get_admin_client", mock_sb),
        # Dependencies module
        ("app.dependencies.get_supabase_client", mock_sb),
        ("app.dependencies.get_admin_client", mock_sb),
        # Auth router
        ("app.routers.auth.get_admin_client", mock_sb),
        ("app.routers.auth.get_current_user", mock_get_user),
        ("app.routers.auth.create_client", mock_sb),
        # Organizations router
        ("app.routers.organizations.get_admin_client", mock_sb),
        ("app.routers.organizations.get_current_user", mock_get_user),
        ("app.routers.organizations.get_current_admin", mock_get_admin),
        # Products router
        ("app.routers.products.get_admin_client", mock_sb),
        ("app.routers.products.get_current_user", mock_get_user),
        ("app.routers.products.get_current_admin", mock_get_admin),
        # Licenses router
        ("app.routers.licenses.get_admin_client", mock_sb),
        ("app.routers.licenses.get_current_user", mock_get_user),
        ("app.routers.licenses.get_current_admin", mock_get_admin),
        ("app.routers.licenses.get_org_id", mock_get_org_id),
        # Subscriptions router
        ("app.routers.subscriptions.get_admin_client", mock_sb),
        ("app.routers.subscriptions.get_current_user", mock_get_user),
        ("app.routers.subscriptions.get_current_admin", mock_get_admin),
        ("app.routers.subscriptions.get_org_id", mock_get_org_id),
        # Plans router
        ("app.routers.plans.get_admin_client", mock_sb),
        ("app.routers.plans.get_current_user", mock_get_user),
        ("app.routers.plans.get_current_admin", mock_get_admin),
        # API Keys router
        ("app.routers.api_keys.get_admin_client", mock_sb),
        ("app.routers.api_keys.get_current_user", mock_get_user),
        ("app.routers.api_keys.get_current_admin", mock_get_admin),
        ("app.routers.api_keys.get_org_id", mock_get_org_id),
        # Roles router
        ("app.routers.roles.get_admin_client", mock_sb),
        ("app.routers.roles.get_current_user", mock_get_user),
        ("app.routers.roles.check_permission", mock_check_perm),
        # Team router
        ("app.routers.team.get_admin_client", mock_sb),
        ("app.routers.team.get_current_user", mock_get_user),
        ("app.routers.team.check_permission", mock_check_perm),
        # SSO router
        ("app.routers.sso.get_admin_client", mock_sb),
        ("app.routers.sso.get_current_user", mock_get_user),
        ("app.routers.sso.supabase_admin", mock_sb),
        # Onboarding router
        ("app.routers.onboarding.get_admin_client", mock_sb),
        ("app.routers.onboarding.get_current_user", mock_get_user),
        ("app.routers.onboarding.get_org_id", mock_get_org_id),
        # Analytics router
        ("app.routers.analytics.get_admin_client", mock_sb),
        ("app.routers.analytics.get_current_admin", mock_get_admin),
        # OAuth router
        ("app.routers.oauth.get_admin_client", mock_sb),
        ("app.routers.oauth.get_supabase_client", mock_sb),
        ("app.routers.oauth.get_current_user", mock_get_user),
        # Entitlements router
        ("app.routers.entitlements.get_current_user", mock_get_user),
        ("app.routers.entitlements.get_org_id", mock_get_org_id),
        # Notifications router — DELETED in core-seed-wiring-v2 Phase 3.
        # Core now consumes the framework-bundled /api/notificacoes router
        # (from noctusai_seed.routers._create_notificacoes_router). That
        # router uses deps.get_current_user + deps.get_core_client, which
        # are already patched above via app.dependencies.
        # Webhooks router
        ("app.routers.webhooks.get_admin_client", mock_sb),
        ("app.routers.webhooks.get_current_user", mock_get_user),
        ("app.routers.webhooks.get_current_admin", mock_get_admin),
        ("app.routers.webhooks.get_org_id", mock_get_org_id),
        # Audit logs router
        ("app.routers.audit_logs.get_admin_client", mock_sb),
        ("app.routers.audit_logs.get_current_user", mock_get_user),
        ("app.routers.audit_logs.get_current_admin", mock_get_admin),
        ("app.routers.audit_logs.get_org_id", mock_get_org_id),
        # Test accounts router
        ("app.routers.test_accounts.get_admin_client", mock_sb),
        ("app.routers.test_accounts.get_current_admin", mock_get_admin),
        # Billing router
        ("app.routers.billing.get_admin_client", mock_sb),
        ("app.routers.billing.get_current_user", mock_get_user),
        ("app.routers.billing.get_org_id", mock_get_org_id),
        # Settings router
        ("app.routers.settings.get_admin_client", mock_sb),
        ("app.routers.settings.get_current_user", mock_get_user),
        ("app.routers.settings.get_current_admin", mock_get_admin),
        ("app.routers.settings.get_org_id", mock_get_org_id),
        # Permissions service
        ("app.services.permissions.get_admin_client", mock_sb),
        # Usage router
        ("app.routers.usage.get_admin_client", mock_sb),
        ("app.routers.usage.get_current_user", mock_get_user),
        ("app.routers.usage.get_current_admin", mock_get_admin),
        ("app.routers.usage.get_org_id", mock_get_org_id),
        # Users router (admin)
        ("app.routers.users.get_admin_client", mock_sb),
        ("app.routers.users.get_current_admin", mock_get_admin),
        # Audit digest router (Phase 9 — C2 audit-log narrative digest)
        ("app.routers.audit_digest.get_admin_client", mock_sb),
        ("app.routers.audit_digest.get_current_admin", mock_get_admin),
        # Admin LLM spend router (Phase 18 — X4 cost guardrails)
        ("app.routers.admin_llm_spend.get_admin_client", mock_sb),
        ("app.routers.admin_llm_spend.get_current_admin", mock_get_admin),
        # Me-consents router (Phase 19 — X6 per-feature AI consent)
        ("app.routers.me_consents.get_user_client", mock_sb),
        ("app.routers.me_consents.get_current_user", mock_get_user),
        ("app.routers.me_consents.get_org_id", mock_get_org_id),
    ]


def _is_direct_replacement(target_name, value):
    """Determine if a patch target should be replaced directly (no return_value wrapper).

    Functions (get_current_user, etc.) and module-level variables (supabase_admin)
    are replaced directly; factory functions (get_admin_client, etc.) use return_value.
    """
    direct_targets = (
        "get_current_user",
        "get_current_admin",
        "get_org_id",
        "check_permission",
        "supabase_admin",
    )
    return any(target_name.endswith(dt) for dt in direct_targets)


def _apply_patches(stack, patches):
    """Apply all patches using an ExitStack."""
    for target, value in patches:
        if _is_direct_replacement(target, value):
            stack.enter_context(patch(target, value))
        else:
            stack.enter_context(patch(target, return_value=value))


@pytest.fixture
def mock_user():
    return MockUser()


@pytest.fixture
def mock_supabase():
    return MockSupabaseClient()


@pytest.fixture
def client():
    """
    Test client with fully mocked Supabase + auth.

    get_current_user returns (MOCK_USER, "test-token-valid").
    get_current_admin raises 403 (non-admin user).
    check_permission returns False.
    """
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(MOCK_USER))

    async def _mock_get_current_user(authorization=None):
        if not authorization or not authorization.startswith("Bearer "):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Token ausente")
        return MOCK_USER, "test-token-valid"

    async def _mock_get_current_admin(authorization=None):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")

    async def _mock_check_permission(user_id, org_id, permission_slug):
        return False

    async def _mock_get_org_id(user):
        return "org-1"

    patches = _build_patches(
        mock_sb, _mock_get_current_user, _mock_get_current_admin, _mock_check_permission,
        mock_get_org_id=_mock_get_org_id,
    )

    with contextlib.ExitStack() as stack:
        _apply_patches(stack, patches)
        from app.main import app
        # Per-fixture re-bind of the seed's consent module to THIS test's
        # mock_sb. See KB § PATTERNS/testing.md § Consent-guard product
        # conftest pattern.
        bind_consent_module_to_mock(mock_sb)
        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)


@pytest.fixture
def admin_client():
    """
    Test client where get_current_admin succeeds.

    Both get_current_user and get_current_admin return (MOCK_ADMIN_USER, token).
    check_permission returns True (admin has all permissions).
    """
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(MOCK_ADMIN_USER))

    async def _mock_get_current_user(authorization=None):
        if not authorization or not authorization.startswith("Bearer "):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Token ausente")
        return MOCK_ADMIN_USER, "test-token-valid"

    async def _mock_get_current_admin(authorization=None):
        if not authorization or not authorization.startswith("Bearer "):
            from fastapi import HTTPException
            raise HTTPException(status_code=401, detail="Token ausente")
        return MOCK_ADMIN_USER, "test-token-valid"

    async def _mock_check_permission(user_id, org_id, permission_slug):
        return True

    async def _mock_get_org_id(user):
        return "org-1"

    patches = _build_patches(
        mock_sb, _mock_get_current_user, _mock_get_current_admin, _mock_check_permission,
        mock_get_org_id=_mock_get_org_id,
    )

    with contextlib.ExitStack() as stack:
        _apply_patches(stack, patches)
        from app.main import app
        # Per-fixture re-bind of the seed's consent module to THIS test's
        # mock_sb. See KB § PATTERNS/testing.md § Consent-guard product
        # conftest pattern.
        bind_consent_module_to_mock(mock_sb)
        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)


@pytest.fixture
def unauth_client():
    """
    Test client that sends requests WITHOUT any Authorization header.
    Useful for testing unauthenticated access (401 responses).
    """
    mock_sb = MockSupabaseClient()

    async def _mock_get_current_user(authorization=None):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Token ausente")

    async def _mock_get_current_admin(authorization=None):
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Token ausente")

    async def _mock_check_permission(user_id, org_id, permission_slug):
        return False

    async def _mock_get_org_id(user):
        return "org-1"

    patches = _build_patches(
        mock_sb, _mock_get_current_user, _mock_get_current_admin, _mock_check_permission,
        mock_get_org_id=_mock_get_org_id,
    )

    with contextlib.ExitStack() as stack:
        _apply_patches(stack, patches)
        from app.main import app
        bind_consent_module_to_mock(mock_sb)
        tc = TestClient(app)
        yield UnauthClient(tc, mock_sb)
