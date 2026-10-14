"""The generated DDL on a REAL Postgres (PGlite, PG16/WASM) -- applied twice, then every DB-side rule exercised.

The mock PostgREST client cannot enforce unique indexes, CHECKs or FKs, and a parser cannot prove DDL
RUNS. This drives the toolkit's own migration-replay node harness (`mcp/noctusai/node`) with the
generator's output: the chain-replay contract is "a new migration applies whole, then again".
Skips (visibly, with the reason) when `node` or the harness install is unavailable -- a skip is not a pass.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.parties import PartiesConfig, parties_migration

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
SCHEMA = "ptyx"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
"""

_BASE = f"""
DO $$
DECLARE o uuid := gen_random_uuid(); o2 uuid := gen_random_uuid(); p uuid := gen_random_uuid();
BEGIN
  INSERT INTO {SCHEMA}.pty_parties(id,org_id,kind,doc,legal_name) VALUES (p,o,'PF','52998224725','Ana');
  INSERT INTO {SCHEMA}.pty_party_roles(org_id,party_id,role) VALUES (o,p,'customer');
  {{body}}
END $$;
"""

#: name -> (SQLSTATE exception clause, statement that MUST be refused). A rule that is not enforced
#: reaches `RAISE EXCEPTION 'NOT ENFORCED'`, which no handler catches, so the step fails by name.
RULES: dict[str, tuple[str, str]] = {
    "doc unique per org": ("unique_violation",
        f"INSERT INTO {SCHEMA}.pty_parties(org_id,kind,doc,legal_name) VALUES (o,'PF','52998224725','Dup')"),
    "the same doc may exist in ANOTHER org": ("unique_violation",
        f"INSERT INTO {SCHEMA}.pty_parties(org_id,kind,doc,legal_name) VALUES (o2,'PF','52998224725','Other org'); "
        f"INSERT INTO {SCHEMA}.pty_parties(org_id,kind,doc,legal_name) VALUES (o2,'PF','52998224725','Other org dup')"),
    "kind is PF or PJ": ("check_violation",
        f"INSERT INTO {SCHEMA}.pty_parties(org_id,kind,legal_name) VALUES (o,'XX','x')"),
    "PF doc must have 11 chars": ("check_violation",
        f"INSERT INTO {SCHEMA}.pty_parties(org_id,kind,doc,legal_name) VALUES (o,'PF','1122233300018','x')"),
    "PJ doc must have 14 chars": ("check_violation",
        f"INSERT INTO {SCHEMA}.pty_parties(org_id,kind,doc,legal_name) VALUES (o,'PJ','52998224725','x')"),
    "legal_name not blank": ("check_violation",
        f"INSERT INTO {SCHEMA}.pty_parties(org_id,kind,legal_name) VALUES (o,'PF','   ')"),
    "phones must be an array": ("check_violation",
        f"INSERT INTO {SCHEMA}.pty_parties(org_id,kind,legal_name,phones) VALUES (o,'PF','x','{{}}'::jsonb)"),
    "role unique per party": ("unique_violation",
        f"INSERT INTO {SCHEMA}.pty_party_roles(org_id,party_id,role) VALUES (o,p,'customer')"),
    "role is one of the four": ("check_violation",
        f"INSERT INTO {SCHEMA}.pty_party_roles(org_id,party_id,role) VALUES (o,p,'ceo')"),
    "a role cannot name a party of another org": ("foreign_key_violation",
        f"INSERT INTO {SCHEMA}.pty_party_roles(org_id,party_id,role) VALUES (o2,p,'supplier')"),
    "deleting a party cascades its roles": ("check_violation",
        f"DELETE FROM {SCHEMA}.pty_parties WHERE id = p; "
        f"IF EXISTS (SELECT 1 FROM {SCHEMA}.pty_party_roles WHERE party_id = p) THEN RAISE EXCEPTION 'cascade missing'; END IF; "
        "RAISE check_violation USING MESSAGE = 'cascade ok'"),
}


def _rule_sql(clause: str, stmt: str) -> str:
    body = f"""BEGIN
    {stmt};
    RAISE EXCEPTION 'NOT ENFORCED';
  EXCEPTION WHEN {clause} THEN NULL;
  END;"""
    return _BASE.replace("{body}", body)


@pytest.fixture(scope="module")
def replay() -> dict:
    sql = parties_migration(PartiesConfig(schema=SCHEMA), SCHEMA)
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "parties_migration", "sql": sql, "mode": "file", "twice": True},
        *({"product": SCHEMA, "file": f"rule: {name}", "sql": _rule_sql(*rule), "mode": "file", "twice": False} for name, rule in RULES.items()),
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=300,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:  # the harness could not MEASURE: say so, never read it as a pass
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    return {step["file"]: step for step in out["steps"]}


def test_ddl_applies_twice_on_real_postgres(replay):
    step = replay["parties_migration"]
    assert step["failures"] == [], step["failures"]


@pytest.mark.parametrize("rule", list(RULES))
def test_database_rule_is_enforced(replay, rule):
    step = replay[f"rule: {rule}"]
    assert step["failures"] == [], f"{rule}: {step['failures']}"
