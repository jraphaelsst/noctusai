"""
Pytest configuration and shared fixtures for NoctusAI Core backend tests.
Uses mocking to avoid requiring a live Supabase instance.

All mock classes are imported from the shared testing package
(noctusai_lib.testing). Core-specific fixtures (client, admin_client,
unauth_client) and the _build_patches() helper remain here.
"""
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
    MockQueryBuilder as _SharedMockQueryBuilder,
    MockRequestBuilder as _SharedMockRequestBuilder,
    MockSupabaseClient as _SharedMockSupabaseClient,
    MockUser,
    MockUserResponse,
    AuthClient,
)


# ---------------------------------------------------------------------------
# Core-specific insert-data tracking (backwards compat)
#
# The old Core MockQueryBuilder captured insert payloads and returned them
# via execute() when the table had no pre-set data.  This lets router code
# like ``result = db.table("x").insert(data).execute(); result.data[0]``
# work even when the test sets the table to [].
# ---------------------------------------------------------------------------

class MockQueryBuilder(_SharedMockQueryBuilder):
    """Core QueryBuilder with insert-data fallback."""

    def __init__(self, data=None, response_queue=None, response_idx=None,
                 insert_data=None):
        super().__init__(data=data, response_queue=response_queue,
                         response_idx=response_idx)
        self._insert_data = insert_data

    def execute(self):
        if self._insert_data is not None:
            if not self._data or (isinstance(self._data, list) and len(self._data) == 0):
                self._data = self._insert_data
        return self._do_execute()


class MockRequestBuilder(_SharedMockRequestBuilder):
    """Core RequestBuilder that captures insert data for fallback."""

    def insert(self, row_data=None, *a, **k):
        insert_data = None
        if row_data is not None:
            insert_data = row_data if isinstance(row_data, list) else [row_data]
        return MockQueryBuilder(
            self._data,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
            insert_data=insert_data,
        )


# ---------------------------------------------------------------------------
# Core-specific MockSupabaseClient with insert-data tracking + compat
# ---------------------------------------------------------------------------

class MockSupabaseClient(_SharedMockSupabaseClient):
    """Core-compatible MockSupabaseClient.

    Uses ``MockRequestBuilder`` (with insert-data fallback) for all tables.

    Adds ``set_table_responses(name, responses)`` which wraps raw data items
    into ``MockSupabaseResponse`` objects before delegating to the shared
    ``set_sequential_responses`` method.  This preserves backwards
    compatibility with existing Core tests that pass plain dicts/lists::

        mock_sb.set_table_responses("noctus_users", [
            {"org_id": "org-1"},   # first execute()
            [],                     # second execute()
        ])
    """

    def table(self, name):
        if name not in self._tables:
            self._tables[name] = MockRequestBuilder(self._data)
        return self._tables[name]

    def set_table_data(self, name, data):
        """Set mock data for a specific table."""
        self._tables[name] = MockRequestBuilder(data)

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
        # Notifications router
        ("app.routers.notifications.get_admin_client", mock_sb),
        ("app.routers.notifications.get_current_user", mock_get_user),
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

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
        return "test-org-123"

    patches = _build_patches(
        mock_sb, _mock_get_current_user, _mock_get_current_admin, _mock_check_permission,
        mock_get_org_id=_mock_get_org_id,
    )

    with contextlib.ExitStack() as stack:
        _apply_patches(stack, patches)
        from app.main import app
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
        return "test-org-123"

    patches = _build_patches(
        mock_sb, _mock_get_current_user, _mock_get_current_admin, _mock_check_permission,
        mock_get_org_id=_mock_get_org_id,
    )

    with contextlib.ExitStack() as stack:
        _apply_patches(stack, patches)
        from app.main import app
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
        return "test-org-123"

    patches = _build_patches(
        mock_sb, _mock_get_current_user, _mock_get_current_admin, _mock_check_permission,
        mock_get_org_id=_mock_get_org_id,
    )

    with contextlib.ExitStack() as stack:
        _apply_patches(stack, patches)
        from app.main import app
        tc = TestClient(app)
        yield UnauthClient(tc, mock_sb)
