"""Tests for the batch-speed-gain SQLite tracker."""
from __future__ import annotations

import os
import sys
import sqlite3
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tools.noctus.dev.batch_speed_gains import (
    cumulative_stats,
    get_db_path,
    log_batch,
    query_batches,
    update_batch,
)


@pytest.fixture
def tmp_db(monkeypatch) -> Path:
    fd, path_str = tempfile.mkstemp(prefix="batch_speed_gains_test_", suffix=".db")
    os.close(fd)
    p = Path(path_str)
    p.unlink(missing_ok=True)
    monkeypatch.setenv("NOCTUS_BATCH_SPEED_GAINS_DB", str(p))
    yield p
    p.unlink(missing_ok=True)


class TestGetDbPath:
    def test_default_path_under_mcp_data(self, monkeypatch):
        monkeypatch.delenv("NOCTUS_BATCH_SPEED_GAINS_DB", raising=False)
        path = get_db_path()
        assert path.parent.name == "data"
        assert path.name == "batch_speed_gains.db"

    def test_env_override_respected(self, monkeypatch):
        monkeypatch.setenv("NOCTUS_BATCH_SPEED_GAINS_DB", "/tmp/custom.db")
        assert str(get_db_path()) == "/tmp/custom.db"


class TestLogBatch:
    def test_inserts_and_computes_gain(self, tmp_db):
        new_id = log_batch(
            orchestration_slug="orch-x",
            batch_label="1A",
            engineer_count=2,
            wall_clock_parallel_s=100.0,
            estimated_serial_s=200.0,
            notes="seed batch",
            status="COMPLETED",
        )
        assert new_id == 1
        rows = query_batches("orch-x")
        assert len(rows) == 1
        row = rows[0]
        assert row["engineer_count"] == 2
        assert row["speed_gain_pct"] == 50.0
        assert row["status"] == "COMPLETED"
        assert row["closed_at"] is not None

    def test_in_flight_status_default(self, tmp_db):
        log_batch(
            orchestration_slug="orch-y",
            batch_label="1A",
            engineer_count=3,
        )
        row = query_batches("orch-y")[0]
        assert row["status"] == "IN_FLIGHT"
        assert row["closed_at"] is None
        assert row["speed_gain_pct"] is None

    def test_unique_constraint_on_orchestration_label(self, tmp_db):
        log_batch(orchestration_slug="orch-z", batch_label="1A", engineer_count=2)
        with pytest.raises(sqlite3.IntegrityError):
            log_batch(orchestration_slug="orch-z", batch_label="1A", engineer_count=3)

    def test_engineer_count_must_be_positive(self, tmp_db):
        with pytest.raises(ValueError):
            log_batch(orchestration_slug="o", batch_label="1A", engineer_count=0)

    def test_invalid_status_rejected(self, tmp_db):
        with pytest.raises(ValueError):
            log_batch(
                orchestration_slug="o",
                batch_label="1A",
                engineer_count=1,
                status="WHATEVER",
            )


class TestUpdateBatch:
    def test_in_flight_to_completed(self, tmp_db):
        log_batch(orchestration_slug="o", batch_label="1A", engineer_count=3)
        ok = update_batch(
            orchestration_slug="o",
            batch_label="1A",
            wall_clock_parallel_s=300.0,
            estimated_serial_s=900.0,
            status="COMPLETED",
        )
        assert ok is True
        row = query_batches("o")[0]
        assert row["status"] == "COMPLETED"
        assert row["speed_gain_pct"] == pytest.approx(66.7, abs=0.1)
        assert row["closed_at"] is not None

    def test_returns_false_when_no_row_matches(self, tmp_db):
        ok = update_batch(orchestration_slug="o", batch_label="missing", status="COMPLETED")
        assert ok is False

    def test_no_op_when_nothing_to_update(self, tmp_db):
        log_batch(orchestration_slug="o", batch_label="1A", engineer_count=1)
        assert update_batch(orchestration_slug="o", batch_label="1A") is False


class TestQueryBatches:
    def test_filters_by_orchestration(self, tmp_db):
        log_batch(orchestration_slug="o1", batch_label="1A", engineer_count=2)
        log_batch(orchestration_slug="o2", batch_label="1A", engineer_count=3)
        rows = query_batches("o1")
        assert len(rows) == 1
        assert rows[0]["orchestration_slug"] == "o1"

    def test_returns_all_when_none(self, tmp_db):
        log_batch(orchestration_slug="o1", batch_label="1A", engineer_count=2)
        log_batch(orchestration_slug="o2", batch_label="1A", engineer_count=3)
        rows = query_batches()
        assert len(rows) == 2


class TestCumulativeStats:
    def test_aggregates_completed_only(self, tmp_db):
        log_batch(
            orchestration_slug="o",
            batch_label="1A",
            engineer_count=2,
            wall_clock_parallel_s=100.0,
            estimated_serial_s=200.0,
            status="COMPLETED",
        )
        log_batch(
            orchestration_slug="o",
            batch_label="1B",
            engineer_count=3,
            wall_clock_parallel_s=300.0,
            estimated_serial_s=900.0,
            status="COMPLETED",
        )
        log_batch(
            orchestration_slug="o",
            batch_label="1C",
            engineer_count=3,
            status="IN_FLIGHT",  # excluded from cumulative
        )
        stats = cumulative_stats("o")
        assert stats["batch_count"] == 2
        assert stats["engineer_total"] == 5
        assert stats["parallel_total_s"] == 400.0
        assert stats["serial_total_s"] == 1100.0
        assert stats["speed_gain_pct"] == pytest.approx(63.6, abs=0.1)

    def test_returns_zeros_for_unknown_orchestration(self, tmp_db):
        stats = cumulative_stats("nothing-here")
        assert stats["batch_count"] == 0
        assert stats["engineer_total"] == 0
        assert stats["speed_gain_pct"] is None
