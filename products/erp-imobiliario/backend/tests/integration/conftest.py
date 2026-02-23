"""
Integration test fixtures with stateful mocking.

These fixtures provide a more realistic testing environment by maintaining
state across operations, allowing for full CRUD cycle testing.
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


class StatefulQueryBuilder:
    """
    Chainable mock that maintains state across operations.
    Simulates real database behavior for integration testing.
    """
    def __init__(self, storage: Dict[str, List[Dict]], table_name: str):
        self._storage = storage
        self._table = table_name
        self._filters = []
        self._order_by = None
        self._order_desc = False
        self._limit_val = None
        self._offset_val = 0
        self._single = False
        self._count_mode = False
        self._pending_insert = None
        self._pending_update = None
        self._pending_delete = False
        self._select_fields = "*"

    def select(self, fields="*", count=None):
        self._select_fields = fields
        if count == "exact":
            self._count_mode = True
        return self

    def insert(self, data):
        if isinstance(data, list):
            self._pending_insert = data
        else:
            self._pending_insert = [data]
        return self

    def update(self, data):
        self._pending_update = data
        return self

    def upsert(self, data, on_conflict=None):
        self._pending_insert = [data] if not isinstance(data, list) else data
        return self

    def delete(self):
        self._pending_delete = True
        return self

    def eq(self, field, value):
        self._filters.append(("eq", field, value))
        return self

    def neq(self, field, value):
        self._filters.append(("neq", field, value))
        return self

    def in_(self, field, values):
        self._filters.append(("in", field, values))
        return self

    def gte(self, field, value):
        self._filters.append(("gte", field, value))
        return self

    def lte(self, field, value):
        self._filters.append(("lte", field, value))
        return self

    def ilike(self, field, pattern):
        self._filters.append(("ilike", field, pattern))
        return self

    def order(self, field, desc=False):
        self._order_by = field
        self._order_desc = desc
        return self

    def limit(self, n):
        self._limit_val = n
        return self

    def range(self, start, end):
        self._offset_val = start
        self._limit_val = end - start + 1
        return self

    def single(self):
        self._single = True
        return self

    def _apply_filters(self, data: List[Dict]) -> List[Dict]:
        """Apply all registered filters to the data."""
        result = data.copy()

        for op, field, value in self._filters:
            if op == "eq":
                result = [r for r in result if r.get(field) == value]
            elif op == "neq":
                result = [r for r in result if r.get(field) != value]
            elif op == "in":
                result = [r for r in result if r.get(field) in value]
            elif op == "gte":
                result = [r for r in result if r.get(field, 0) >= value]
            elif op == "lte":
                result = [r for r in result if r.get(field, 0) <= value]
            elif op == "ilike":
                pattern = value.strip("%").lower()
                result = [r for r in result if pattern in str(r.get(field, "")).lower()]

        return result

    def execute(self) -> StatefulMockResponse:
        """Execute the query against the stateful storage."""
        table_data = self._storage.setdefault(self._table, [])

        # Handle INSERT
        if self._pending_insert:
            for item in self._pending_insert:
                new_item = item.copy()
                if "id" not in new_item:
                    new_item["id"] = str(uuid.uuid4())
                new_item["created_at"] = datetime.utcnow().isoformat()
                new_item["updated_at"] = datetime.utcnow().isoformat()
                table_data.append(new_item)
            return StatefulMockResponse(data=self._pending_insert)

        # Handle UPDATE
        if self._pending_update:
            filtered = self._apply_filters(table_data)
            for item in filtered:
                item.update(self._pending_update)
                item["updated_at"] = datetime.utcnow().isoformat()
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

        # Apply ordering
        if self._order_by:
            result = sorted(
                result,
                key=lambda x: x.get(self._order_by, ""),
                reverse=self._order_desc
            )

        # Apply pagination
        if self._offset_val > 0:
            result = result[self._offset_val:]
        if self._limit_val:
            result = result[:self._limit_val]

        # Handle single mode
        if self._single:
            result = result[0] if result else None

        return StatefulMockResponse(data=result, count=total_count if self._count_mode else None)


class StatefulMockClient:
    """
    Mock Supabase client that maintains state across operations.
    Allows testing complete workflows (create → read → update → delete).
    """
    def __init__(self):
        self._storage: Dict[str, List[Dict]] = {}
        self.auth = MagicMock()

    def table(self, name: str) -> StatefulQueryBuilder:
        return StatefulQueryBuilder(self._storage, name)

    def rpc(self, name: str):
        """Mock RPC calls."""
        return StatefulQueryBuilder({"_rpc": [datetime.now().strftime("%Y-%m-%d")]}, "_rpc")

    def seed_data(self, table: str, data: List[Dict]):
        """Seed initial data for a table."""
        self._storage[table] = [
            {**d, "id": d.get("id", str(uuid.uuid4())), "created_at": datetime.utcnow().isoformat()}
            for d in data
        ]

    def get_table_data(self, table: str) -> List[Dict]:
        """Get all data from a table (for assertions)."""
        return self._storage.get(table, [])

    def clear(self):
        """Clear all stored data."""
        self._storage.clear()


class MockUser:
    def __init__(self, id="test-user-integration", email="integration@test.com"):
        self.id = id
        self.email = email


class MockUserResponse:
    def __init__(self, user=None):
        self.user = user or MockUser()


class IntegrationClient:
    """
    Test client for integration tests with stateful backend.
    """
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

    def seed(self, table: str, data: List[Dict]):
        """Seed test data into a table."""
        self.mock_supabase.seed_data(table, data)

    def get_data(self, table: str) -> List[Dict]:
        """Get current table data for assertions."""
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
         patch("app.dependencies.get_supabase_client", return_value=mock_sb), \
         patch("app.dependencies.log_action", MagicMock()):

        from app.main import app
        tc = TestClient(app)
        client = IntegrationClient(tc, mock_sb)
        yield client
        mock_sb.clear()
