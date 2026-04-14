"""
Mock Supabase builders that mirror the real postgrest SDK hierarchy.

Builder hierarchy (postgrest 0.17.2):
  table(name)        → MockRequestBuilder
    .select(...)     → MockSelectBuilder   (filters, order, limit, range, single, execute)
    .insert(...)     → MockQueryBuilder    (execute only)
    .update(...)     → MockFilterBuilder   (filters, execute)
    .delete()        → MockFilterBuilder
    .upsert(...)     → MockFilterBuilder

All builders support optional response queues for sequential test scenarios.
"""
from __future__ import annotations

from typing import Optional
from unittest.mock import MagicMock


class MockSupabaseResponse:
    """Simulates a Supabase PostgREST response."""

    def __init__(self, data=None, error=None, count=None):
        self.data = data or []
        self.error = error
        self.count = count


# ---------------------------------------------------------------------------
# Base mixin with shared execute logic
# ---------------------------------------------------------------------------

class _MockExecuteMixin:
    """Shared execute() logic for all builder types."""

    _data: list
    _single_mode: bool
    _count: Optional[int]
    _response_queue: Optional[list]
    _response_idx: Optional[list]

    def _do_execute(self):
        if self._response_queue is not None:
            idx = self._response_idx[0]
            self._response_idx[0] += 1
            if idx < len(self._response_queue):
                resp = self._response_queue[idx]
            else:
                resp = MockSupabaseResponse(data=[])
            # Apply single-mode unwrapping to queued responses too
            if self._single_mode and isinstance(resp.data, list):
                resp = MockSupabaseResponse(
                    data=resp.data[0] if resp.data else None,
                    error=resp.error,
                    count=resp.count,
                )
            self._single_mode = False
            return resp

        data = self._data
        if self._single_mode and isinstance(data, list):
            data = data[0] if data else None
        self._single_mode = False
        return MockSupabaseResponse(data=data, count=self._count)


# ---------------------------------------------------------------------------
# Filter methods mixin (DRY — used by SelectBuilder and FilterBuilder)
# ---------------------------------------------------------------------------

class _FilterMixin:
    """All PostgREST filter methods. Returns self for chaining."""

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
    def or_(self, *a, **k): return self

    @property
    def not_(self): return self


# ---------------------------------------------------------------------------
# MockSelectBuilder — returned by .select()
# ---------------------------------------------------------------------------

class MockSelectBuilder(_FilterMixin, _MockExecuteMixin):
    """Mirrors SyncSelectRequestBuilder."""

    def __init__(self, data=None, count=None, response_queue=None, response_idx=None):
        self._data = data or []
        self._single_mode = False
        self._count = count
        self._response_queue = response_queue
        self._response_idx = response_idx

    def order(self, *a, **k): return self
    def limit(self, *a, **k): return self
    def range(self, *a, **k): return self
    def offset(self, *a, **k): return self

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

class MockFilterBuilder(_FilterMixin, _MockExecuteMixin):
    """Mirrors SyncFilterRequestBuilder."""

    def __init__(self, data=None, response_queue=None, response_idx=None):
        self._data = data or []
        self._single_mode = False
        self._count = None
        self._response_queue = response_queue
        self._response_idx = response_idx

    def execute(self):
        return self._do_execute()


# ---------------------------------------------------------------------------
# MockQueryBuilder — returned by .insert() / .upsert()
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
# ---------------------------------------------------------------------------

class MockRequestBuilder:
    """Mirrors SyncRequestBuilder — the object returned by .table(name)."""

    def __init__(self, data=None):
        self._data = data or []
        if isinstance(self._data, dict):
            self._data = [self._data]
        self._response_queue = None
        self._response_idx = None

    def set_responses(self, responses):
        """Configure sequential responses for this table."""
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
    """Mocked Supabase client with per-table data control and response queues."""

    def __init__(self, data=None):
        self._data = data
        self.auth = MagicMock()
        self.storage = MagicMock()
        self._tables = {}
        self._rpcs = {}

    def table(self, name):
        if name not in self._tables:
            self._tables[name] = MockRequestBuilder(self._data)
        return self._tables[name]

    def set_table_data(self, name, data):
        """Set mock data for a specific table."""
        self._tables[name] = MockRequestBuilder(data)

    def set_sequential_responses(self, table_name, responses):
        """Configure a table to return sequential responses on each execute()."""
        builder = self.table(table_name)
        builder.set_responses(responses)

    def set_rpc_data(self, name, data):
        """Set mock data for an RPC call."""
        self._rpcs[name] = data

    def rpc(self, name, params=None):
        """Simulate an RPC call."""
        data = self._rpcs.get(name, [])
        return MockSelectBuilder(data)
