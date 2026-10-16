"""Orbity 019/021/023 (billing on the seed organs) on the REAL core + orbity chain on PGlite, over prod-shaped rows.

`products/orbity/backend/migration-replay.json` inserts the legacy rows (the owner's SMOKE-TEST contract/client
included) just before 023. The replay applies 023 TWICE (idempotency), then every assertion below runs as a SQL step
that RAISES on a mismatch -- so a red here names the property that broke:

* nothing is lost, ids are preserved, money is equal to the cent;
* the seed billing run cannot bill an already-migrated month a second time (contract_billings carry them);
* the billing cursor never backfills the past;
* the compat views still answer the old shape; the RPCs enforce their invariants (atomic offboarding, stale-claim recovery).
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from tools.noctus.dev import migration_replay as mr

_A = "a0000000-0000-4000-8000-00000000000a"
_TARGETS = {f"products/orbity/backend/migrations/{n}" for n in ("019_finance.sql", "021_contracts.sql", "023_billing_on_seed_organs.sql")}


def _check(name: str, condition: str) -> dict:
    sql = f"DO $chk$ BEGIN IF NOT ({condition}) THEN RAISE EXCEPTION 'ASSERT {name}'; END IF; END $chk$;"
    return {"product": "orbity", "file": f"assert:{name}", "sql": sql, "mode": "file", "twice": False}


def _step(name: str, sql: str) -> dict:
    return {"product": "orbity", "file": name, "sql": sql, "mode": "file", "twice": False}


ASSERTIONS = [
    # --- nothing lost, ids preserved ---------------------------------------------------------------------------------
    _check("clients_legal_name_backfilled", "(SELECT count(*) FROM orbity.clients WHERE legal_name IS NULL OR legal_name <> name) = 0"),
    _check("inactive_client_has_inactivated_at", "(SELECT inactivated_at IS NOT NULL FROM orbity.clients WHERE id = 'c2000000-0000-4000-8000-000000000002')"),
    _check("every_contract_moved_with_its_id", "(SELECT count(*) FROM orbity.ctr_contracts) = (SELECT count(*) FROM orbity.contracts_legacy)"),
    _check("smoke_test_contract_survives", "(SELECT count(*) FROM orbity.ctr_contracts WHERE id = 'd1000000-0000-4000-8000-000000000001' AND title = 'SMOKE-TEST Contrato' AND party_id = 'c1000000-0000-4000-8000-000000000001') = 1"),
    _check("contract_status_mapping", "(SELECT string_agg(status, ',' ORDER BY id) FROM orbity.ctr_contracts WHERE org_id = '" + _A + "') = 'active,suspended,terminated,draft'"),
    _check("contract_money_in_cents", "(SELECT amount_cents FROM orbity.ctr_contracts WHERE id = 'd1000000-0000-4000-8000-000000000001') = 150050"),
    _check("every_revenue_moved_with_its_id", "(SELECT count(*) FROM orbity.fin_entries e JOIN orbity.revenues_legacy r ON r.id = e.id AND e.direction = 'receivable') = (SELECT count(*) FROM orbity.revenues_legacy)"),
    _check("every_expense_moved_with_its_id", "(SELECT count(*) FROM orbity.fin_entries e JOIN orbity.expenses_legacy x ON x.id = e.id AND e.direction = 'payable') = (SELECT count(*) FROM orbity.expenses_legacy)"),
    _check("receivable_total_equal_to_the_cent", "(SELECT sum(amount_cents) FROM orbity.fin_entries WHERE direction = 'receivable') = (SELECT round(sum(amount) * 100) FROM orbity.revenues_legacy)"),
    _check("payable_total_equal_to_the_cent", "(SELECT sum(amount_cents) FROM orbity.fin_entries WHERE direction = 'payable') = (SELECT round(sum(amount) * 100) FROM orbity.expenses_legacy)"),
    _check("paid_ones_have_a_settlement_and_a_ledger_row", "(SELECT count(*) FROM orbity.fin_settlements) = 4 AND (SELECT count(*) FROM orbity.fin_ledger WHERE origin = 'settlement') = 4"),
    _check("cash_in_out_balance", "(SELECT sum(CASE direction WHEN 'in' THEN amount_cents ELSE -amount_cents END) FROM orbity.fin_ledger) = (150050 + 150050 + 9999 - 200000)"),
    _check("status_mapping", "(SELECT string_agg(status, ',' ORDER BY id) FROM orbity.fin_entries WHERE direction = 'receivable' AND org_id = '" + _A + "') = 'paid,paid,open,cancelled,open,open,paid'"),
    _check("every_revenue_has_a_charge_row", "(SELECT count(*) FROM orbity.billing_charges) = (SELECT count(*) FROM orbity.revenues_legacy)"),
    _check("charges_default_to_not_preserved_and_simple", "(SELECT count(*) FROM orbity.billing_charges WHERE preserved_after_deactivation OR generation_status <> 'skipped') = 0"),
    # --- the seed billing run can never double-bill a migrated month ---------------------------------------------------
    _check("contract_born_months_are_recorded_for_the_billing_run", "(SELECT count(*) FROM orbity.ctr_contract_billings) = (SELECT count(*) FROM orbity.revenues_legacy WHERE contract_id IS NOT NULL)"),
    _check("a_duplicate_due_date_keeps_both_rows", "(SELECT count(DISTINCT source_ref) FROM orbity.fin_entries WHERE source = 'contracts' AND org_id = '" + _A + "') = 6"),
    _check("billing_source_ref_matches_the_organ_key", "(SELECT count(*) FROM orbity.ctr_contract_billings b JOIN orbity.fin_entries e ON e.id = b.entry_id WHERE e.source_ref = b.source_ref AND b.source_ref LIKE b.contract_id::text || ':%') = (SELECT count(*) FROM orbity.ctr_contract_billings)"),
    # --- the cursor never backfills the past ---------------------------------------------------------------------------
    _check("cursor_is_not_in_the_past_for_active_and_suspended", "(SELECT count(*) FROM orbity.ctr_contracts WHERE status IN ('active','suspended') AND (next_period_on IS NULL OR next_period_on < CURRENT_DATE)) = 0"),
    _check("cursor_is_null_for_ended_and_draft", "(SELECT count(*) FROM orbity.ctr_contracts WHERE status IN ('terminated','draft') AND next_period_on IS NOT NULL) = 0"),
    _check("due_day_clamps_to_short_months", "(SELECT extract(day FROM next_period_on) FROM orbity.ctr_contracts WHERE id = 'd1000000-0000-4000-8000-000000000001') = extract(day FROM (date_trunc('month', (SELECT next_period_on FROM orbity.ctr_contracts WHERE id = 'd1000000-0000-4000-8000-000000000001')) + interval '1 month' - interval '1 day')) OR (SELECT extract(day FROM next_period_on) FROM orbity.ctr_contracts WHERE id = 'd1000000-0000-4000-8000-000000000001') = 31"),
    # --- compat views (reports_service still reads the old shape) ----------------------------------------------------
    _check("revenues_view_paid_sum", "(SELECT sum(amount) FROM orbity.revenues WHERE status = 'paid') = (SELECT sum(amount) FROM orbity.revenues_legacy WHERE status = 'paid')"),
    _check("revenues_view_maps_overdue_and_canceled", "(SELECT count(*) FROM orbity.revenues WHERE status = 'canceled') = 1 AND (SELECT count(*) FROM orbity.revenues WHERE status = 'overdue') >= 1"),
    _check("revenues_view_exposes_client_and_paid_at", "(SELECT count(*) FROM orbity.revenues WHERE status = 'paid' AND paid_at IS NOT NULL AND client_id IS NOT NULL) >= 2"),
    _check("expenses_view_matches", "(SELECT count(*) FROM orbity.expenses WHERE paid) = 1 AND (SELECT sum(amount) FROM orbity.expenses) = (SELECT sum(amount) FROM orbity.expenses_legacy)"),
    # --- offboard_client: atomic, every charge decided -----------------------------------------------------------------
    _step("offboard_refuses_an_undecided_charge", f"""
DO $t$ BEGIN
  BEGIN
    PERFORM orbity.offboard_client('{_A}', 'c1000000-0000-4000-8000-000000000001', '{{}}'::uuid[], '{{}}'::uuid[]);
    RAISE EXCEPTION 'ASSERT offboard accepted an undecided charge';
  EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
  END;
  IF NOT (SELECT active FROM orbity.clients WHERE id = 'c1000000-0000-4000-8000-000000000001') THEN
    RAISE EXCEPTION 'ASSERT a refused offboarding must leave the client active';
  END IF;
END $t$;"""),
    _step("offboard_refuses_a_foreign_entry", f"""
DO $t$ BEGIN
  BEGIN
    PERFORM orbity.offboard_client('{_A}', 'c1000000-0000-4000-8000-000000000001',
      ARRAY['e3000000-0000-4000-8000-000000000003','e5000000-0000-4000-8000-000000000005','e8000000-0000-4000-8000-000000000008']::uuid[], '{{}}'::uuid[]);
    RAISE EXCEPTION 'ASSERT offboard accepted another org''s entry';
  EXCEPTION WHEN SQLSTATE '22023' THEN NULL;
  END;
  IF (SELECT status FROM orbity.fin_entries WHERE id = 'e3000000-0000-4000-8000-000000000003') <> 'open' THEN
    RAISE EXCEPTION 'ASSERT a refused offboarding must roll every cancel back';
  END IF;
END $t$;"""),
    _step("offboard_cancels_and_keeps", f"""
DO $t$ DECLARE r jsonb; BEGIN
  UPDATE orbity.billing_charges SET external_id = 'pay_9', generation_status = 'generated' WHERE entry_id = 'e3000000-0000-4000-8000-000000000003';
  r := orbity.offboard_client('{_A}', 'c1000000-0000-4000-8000-000000000001',
        ARRAY['e3000000-0000-4000-8000-000000000003']::uuid[], ARRAY['e5000000-0000-4000-8000-000000000005']::uuid[]);
  IF (r->>'cancelled')::int <> 1 OR (r->>'preserved')::int <> 1 THEN RAISE EXCEPTION 'ASSERT counts %', r; END IF;
  IF (SELECT status FROM orbity.fin_entries WHERE id = 'e3000000-0000-4000-8000-000000000003') <> 'cancelled' THEN RAISE EXCEPTION 'ASSERT cancel'; END IF;
  IF (SELECT status FROM orbity.fin_entries WHERE id = 'e5000000-0000-4000-8000-000000000005') <> 'open' THEN RAISE EXCEPTION 'ASSERT kept stays open'; END IF;
  IF NOT (SELECT preserved_after_deactivation FROM orbity.billing_charges WHERE entry_id = 'e5000000-0000-4000-8000-000000000005') THEN RAISE EXCEPTION 'ASSERT kept flagged'; END IF;
  IF (SELECT gateway_cancel_status FROM orbity.billing_charges WHERE entry_id = 'e3000000-0000-4000-8000-000000000003') IS DISTINCT FROM 'pending' THEN RAISE EXCEPTION 'ASSERT gateway cancel queued'; END IF;
  IF (SELECT active OR inactivated_at IS NULL FROM orbity.clients WHERE id = 'c1000000-0000-4000-8000-000000000001') THEN RAISE EXCEPTION 'ASSERT client inactive'; END IF;
  IF jsonb_array_length(r->'gateway_cancel_entry_ids') <> 1 THEN RAISE EXCEPTION 'ASSERT gateway ids %', r; END IF;
END $t$;"""),
    # --- billing_reserve_charges: claim once, recover the stale ----------------------------------------------------------
    _step("reserve_claims_once_and_recovers_the_stale", f"""
DO $t$ DECLARE n int; BEGIN
  UPDATE orbity.billing_charges SET generation_status = 'queued', next_attempt_at = NULL, generation_attempts = 0
   WHERE entry_id IN ('e6000000-0000-4000-8000-000000000006');
  SELECT count(*) INTO n FROM orbity.billing_reserve_charges(5, 'w1');
  IF n <> 1 THEN RAISE EXCEPTION 'ASSERT first claim got %', n; END IF;
  SELECT count(*) INTO n FROM orbity.billing_reserve_charges(5, 'w2');
  IF n <> 0 THEN RAISE EXCEPTION 'ASSERT second claim must get nothing, got %', n; END IF;
  UPDATE orbity.billing_charges SET locked_at = now() - interval '30 minutes' WHERE entry_id = 'e6000000-0000-4000-8000-000000000006';
  SELECT count(*) INTO n FROM orbity.billing_reserve_charges(5, 'w3');
  IF n <> 1 THEN RAISE EXCEPTION 'ASSERT a stale claim must be recovered and re-claimed, got %', n; END IF;
  IF (SELECT generation_attempts FROM orbity.billing_charges WHERE entry_id = 'e6000000-0000-4000-8000-000000000006') <> 2 THEN
    RAISE EXCEPTION 'ASSERT attempts must keep counting across a recovery';
  END IF;
  UPDATE orbity.billing_charges SET generation_status = 'generating', locked_at = now() - interval '30 minutes', generation_attempts = 5
   WHERE entry_id = 'e6000000-0000-4000-8000-000000000006';
  PERFORM count(*) FROM orbity.billing_reserve_charges(5, 'w4');
  IF (SELECT generation_status FROM orbity.billing_charges WHERE entry_id = 'e6000000-0000-4000-8000-000000000006') <> 'failed' THEN
    RAISE EXCEPTION 'ASSERT spent attempts must end failed, not loop';
  END IF;
END $t$;"""),
]


def test_billing_migration_keeps_every_row_and_the_rpcs_hold_on_the_real_chain(pglite):
    root = Path(REPO_ROOT)
    steps = mr._steps_for(root, "orbity", set(_TARGETS), "worktree", {})
    assert any(s["file"] == "fixture:023_billing_on_seed_organs.sql" for s in steps), "the prod-shaped fixture must be replayed"
    steps.extend(ASSERTIONS)
    res = mr._run_harness(steps, 900, None)
    assert res.get("ok"), res
    by_file = {(s["product"], s["file"]): s for s in res["steps"]}
    for target in ("019_finance.sql", "021_contracts.sql", "023_billing_on_seed_organs.sql"):
        assert not by_file[("orbity", target)]["failures"], (target, by_file[("orbity", target)]["failures"])
    assert not by_file[("orbity", "fixture:023_billing_on_seed_organs.sql")]["failures"], by_file[("orbity", "fixture:023_billing_on_seed_organs.sql")]["failures"]
    failed = {name: s["failures"][0]["error"] for (prod, name), s in by_file.items() if prod == "orbity" and name.startswith(("assert:", "offboard", "reserve")) and s["failures"]}
    assert not failed, failed
    ran = [name for (prod, name) in by_file if prod == "orbity" and name.startswith(("assert:", "offboard", "reserve"))]
    assert len(ran) == len(ASSERTIONS), "every assertion step must have run"
