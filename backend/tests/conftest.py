"""
Pytest configuration and shared fixtures for backend tests.
Uses mocking to avoid requiring a live Supabase instance.
"""
import pytest
from typing import Optional
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


# --- Mock Supabase Response ---
class MockSupabaseResponse:
    def __init__(self, data=None, error=None):
        self.data = data or []
        self.error = error


class MockQueryBuilder:
    """Chainable mock that simulates Supabase PostgREST query builder."""
    def __init__(self, data=None):
        self._data = data or []

    def select(self, *a, **k): return self
    def insert(self, *a, **k): return self
    def update(self, *a, **k): return self
    def upsert(self, *a, **k): return self
    def delete(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def neq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def lte(self, *a, **k): return self
    def ilike(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def single(self): return self

    def execute(self):
        return MockSupabaseResponse(data=self._data)


class MockSupabaseClient:
    def __init__(self, data=None):
        self._data = data
        self.auth = MagicMock()
        self._tables = {}

    def table(self, name):
        if name not in self._tables:
            self._tables[name] = MockQueryBuilder(self._data)
        return self._tables[name]

    def set_table_data(self, name, data):
        self._tables[name] = MockQueryBuilder(data)

    def rpc(self, name):
        return MockQueryBuilder(["2026-02-23"])


class MockUser:
    def __init__(self, id="test-user-123", email="test@example.com"):
        self.id = id
        self.email = email


class MockUserResponse:
    def __init__(self, user=None):
        self.user = user or MockUser()


# --- Auth wrapper ---
class AuthClient:
    """
    Wraps a TestClient and adds Authorization header to every request.
    Also holds references to mock objects for assertions.
    """
    def __init__(self, tc: TestClient, mock_sb: MockSupabaseClient, mock_log: MagicMock):
        self._tc = tc
        self._mock_supabase = mock_sb
        self._mock_log = mock_log
        self._headers = {"Authorization": "Bearer test-token-valid"}

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


# --- Fixtures ---

@pytest.fixture
def mock_user():
    return MockUser()


@pytest.fixture
def mock_supabase():
    return MockSupabaseClient()


@pytest.fixture
def client():
    """
    Test client with fully mocked Supabase and automatic auth headers.
    """
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse())
    mock_log = MagicMock()

    with patch("app.database.get_supabase_client", return_value=mock_sb), \
         patch("app.dependencies.get_supabase_client", return_value=mock_sb), \
         patch("app.dependencies.log_action", mock_log):

        from app.main import app
        tc = TestClient(app)
        yield AuthClient(tc, mock_sb, mock_log)
