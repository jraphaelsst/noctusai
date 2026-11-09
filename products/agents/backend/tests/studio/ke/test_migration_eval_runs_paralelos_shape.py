"""eval_runs_paralelos (071) lets several eval runs of ONE version execute at once (owner, 2026-11-09: batch evals run in parallel, not
queued). Both one-in-flight-per-version indexes go; a plain (version_id, status) lookup index replaces each."""
from __future__ import annotations

import re
from pathlib import Path

from noctusai_lib.testing.migrations import migration_sql

SQL = migration_sql(Path(__file__).resolve().parents[3] / "migrations", "eval_runs_paralelos")


def test_drops_both_one_in_flight_indexes():
    assert "DROP INDEX IF EXISTS agents.eval_runs_one_active_per_version_idx;" in SQL
    assert "DROP INDEX IF EXISTS agents.uq_eval_mecanismo_runs_um_em_execucao;" in SQL


def test_creates_no_unique_index():
    assert not re.search(r"CREATE\s+UNIQUE\s+INDEX", SQL, re.I)


def test_keeps_the_version_lookup_indexed_for_both_suites():
    assert "ON agents.eval_runs (version_id, status)" in SQL
    assert "ON agents.eval_mecanismo_runs (version_id, status)" in SQL
