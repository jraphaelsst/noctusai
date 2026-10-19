"""Gateway sync: Fake ChargeOperations, cursor resume, recorded errors, idempotent re-runs, no double-booking."""
from __future__ import annotations

import json
from datetime import date

from noctusai_lib.domain.finance import accounts, make_finance_booking, run_gateway_sync_all
from noctusai_lib.domain.finance.gateway_sync import sync_gateway_account
from noctusai_lib.integrations.payments.charges import FakeChargeOperations
from noctusai_lib.integrations.payments.errors import PaymentGatewayError

from .conftest import CFG, ORG_A, mk_account
from .recon_support import bt, build_recon_harness, rh  # noqa: F401

P = "/api/finance"


def gw(s, name="asaas"):
    # the fixture statement lines are fixed October-2026 days: the opening date anchors the sync window there,
    # otherwise the default "last 30 days from today" lookback slides past them as the clock moves
    return accounts.create_account(s, {"name": "Asaas", "kind": "gateway", "gateway": name, "opening_date": "2026-10-01"})


def sync(rh, acc, **body):
    return rh.client.post(f"{P}/accounts/{acc['id']}/gateway-sync", headers=rh.admin, json=body)


def state(rh, acc):
    return rh.s.rows("gateway_sync", eq={"account_id": acc["id"]}, order_col="account_id")[0]


class FlakyOps(FakeChargeOperations):
    """Real Fake plus a failure on the Nth statement call -- the vendor's 500 mid-pagination."""

    def __init__(self, fail_on_call: int | None = None):
        super().__init__()
        self.fail_on_call, self.n = fail_on_call, 0

    def list_balance_transactions(self, *, since, cursor=None):
        self.n += 1
        if self.n == self.fail_on_call:
            raise PaymentGatewayError("asaas", "boom: secret-body-token-123", status=500, code="upstream", retryable=True)
        return super().list_balance_transactions(since=since, cursor=cursor)


def test_fees_and_transfers_are_booked_once_and_rerun_is_idempotent(rh):
    acc = gw(rh.s)
    rh.ops.add_balance_transaction(bt("f1", "fee", -199, desc="Tarifa de saque"))
    rh.ops.add_balance_transaction(bt("t1", "transfer", -50000, desc="Repasse"))
    first = sync(rh, acc)
    d = first.json()["data"]
    assert first.status_code == 200 and (d["booked_fees"], d["booked_transfers"], d["review"]) == (1, 1, [])
    ledger = rh.s.rows("ledger")
    assert sorted((r["origin"], r["direction"], r["amount_cents"]) for r in ledger) == [("adjustment", "out", 199), ("transfer", "out", 50000)]
    assert all(r["transfer_group"] for r in ledger if r["origin"] == "transfer")
    second = sync(rh, acc).json()["data"]
    assert (second["booked_fees"], second["booked_transfers"], second["already_booked"]) == (0, 0, 2)
    assert len(rh.s.rows("ledger")) == 2
    again = sync(rh, acc, since="2026-10-01").json()["data"]  # an explicit wider window re-reads the same lines
    assert again["booked_fees"] == 0 and len(rh.s.rows("ledger")) == 2


def test_bridge_booked_charge_is_not_double_booked_and_unbooked_is_reviewed(rh):
    acc = gw(rh.s)
    booking = make_finance_booking("supabase", db=rh.db, cfg=CFG)
    booking.book_receivable(ORG_A, source="commerce_order", source_ref="o1", description="Pedido", counterparty_name="Ana",
                            counterparty_doc=None, amount_cents=10000, competence_month=date(2026, 10, 1), due_date=date(2026, 10, 3))
    booking.book_settlement(ORG_A, source="commerce_order", source_ref="o1", kind="payment", external_ref="pay_1",
                            amount_cents=10000, fee_cents=199, settled_on=date(2026, 10, 3))
    before = (len(rh.s.rows("ledger")), len(rh.s.rows("settlements")))
    rh.ops.add_balance_transaction(bt("c1", "charge", 10000, charge="pay_1"))
    rh.ops.add_balance_transaction(bt("f1", "fee", -199, charge="pay_1"))  # already the settlement's fee row
    rh.ops.add_balance_transaction(bt("c2", "charge", 5000, charge="pay_2"))
    rh.ops.add_balance_transaction(bt("cb", "chargeback", -2000, charge="pay_3"))
    d = sync(rh, acc).json()["data"]
    assert d["already_booked"] == 2 and d["booked_fees"] == 0
    assert {(r["id"], r["reason"]) for r in d["review"]} == {("c2", "sem_baixa_no_comercio"), ("cb", "chargeback_para_revisao")}
    assert (len(rh.s.rows("ledger")), len(rh.s.rows("settlements"))) == before


def test_fee_of_an_unsettled_charge_waits_instead_of_booking(rh):
    acc = gw(rh.s)
    rh.ops.add_balance_transaction(bt("f9", "fee", -100, charge="pay_late"))
    d = sync(rh, acc).json()["data"]
    assert d["booked_fees"] == 0 and d["review"][0]["reason"] == "tarifa_aguardando_baixa" and rh.s.rows("ledger") == []


def test_refund_booked_by_the_bridge_is_recognised(rh):
    acc = gw(rh.s)
    booking = make_finance_booking("supabase", db=rh.db, cfg=CFG)
    booking.book_receivable(ORG_A, source="commerce_order", source_ref="o1", description="P", counterparty_name=None,
                            counterparty_doc=None, amount_cents=10000, competence_month=date(2026, 10, 1), due_date=date(2026, 10, 3))
    for kind, ref, cents in (("payment", "pay_1", 10000), ("refund", "re_1", 3000)):
        booking.book_settlement(ORG_A, source="commerce_order", source_ref="o1", kind=kind, external_ref=ref,
                                amount_cents=cents, settled_on=date(2026, 10, 4))
    rh.ops.add_balance_transaction(bt("re_1", "refund", -3000, charge="pay_1"))
    d = sync(rh, acc).json()["data"]
    assert d["already_booked"] == 1 and d["review"] == []


def test_resume_from_saved_page_after_mid_pagination_failure(finance_schema_cache):
    ops = FlakyOps(fail_on_call=2)
    h = build_recon_harness(ops)
    acc = gw(h.s)
    for i in range(150):
        ops.add_balance_transaction(bt(f"f{i:03d}", "fee", -10, day=1 + i % 20))
    failed = sync(h, acc)
    assert failed.status_code == 502 and failed.json()["error"]["code"] == "sincronizacao_falhou"
    st = state(h, acc)
    assert json.loads(st["cursor"])["page"] == "100"  # page 1 was kept, page 2 is where we resume
    assert st["last_error"] and "secret-body-token-123" not in st["last_error"] and "boom" not in st["last_error"]
    assert "secret-body-token-123" not in failed.text
    assert len(h.s.rows("ledger")) == 100
    ok = sync(h, acc).json()["data"]
    assert ok["fetched"] == 50 and ok["booked_fees"] == 50
    assert ops.calls[-1][1][1] == "100"  # the resumed call carried the saved page cursor
    done = state(h, acc)
    assert done["last_error"] is None and done["last_synced_at"] and json.loads(done["cursor"])["page"] is None
    assert len(h.s.rows("ledger")) == 150
    assert sync(h, acc).json()["data"]["booked_fees"] == 0 and len(h.s.rows("ledger")) == 150


def test_page_budget_returns_202_and_continues_next_call(finance_schema_cache):
    h = build_recon_harness()
    acc = gw(h.s)
    for i in range(150):
        h.ops.add_balance_transaction(bt(f"f{i:03d}", "fee", -10))
    part = sync_gateway_account(h.s, h.ops, acc["id"], max_pages=1)
    assert part["status"] == "partial" and part["fetched"] == 100
    assert sync_gateway_account(h.s, h.ops, acc["id"])["fetched"] == 50
    assert len(h.s.rows("ledger")) == 150


def test_non_gateway_account_and_foreign_account_are_refused(rh):
    bank = mk_account(rh.s)
    r = sync(rh, bank)
    assert r.status_code == 422 and r.json()["error"]["code"] == "conta_nao_gateway"
    other = gw(rh.s_b)
    assert sync(rh, other).status_code == 404


def test_non_brl_line_goes_to_review(rh):
    from noctusai_lib.integrations.payments.types import BalanceTransaction, Money
    import datetime as dt

    acc = gw(rh.s)
    rh.ops.add_balance_transaction(BalanceTransaction("u1", dt.datetime(2026, 10, 3, tzinfo=dt.timezone.utc), "fee", Money(-100, "USD")))
    d = sync(rh, acc).json()["data"]
    assert d["review"][0]["reason"] == "moeda_nao_suportada" and rh.s.rows("ledger") == []


def test_job_syncs_every_orgs_gateway_account_and_isolates_failures(finance_schema_cache):
    h = build_recon_harness()
    a, b = gw(h.s), gw(h.s_b)
    h.ops.add_balance_transaction(bt("f1", "fee", -100))

    def ops_for(org_id, gateway):
        if org_id == h.s_b.org_id:
            return FlakyOps(fail_on_call=1)
        return h.ops

    summary = run_gateway_sync_all(h.db, CFG, ops_for)
    assert summary["accounts"] == 2 and summary["synced"] == 1 and summary["failed"] == 1
    assert len(h.s.rows("ledger")) == 1 and h.s_b.rows("ledger") == []
    assert state(h, a)["last_error"] is None
    assert h.s_b.rows("gateway_sync", eq={"account_id": b["id"]}, order_col="account_id")[0]["last_error"]
    assert run_gateway_sync_all(h.db, CFG, lambda o, g: None)["skipped"] == 2
