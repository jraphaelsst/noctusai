"""
Pytest configuration and shared fixtures for backend tests.
Uses mocking to avoid requiring a live Supabase instance.

The mock builders mirror the real supabase-py / postgrest SDK's type
hierarchy so that tests fail when application code calls a method that
doesn't exist on the real builder.

Builder hierarchy (postgrest 0.17.2):
  table(name)        → MockRequestBuilder
    .select(...)     → MockSelectBuilder   (filters, order, limit, range, single, execute)
    .insert(...)     → MockQueryBuilder    (execute only)
    .update(...)     → MockFilterBuilder   (filters, execute)
    .delete()        → MockFilterBuilder
    .upsert(...)     → MockQueryBuilder
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


# ---------------------------------------------------------------------------
# Base mixin with shared data + execute
# ---------------------------------------------------------------------------
class _MockExecuteMixin:
    """Shared execute() logic for all builder types."""

    def _do_execute(self):
        data = self._data
        if self._single_mode and isinstance(data, list):
            data = data[0] if data else None
        self._single_mode = False
        return MockSupabaseResponse(data=data)


# ---------------------------------------------------------------------------
# MockSelectBuilder — returned by .select()
# ---------------------------------------------------------------------------
class MockSelectBuilder(_MockExecuteMixin):
    """Mirrors SyncSelectRequestBuilder."""

    def __init__(self, data=None, count=None):
        self._data = data or []
        self._single_mode = False
        self._count = count

    # Filters
    def eq(self, *a, **k): return self
    def neq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def gt(self, *a, **k): return self
    def lt(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def lte(self, *a, **k): return self
    def ilike(self, *a, **k): return self
    def like(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def contains(self, *a, **k): return self
    def filter(self, *a, **k): return self

    @property
    def not_(self): return self

    # Modifiers
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def range(self, *a, **k): return self
    def offset(self, *a, **k): return self

    # Terminals
    def single(self):
        self._single_mode = True
        return self

    def maybe_single(self):
        self._single_mode = True
        return self

    def execute(self):
        return self._do_execute()


# ---------------------------------------------------------------------------
# MockFilterBuilder — returned by .update() / .delete()
# ---------------------------------------------------------------------------
class MockFilterBuilder(_MockExecuteMixin):
    """Mirrors SyncFilterRequestBuilder."""

    def __init__(self, data=None):
        self._data = data or []
        self._single_mode = False

    # Filters
    def eq(self, *a, **k): return self
    def neq(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def gt(self, *a, **k): return self
    def lt(self, *a, **k): return self
    def gte(self, *a, **k): return self
    def lte(self, *a, **k): return self
    def ilike(self, *a, **k): return self
    def is_(self, *a, **k): return self
    def contains(self, *a, **k): return self
    def filter(self, *a, **k): return self

    @property
    def not_(self): return self

    def execute(self):
        return self._do_execute()


# ---------------------------------------------------------------------------
# MockQueryBuilder — returned by .insert() / .upsert()
# ---------------------------------------------------------------------------
class MockQueryBuilder(_MockExecuteMixin):
    """Mirrors SyncQueryRequestBuilder."""

    def __init__(self, data=None):
        self._data = data or []
        self._single_mode = False

    def execute(self):
        return self._do_execute()


# ---------------------------------------------------------------------------
# MockRequestBuilder — returned by .table()
# ---------------------------------------------------------------------------
class MockRequestBuilder:
    """Mirrors SyncRequestBuilder — the object returned by .table(name)."""

    def __init__(self, data=None):
        self._data = data or []
        # Normalize: real SDK always returns lists, so wrap single dicts
        if isinstance(self._data, dict):
            self._data = [self._data]

    def select(self, *a, **k):
        count = k.get("count")
        return MockSelectBuilder(
            self._data,
            count=len(self._data) if count == "exact" else None,
        )

    def insert(self, *a, **k):
        return MockQueryBuilder(self._data)

    def update(self, *a, **k):
        return MockFilterBuilder(self._data)

    def upsert(self, *a, **k):
        return MockFilterBuilder(self._data)

    def delete(self, *a, **k):
        return MockFilterBuilder(self._data)


# ---------------------------------------------------------------------------
# MockSupabaseClient
# ---------------------------------------------------------------------------
class MockSupabaseClient:
    def __init__(self, data=None):
        self._data = data
        self.auth = MagicMock()
        self._tables = {}

    def table(self, name):
        if name not in self._tables:
            self._tables[name] = MockRequestBuilder(self._data)
        return self._tables[name]

    def set_table_data(self, name, data):
        self._tables[name] = MockRequestBuilder(data)


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
