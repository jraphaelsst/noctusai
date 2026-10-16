"""`finance_reminders_migration`: org_id + RLS on every table, guard probes complete, and the DDL on a REAL Postgres
(applied twice; the dedup UNIQUE and the CHECKs actually refuse)."""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from noctusai_lib.domain.finance import FinanceConfig, finance_migration
from noctusai_lib.domain.finance.reminders import REMINDER_TABLES, finance_reminders_guard_probes, finance_reminders_migration

CFG = FinanceConfig(schema="finx")
SQL = finance_reminders_migration(CFG, "finx")


@pytest.mark.parametrize("table", REMINDER_TABLES)
def test_every_table_has_org_id_and_rls(table):
    name = f"fin_{table}"
    block = re.search(rf"CREATE TABLE IF NOT EXISTS finx\.{name} \((.*?)\n\);", SQL, re.S)
    assert block and re.search(r"\borg_id\s+UUID\b", block.group(1))
    assert f"ALTER TABLE finx.{name} ENABLE ROW LEVEL SECURITY;" in SQL
    assert f'"{name}_select_own_org"' in SQL and "service_role_bypass" in SQL


def test_dedup_unique_covers_org_entry_rule_cycle():
    assert re.search(r"CREATE UNIQUE INDEX IF NOT EXISTS uq_fin_reminder_log_dedup ON finx\.fin_reminder_log \(org_id, entry_id, rule_id, cycle_date\);", SQL)


def test_guard_probes_declare_every_unique_and_named_check():
    declared = {p.guard_name for p in finance_reminders_guard_probes("finx")}
    emitted = set(re.findall(r"CREATE UNIQUE INDEX IF NOT EXISTS (\w+)", SQL)) | set(re.findall(r"CONSTRAINT (\w+) CHECK", SQL))
    assert emitted == declared


def test_migration_rejects_blank_schema():
    with pytest.raises(ValueError):
        finance_reminders_migration(CFG, " ")


ROOT = Path(__file__).resolve().parents[6]
NODE_DIR = ROOT / "mcp" / "noctusai" / "node"
HARNESS = NODE_DIR / "migration_replay" / "replay.mjs"
STUBS = NODE_DIR / "migration_replay" / "stubs.sql"
needs_pg = pytest.mark.skipif(
    shutil.which("node") is None or not HARNESS.exists() or not (NODE_DIR / "node_modules" / "@electric-sql").exists(),
    reason="PGlite replay harness unavailable (needs `node` and mcp/noctusai/node/node_modules)",
)

PRELUDE = """
CREATE SCHEMA IF NOT EXISTS finx;
CREATE OR REPLACE FUNCTION public.current_org_id_for(text) RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
CREATE OR REPLACE FUNCTION public.current_org_id() RETURNS uuid LANGUAGE sql STABLE AS $$ SELECT NULL::uuid $$;
"""
_SETUP = """DO $$ DECLARE o uuid := gen_random_uuid(); e uuid := gen_random_uuid(); r uuid := gen_random_uuid(); BEGIN
  INSERT INTO finx.fin_entries(id,org_id,direction,description,competence_month,due_date,amount_cents) VALUES (e,o,'receivable','x','2026-10-01','2026-10-10',1000);
  INSERT INTO finx.fin_reminder_rules(id,org_id,channel,offset_days,template) VALUES (r,o,'whatsapp',0,'t');
  {body}
END $$;"""
_LOG = ("INSERT INTO finx.fin_reminder_log(org_id,entry_id,rule_id,channel,offset_days,cycle_date,recipient,message)"
        " VALUES (o,e,r,'whatsapp',0,'2026-10-10','5511','m')")
RULES = {
    "the same (receivable, rule, cycle) cannot be logged twice": ("unique_violation", f"{_LOG}; {_LOG}"),
    "one rule per (org, channel, offset)": ("unique_violation",
        "INSERT INTO finx.fin_reminder_rules(org_id,channel,offset_days,template) VALUES (o,'whatsapp',0,'dup')"),
    "log status is an enum": ("check_violation", _LOG.replace("recipient,message)", "recipient,message,status)").replace("'m')", "'m','bogus')")),
    "offset is bounded": ("check_violation",
        "INSERT INTO finx.fin_reminder_rules(org_id,channel,offset_days,template) VALUES (o,'whatsapp',9999,'x')"),
    "a rule cannot be deleted once it has history": ("foreign_key_violation", f"{_LOG}; DELETE FROM finx.fin_reminder_rules WHERE id = r"),
}


@pytest.fixture(scope="module")
def replay() -> dict:
    steps = [
        {"product": "finx", "file": "prelude", "sql": PRELUDE, "mode": "file", "twice": False},
        {"product": "finx", "file": "finance", "sql": finance_migration(CFG, "finx"), "mode": "file", "twice": True},
        {"product": "finx", "file": "reminders", "sql": SQL, "mode": "file", "twice": True},
        *(
            {"product": "finx", "file": f"rule: {n}", "mode": "file", "twice": False,
             "sql": _SETUP.replace("{body}", f"BEGIN {stmt}; RAISE EXCEPTION 'NOT ENFORCED'; EXCEPTION WHEN {clause} THEN NULL; END;")}
            for n, (clause, stmt) in RULES.items()
        ),
    ]
    proc = subprocess.run(["node", str(HARNESS)], input=json.dumps({"stubs": STUBS.read_text(encoding="utf-8"), "steps": steps}),
                          capture_output=True, text=True, cwd=NODE_DIR, timeout=300)
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        pytest.fail(f"PGlite harness produced no verdict: {(proc.stderr or proc.stdout)[-400:]}")
    assert out.get("ok"), out
    return {step["file"]: step for step in out["steps"]}


@needs_pg
def test_reminders_ddl_applies_twice_on_real_postgres(replay):
    assert replay["reminders"]["failures"] == [], replay["reminders"]["failures"]


@needs_pg
@pytest.mark.parametrize("name", list(RULES))
def test_db_side_rule_is_enforced(replay, name):
    assert replay[f"rule: {name}"]["failures"] == [], replay[f"rule: {name}"]["failures"]
