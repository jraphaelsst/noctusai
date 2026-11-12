"""The generated DDL: shape, access tier, the guard-probe completeness, the registry entry; and (PGlite) a REAL Postgres replay."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.assignment import (
    ASSIGNMENT_MIGRATION_HEADER,
    ASSIGNMENT_TABLES,
    AssignmentConfig,
    assignment_guard_probes,
    assignment_migration,
)
from noctusai_lib.domain.assignment.store import table_specs

SCHEMA = "asgx"
ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"


def sql(**kw) -> str:
    return assignment_migration(AssignmentConfig(schema=SCHEMA, **kw))


def test_header_and_schema_binding():
    out = sql()
    assert out.startswith(ASSIGNMENT_MIGRATION_HEADER)
    with pytest.raises(ValueError, match="cfg.schema"):
        assignment_migration(AssignmentConfig(schema=SCHEMA), "other")


def test_every_table_declares_its_access_tier_and_is_service_only():
    out = sql()
    for t in ASSIGNMENT_TABLES:
        name = f"{SCHEMA}.asg_{t}"
        assert f"COMMENT ON TABLE {name} IS 'tier:org';" in out
        assert f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY;" in out
        assert f"REVOKE ALL ON {name} FROM PUBLIC, anon, authenticated;" in out
        assert f"GRANT SELECT ON {name} TO authenticated" not in out  # the browser never reads these: the API is the only door
    assert "service_role_bypass" in out


def test_the_rpcs_are_definer_pinned_and_service_role_only():
    out = sql()
    for rpc in ("asg_assign(UUID, JSONB)", "asg_release(UUID, JSONB)"):
        assert f"REVOKE EXECUTE ON FUNCTION {SCHEMA}.{rpc} FROM PUBLIC, anon, authenticated;" in out
        assert f"GRANT EXECUTE ON FUNCTION {SCHEMA}.{rpc} TO service_role;" in out
    assert out.count("SET search_path = pg_catalog, asgx, pg_temp") >= 3  # assign, release, the events guard
    assert "pg_advisory_xact_lock" in out  # capacity is checked under a per-member lock, never in Python


def test_the_card_projection_exists_only_when_the_host_names_its_card_table():
    plain = sql()
    assert "responsavel" not in plain
    bound = sql(card_table="cards", responsavel_field="owner_id")
    assert f"UPDATE {SCHEMA}.cards SET owner_id = v_user WHERE id = v_subject AND org_id = p_org" in bound
    assert f"UPDATE {SCHEMA}.cards SET owner_id = NULL WHERE id = v_subject AND org_id = p_org" in bound
    platform = sql(card_table="leads_noc", card_has_org_id=False)
    assert "WHERE id = v_subject;" in platform and "AND org_id = p_org;" not in platform.split("asg_release")[-1]


def test_closing_leaves_the_funnel_owner_alone_only_unassigning_clears_it():
    release = sql(card_table="cards").split("FUNCTION asgx.asg_release")[1]
    assert "v_event = 'unassigned'" in release


def test_for_funnel_binds_the_card_table_and_the_owner_column():
    from types import SimpleNamespace

    funnel = SimpleNamespace(pipeline=SimpleNamespace(card_table="negociacoes"), responsavel_field="corretor_id", tenancy="org")
    cfg = AssignmentConfig.for_funnel(SCHEMA, funnel)
    assert (cfg.card_table, cfg.responsavel_field, cfg.card_has_org_id) == ("negociacoes", "corretor_id", True)
    platform = SimpleNamespace(pipeline=SimpleNamespace(card_table="website_leads"), responsavel_field="responsavel_id", tenancy="platform")
    assert AssignmentConfig.for_funnel(SCHEMA, platform).card_has_org_id is False


def test_config_rejects_unsafe_identifiers():
    for bad in ({"table_prefix": "A-"}, {"card_table": "x; drop table y"}, {"responsavel_field": "a b"}, {"subject_kind": "Bad"}):
        with pytest.raises(ValueError):
            AssignmentConfig(schema=SCHEMA, **bad)


def test_every_guard_the_generator_emits_has_a_probe_and_nothing_is_probed_twice():
    out = sql()
    declared = {p.guard_name for p in assignment_guard_probes(SCHEMA)}
    emitted = set(re.findall(r"CREATE UNIQUE INDEX IF NOT EXISTS (\w+)", out))
    emitted |= set(re.findall(r"CONSTRAINT (\w+) CHECK", out))
    emitted |= set(re.findall(r"CREATE TRIGGER (\w+)", out))
    assert emitted == declared
    keys = [p.probe_key for p in assignment_guard_probes(SCHEMA)]
    assert len(keys) == len(set(keys))


def test_the_fake_store_mirrors_every_unique_index_of_the_ddl():
    out = sql()
    specs = table_specs(AssignmentConfig(schema=SCHEMA))
    mirrored = {uk.name for spec in specs.values() for uk in spec.unique}
    ddl_unique = set(re.findall(r"CREATE UNIQUE INDEX IF NOT EXISTS (\w+)", out))
    assert mirrored == ddl_unique


def test_the_organ_is_registered_and_its_registry_output_matches_the_generator():
    from noctusai_seed.organs import ORGAN_REGISTRY, organ_guard_probes, organ_migration_sql

    spec = ORGAN_REGISTRY["assignment"]
    assert organ_migration_sql("assignment", SCHEMA).startswith(spec.migration_header)
    assert organ_migration_sql("assignment", SCHEMA) == assignment_migration(AssignmentConfig(schema=SCHEMA))
    assert {p.probe_key for p in organ_guard_probes("assignment", SCHEMA)} == {p.probe_key for p in assignment_guard_probes(SCHEMA)}


_REAL = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
CREATE TABLE IF NOT EXISTS {SCHEMA}.cards (id uuid PRIMARY KEY, org_id uuid NOT NULL, responsavel_id uuid);
"""


def _need(cond: str, msg: str) -> str:
    return f"IF NOT ({cond}) THEN RAISE EXCEPTION '{msg}: %', r; END IF;"


def _assign(card: str, user: str, extra: str = "") -> str:
    return (
        f"jsonb_build_object('subject_kind','card','subject_id',{card},'user_id',{user},'team_id',t,"
        f"'strategy','round_robin','criterion','round_robin','advance_cursor',true,'enforce_capacity',true{extra})"
    )


def _case(body: str) -> str:
    return f"""DO $$ DECLARE o uuid := gen_random_uuid(); o2 uuid := gen_random_uuid(); t uuid := gen_random_uuid();
  u1 uuid := gen_random_uuid(); u2 uuid := gen_random_uuid(); c1 uuid := gen_random_uuid(); c2 uuid := gen_random_uuid(); c3 uuid := gen_random_uuid();
  r jsonb; n int; s text;
BEGIN
  INSERT INTO {SCHEMA}.asg_teams(id, org_id, name) VALUES (t, o, 'Vendas');
  INSERT INTO {SCHEMA}.asg_members(org_id, team_id, user_id, capacity) VALUES (o, t, u1, 1), (o, t, u2, NULL);
  INSERT INTO {SCHEMA}.cards(id, org_id) VALUES (c1, o), (c2, o), (c3, o);
  {body}
END $$;"""


SCENARIOS = {
    "assign writes the assignment, the cursor, the event AND the card owner in one call": f"""
  r := {SCHEMA}.asg_assign(o, {_assign('c1', 'u1')});
  {_need("r->>'changed' = 'true' AND r->>'event' = 'assigned'", 'first assign')}
  {_need(f"(SELECT responsavel_id FROM {SCHEMA}.cards WHERE id = c1) = u1", 'card owner projected')}
  {_need(f"(SELECT last_user_id FROM {SCHEMA}.asg_cursors WHERE team_id = t) = u1", 'cursor moved')}
  {_need(f"(SELECT count(*) FROM {SCHEMA}.asg_events WHERE org_id = o AND event = 'assigned' AND to_user_id = u1) = 1", 'event written')}""",
    "assigning the same owner again is a no-op with no second event": f"""
  r := {SCHEMA}.asg_assign(o, {_assign('c1', 'u1')});
  r := {SCHEMA}.asg_assign(o, {_assign('c1', 'u1')});
  {_need("r->>'changed' = 'false'", 'noop')}
  {_need(f"(SELECT count(*) FROM {SCHEMA}.asg_events WHERE org_id = o) = 1", 'one event only')}""",
    "a different owner is a reassignment carrying from and to": f"""
  r := {SCHEMA}.asg_assign(o, {_assign('c1', 'u1')});
  r := {SCHEMA}.asg_assign(o, {_assign('c1', 'u2', ",'actor_id',u2::text,'note','troca'")});
  {_need("r->>'event' = 'reassigned'", 'reassigned')}
  {_need(f"EXISTS (SELECT 1 FROM {SCHEMA}.asg_events WHERE event = 'reassigned' AND from_user_id = u1 AND to_user_id = u2 AND actor_id = u2 AND note = 'troca')", 'event from/to/actor')}
  {_need(f"(SELECT responsavel_id FROM {SCHEMA}.cards WHERE id = c1) = u2", 'card follows')}""",
    "capacity is enforced inside the transaction and a refusal leaves NOTHING behind": f"""
  r := {SCHEMA}.asg_assign(o, {_assign('c1', 'u1')});
  BEGIN
    r := {SCHEMA}.asg_assign(o, {_assign('c2', 'u1')});
    RAISE EXCEPTION 'capacity not enforced';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> 'asg_capacity_full' THEN RAISE; END IF;
  END;
  {_need(f"(SELECT count(*) FROM {SCHEMA}.asg_assignments WHERE org_id = o) = 1", 'no partial assignment')}
  {_need(f"(SELECT count(*) FROM {SCHEMA}.asg_events WHERE org_id = o) = 1", 'no partial event')}
  {_need(f"(SELECT responsavel_id FROM {SCHEMA}.cards WHERE id = c2) IS NULL", 'no partial card write')}
  r := {SCHEMA}.asg_assign(o, {_assign('c2', 'u2')});
  {_need("r->>'changed' = 'true'", 'unlimited member still takes work')}""",
    "a manual assign may exceed capacity (enforce_capacity off)": f"""
  r := {SCHEMA}.asg_assign(o, {_assign('c1', 'u1')});
  r := {SCHEMA}.asg_assign(o, jsonb_build_object('subject_kind','card','subject_id',c2,'user_id',u1,'team_id',t,'strategy','manual','criterion','manual'));
  {_need("r->>'changed' = 'true'", 'human override')}""",
    "close frees the seat, keeps the owner and the card, and writes `closed`": f"""
  r := {SCHEMA}.asg_assign(o, {_assign('c1', 'u1')});
  r := {SCHEMA}.asg_release(o, jsonb_build_object('subject_kind','card','subject_id',c1,'event','closed'));
  {_need("r->>'changed' = 'true' AND r->>'event' = 'closed'", 'closed')}
  {_need(f"(SELECT responsavel_id FROM {SCHEMA}.cards WHERE id = c1) = u1", 'card owner stays')}
  r := {SCHEMA}.asg_assign(o, {_assign('c2', 'u1')});
  {_need("r->>'changed' = 'true'", 'seat freed')}
  r := {SCHEMA}.asg_release(o, jsonb_build_object('subject_kind','card','subject_id',c1,'event','closed'));
  {_need("r->>'changed' = 'false'", 'closing twice is a no-op')}""",
    "unassign deletes the current owner, clears the card and keeps the event history": f"""
  r := {SCHEMA}.asg_assign(o, {_assign('c1', 'u1')});
  r := {SCHEMA}.asg_release(o, jsonb_build_object('subject_kind','card','subject_id',c1,'event','unassigned'));
  {_need(f"NOT EXISTS (SELECT 1 FROM {SCHEMA}.asg_assignments WHERE subject_id = c1)", 'owner gone')}
  {_need(f"(SELECT responsavel_id FROM {SCHEMA}.cards WHERE id = c1) IS NULL", 'card cleared')}
  {_need(f"(SELECT count(*) FROM {SCHEMA}.asg_events WHERE subject_id = c1) = 2", 'history kept')}""",
    "an assign for a card that does not exist is refused and records nothing": f"""
  BEGIN
    r := {SCHEMA}.asg_assign(o, {_assign('gen_random_uuid()', 'u1')});
    RAISE EXCEPTION 'ghost card accepted';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> 'asg_subject_not_found' THEN RAISE; END IF;
  END;
  {_need(f"(SELECT count(*) FROM {SCHEMA}.asg_events WHERE org_id = o) = 0", 'nothing recorded')}""",
    "another org's card is invisible to the projection": f"""
  BEGIN
    r := {SCHEMA}.asg_assign(o2, {_assign('c1', 'u1')});
    RAISE EXCEPTION 'cross-org projection';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> 'asg_subject_not_found' THEN RAISE; END IF;
  END;
  {_need(f"(SELECT responsavel_id FROM {SCHEMA}.cards WHERE id = c1) IS NULL", 'untouched')}""",
    "events are append-only for the service role too": f"""
  r := {SCHEMA}.asg_assign(o, {_assign('c1', 'u1')});
  BEGIN
    UPDATE {SCHEMA}.asg_events SET note = 'x' WHERE org_id = o;
    RAISE EXCEPTION 'UPDATE allowed';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
  BEGIN
    DELETE FROM {SCHEMA}.asg_events WHERE org_id = o;
    RAISE EXCEPTION 'DELETE allowed';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;""",
    "a unique team name ignores case and padding, per org": f"""
  BEGIN
    INSERT INTO {SCHEMA}.asg_teams(org_id, name) VALUES (o, '  vENDAS ');
    RAISE EXCEPTION 'duplicate team';
  EXCEPTION WHEN unique_violation THEN NULL;
  END;
  INSERT INTO {SCHEMA}.asg_teams(org_id, name) VALUES (o2, 'vendas');""",
    "an event of an unknown kind and an inverted absence window are refused": f"""
  BEGIN
    INSERT INTO {SCHEMA}.asg_events(org_id, subject_kind, subject_id, event) VALUES (o, 'card', c1, 'bogus');
    RAISE EXCEPTION 'bogus event';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  BEGIN
    UPDATE {SCHEMA}.asg_members SET ooo_from = now(), ooo_until = now() - interval '1 day' WHERE org_id = o AND user_id = u1;
    RAISE EXCEPTION 'inverted window';
  EXCEPTION WHEN check_violation THEN NULL;
  END;""",
}


def _replay(steps: list[dict]) -> dict:
    proc = subprocess.run(
        ["node", str(HARNESS)], input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=300,
    )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")


@_REAL
def test_the_ddl_applies_twice_and_every_rpc_and_guard_behaves_on_a_real_postgres():
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "assignment_migration", "sql": sql(card_table="cards"), "mode": "file", "twice": True},
        *({"product": SCHEMA, "file": f"scenario: {n}", "sql": _case(b), "mode": "file", "twice": False} for n, b in SCENARIOS.items()),
    ]
    out = _replay(steps)
    assert out.get("ok"), out
    failed = {s["file"]: s["failures"] for s in out["steps"] if s["failures"]}
    assert not failed, failed


@_REAL
def test_the_generic_migration_without_a_card_table_also_applies_twice():
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "assignment_migration", "sql": sql(), "mode": "file", "twice": True},
    ]
    out = _replay(steps)
    assert out.get("ok"), out
