from __future__ import annotations

import pytest

from noctusai_lib.testing.migrations import (
    MigrationLookupError,
    migration_path,
    migration_sql,
)


def _mk(tmp_path, *names):
    d = tmp_path / "backend" / "migrations"
    d.mkdir(parents=True)
    for n in names:
        (d / n).write_text(f"-- {n}")
    return d


def test_resolves_by_suffix_from_dir_backend_and_root(tmp_path):
    d = _mk(tmp_path, "001_a.sql", "217_cs_thing.sql")
    for root in (d, d.parent, tmp_path):
        assert migration_path(root, "cs_thing").name == "217_cs_thing.sql"
    assert migration_path(d, "cs_thing.sql").name == "217_cs_thing.sql"
    assert migration_sql(d, "cs_thing") == "-- 217_cs_thing.sql"


def test_survives_renumbering(tmp_path):
    d = _mk(tmp_path, "230_cs_thing.sql")
    assert migration_path(d, "cs_thing").name == "230_cs_thing.sql"


def test_zero_matches_raises(tmp_path):
    d = _mk(tmp_path, "001_a.sql")
    with pytest.raises(MigrationLookupError, match="none"):
        migration_path(d, "missing")


def test_ambiguous_raises_naming_candidates(tmp_path):
    d = _mk(tmp_path, "010_x.sql", "011_x.sql")
    with pytest.raises(MigrationLookupError, match="010_x.sql.*011_x.sql"):
        migration_path(d, "x")


def test_suffix_is_not_a_substring_match(tmp_path):
    d = _mk(tmp_path, "010_big_x.sql")
    with pytest.raises(MigrationLookupError):
        migration_path(d, "x")


def test_no_migrations_dir(tmp_path):
    with pytest.raises(MigrationLookupError):
        migration_path(tmp_path, "x")
