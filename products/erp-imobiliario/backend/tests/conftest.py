"""
Pytest configuration and shared fixtures for backend tests.
Uses mocking to avoid requiring a live Supabase instance.

The mock builders mirror the real supabase-py / postgrest SDK's type
hierarchy so that tests fail when application code calls a method that
doesn't exist on the real builder.  This prevents "works in tests, breaks
in production" bugs.

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


# ---------------------------------------------------------------------------
# Mock responses
# ---------------------------------------------------------------------------
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
        # If a response queue is configured, use it instead of static data
        if self._response_queue is not None:
            idx = self._response_idx[0]
            self._response_idx[0] += 1
            if idx < len(self._response_queue):
                return self._response_queue[idx]
            return MockSupabaseResponse(data=[])

        data = self._data
        if self._single_mode and isinstance(data, list):
            data = data[0] if data else None
        self._single_mode = False
        return MockSupabaseResponse(data=data, count=self._count)


# ---------------------------------------------------------------------------
# MockSelectBuilder — returned by .select()
#   Allowed: filters, order, limit, range, offset, single, maybe_single, execute
#   NOT allowed: insert, update, delete, upsert
# ---------------------------------------------------------------------------
class MockSelectBuilder(_MockExecuteMixin):
    """Mirrors SyncSelectRequestBuilder."""

    def __init__(self, data=None, count=None, response_queue=None, response_idx=None):
        self._data = data or []
        self._single_mode = False
        self._count = count
        self._response_queue = response_queue
        self._response_idx = response_idx

    # --- Filters (return self) ---
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
    def contained_by(self, *a, **k): return self
    def overlaps(self, *a, **k): return self
    def filter(self, *a, **k): return self
    def match(self, *a, **k): return self
    def fts(self, *a, **k): return self
    def text_search(self, *a, **k): return self

    @property
    def not_(self): return self

    # --- Modifiers ---
    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def range(self, *a, **k): return self
    def offset(self, *a, **k): return self

    # --- Terminals ---
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
#   Allowed: filters, execute
#   NOT allowed: insert, update, delete, upsert, order, limit, range, select, single
# ---------------------------------------------------------------------------
class MockFilterBuilder(_MockExecuteMixin):
    """Mirrors SyncFilterRequestBuilder."""

    def __init__(self, data=None, response_queue=None, response_idx=None):
        self._data = data or []
        self._single_mode = False
        self._count = None
        self._response_queue = response_queue
        self._response_idx = response_idx

    # --- Filters (return self) ---
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
    def contained_by(self, *a, **k): return self
    def overlaps(self, *a, **k): return self
    def filter(self, *a, **k): return self
    def match(self, *a, **k): return self

    @property
    def not_(self): return self

    def execute(self):
        return self._do_execute()


# ---------------------------------------------------------------------------
# MockQueryBuilder — returned by .insert() / .upsert()
#   Allowed: execute only
#   NOT allowed: filters, order, limit, range, insert, update, delete, select, single
# ---------------------------------------------------------------------------
class MockQueryBuilder(_MockExecuteMixin):
    """Mirrors SyncQueryRequestBuilder."""

    def __init__(self, data=None, response_queue=None, response_idx=None):
        self._data = data or []
        self._single_mode = False
        self._count = None
        self._response_queue = response_queue
        self._response_idx = response_idx

    def execute(self):
        return self._do_execute()


# ---------------------------------------------------------------------------
# MockRequestBuilder — returned by .table()
#   This is the entry point: only .select/.insert/.update/.delete/.upsert
# ---------------------------------------------------------------------------
class MockRequestBuilder:
    """Mirrors SyncRequestBuilder — the object returned by .table(name)."""

    def __init__(self, data=None):
        self._data = data or []
        # Normalize: real SDK always returns lists, so wrap single dicts
        if isinstance(self._data, dict):
            self._data = [self._data]
        # Response queue for sequential responses (shared across child builders)
        self._response_queue = None
        self._response_idx = None

    def set_responses(self, responses):
        """Configure sequential responses for this table's operations."""
        self._response_queue = responses
        self._response_idx = [0]

    def select(self, *a, **k):
        count = k.get("count")
        return MockSelectBuilder(
            self._data,
            count=len(self._data) if count == "exact" else None,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
        )

    def insert(self, *a, **k):
        return MockQueryBuilder(
            self._data,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
        )

    def update(self, *a, **k):
        return MockFilterBuilder(
            self._data,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
        )

    def upsert(self, *a, **k):
        return MockFilterBuilder(
            self._data,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
        )

    def delete(self, *a, **k):
        return MockFilterBuilder(
            self._data,
            response_queue=self._response_queue,
            response_idx=self._response_idx,
        )


# ---------------------------------------------------------------------------
# MockSupabaseClient
# ---------------------------------------------------------------------------
class MockSupabaseClient:
    def __init__(self, data=None):
        self._data = data
        self.auth = MagicMock()
        self._tables = {}
        self._rpcs = {}

    def table(self, name):
        if name not in self._tables:
            self._tables[name] = MockRequestBuilder(self._data)
        return self._tables[name]

    def set_table_data(self, name, data):
        self._tables[name] = MockRequestBuilder(data)

    def set_sequential_responses(self, table_name, responses):
        """Configure a table to return sequential responses on each .execute() call."""
        builder = self.table(table_name)
        builder.set_responses(responses)

    def set_rpc_data(self, name, data):
        self._rpcs[name] = data

    def rpc(self, name, params=None):
        data = self._rpcs.get(name, ["2026-02-23"])
        return MockSelectBuilder(data)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
class MockUser:
    def __init__(self, id="test-user-123", email="test@example.com"):
        self.id = id
        self.email = email
        self.user_metadata = {"org_id": "test-org-123"}


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
