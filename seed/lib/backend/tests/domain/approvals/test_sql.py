"""The generated DDL: shape, access tier, guard-probe completeness, the registry entry; and (PGlite) a REAL Postgres replay."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.approvals import (
    APPROVALS_MIGRATION_HEADER,
    ApprovalsConfig,
    approvals_guard_probes,
    approvals_migration,
    table_specs,
)

SCHEMA = "aprx"
ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"


def sql() -> str:
    return approvals_migration(ApprovalsConfig(schema=SCHEMA))


def test_header_and_schema_binding():
    assert sql().startswith(APPROVALS_MIGRATION_HEADER)
    with pytest.raises(ValueError, match="cfg.schema"):
        approvals_migration(ApprovalsConfig(schema=SCHEMA), "other")


def test_the_table_declares_its_tier_and_is_service_only():
    out = sql()
    name = f"{SCHEMA}.apr_events"
    assert f"COMMENT ON TABLE {name} IS 'tier:org';" in out
    assert f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY;" in out
    assert f"REVOKE ALL ON {name} FROM PUBLIC, anon, authenticated;" in out
    assert f"GRANT SELECT ON {name} TO authenticated" not in out


def test_the_rpc_is_definer_pinned_and_service_role_only():
    out = sql()
    rpc = "apr_record(UUID, JSONB)"
    assert f"REVOKE EXECUTE ON FUNCTION {SCHEMA}.{rpc} FROM PUBLIC, anon, authenticated;" in out
    assert f"GRANT EXECUTE ON FUNCTION {SCHEMA}.{rpc} TO service_role;" in out
    assert "pg_advisory_xact_lock" in out
    assert out.count("SET search_path = pg_catalog, aprx, pg_temp") >= 2  # the RPC and the events guard


def test_config_rejects_unsafe_identifiers():
    for bad in ({"table_prefix": "A-"}, {"schema": "x; drop"}):
        with pytest.raises(ValueError):
            ApprovalsConfig(**{"schema": SCHEMA, **bad})


def test_every_guard_the_generator_emits_has_a_probe_and_nothing_is_probed_twice():
    out = sql()
    declared = {p.guard_name for p in approvals_guard_probes(SCHEMA)}
    emitted = set(re.findall(r"CREATE UNIQUE INDEX IF NOT EXISTS (\w+)", out))
    emitted |= set(re.findall(r"CONSTRAINT (\w+) CHECK", out))
    emitted |= set(re.findall(r"CREATE TRIGGER (\w+)", out))
    assert emitted == declared
    keys = [p.probe_key for p in approvals_guard_probes(SCHEMA)]
    assert len(keys) == len(set(keys))


def test_the_fake_store_mirrors_every_unique_index_of_the_ddl():
    mirrored = {uk.name for spec in table_specs(ApprovalsConfig(schema=SCHEMA)).values() for uk in spec.unique}
    assert mirrored == set(re.findall(r"CREATE UNIQUE INDEX IF NOT EXISTS (\w+)", sql()))


def test_the_organ_is_registered_and_its_registry_output_matches_the_generator():
    from noctusai_seed.organs import ORGAN_REGISTRY, organ_guard_probes, organ_migration_sql

    spec = ORGAN_REGISTRY["approvals"]
    assert organ_migration_sql("approvals", SCHEMA).startswith(spec.migration_header)
    assert organ_migration_sql("approvals", SCHEMA) == approvals_migration(ApprovalsConfig(schema=SCHEMA))
    assert {p.probe_key for p in organ_guard_probes("approvals", SCHEMA)} == {p.probe_key for p in approvals_guard_probes(SCHEMA)}


_REAL = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
"""


def _need(cond: str, msg: str) -> str:
    return f"IF NOT ({cond}) THEN RAISE EXCEPTION '{msg}: %', r; END IF;"


def _rec(event: str, versao: int, extra: str = "") -> str:
    return (f"{SCHEMA}.apr_record(o, jsonb_build_object('subject_kind','roteiro','subject_id',s,'versao',{versao},"
            f"'event','{event}'{extra}))")


def _refused(call: str, text: str) -> str:
    return f"""BEGIN
    r := {call};
    RAISE EXCEPTION 'accepted: {text}';
  EXCEPTION WHEN OTHERS THEN
    IF SQLERRM <> '{text}' THEN RAISE; END IF;
  END;"""


def _case(body: str) -> str:
    return f"""DO $$ DECLARE o uuid := gen_random_uuid(); o2 uuid := gen_random_uuid(); s uuid := gen_random_uuid(); u uuid := gen_random_uuid(); r jsonb;
BEGIN
  {body}
END $$;"""


SCENARIOS = {
    "submit then approve writes one event each and the decision is final": f"""
  r := {_rec('submitted', 1)};
  {_need("r->>'changed' = 'true'", 'submit')}
  r := {_rec('approved', 1, ",'actor_id',u::text")};
  {_need("r->>'event' = 'approved'", 'approve')}
  {_need(f"(SELECT count(*) FROM {SCHEMA}.apr_events WHERE org_id = o AND actor_id = u) = 1", 'actor recorded')}
  {_refused(_rec('rejected', 1, ",'motivo','x'"), 'apr_already_decided')}""",
    "re-submitting the current versao is a no-op, a lower one is stale": f"""
  r := {_rec('submitted', 2)};
  r := {_rec('submitted', 2)};
  {_need("r->>'changed' = 'false'", 'noop')}
  {_need(f"(SELECT count(*) FROM {SCHEMA}.apr_events WHERE org_id = o) = 1", 'one event')}
  {_refused(_rec('submitted', 1), 'apr_stale_versao')}""",
    "a stale or future versao cannot be decided, and a refusal records nothing": f"""
  r := {_rec('submitted', 1)};
  r := {_rec('submitted', 2)};
  {_refused(_rec('approved', 1), 'apr_stale_versao')}
  {_refused(_rec('approved', 3), 'apr_stale_versao')}
  {_need(f"(SELECT count(*) FROM {SCHEMA}.apr_events WHERE org_id = o) = 2", 'nothing partial')}""",
    "deciding an unsubmitted subject is refused": f"""
  {_refused(_rec('approved', 1), 'apr_not_submitted')}""",
    "a rejection needs a motivo (CHECK) and a revised versao can be approved": f"""
  r := {_rec('submitted', 1)};
  BEGIN
    r := {_rec('rejected', 1)};
    RAISE EXCEPTION 'rejected without motivo';
  EXCEPTION WHEN check_violation THEN NULL;
  END;
  r := {_rec('rejected', 1, ",'motivo','  gancho fraco '")};
  {_need(f"(SELECT motivo FROM {SCHEMA}.apr_events WHERE event = 'rejected' AND org_id = o) = 'gancho fraco'", 'motivo trimmed')}
  r := {_rec('submitted', 2)};
  r := {_rec('approved', 2)};
  {_need("r->>'changed' = 'true'", 'v2 approved')}""",
    "orgs are isolated": f"""
  r := {_rec('submitted', 1)};
  {_refused(_rec('approved', 1).replace('apr_record(o,', 'apr_record(o2,'), 'apr_not_submitted')}""",
    "events are append-only for the service role too": f"""
  r := {_rec('submitted', 1)};
  BEGIN
    UPDATE {SCHEMA}.apr_events SET note = 'x' WHERE org_id = o;
    RAISE EXCEPTION 'UPDATE allowed';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
  END;
  BEGIN
    DELETE FROM {SCHEMA}.apr_events WHERE org_id = o;
    RAISE EXCEPTION 'DELETE allowed';
  EXCEPTION WHEN insufficient_privilege THEN NULL;
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
def test_the_ddl_applies_twice_and_the_rpc_and_guards_behave_on_a_real_postgres():
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "approvals_migration", "sql": sql(), "mode": "file", "twice": True},
        *({"product": SCHEMA, "file": f"scenario: {n}", "sql": _case(b), "mode": "file", "twice": False} for n, b in SCENARIOS.items()),
    ]
    out = _replay(steps)
    assert out.get("ok"), out
    failed = {s["file"]: s["failures"] for s in out["steps"] if s["failures"]}
    assert not failed, failed
