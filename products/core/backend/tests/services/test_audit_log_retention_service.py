"""Tests for the audit log retention service.

Owner directive (2026-09-23) + migration 053. Unlike webhook_retention
(`.table(...).delete()`), audit_logs is append-only — the sweep MUST go
through the `purge_expired_audit_logs` RPC (the only path the guard trigger
allows). These tests assert the RPC call shape + return-value handling, not
row-level state mutation (the mock doesn't simulate a real DB function).
"""
from __future__ import annotations

from unittest.mock import MagicMock

from app.services import audit_log_retention_service


def _mock_db(rpc_return=None):
    db = MagicMock()
    rpc_chain = MagicMock()
    rpc_chain.execute.return_value = MagicMock(data=rpc_return)
    db.rpc.return_value = rpc_chain
    return db, rpc_chain


class TestRunRetentionSweep:
    def test_calls_the_purge_rpc_with_default_batch_limit(self):
        db, rpc_chain = _mock_db(rpc_return=0)
        audit_log_retention_service.run_retention_sweep(db)
        db.rpc.assert_called_once_with("purge_expired_audit_logs", {"p_batch_limit": 5000})

    def test_calls_the_purge_rpc_with_a_custom_batch_limit(self):
        db, rpc_chain = _mock_db(rpc_return=0)
        audit_log_retention_service.run_retention_sweep(db, batch_limit=100)
        db.rpc.assert_called_once_with("purge_expired_audit_logs", {"p_batch_limit": 100})

    def test_returns_the_purged_count(self):
        db, _ = _mock_db(rpc_return=3)
        result = audit_log_retention_service.run_retention_sweep(db)
        assert result == {"purged": 3}

    def test_zero_purged_is_a_valid_result(self):
        db, _ = _mock_db(rpc_return=0)
        result = audit_log_retention_service.run_retention_sweep(db)
        assert result == {"purged": 0}

    def test_non_int_rpc_response_is_treated_as_zero_never_raises(self):
        """A malformed/None RPC response must not crash the scheduler job —
        fail closed to 'nothing purged', never propagate a TypeError."""
        db, _ = _mock_db(rpc_return=None)
        result = audit_log_retention_service.run_retention_sweep(db)
        assert result == {"purged": 0}
