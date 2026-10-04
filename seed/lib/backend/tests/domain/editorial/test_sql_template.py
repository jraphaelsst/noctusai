"""Shape tests for ``sql_templates.editorial_tables`` (no database: applying the
template is a migration decision, and the behaviour probes live in
``noctus.dev.verify_db_guards``)."""
from __future__ import annotations

import re

import pytest

from noctusai_lib.domain.editorial.workflow import ACTIONS, DEFAULT_TRANSITIONS, STATES, EditorialWorkflow
from noctusai_lib.domain.sql_templates import EDITORIAL_IN_TRANSITION_GUC, editorial_tables
from noctusai_lib.testing.migration_parser import _walk_statements

SQL = editorial_tables("demo")


def test_emits_the_three_tables_with_rls_deny_by_default():
    for t in ("editorial_items", "editorial_versions", "editorial_events"):
        assert f"CREATE TABLE IF NOT EXISTS demo.{t}" in SQL
        assert f"ALTER TABLE demo.{t} ENABLE ROW LEVEL SECURITY" in SQL
        assert f'CREATE POLICY "service_role_bypass" ON demo.{t} FOR ALL TO service_role' in SQL
    assert "REVOKE ALL ON demo.editorial_items, demo.editorial_versions, demo.editorial_events FROM anon, authenticated" in SQL
    policies = re.findall(r"CREATE POLICY \"([a-z_]+)\"", SQL)
    assert policies == ["service_role_bypass"] * 3  # no policy opens a client read/write


def test_states_and_actions_come_from_the_workflow():
    for s in STATES:
        assert f"'{s}'" in SQL.split("editorial_items_state_check")[1].split(")")[0]
    for a in ACTIONS:
        assert f"'{a}'" in SQL
    assert "CHECK (state IN ('rascunho', 'revisao_editorial', 'revisao_seguranca', 'publicado', 'arquivado'))" in SQL


def test_rule_table_has_one_row_per_transition_and_matches_the_flags():
    body = SQL.split("SELECT * FROM (VALUES")[1].split(") AS r(")[0]
    rows = re.findall(r"^\s*\((.*)\)[,]?$", body, flags=re.M)
    assert len(rows) == len(DEFAULT_TRANSITIONS)
    for row, t in zip(rows, DEFAULT_TRANSITIONS):
        frm = f"'{t.from_state.value}'" if t.from_state else "NULL::text"
        flags = ", ".join("true" if f else "false" for f in (
            t.needs_motivo, t.not_author, t.not_editorial_approver, t.needs_security_signoff, t.creates_version))
        assert row == f"'{t.action.value}', {frm}, '{t.to_state.value}', '{t.grant.value}', {flags}"


def test_custom_workflow_changes_the_generated_rules_and_motivo_check():
    wf = EditorialWorkflow(tuple(t for t in DEFAULT_TRANSITIONS if t.action.value != "archive"))
    sql = editorial_tables("demo", wf)
    assert "'archive', 'publicado'" not in sql and "'archive'" in sql.split("action IN (")[1].split(")")[0]
    assert "action NOT IN ('send_back')" in sql
    assert "action NOT IN ('archive', 'send_back')" in SQL


def test_security_definer_functions_are_schema_locked_and_execute_locked_down():
    for fn in ("editorial_guard_immutable", "editorial_guard_via_transition", "editorial_create_item", "editorial_transition"):
        block = SQL.split(f"CREATE OR REPLACE FUNCTION demo.{fn}(")[1].split("$fn$;")[0]
        assert "SECURITY DEFINER SET search_path = demo, public" in block, fn
        assert re.search(rf"REVOKE ALL ON FUNCTION demo\.{fn}\([^)]*\)\s+FROM PUBLIC, anon, authenticated", SQL), fn
    for fn in ("editorial_create_item", "editorial_transition"):
        assert re.search(rf"GRANT EXECUTE ON FUNCTION demo\.{fn}\([^)]*\)\s+TO service_role", SQL), fn


def test_db_refuses_every_python_denial_code():
    from noctusai_lib.domain.editorial.workflow import Code

    emitted = set(re.findall(r"RAISE EXCEPTION 'editorial_([a-z_]+)'", SQL))
    assert {c.value for c in Code} - {"ok"} <= emitted
    assert {"item_not_found", "version_immutable", "event_append_only", "write_via_transition_only"} <= emitted


def test_check_order_in_the_function_matches_decide_transition():
    body = SQL.split("CREATE OR REPLACE FUNCTION demo.editorial_transition(")[1]
    order = [
        "editorial_item_not_found", "editorial_unknown_action", "editorial_illegal_transition",
        "editorial_actor_required", "editorial_missing_grant", "editorial_motivo_required",
        "editorial_content_required", "editorial_self_approval", "editorial_same_approver",
        "editorial_security_signoff_missing",
    ]
    idx = [body.index(f"'{c}'") for c in order]
    assert idx == sorted(idx)


def test_write_once_and_append_only_triggers_exist():
    assert "BEFORE UPDATE OR DELETE ON demo.editorial_versions" in SQL
    assert "BEFORE UPDATE OR DELETE ON demo.editorial_events" in SQL
    assert "BEFORE INSERT OR UPDATE OR DELETE ON demo.editorial_items" in SQL
    assert "BEFORE INSERT ON demo.editorial_versions" in SQL and "BEFORE INSERT ON demo.editorial_events" in SQL
    assert SQL.count(f"set_config('{EDITORIAL_IN_TRANSITION_GUC}', 'on', true)") == 2
    assert SQL.count(f"set_config('{EDITORIAL_IN_TRANSITION_GUC}', 'off', true)") == 2


def test_schema_is_validated_and_output_is_deterministic():
    for bad in ("", "Demo", "a-b", "a; DROP SCHEMA x", "1abc"):
        with pytest.raises(ValueError):
            editorial_tables(bad)
    assert editorial_tables("demo") == SQL
    assert not re.search(r"__[A-Z]+__", SQL)  # every placeholder substituted


def test_template_is_embeddable_in_a_probe_and_splits_into_statements():
    assert "$noc_probe$" not in SQL and "$tpl$" not in SQL
    stmts = [s for s in _walk_statements(SQL) if s.strip()]
    assert len(stmts) > 20
    assert all(s.count("$fn$") % 2 == 0 for s in stmts)


def test_plpgsql_bodies_parse():
    parser = pytest.importorskip("pglast.parser")
    parser.parse_sql(SQL)
    for body in re.findall(r"LANGUAGE plpgsql[^\n]*\nAS \$fn\$(.*?)\$fn\$", SQL, flags=re.S):
        parser.parse_plpgsql_json(f"CREATE FUNCTION f() RETURNS trigger LANGUAGE plpgsql AS $x${body}$x$")
