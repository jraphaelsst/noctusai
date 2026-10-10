"""Structural tests for ``*_instagram_insights.sql`` (parse-based — the
migration is a FILE, not an applied change)."""
from __future__ import annotations

import re
from pathlib import Path
from noctusai_lib.testing.migrations import migration_path

import pytest

MIGRATION = migration_path(Path(__file__).resolve().parents[1], "instagram_insights")
TABLES = ("ig_media", "ig_media_snapshots", "ig_profile_snapshots")


@pytest.fixture(scope="module")
def sql():
    raw = MIGRATION.read_text(encoding="utf-8")
    code = "\n".join(l for l in raw.splitlines() if not l.strip().startswith("--"))
    code = re.sub(r"--[^\n]*", "", code)
    return " ".join(code.split())


def test_parses():
    pglast = pytest.importorskip("pglast", reason="pglast not installed in this env")
    assert len(pglast.parse_sql(MIGRATION.read_text(encoding="utf-8"))) > 0


def test_forward_only(sql):
    upper = sql.upper()
    for forbidden in ("DROP TABLE", "DROP COLUMN", "TRUNCATE", "DELETE FROM", "ALTER COLUMN"):
        assert forbidden not in upper


def test_idempotent(sql):
    assert "SET search_path = social_wiring, public;" in sql
    for t in TABLES:
        assert f"CREATE TABLE IF NOT EXISTS social_wiring.{t} (" in sql
    assert sql.count("CREATE INDEX") == sql.count("CREATE INDEX IF NOT EXISTS")
    assert sql.count("CREATE POLICY") == sql.count("DROP POLICY IF EXISTS")


@pytest.mark.parametrize("table", TABLES)
def test_rls_org_scoped_like_siblings(sql, table):
    assert f"ALTER TABLE social_wiring.{table} ENABLE ROW LEVEL SECURITY" in sql
    assert (
        f'CREATE POLICY "{table}_select_own_org" ON social_wiring.{table} '
        "FOR SELECT TO authenticated USING (org_id = public.current_org_id());"
    ) in sql
    assert (
        f'CREATE POLICY "{table}_service_role" ON social_wiring.{table} '
        "FOR ALL TO service_role USING (true) WITH CHECK (true);"
    ) in sql


def test_natural_keys_make_daily_writes_idempotent(sql):
    assert "UNIQUE (account_id, ig_media_id)" in sql
    assert "UNIQUE (account_id, ig_media_id, snapshot_date)" in sql
    assert "UNIQUE (account_id, snapshot_date)" in sql
    assert sql.count("REFERENCES social_wiring.integration_accounts(id) ON DELETE CASCADE") == 3


def test_metric_columns_are_nullable_never_defaulted(sql):
    for col in ("views", "reach", "likes", "saved", "total_interactions",
                "ig_reels_avg_watch_time", "accounts_engaged", "followers_count"):
        for m in re.finditer(rf"\b{col}\s+BIGINT([^,]*),", sql):
            assert "NOT NULL" not in m.group(1) and "DEFAULT" not in m.group(1), col


def test_grid_keyset_index(sql):
    assert "published_at TIMESTAMPTZ NOT NULL" in sql
    assert "ON social_wiring.ig_media (account_id, published_at DESC, ig_media_id DESC)" in sql


def test_columns_match_repository_writes(sql):
    """Every column the repository/service writes exists in the DDL."""
    from app.modules.instagram.repository import (
        MEDIA_TYPED_METRICS,
        PROFILE_FIELD_COLUMNS,
        PROFILE_TYPED_METRICS,
    )

    snaps = sql.split("CREATE TABLE IF NOT EXISTS social_wiring.ig_media_snapshots")[1].split(");")[0]
    prof = sql.split("CREATE TABLE IF NOT EXISTS social_wiring.ig_profile_snapshots")[1].split(");")[0]
    for c in MEDIA_TYPED_METRICS + ("extra_metrics", "unsupported_metrics", "media_product_type"):
        assert re.search(rf"\b{c}\b", snaps), c
    for c in PROFILE_TYPED_METRICS + PROFILE_FIELD_COLUMNS + ("window_since", "window_until", "ig_user_id"):
        assert re.search(rf"\b{c}\b", prof), c
