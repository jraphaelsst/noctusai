"""
Pytest configuration and shared fixtures for backend tests.
Uses mocking to avoid requiring a live Supabase instance.
"""
import pytest
from typing import Optional
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient


class MockSupabaseResponse:
    def __init__(self, data=None, error=None, count=None):
        self.data = data or []
        self.error = error
        self.count = count


class MockQueryBuilder:
    def __init__(self, data=None):
        self._data = data or []
        self._single_mode = False

    def select(self, *a, **k): return self
    def insert(self, *a, **k): return self
    def update(self, *a, **k): return self
    def upsert(self, *a, **k): return self
    def delete(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def neq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def gt(self, *a, **k): return self
    def lt(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def lte(self, *a, **k): return self
    def ilike(self, *a, **k): return self
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def range(self, *a, **k): return self
    def is_(self, *a, **k): return self

    def single(self):
        self._single_mode = True
        return self

    @property
    def not_(self): return self

    def execute(self):
        data = self._data
        if self._single_mode and isinstance(data, list):
            data = data[0] if data else None
        self._single_mode = False
        return MockSupabaseResponse(data=data)


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


class MockUser:
    def __init__(self, id="test-user-123", email="test@example.com"):
        self.id = id
        self.email = email
        self.user_metadata = {"org_id": "test-org-123"}


class MockUserResponse:
    def __init__(self, user=None):
        self.user = user or MockUser()


class AuthClient:
    def __init__(self, tc: TestClient, mock_sb: MockSupabaseClient):
        self._tc = tc
        self._mock_supabase = mock_sb
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


@pytest.fixture
def client():
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse())

    with patch("app.database.get_supabase_client", return_value=mock_sb), \
         patch("app.dependencies.get_supabase_client", return_value=mock_sb):

        from app.main import app
        tc = TestClient(app)
        yield AuthClient(tc, mock_sb)
