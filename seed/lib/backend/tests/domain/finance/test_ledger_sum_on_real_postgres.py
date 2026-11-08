"""`<prefix>ledger_signed_sum` on a REAL Postgres (PGlite) equals the Python fold it replaced, row for row.

`account_balance` and the cash-flow opening balance used to read every ledger row and fold them with
`accounts.signed_ledger_cents`. They now ask Postgres for the one number (event-sourcing-program P0). This
suite builds a mixed ledger in Python -- two orgs, two accounts, IN/OUT, transfers, reversal rows carrying
`reverses_id`, rows ON the boundary day -- computes every expected sum with the OLD Python fold, and makes
the database function prove it returns the same number (a mismatch RAISEs with both values).
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import uuid
from datetime import date, timedelta
from pathlib import Path

import pytest

from noctusai_lib.domain.finance import FinanceConfig, finance_migration
from noctusai_lib.domain.finance.accounts import signed_ledger_cents

ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
SCHEMA = "finsum"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

PRELUDE = f"""
CREATE SCHEMA IF NOT EXISTS {SCHEMA};
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
CREATE OR REPLACE FUNCTION public.current_org_id() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
"""

ORG_A, ORG_B = str(uuid.UUID(int=1)), str(uuid.UUID(int=2))
ACC_A1, ACC_A2, ACC_B1 = str(uuid.UUID(int=11)), str(uuid.UUID(int=12)), str(uuid.UUID(int=21))
ACCOUNTS = ((ORG_A, ACC_A1), (ORG_A, ACC_A2), (ORG_B, ACC_B1))
DAY0 = date(2026, 1, 1)
BOUNDARY = date(2026, 3, 15)


def _ledger() -> list[dict]:
    """~300 deterministic rows; ~1 in 6 is later reversed by an opposite row carrying `reverses_id`."""
    rng = random.Random(20261107)
    rows: list[dict] = []
    for i in range(240):
        org, acc = ACCOUNTS[i % 3]
        day = BOUNDARY if i % 17 == 0 else DAY0 + timedelta(days=rng.randrange(0, 150))  # boundary-day rows on purpose
        rows.append({
            "id": str(uuid.UUID(int=10_000 + i)), "org_id": org, "account_id": acc, "occurred_on": day,
            "direction": rng.choice(("in", "out")), "amount_cents": rng.randrange(1, 2_000_000),
            "origin": rng.choice(("transfer", "adjustment", "opening")), "reverses_id": None,
        })
        rows[-1]["transfer_group"] = str(uuid.UUID(int=50_000 + i)) if rows[-1]["origin"] == "transfer" else None
    for i, orig in enumerate([r for r in rows if rng.random() < 1 / 6]):
        rows.append({
            **orig, "id": str(uuid.UUID(int=90_000 + i)), "reverses_id": orig["id"],
            "occurred_on": orig["occurred_on"] + timedelta(days=rng.randrange(0, 20)),
            "direction": "out" if orig["direction"] == "in" else "in",
        })
    return rows


def _fold(rows: list[dict], org: str, account: str | None, on: date, inclusive: bool) -> int:
    """The OLD read path: select the rows the old PostgREST filters selected, fold them in Python."""
    return signed_ledger_cents([
        r for r in rows
        if r["org_id"] == org and (account is None or r["account_id"] == account)
        and (r["occurred_on"] <= on if inclusive else r["occurred_on"] < on)
    ])


def _cases(rows: list[dict]) -> list[tuple[str, str | None, date, bool, int]]:
    out = []
    for on in (DAY0 - timedelta(days=1), DAY0, BOUNDARY, date(2026, 6, 30), date(2027, 1, 1)):
        for inclusive in (True, False):
            for org, account in ((ORG_A, None), (ORG_B, None), *ACCOUNTS, (ORG_B, ACC_A1)):  # last: foreign account -> 0
                out.append((org, account, on, inclusive, _fold(rows, org, account, on, inclusive)))
    return out


def _sql_literal(v) -> str:
    if v is None:
        return "NULL"
    return f"'{v.isoformat() if isinstance(v, date) else v}'"


def _seed_sql(rows: list[dict]) -> str:
    accts = ",".join(f"('{acc}','{org}','Conta','checking')" for org, acc in ACCOUNTS)
    values = ",".join(
        "(" + ",".join(_sql_literal(r[k]) for k in ("id", "org_id", "account_id", "occurred_on", "direction", "origin", "transfer_group", "reverses_id"))
        + f",{r['amount_cents']})"
        for r in rows
    )
    return (f"INSERT INTO {SCHEMA}.fin_accounts(id,org_id,name,kind) VALUES {accts};\n"
            f"INSERT INTO {SCHEMA}.fin_ledger(id,org_id,account_id,occurred_on,direction,origin,transfer_group,reverses_id,amount_cents) VALUES {values};\n")


def _parity_sql(cases) -> str:
    checks = "\n".join(
        f"  got := {SCHEMA}.fin_ledger_signed_sum('{org}', {_sql_literal(acc)}, '{on.isoformat()}', {str(inc).lower()});\n"
        f"  IF got IS DISTINCT FROM {want}::bigint THEN RAISE EXCEPTION 'parity: org={org} acc={acc} on={on} incl={inc} sql=% python={want}', got; END IF;"
        for org, acc, on, inc, want in cases
    )
    return f"DO $$\nDECLARE got bigint;\nBEGIN\n{checks}\nEND $$;\n"


_DB_REVERSAL = f"""
DO $$
DECLARE o uuid := gen_random_uuid(); a uuid := gen_random_uuid(); e uuid := gen_random_uuid(); r jsonb; sid uuid; got bigint;
BEGIN
  INSERT INTO {SCHEMA}.fin_accounts(id,org_id,name,kind) VALUES (a,o,'Banco','checking');
  INSERT INTO {SCHEMA}.fin_entries(id,org_id,direction,description,competence_month,due_date,amount_cents)
    VALUES (e,o,'receivable','x','2026-10-01','2026-10-10',1000);
  r := {SCHEMA}.fin_settle_entry_locked(o, e, jsonb_build_object('id', gen_random_uuid(), 'org_id', o, 'entry_id', e,
       'account_id', a, 'kind', 'payment', 'settled_on', '2026-10-10', 'amount_cents', 700, 'fee_cents', 0, 'created_at', now()));
  sid := (r->'settlement'->>'id')::uuid;
  INSERT INTO {SCHEMA}.fin_ledger(org_id,account_id,occurred_on,direction,amount_cents,origin,settlement_id)
    VALUES (o,a,'2026-10-10','in',700,'settlement',sid);
  got := {SCHEMA}.fin_ledger_signed_sum(o, a, '2026-10-10', true);
  IF got <> 700 THEN RAISE EXCEPTION 'before reversal: %', got; END IF;
  r := {SCHEMA}.fin_reverse_settlement_locked(o, sid, 'engano', NULL, '2026-10-11');
  got := {SCHEMA}.fin_ledger_signed_sum(o, a, '2026-10-10', true);
  IF got <> 700 THEN RAISE EXCEPTION 'reversal booked on 10-11 must not count on 10-10: %', got; END IF;
  got := {SCHEMA}.fin_ledger_signed_sum(o, a, '2026-10-11', false);
  IF got <> 700 THEN RAISE EXCEPTION 'exclusive bound must drop the 10-11 reversal: %', got; END IF;
  got := {SCHEMA}.fin_ledger_signed_sum(o, a, '2026-10-11', true);
  IF got <> 0 THEN RAISE EXCEPTION 'after reversal: %', got; END IF;
  got := {SCHEMA}.fin_ledger_signed_sum(o, NULL, '2026-10-11', true);
  IF got <> 0 THEN RAISE EXCEPTION 'org-wide after reversal: %', got; END IF;
END $$;
"""

_POSTURE = f"""
DO $$
DECLARE n int;
BEGIN
  SELECT count(*) INTO n FROM pg_proc p JOIN pg_namespace ns ON ns.oid = p.pronamespace
    WHERE ns.nspname = '{SCHEMA}' AND p.proname = 'fin_ledger_signed_sum' AND p.prosecdef AND p.provolatile = 's'
      AND p.proconfig::text LIKE '%search_path=pg_catalog, {SCHEMA}, pg_temp%';
  IF n <> 1 THEN RAISE EXCEPTION 'ledger_signed_sum must be SECURITY DEFINER, STABLE, search_path pinned'; END IF;
  IF has_function_privilege('anon', '{SCHEMA}.fin_ledger_signed_sum(uuid, uuid, date, boolean)', 'EXECUTE')
     OR has_function_privilege('authenticated', '{SCHEMA}.fin_ledger_signed_sum(uuid, uuid, date, boolean)', 'EXECUTE') THEN
    RAISE EXCEPTION 'ledger_signed_sum must not be executable by anon/authenticated (it takes the org as a parameter)';
  END IF;
  -- tier:org, served only through the API: no browser privilege at all; the service role keeps everything.
  IF has_table_privilege('authenticated', '{SCHEMA}.fin_ledger', 'SELECT')
     OR NOT has_table_privilege('service_role', '{SCHEMA}.fin_ledger', 'INSERT')
     OR has_table_privilege('authenticated', '{SCHEMA}.fin_ledger', 'INSERT')
     OR has_table_privilege('authenticated', '{SCHEMA}.fin_ledger', 'UPDATE')
     OR has_table_privilege('authenticated', '{SCHEMA}.fin_ledger', 'DELETE')
     OR has_table_privilege('anon', '{SCHEMA}.fin_ledger', 'SELECT') THEN
    RAISE EXCEPTION 'fin_ledger privileges are not the tier:org shape';
  END IF;
  SELECT count(*) INTO n FROM pg_policies WHERE schemaname = '{SCHEMA}' AND tablename = 'fin_ledger'
    AND ('authenticated' = ANY(roles) OR 'anon' = ANY(roles) OR 'public' = ANY(roles));
  IF n <> 0 THEN RAISE EXCEPTION 'fin_ledger keeps % browser polic(ies)', n; END IF;
  IF obj_description('{SCHEMA}.fin_ledger'::regclass, 'pg_class') IS DISTINCT FROM 'tier:org' THEN
    RAISE EXCEPTION 'fin_ledger does not declare tier:org';
  END IF;
END $$;
"""


@pytest.fixture(scope="module")
def replay() -> dict:
    rows = _ledger()
    sql = finance_migration(FinanceConfig(schema=SCHEMA), SCHEMA)
    steps = [
        {"product": SCHEMA, "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "migration", "sql": sql, "mode": "file", "twice": True},
        {"product": SCHEMA, "file": "seed ledger", "sql": _seed_sql(rows), "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "parity", "sql": _parity_sql(_cases(rows)), "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "db reversal", "sql": _DB_REVERSAL, "mode": "file", "twice": False},
        {"product": SCHEMA, "file": "posture", "sql": _POSTURE, "mode": "file", "twice": False},
    ]
    proc = subprocess.run(
        ["node", str(HARNESS)],
        input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
        capture_output=True, text=True, cwd=NODE_DIR, timeout=300,
    )
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    return {step["file"]: step for step in out["steps"]}


def test_the_mixed_ledger_is_really_mixed():
    rows = _ledger()
    assert any(r["reverses_id"] for r in rows) and any(r["occurred_on"] == BOUNDARY for r in rows)
    assert {r["direction"] for r in rows} == {"in", "out"} and {r["org_id"] for r in rows} == {ORG_A, ORG_B}
    assert any(want != 0 for *_, want in _cases(rows))  # the parity is not 0 == 0 everywhere


@pytest.mark.parametrize("step", ["migration", "seed ledger", "parity", "db reversal", "posture"])
def test_sql_sum_matches_the_python_fold(replay, step):
    assert replay[step]["failures"] == [], replay[step]["failures"]
