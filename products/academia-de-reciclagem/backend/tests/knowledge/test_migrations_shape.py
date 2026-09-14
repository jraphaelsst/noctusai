"""Static SQL-shape assertions over 006_knowledge.sql / 007_revisions.sql.

Parses the migration files as TEXT — this suite never connects to a
database and never applies a migration anywhere (the A1 dispatch brief's
hard rule: migrations are the tech-lead's to apply via
`noctus.dev.migrate_product`, never this test's). It is a regex/structural
check, not a live-DB integration test — see `test_store_conformance.py`
for the behavioural suite (run against `FakeKnowledgeStore`).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

_006 = (_MIGRATIONS_DIR / "006_knowledge.sql").read_text()
_007 = (_MIGRATIONS_DIR / "007_revisions.sql").read_text()
_BOTH = _006 + "\n" + _007

_A1_A9_TABLES = [
    "kb_entries", "decisions", "open_questions", "roadmap_phases",
    "tasks", "content_drafts", "timeline_events", "research_sources",
    "code_counters",
]


def test_migration_files_exist():
    assert (_MIGRATIONS_DIR / "006_knowledge.sql").is_file()
    assert (_MIGRATIONS_DIR / "007_revisions.sql").is_file()


@pytest.mark.parametrize("table", _A1_A9_TABLES)
def test_every_a_table_has_rls_enabled(table):
    assert re.search(
        rf"ALTER TABLE academia_de_reciclagem\.{re.escape(table)}\s+ENABLE ROW LEVEL SECURITY",
        _006,
    ), f"{table}: missing ENABLE ROW LEVEL SECURITY"


@pytest.mark.parametrize("table", _A1_A9_TABLES)
def test_every_a_table_has_service_role_bypass(table):
    pattern = (
        rf'CREATE POLICY "service_role_bypass" ON academia_de_reciclagem\.{re.escape(table)} '
        r"FOR ALL TO service_role USING \(true\) WITH CHECK \(true\);"
    )
    assert re.search(pattern, _006), f"{table}: missing the literal service_role_bypass policy"


@pytest.mark.parametrize("table", _A1_A9_TABLES)
def test_every_a_table_has_an_org_select_policy(table):
    assert re.search(
        rf'CREATE POLICY "{re.escape(table)}_select_own_org" ON academia_de_reciclagem\.{re.escape(table)}\s*'
        r"FOR SELECT TO authenticated\s*"
        r"USING \(org_id = public\.current_org_id\(\)\)",
        _006,
    ), f"{table}: missing an org-scoped SELECT policy via public.current_org_id()"


@pytest.mark.parametrize(
    "table,cols",
    [
        ("kb_entries", ("org_id", "slug")),
        ("decisions", ("org_id", "codigo")),
        ("open_questions", ("org_id", "codigo")),
        ("roadmap_phases", ("org_id", "codigo")),
        ("tasks", ("org_id", "codigo")),
        ("content_drafts", ("org_id", "codigo")),
    ],
)
def test_unique_index_on_org_and_natural_key(table, cols):
    pattern = rf"UNIQUE\s*\({cols[0]}\s*,\s*{cols[1]}\)"
    assert re.search(pattern, _006), f"{table}: missing UNIQUE ({cols[0]}, {cols[1]})"


def test_code_counters_pk_is_org_and_prefix():
    assert re.search(r"PRIMARY KEY\s*\(org_id, prefix\)", _006)


def test_decisions_append_only_trigger_exists():
    assert "academia_decisions_append_only" in _006
    assert re.search(
        r"CREATE OR REPLACE TRIGGER academia_decisions_append_only\s+"
        r"BEFORE UPDATE OR DELETE ON academia_de_reciclagem\.decisions",
        _006,
    )
    # DELETE is rejected outright, and the UPDATE branch enumerates every
    # column except estado/superseded_by (updated_at is exempt for the
    # touch trigger).
    assert "DELETE is not permitted" in _006
    assert "only estado and superseded_by may change" in _006


def test_kb_revisions_table_shape():
    assert re.search(r"CREATE TABLE IF NOT EXISTS academia_de_reciclagem\.kb_revisions", _007)
    assert "UNIQUE (entity_type, entity_id, rev_no)" in _007
    assert re.search(
        r"CREATE UNIQUE INDEX IF NOT EXISTS kb_revisions_approval_entity_unique\s+"
        r"ON academia_de_reciclagem\.kb_revisions \(approval_id, entity_type, entity_id\)\s+"
        r"WHERE approval_id IS NOT NULL",
        _007,
    )


def test_kb_revisions_has_rls_and_service_role_bypass():
    assert re.search(
        r"ALTER TABLE academia_de_reciclagem\.kb_revisions\s+ENABLE ROW LEVEL SECURITY", _007,
    )
    assert 'CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.kb_revisions' in _007


def test_kb_revisions_update_delete_revoked_and_trigger_exists():
    assert re.search(
        r"REVOKE UPDATE, DELETE ON academia_de_reciclagem\.kb_revisions "
        r"FROM anon, authenticated, service_role",
        _007,
    )
    assert re.search(
        r"CREATE OR REPLACE TRIGGER kb_revisions_immutable_trg\s+"
        r"BEFORE UPDATE OR DELETE ON academia_de_reciclagem\.kb_revisions",
        _007,
    )


def test_approval_consumptions_table_shape_and_rls():
    assert re.search(
        r"CREATE TABLE IF NOT EXISTS academia_de_reciclagem\.approval_consumptions\s*\(\s*"
        r"jti\s+UUID PRIMARY KEY,\s*"
        r"org_id\s+UUID NOT NULL,\s*"
        r"consumed_at\s+TIMESTAMPTZ NOT NULL DEFAULT now\(\)",
        _007,
    )
    assert re.search(
        r"ALTER TABLE academia_de_reciclagem\.approval_consumptions\s+ENABLE ROW LEVEL SECURITY", _007,
    )
    assert 'CREATE POLICY "service_role_bypass" ON academia_de_reciclagem.approval_consumptions' in _007


def test_kb_entries_current_revision_id_fk_attached_in_007():
    assert re.search(
        r"ADD CONSTRAINT kb_entries_current_revision_id_fkey\s+"
        r"FOREIGN KEY \(current_revision_id\) REFERENCES academia_de_reciclagem\.kb_revisions \(id\)",
        _007,
    )


def test_research_sources_fk_to_kb_entries():
    assert re.search(
        r"CONSTRAINT research_sources_kb_slug_fkey FOREIGN KEY \(org_id, kb_slug\)\s*"
        r"REFERENCES academia_de_reciclagem\.kb_entries \(org_id, slug\)",
        _006,
    )


def test_write_rpc_functions_locked_to_service_role_only():
    assert re.search(
        r"REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA academia_de_reciclagem "
        r"FROM PUBLIC, anon, authenticated",
        _007,
    )
    assert re.search(
        r"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA academia_de_reciclagem TO service_role",
        _007,
    )


@pytest.mark.parametrize("fn_name", [
    "create_kb_entry", "update_kb_entry", "archive_kb_entry",
    "create_decision", "supersede_decision",
    "create_open_question", "answer_open_question",
    "update_roadmap_phase", "create_task", "update_task",
    "create_content_draft", "create_timeline_event", "create_research_source",
    "import_entity", "import_bundle", "seed_counters",
    "_allocate_code", "_append_revision", "_consume_approval",
])
def test_write_rpc_function_declared(fn_name):
    assert re.search(
        rf"CREATE OR REPLACE FUNCTION academia_de_reciclagem\.{re.escape(fn_name)}\s*\(",
        _007,
    ), f"missing function {fn_name}"


def test_check_constraints_cover_every_enum_from_contract():
    assert "'contexto', 'dominio', 'instrucoes', 'skills'" in _006  # kb_entries.categoria
    assert "'vigente', 'superseded'" in _006  # decisions.estado
    assert "'aberta', 'respondida'" in _006  # open_questions.estado
    assert "'pendente', 'em-andamento', 'concluida', 'cancelada'" in _006  # phases/tasks estado
    assert "'roteiro', 'trilha', 'quiz', 'copy', 'proposta', 'outro'" in _006  # content_drafts.tipo
    assert "'kb_entry', 'decision', 'open_question', 'roadmap_phase'" in _007  # kb_revisions.entity_type
    assert "'create', 'update', 'archive', 'supersede', 'import'" in _007  # kb_revisions.op
    assert "'human', 'agent', 'import'" in _007  # kb_revisions.author_kind
