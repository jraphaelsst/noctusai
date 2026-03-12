"""
Pytest configuration and shared fixtures for NoctusAI Core backend tests.
Uses mocking to avoid requiring a live Supabase instance.
"""
import contextlib
import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "realdb: tests that require a live Supabase instance")
from typing import Optional
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Mock Supabase layer
# ---------------------------------------------------------------------------

class MockSupabaseResponse:
    """Simulates a Supabase PostgREST response."""

    def __init__(self, data=None, error=None, count=None):
        self.data = data or []
        self.error = error
        self.count = count


class MockQueryBuilder:
    """Chainable mock that simulates Supabase PostgREST query builder.

    When `.single()` is called before `.execute()`, the response data is
    unwrapped: if the underlying data is a list, the first element (a dict)
    is returned — matching real Supabase PostgREST behaviour where `single()`
    returns a single record instead of a list.

    Supports a response queue: if initialized with a list via
    ``MockQueryBuilder(data, queue=True)``, each ``.execute()`` call pops
    and returns the next item from the list, allowing different responses
    for successive queries on the same table.
    """

    def __init__(self, data=None, queue=False):
        self._queue = None
        if queue and isinstance(data, list):
            self._queue = list(data)  # copy
            self._data = data[0] if data else []
        else:
            self._data = data or []
        self._single = False
        self._insert_data = None

    def select(self, *a, **k):
        return self

    def insert(self, row_data=None, *a, **k):
        # Capture the inserted data so execute() can return it when the
        # table's mock data is empty (simulating a real insert that returns
        # the newly created row).
        if row_data is not None:
            self._insert_data = row_data if isinstance(row_data, list) else [row_data]
        return self

    def update(self, *a, **k):
        return self

    def upsert(self, *a, **k):
        return self

    def delete(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def neq(self, *a, **k):
        return self

    def in_(self, *a, **k):
        return self

    def is_(self, *a, **k):
        return self

    def gte(self, *a, **k):
        return self

    def lte(self, *a, **k):
        return self

    def ilike(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def range(self, *a, **k):
        return self

    def single(self):
        self._single = True
        return self

    def execute(self):
        # If a response queue is active, pop the next item
        if self._queue is not None and len(self._queue) > 0:
            data = self._queue.pop(0)
        else:
            data = self._data
        # If an insert was performed and the table had no data, return the
        # inserted rows so that router code like ``result.data[0]`` works.
        if self._insert_data is not None:
            if not data or (isinstance(data, list) and len(data) == 0):
                data = self._insert_data
            self._insert_data = None
        # Reset _single flag for next query chain on the same builder
        if self._single:
            self._single = False
            # Unwrap: if data is a list with items, return the first element
            # (mimics Supabase PostgREST .single() which returns a record, not a list)
            if isinstance(data, list) and len(data) > 0:
                data = data[0]
            elif isinstance(data, list) and len(data) == 0:
                data = None
        return MockSupabaseResponse(data=data)


class MockSupabaseClient:
    """Mocked Supabase client with table-level data control."""

    def __init__(self, data=None):
        self._data = data
        self.auth = MagicMock()
        self.auth.admin = MagicMock()
        self._tables = {}

    def table(self, name):
        if name not in self._tables:
            self._tables[name] = MockQueryBuilder(self._data)
        return self._tables[name]

    def set_table_data(self, name, data):
        """Set mock data for a specific table."""
        self._tables[name] = MockQueryBuilder(data)

    def set_table_responses(self, name, responses):
        """Set a queue of mock responses for a specific table.

        Each call to ``.execute()`` on this table will pop the next item
        from the queue.  When the queue is exhausted, subsequent calls
        return the last item.

        Example::

            mock_sb.set_table_responses("noctus_users", [
                {"id": "u1", "org_id": "o1"},   # first execute()
                [],                               # second execute()
            ])
        """
        self._tables[name] = MockQueryBuilder(responses, queue=True)

    def rpc(self, name):
        return MockQueryBuilder(["2026-02-24"])


class MockUser:
    """Simulates a Supabase auth user object."""

    def __init__(self, id="test-user-123", email="test@example.com"):
        self.id = id
        self.email = email
        self.user_metadata = {}


class MockUserResponse:
    """Simulates a Supabase auth.get_user() response."""

    def __init__(self, user=None):
        self.user = user or MockUser()


# ---------------------------------------------------------------------------
# Auth wrapper for TestClient
# ---------------------------------------------------------------------------

class AuthClient:
    """
    Wraps a TestClient and adds Authorization header to every request.
    Also holds references to mock objects for assertions in tests.
    """

    def __init__(self, tc: TestClient, mock_sb: MockSupabaseClient):
        self._tc = tc
        self._mock_supabase = mock_sb
        self._headers = {"Authorization": "Bearer test-token-valid"}

    @property
    def mock_supabase(self) -> MockSupabaseClient:
        return self._mock_supabase

    def get(self, url, **kwargs):
        return self._tc.get(url, headers=self._headers, **kwargs)

    def post(self, url, **kwargs):
        return self._tc.post(url, headers=self._headers, **kwargs)

    def patch(self, url, **kwargs):
        return self._tc.patch(url, headers=self._headers, **kwargs)

    def delete(self, url, **kwargs):
        return self._tc.delete(url, headers=self._headers, **kwargs)

    def put(self, url, **kwargs):
        return self._tc.put(url, headers=self._headers, **kwargs)

    def raw(self) -> TestClient:
        """Access the underlying TestClient without auth headers."""
        return self._tc


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
