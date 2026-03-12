"""
Integration test fixtures with stateful mocking.

These fixtures provide a more realistic testing environment by maintaining
state across operations, allowing for full CRUD cycle and cross-service
workflow testing.

Like the unit-test conftest, the builders here mirror the real SDK hierarchy
so invalid method chains (e.g. .insert().order()) are caught at test time.
"""
import pytest
import uuid
from typing import Dict, List, Optional, Any
from unittest.mock import MagicMock, patch
from datetime import datetime
from fastapi.testclient import TestClient


class StatefulMockResponse:
    """Mock response with data and count support."""
    def __init__(self, data=None, count=None, error=None):
        self.data = data
        self.count = count
        self.error = error


# Simulated DB column defaults for known tables
TABLE_DEFAULTS = {
    "contas": {"ativo": True, "moeda": "BRL"},
    "carteiras": {"ativo": True},
    "metas": {"status": "ativa"},
    "recorrentes": {"ativo": True, "is_automatico": True},
}


# ---------------------------------------------------------------------------
# Shared execution logic
# ---------------------------------------------------------------------------
class _StatefulExecuteMixin:
    """Shared execute() for all stateful builders."""

    def _do_execute(self):
        table_data = self._storage.setdefault(self._table, [])

        # Handle INSERT
        if self._pending_insert:
            inserted = []
            defaults = TABLE_DEFAULTS.get(self._table, {})
            for item in self._pending_insert:
                new_item = {**defaults, **item}
                if "id" not in new_item:
                    new_item["id"] = str(uuid.uuid4())
                new_item.setdefault("created_at", datetime.utcnow().isoformat())
                new_item.setdefault("updated_at", datetime.utcnow().isoformat())
                table_data.append(new_item)
                inserted.append(new_item)
            if self._single_mode and inserted:
                return StatefulMockResponse(data=inserted[0])
            return StatefulMockResponse(data=inserted)

        # Handle UPDATE
        if self._pending_update:
            filtered = self._apply_filters(table_data)
            for item in filtered:
                item.update(self._pending_update)
                item["updated_at"] = datetime.utcnow().isoformat()
            if self._single_mode and filtered:
                return StatefulMockResponse(data=filtered[0])
            return StatefulMockResponse(data=filtered)

        # Handle DELETE
        if self._pending_delete:
            filtered = self._apply_filters(table_data)
            filtered_ids = {r.get("id") for r in filtered}
            self._storage[self._table] = [r for r in table_data if r.get("id") not in filtered_ids]
            return StatefulMockResponse(data=filtered)

        # Handle SELECT
        result = self._apply_filters(table_data)
        total_count = len(result)

        if self._order_by:
            result = sorted(
                result,
                key=lambda x: x.get(self._order_by, ""),
                reverse=self._order_desc,
            )

        if self._offset_val > 0:
            result = result[self._offset_val:]
        if self._limit_val:
            result = result[:self._limit_val]

        if self._single_mode:
            result = result[0] if result else None

        return StatefulMockResponse(data=result, count=total_count if self._count_mode else None)

    def _apply_filters(self, data: List[Dict]) -> List[Dict]:
        result = data.copy()
        for op, field, value in self._filters:
            if op == "eq":
                result = [r for r in result if r.get(field) == value]
            elif op == "neq":
                result = [r for r in result if r.get(field) != value]
            elif op == "in":
                result = [r for r in result if r.get(field) in value]
            elif op == "gte":
                result = [r for r in result if str(r.get(field, "")) >= str(value)]
            elif op == "lte":
                result = [r for r in result if str(r.get(field, "")) <= str(value)]
            elif op == "gt":
                result = [r for r in result if str(r.get(field, "")) > str(value)]
            elif op == "lt":
                result = [r for r in result if str(r.get(field, "")) < str(value)]
            elif op == "ilike":
                pattern = value.strip("%").lower()
                result = [r for r in result if pattern in str(r.get(field, "")).lower()]
        return result


def _init_base_state(obj, storage, table_name):
    """Initialize common state fields on a builder."""
    obj._storage = storage
    obj._table = table_name
    obj._filters = []
    obj._order_by = None
    obj._order_desc = False
    obj._limit_val = None
    obj._offset_val = 0
    obj._single_mode = False
    obj._count_mode = False
    obj._pending_insert = None
    obj._pending_update = None
    obj._pending_delete = False


# ---------------------------------------------------------------------------
# StatefulSelectBuilder — returned by .select()
# ---------------------------------------------------------------------------
class StatefulSelectBuilder(_StatefulExecuteMixin):
    """Mirrors SyncSelectRequestBuilder."""

    def __init__(self, storage, table_name, count_mode=False):
        _init_base_state(self, storage, table_name)
        self._count_mode = count_mode

    # Filters
    def eq(self, field, value):
        self._filters.append(("eq", field, value)); return self
    def neq(self, field, value):
        self._filters.append(("neq", field, value)); return self
    def in_(self, field, values):
        self._filters.append(("in", field, values)); return self
    def gte(self, field, value):
        self._filters.append(("gte", field, value)); return self
    def lte(self, field, value):
        self._filters.append(("lte", field, value)); return self
    def gt(self, field, value):
        self._filters.append(("gt", field, value)); return self
    def lt(self, field, value):
        self._filters.append(("lt", field, value)); return self
    def ilike(self, field, pattern):
        self._filters.append(("ilike", field, pattern)); return self
    def like(self, field, pattern):
        self._filters.append(("like", field, pattern)); return self
    def is_(self, *a, **k): return self
    def or_(self, *a, **k): return self
    def contains(self, *a, **k): return self
    def filter(self, *a, **k): return self

    @property
    def not_(self): return self

    # Modifiers
    def order(self, field, desc=False):
        self._order_by = field; self._order_desc = desc; return self
    def limit(self, n):
        self._limit_val = n; return self
    def range(self, start, end):
        self._offset_val = start; self._limit_val = end - start + 1; return self
    def offset(self, n):
        self._offset_val = n; return self

    # Terminals
    def single(self):
        self._single_mode = True; return self
    def maybe_single(self):
        self._single_mode = True; return self
    def execute(self):
        return self._do_execute()


# ---------------------------------------------------------------------------
# StatefulFilterBuilder — returned by .update() / .delete()
# ---------------------------------------------------------------------------
class StatefulFilterBuilder(_StatefulExecuteMixin):
    """Mirrors SyncFilterRequestBuilder."""

    def __init__(self, storage, table_name, pending_update=None, pending_delete=False):
        _init_base_state(self, storage, table_name)
        self._pending_update = pending_update
        self._pending_delete = pending_delete

    # Filters
    def eq(self, field, value):
        self._filters.append(("eq", field, value)); return self
    def neq(self, field, value):
        self._filters.append(("neq", field, value)); return self
    def in_(self, field, values):
        self._filters.append(("in", field, values)); return self
    def gte(self, field, value):
        self._filters.append(("gte", field, value)); return self
    def lte(self, field, value):
        self._filters.append(("lte", field, value)); return self
    def gt(self, field, value):
        self._filters.append(("gt", field, value)); return self
    def lt(self, field, value):
        self._filters.append(("lt", field, value)); return self
    def ilike(self, field, pattern):
        self._filters.append(("ilike", field, pattern)); return self
    def is_(self, *a, **k): return self
    def contains(self, *a, **k): return self

    @property
    def not_(self): return self

    def execute(self):
        return self._do_execute()


# ---------------------------------------------------------------------------
# StatefulQueryBuilder — returned by .insert() / .upsert()
# ---------------------------------------------------------------------------
class StatefulQueryBuilder(_StatefulExecuteMixin):
    """Mirrors SyncQueryRequestBuilder."""

    def __init__(self, storage, table_name, pending_insert=None):
        _init_base_state(self, storage, table_name)
        self._pending_insert = pending_insert

    def execute(self):
        return self._do_execute()


# ---------------------------------------------------------------------------
# StatefulRequestBuilder — returned by .table()
# ---------------------------------------------------------------------------
class StatefulRequestBuilder:
    """Mirrors SyncRequestBuilder — entry point from .table(name)."""

    def __init__(self, storage, table_name):
        self._storage = storage
        self._table = table_name

    def select(self, fields="*", count=None):
        return StatefulSelectBuilder(
            self._storage, self._table,
            count_mode=(count == "exact"),
        )

    def insert(self, data):
        items = data if isinstance(data, list) else [data]
        return StatefulQueryBuilder(self._storage, self._table, pending_insert=items)

    def update(self, data):
        return StatefulFilterBuilder(self._storage, self._table, pending_update=data)

    def upsert(self, data, on_conflict=None):
        items = data if isinstance(data, list) else [data]
        return StatefulQueryBuilder(self._storage, self._table, pending_insert=items)

    def delete(self):
        return StatefulFilterBuilder(self._storage, self._table, pending_delete=True)


# ---------------------------------------------------------------------------
# StatefulMockClient
# ---------------------------------------------------------------------------
class StatefulMockClient:
    """
    Mock Supabase client that maintains state across operations.
    Allows testing complete workflows (create -> read -> update -> delete).
    """
    def __init__(self):
        self._storage: Dict[str, List[Dict]] = {}
        self.auth = MagicMock()

    def table(self, name: str) -> StatefulRequestBuilder:
        return StatefulRequestBuilder(self._storage, name)

    def seed_data(self, table: str, data: List[Dict]):
        self._storage[table] = [
            {**d, "id": d.get("id", str(uuid.uuid4())), "created_at": datetime.utcnow().isoformat()}
            for d in data
        ]

    def get_table_data(self, table: str) -> List[Dict]:
        return self._storage.get(table, [])

    def clear(self):
        self._storage.clear()


class MockUser:
    def __init__(self, id="test-user-integration", email="integration@test.com"):
        self.id = id
        self.email = email
        self.user_metadata = {"org_id": "test-org-123"}


class MockUserResponse:
    def __init__(self, user=None):
        self.user = user or MockUser()


class IntegrationClient:
    """Test client for integration tests with stateful backend."""
    def __init__(self, tc: TestClient, mock_sb: StatefulMockClient):
        self._tc = tc
        self.mock_supabase = mock_sb
        self._headers = {"Authorization": "Bearer test-integration-token"}

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

    def seed(self, table: str, data: List[Dict]):
        self.mock_supabase.seed_data(table, data)

    def get_data(self, table: str) -> List[Dict]:
        return self.mock_supabase.get_table_data(table)


@pytest.fixture
def integration_client():
    """
    Integration test client with stateful mocking.
    Data persists across operations within a single test.
    """
    mock_sb = StatefulMockClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse())

    with patch("app.database.get_supabase_client", return_value=mock_sb), \
         patch("app.dependencies.get_supabase_client", return_value=mock_sb):

        from app.main import app
        tc = TestClient(app)
        client = IntegrationClient(tc, mock_sb)
        yield client
        mock_sb.clear()
