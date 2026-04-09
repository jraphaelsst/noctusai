"""
Pytest fixtures for the Therapy Platform backend.

Provides MockSupabaseClient (chainable query builder that simulates
Supabase PostgREST), AuthClient (TestClient with auth headers), and
role-specific fixtures.

Key difference from ERP/PF: no org_id. Instead, users have roles
(platform_admin, clinic_admin, therapist, patient) and optional clinic_id.
"""
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Mock Supabase response
# ---------------------------------------------------------------------------
class MockSupabaseResponse:
    def __init__(self, data=None, count=None):
        self.data = data if data is not None else []
        self.count = count if count is not None else (
            len(data) if isinstance(data, list) else (1 if data else 0)
        )


# ---------------------------------------------------------------------------
# Mock query builder (chainable — mirrors real Supabase SDK)
# ---------------------------------------------------------------------------
class MockSelectBuilder:
    def __init__(self, data=None, count=None):
        self._data = data if data is not None else []
        self._count = count

    def eq(self, *args, **kwargs): return self
    def neq(self, *args, **kwargs): return self
    def gt(self, *args, **kwargs): return self
    def gte(self, *args, **kwargs): return self
    def lt(self, *args, **kwargs): return self
    def lte(self, *args, **kwargs): return self
    def in_(self, *args, **kwargs): return self
    def is_(self, *args, **kwargs): return self
    def or_(self, *args, **kwargs): return self
    @property
    def not_(self): return self
    def contains(self, *args, **kwargs): return self
    def order(self, *args, **kwargs): return self
    def limit(self, *args, **kwargs): return self
    def range(self, *args, **kwargs): return self
    def single(self, *args, **kwargs): return self
    def insert(self, *args, **kwargs): return self
    def update(self, *args, **kwargs): return self
    def upsert(self, *args, **kwargs): return self
    def delete(self, *args, **kwargs): return self

    def select(self, *args, **kwargs):
        return self

    def execute(self):
        data = self._data
        if isinstance(data, dict):
            data = data
        elif isinstance(data, list):
            data = data
        else:
            data = []
        count = self._count if self._count is not None else (
            len(data) if isinstance(data, list) else (1 if data else 0)
        )
        return MockSupabaseResponse(data=data, count=count)


# ---------------------------------------------------------------------------
# Mock Supabase client
# ---------------------------------------------------------------------------
class MockSupabaseClient:
    def __init__(self):
        self._tables = {}
        self._rpcs = {}
        self.auth = MagicMock()
        self.storage = MagicMock()

    def set_table_data(self, table_name, data):
        """Set mock data for a table."""
        self._tables[table_name] = data

    def set_rpc_data(self, name, data):
        """Set mock data for an RPC call."""
        self._rpcs[name] = data

    def table(self, name):
        data = self._tables.get(name, [])
        return MockSelectBuilder(data)

    def rpc(self, name, params=None):
        data = self._rpcs.get(name, None)
        return MockSelectBuilder(data)


# ---------------------------------------------------------------------------
# Mock auth user
# ---------------------------------------------------------------------------
class MockUser:
    def __init__(
        self,
        id="test-user-123",
        email="test@example.com",
        role="therapist",
        clinic_id=None,
    ):
        self.id = id
        self.email = email
        self.user_metadata = {
            "role": role,
        }
        if clinic_id:
            self.user_metadata["clinic_id"] = clinic_id


class MockUserResponse:
    def __init__(self, user):
        self.user = user


# ---------------------------------------------------------------------------
# Auth-wrapped test client
# ---------------------------------------------------------------------------
class AuthClient:
    """TestClient wrapper that auto-injects Authorization header."""

    def __init__(self, test_client, mock_supabase):
        self._tc = test_client
        self._mock_supabase = mock_supabase
        self._headers = {"Authorization": "Bearer test-token-123"}

    def get(self, url, **kwargs):
        return self._tc.get(url, headers=self._headers, **kwargs)

    def post(self, url, **kwargs):
        return self._tc.post(url, headers=self._headers, **kwargs)

    def put(self, url, **kwargs):
        return self._tc.put(url, headers=self._headers, **kwargs)

    def patch(self, url, **kwargs):
        return self._tc.patch(url, headers=self._headers, **kwargs)

    def delete(self, url, **kwargs):
        return self._tc.delete(url, headers=self._headers, **kwargs)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _make_client_context(role="therapist", clinic_id=None):
    """Create an AuthClient with mocked auth for a given role.

    Returns a context manager that keeps patches alive for the duration
    of the test.
    """
    mock_sb = MockSupabaseClient()
    mock_user = MockUser(role=role, clinic_id=clinic_id)
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(mock_user))

    patcher1 = patch("app.dependencies.get_supabase_client", return_value=mock_sb)
    patcher2 = patch("app.database.get_supabase_client", return_value=mock_sb)
    patcher1.start()
    patcher2.start()

    from app.main import app
    tc = TestClient(app)
    client = AuthClient(tc, mock_sb)
    return client, (patcher1, patcher2)


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
