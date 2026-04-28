"""Tests for the webhook retention service.

compliance-audit-reconciliation Phase 6 (finding 8 — LGPD minimization).
Exercises call-shape + idempotency. The mock client doesn't simulate
state mutation on `.delete()` — we assert dispatch + purge_row_count only.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from app.services import webhook_retention_service


def _mock_db(expired_rows=None):
    db = MagicMock()
    table = MagicMock()
    query = MagicMock()

    query.data = expired_rows or []

    # Chain: db.table(...).select(...).lt(...).limit(...).execute() -> query
    table.select.return_value = table
    table.lt.return_value = table
    table.limit.return_value = table
    table.execute.return_value = query

    # Chain: db.table(...).delete().in_(...).execute() -> anything
    delete_chain = MagicMock()
    delete_chain.in_.return_value = delete_chain
    delete_chain.execute.return_value = MagicMock(data=[])
    table.delete.return_value = delete_chain

    db.table.return_value = table
    return db, table, delete_chain


class TestFindExpiredDeliveries:
    def test_returns_empty_when_none_expired(self):
        db, _, _ = _mock_db(expired_rows=[])
        assert webhook_retention_service.find_expired_deliveries(db) == []

    def test_returns_expired(self):
        rows = [
            {"id": "d1", "retention_until": "2026-01-01T00:00:00Z"},
            {"id": "d2", "retention_until": "2026-02-01T00:00:00Z"},
        ]
        db, _, _ = _mock_db(expired_rows=rows)
        assert webhook_retention_service.find_expired_deliveries(db) == rows


class TestPurgeExpiredDeliveries:
    def test_purge_zero_when_none(self):
        db, _, delete_chain = _mock_db(expired_rows=[])
        purged = webhook_retention_service.purge_expired_deliveries(db)
        assert purged == 0
        delete_chain.in_.assert_not_called()

    def test_purge_calls_delete_in_with_ids(self):
        rows = [{"id": "d1", "retention_until": "2026-01-01T00:00:00Z"},
                {"id": "d2", "retention_until": "2026-01-01T00:00:00Z"}]
        db, _, delete_chain = _mock_db(expired_rows=rows)
        purged = webhook_retention_service.purge_expired_deliveries(db)
        assert purged == 2
        delete_chain.in_.assert_called_once_with("id", ["d1", "d2"])


class TestRunRetentionSweep:
    def test_sweep_returns_shape(self):
        db, _, _ = _mock_db(expired_rows=[])
        result = webhook_retention_service.run_retention_sweep(db)
        assert result == {"purged": 0}

    def test_sweep_with_expired(self):
        db, _, _ = _mock_db(expired_rows=[{"id": "d1", "retention_until": "2026-01-01T00:00:00Z"}])
        result = webhook_retention_service.run_retention_sweep(db)
        assert result == {"purged": 1}
