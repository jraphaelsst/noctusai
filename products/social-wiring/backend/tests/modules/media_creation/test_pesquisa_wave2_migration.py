"""Pesquisa wave 2 migration (cs_research_extraction) - static contract test.

CHECK enums are asserted against the Python constants in
``pesquisa_wave2_constants`` so SQL and code cannot drift. The migration is
located by name (not number): the number is assigned by
``noctus.dev.scaffold_migration`` and can shift on rebase.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.modules.media_creation import pesquisa_wave2_constants as C

_MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"
_FILES = sorted(_MIGRATIONS.glob("*_cs_research_extraction.sql"))
_TABLES = (
    "cs_viral_topics",
    "cs_viral_topic_sources",
    "cs_extraction_jobs",
    "cs_extraction_post_runs",
)


@pytest.fixture(scope="module")
def sql() -> str:
    assert len(_FILES) == 1, f"expected exactly one cs_research_extraction migration, got {_FILES}"
    return _FILES[0].read_text()


def _table_body(sql: str, table: str) -> str:
    m = re.search(
        rf"CREATE TABLE IF NOT EXISTS social_wiring\.{table} \((.*?)\n\);", sql, re.DOTALL
    )
    assert m, f"{table} not created"
    return m.group(1)


def _in_list(text: str) -> tuple[str, ...]:
    return tuple(re.findall(r"'([^']+)'", text))


def _column_check_values(body: str, column: str) -> tuple[str, ...]:
    m = re.search(rf"\b{column}\s+TEXT[^,]*?IN \(([^)]*)\)", body, re.DOTALL)
    assert m, f"no IN-list CHECK on {column}"
    return _in_list(m.group(1))


class TestTables:
    @pytest.mark.parametrize("table", _TABLES)
    def test_table_created_with_rls_and_policies(self, sql, table):
        _table_body(sql, table)
        assert f"ALTER TABLE social_wiring.{table} ENABLE ROW LEVEL SECURITY" in sql
        for suffix in ("select_own_org", "write_own_org", "service_role"):
            assert f'CREATE POLICY "{table}_{suffix}"' in sql
        assert sql.count("current_org_id_for('social_wiring')") >= 3 * 3

    def test_guard_requires_217_and_org_helper(self, sql):
        assert "public.current_org_id_for(text)" in sql
        assert "social_wiring.cs_research_items" in sql

    def test_updated_at_triggers(self, sql):
        for table in ("cs_viral_topics", "cs_extraction_jobs"):
            assert f"CREATE TRIGGER set_updated_at_{table}" in sql
        assert "set_updated_at_media_creation" in sql

    def test_extraction_jobs_created_before_its_fk_referrers(self, sql):
        assert sql.index("TABLE IF NOT EXISTS social_wiring.cs_extraction_jobs") < sql.index(
            "TABLE IF NOT EXISTS social_wiring.cs_viral_topic_sources"
        )


class TestIndexes:
    def test_one_active_job_per_user_partial_unique(self, sql):
        m = re.search(
            r"CREATE UNIQUE INDEX IF NOT EXISTS cs_extraction_jobs_one_active_per_user_uq\s+"
            r"ON social_wiring\.cs_extraction_jobs \(created_by\)\s+WHERE status IN \(([^)]*)\);",
            sql,
        )
        assert m
        assert set(_in_list(m.group(1))) == set(C.EXTRACAO_ACTIVE_STATUSES)

    @pytest.mark.parametrize(
        "name",
        (
            "cs_viral_topics_marca_topic_uq",
            "cs_viral_topic_sources_post_uq",
            "cs_extraction_post_runs_post_uq",
        ),
    )
    def test_unique_indexes_present(self, sql, name):
        assert f"CREATE UNIQUE INDEX IF NOT EXISTS {name}" in sql

    def test_post_runs_done_partial_index(self, sql):
        assert re.search(
            r"cs_extraction_post_runs_done_idx\s+ON social_wiring\.cs_extraction_post_runs "
            r"\(marca_id, tipo, source_kind, source_id\)\s+WHERE status = 'done'",
            sql,
        )


class TestCheckEnumsMatchConstants:
    def test_viral_topic_status_and_origin(self, sql):
        body = _table_body(sql, "cs_viral_topics")
        assert _column_check_values(body, "status") == C.VIRAL_TOPIC_STATUSES
        assert _column_check_values(body, "origin") == C.VIRAL_TOPIC_ORIGINS
        assert f"BETWEEN 1 AND {C.VIRAL_TOPIC_MAX_CHARS}" in body
        assert "topic = btrim(topic)" in body

    def test_job_status(self, sql):
        body = _table_body(sql, "cs_extraction_jobs")
        assert _column_check_values(body, "status") == C.EXTRACAO_STATUSES

    def test_job_tipos(self, sql):
        body = _table_body(sql, "cs_extraction_jobs")
        m = re.search(r"tipos\s+TEXT\[\] NOT NULL\s+CHECK \((.*?)\),\n", body, re.DOTALL)
        assert m
        check = m.group(1)
        assert f"BETWEEN 1 AND {C.EXTRACAO_TIPOS_MAX}" in check
        assert _in_list(re.search(r"ARRAY\[(.*?)\]", check).group(1)) == C.EXTRACAO_TIPOS

    @pytest.mark.parametrize("table", ("cs_viral_topic_sources", "cs_extraction_post_runs"))
    def test_source_kind(self, sql, table):
        assert _column_check_values(_table_body(sql, table), "source_kind") == C.FONTE_KINDS

    def test_post_run_enums(self, sql):
        body = _table_body(sql, "cs_extraction_post_runs")
        assert _column_check_values(body, "tipo") == C.EXTRACAO_TIPOS
        assert _column_check_values(body, "status") == C.POST_RUN_STATUSES
        m = re.search(r"motivo\s+TEXT CHECK \(motivo IS NULL OR motivo IN \(([^)]*)\)\)", body)
        assert m and _in_list(m.group(1)) == C.POST_RUN_MOTIVOS


class TestConstantsSane:
    def test_no_duplicates_and_active_subset(self):
        for vals in (
            C.FONTE_KINDS, C.EXTRACAO_TIPOS, C.EXTRACAO_STATUSES,
            C.POST_RUN_STATUSES, C.POST_RUN_MOTIVOS,
        ):
            assert len(vals) == len(set(vals))
        assert set(C.EXTRACAO_ACTIVE_STATUSES) <= set(C.EXTRACAO_STATUSES)
        assert len(C.EXTRACAO_TIPOS) == C.EXTRACAO_TIPOS_MAX
