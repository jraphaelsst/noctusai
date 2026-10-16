"""Orbity 024 (billing reminders / dunning organ) on the REAL core + orbity chain on PGlite, over the prod-shaped rows.

The replay applies 024 TWICE (idempotency) on top of 019/021/023 and the migrated receivables, then each assertion is a SQL
step that RAISES on a mismatch. The organ's own UNIQUE / CHECK guards are proven generically by `test_organ_guard_probes`
(registry-derived); this pins what is specific to Orbity's chain:

* the opt-out column lands on the already-migrated receivables with the OFF-by-default value (nobody is opted out silently);
* reminders are OFF for every existing org (no settings row = off) and no rule/log row appears out of nowhere;
* the dedup ledger rejects a second row for the same (receivable, rule, cycle); a rule cannot be deleted under its history.
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_A = "a0000000-0000-4000-8000-00000000000a"
_E = "e3000000-0000-4000-8000-000000000003"  # a migrated, open, overdue receivable of org A
_TARGETS = {f"products/orbity/backend/migrations/{n}" for n in (
    "019_finance.sql", "021_contracts.sql", "023_billing_on_seed_organs.sql", "024_finance_reminders.sql")}


def _step(name: str, sql: str) -> dict:
    return {"product": "orbity", "file": name, "sql": sql, "mode": "file", "twice": False}


def _check(name: str, condition: str) -> dict:
    return _step(f"assert:{name}", f"DO $chk$ BEGIN IF NOT ({condition}) THEN RAISE EXCEPTION 'ASSERT {name}'; END IF; END $chk$;")


ASSERTIONS = [
    _check("migrated_receivables_are_not_opted_out", "(SELECT count(*) FROM orbity.fin_entries WHERE reminders_opt_out) = 0 AND (SELECT count(*) FROM orbity.fin_entries) > 0"),
    _check("reminders_are_off_for_every_existing_org", "(SELECT count(*) FROM orbity.fin_reminder_settings) = 0 AND (SELECT count(*) FROM orbity.fin_reminder_rules) = 0 AND (SELECT count(*) FROM orbity.fin_reminder_log) = 0"),
    _step("dedup_ledger_and_rule_history", f"""
DO $t$ DECLARE v_rule uuid; BEGIN
  INSERT INTO orbity.fin_reminder_rules (org_id, channel, offset_days, template) VALUES ('{_A}', 'whatsapp', 0, 'Oi {{nome}}') RETURNING id INTO v_rule;
  INSERT INTO orbity.fin_reminder_log (org_id, entry_id, rule_id, channel, offset_days, cycle_date, status, recipient, message)
    VALUES ('{_A}', '{_E}', v_rule, 'whatsapp', 0, DATE '2026-03-31', 'pending', '5511', 'x');
  BEGIN
    INSERT INTO orbity.fin_reminder_log (org_id, entry_id, rule_id, channel, offset_days, cycle_date, status, recipient, message)
      VALUES ('{_A}', '{_E}', v_rule, 'whatsapp', 0, DATE '2026-03-31', 'pending', '5511', 'x');
    RAISE EXCEPTION 'ASSERT a second log row for the same slot was accepted';
  EXCEPTION WHEN unique_violation THEN NULL;
  END;
  BEGIN
    DELETE FROM orbity.fin_reminder_rules WHERE id = v_rule;
    RAISE EXCEPTION 'ASSERT a rule with history was deleted';
  EXCEPTION WHEN foreign_key_violation THEN NULL;
  END;
  DELETE FROM orbity.fin_reminder_log WHERE rule_id = v_rule;
  DELETE FROM orbity.fin_reminder_rules WHERE id = v_rule;
END $t$;"""),
]


def test_reminders_migration_lands_off_by_default_on_the_real_chain_and_is_idempotent(pglite):
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "orbity", set(_TARGETS), "worktree", {})
    assert any(s["file"] == "fixture:023_billing_on_seed_organs.sql" for s in steps), "the prod-shaped fixture must be replayed"
    steps.extend(ASSERTIONS)
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {(s["product"], s["file"]): s for s in res["steps"]}
    assert not by_file[("orbity", "024_finance_reminders.sql")]["failures"], by_file[("orbity", "024_finance_reminders.sql")]["failures"]
    for s in ASSERTIONS:
        assert not by_file[("orbity", s["file"])]["failures"], (s["file"], by_file[("orbity", s["file"])]["failures"])
