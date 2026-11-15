"""NOC_REQUIRE_REAL_PG=1 turns a missing real-Postgres harness from a SKIP into a FAILURE.

CI's seed-backend-tests job sets the flag: there, a PGlite or initdb harness that cannot start is a broken
setup, and a skipped proof would read as green in the pytest summary. Locally (flag unset) the harness still
answers "unavailable" and the caller skips, visibly. Driven through the env seams only (no patching of the
modules under test): `NOCTUS_PGLITE_NODE_DIR` and `NOCTUS_TEST_PG_BIN` pointed at an empty directory.
"""
from __future__ import annotations

import pytest

from noctusai_lib.testing.pglite import REQUIRE_REAL_PG_ENV, RealPgUnavailable, pglite_available, real_pg_required
from noctusai_lib.testing.pgserver import disposable_postgres


@pytest.fixture
def no_harness(tmp_path, monkeypatch):
    monkeypatch.setenv("NOCTUS_PGLITE_NODE_DIR", str(tmp_path))  # no node_modules, no stubs
    monkeypatch.setenv("NOCTUS_TEST_PG_BIN", str(tmp_path))      # no initdb / pg_ctl
    monkeypatch.delenv("NOCTUS_TEST_PG_DSN", raising=False)
    return monkeypatch


@pytest.mark.parametrize("value, expected", [("1", True), ("", False), ("0", False), ("true", False)])
def test_only_the_literal_1_requires_real_pg(monkeypatch, value, expected):
    monkeypatch.setenv(REQUIRE_REAL_PG_ENV, value)
    assert real_pg_required() is expected


def test_without_the_flag_a_missing_pglite_reads_unavailable(no_harness):
    no_harness.delenv(REQUIRE_REAL_PG_ENV, raising=False)
    assert pglite_available() is False


def test_with_the_flag_a_missing_pglite_raises(no_harness):
    no_harness.setenv(REQUIRE_REAL_PG_ENV, "1")
    with pytest.raises(RealPgUnavailable, match="PGlite harness unavailable.*npm ci"):
        pglite_available()


def test_without_the_flag_a_missing_server_yields_none(no_harness):
    no_harness.delenv(REQUIRE_REAL_PG_ENV, raising=False)
    with disposable_postgres() as dsn:
        assert dsn is None


def test_with_the_flag_a_missing_server_raises(no_harness):
    no_harness.setenv(REQUIRE_REAL_PG_ENV, "1")
    with pytest.raises(RealPgUnavailable, match="no Postgres server"):
        with disposable_postgres():
            pass
