"""Gateway "paid" -> the receivable is settled, once. Everything else a gateway says is reported, never guessed."""
import pytest
from noctusai_lib.integrations.payments.webhook_events import make_fake_gateway_event
from noctusai_lib.testing import MockSupabaseClient

from app.services import billing_webhook as bw

ORG = "00000000-0000-0000-0000-000000000abc"
ENTRY = "e1000000-0000-4000-8000-000000000001"
REF = f"orbity:{ENTRY}"


def _event(kind="charge_paid", *, charge_id="pay_1", ref=REF, payment=None):
    ev = make_fake_gateway_event(gateway="asaas", kind=kind, event_id="evt_1", external_reference=ref, charge_id_at_gateway=charge_id)
    raw = {"event": "PAYMENT_RECEIVED", "payment": {"id": charge_id, "value": 1500.0, "netValue": 1498.01, "paymentDate": "2026-10-18",
                                                    "externalReference": ref, **(payment or {})}}
    return type(ev)(**{**ev.__dict__, "raw": raw})


def _db(*, entry_status="open", external_id="pay_1", with_charge=True):
    db = MockSupabaseClient(schema="orbity")
    db.set_table_data("billing_charges", [{
        "id": "ch-1", "org_id": ORG, "entry_id": ENTRY, "client_id": "c1", "external_ref": REF, "external_id": external_id,
        "generation_status": "generated"}] if with_charge else [])
    db.set_table_data("fin_entries", [{"id": ENTRY, "org_id": ORG, "direction": "receivable", "status": entry_status,
                                       "amount_cents": 150_000, "settled_cents": 0, "due_date": "2026-10-20", "competence_month": "2026-10-01"}])
    db.set_table_data("fin_accounts", [{"id": "acc-1", "org_id": ORG, "kind": "gateway", "gateway": "asaas", "name": "Asaas", "active": True}])
    db.set_table_data("fin_settlements", [])
    db.set_table_data("fin_ledger", [])
    db.set_rpc_data("fin_settle_entry_locked", {"status": "ok", "settlement": {
        "id": "st-1", "org_id": ORG, "entry_id": ENTRY, "account_id": "acc-1", "kind": "payment", "settled_on": "2026-10-18",
        "amount_cents": 150_000, "fee_cents": 199, "external_ref": "asaas:pay_1", "created_at": "2026-10-18T10:00:00+00:00"}})
    return db


def test_a_paid_charge_settles_its_receivable_with_the_gateway_fee():
    db = _db()
    out = bw.apply_event(db, ORG, _event())
    assert out["status"] == "settled" and out["entry_id"] == ENTRY
    (name, params), = db.rpc_calls
    assert name == "fin_settle_entry_locked" and params["p_entry_id"] == ENTRY
    row = params["p_row"]
    assert row["amount_cents"] == 150_000 and row["fee_cents"] == 199 and row["external_ref"] == "asaas:pay_1"
    assert row["account_id"] == "acc-1" and row["settled_on"] == "2026-10-18" and row["kind"] == "payment"


def test_the_charge_is_found_by_the_idempotency_reference_when_the_id_was_not_recorded_yet():
    db = _db(external_id=None)
    out = bw.apply_event(db, ORG, _event())
    assert out["status"] == "settled"
    assert db.table("billing_charges")._data[0]["external_id"] == "pay_1", "the webhook can beat our own bookkeeping: remember the id"


def test_a_charge_of_another_org_is_never_settled():
    assert bw.apply_event(_db(), "another-org", _event()) == {"status": "unknown_charge"}


def test_an_unknown_charge_is_reported_not_guessed():
    assert bw.apply_event(_db(with_charge=False), ORG, _event(ref="not-ours", charge_id="pay_x")) == {"status": "unknown_charge"}


@pytest.mark.parametrize("kind", ["charge_failed", "charge_refunded", "charge_partially_refunded", "charge_dispute", "charge_cancelled", "ignored"])
def test_everything_but_a_payment_needs_an_operator(kind):
    db = _db()
    assert bw.apply_event(db, ORG, _event(kind)) == {"status": "ignored", "kind": kind}
    assert db.rpc_calls == []


def test_a_payment_for_a_receivable_that_was_cancelled_is_flagged_not_booked():
    db = _db(entry_status="cancelled")
    assert bw.apply_event(db, ORG, _event()) == {"status": "ignored", "kind": "paid_but_cancelled"}
    assert db.rpc_calls == []
