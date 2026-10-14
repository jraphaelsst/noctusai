"""P4 money states: webhook matrix, refunds, reconciliation, disputes, finance bridge, regenerate, jobs."""
from __future__ import annotations

import threading
from dataclasses import replace
from datetime import timedelta

import pytest

from noctusai_lib.domain.commerce import (
    CommerceError,
    FakeCheckoutGateway,
    FulfillmentType,
    MoneyDeps,
    NoopFulfillment,
    make_fulfillment_registry,
    orders,
    refunds,
)
from noctusai_lib.domain.commerce import jobs as jobs_svc
from noctusai_lib.domain.commerce import regenerate as regen
from noctusai_lib.domain.commerce.order_charges import list_charges
from noctusai_lib.domain.commerce.webhook import IGNORED, PROCESSED, StaleGatewayRead, handle_event
from noctusai_lib.domain.finance.booking import FakeFinanceBooking
from noctusai_lib.domain.payments import FakeEventInbox
from noctusai_lib.integrations.email import FakeEmailSender
from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.primitives.exceptions import NotFoundError
from noctusai_lib.integrations.payments.types import GatewayRefund, Money
from noctusai_lib.integrations.payments.webhook_events import make_fake_gateway_event
from noctusai_lib.domain.commerce._common import now

from .conftest import CFG, ORG_A, ORG_B, USER_ID, money_deps, pay, place_order, run


class Hooks(NoopFulfillment):
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    def on_paid(self, order, items):
        self.calls.append(("paid", order["status"]))

    def on_paused(self, order, items):
        self.calls.append(("paused", order["status"]))

    def on_resumed(self, order, items):
        self.calls.append(("resumed", order["status"]))

    def on_revoked(self, order, items):
        self.calls.append(("revoked", order["status"]))

    def on_expired(self, order, items):
        self.calls.append(("expired", order["status"]))


class World:
    def __init__(self, db, **body):
        self.db = db
        self.gw = FakeCheckoutGateway()
        self.hooks = Hooks()
        self.fin = FakeFinanceBooking()
        self.mail = FakeEmailSender()
        self.paid_hook, self.revoked_hook = [], []
        self.reg = make_fulfillment_registry({ft: self.hooks for ft in FulfillmentType})
        self.inbox = FakeEventInbox()
        self.order = dict(place_order(db, self.gw, **body))
        self.n = 0

    @property
    def deps(self) -> MoneyDeps:
        return money_deps(
            self.gw, fulfillment=self.reg, finance=self.fin, email=self.mail,
            on_paid_hooks=(lambda db, order: self.paid_hook.append(order["id"]),),
            on_revoked_hooks=(lambda db, order, reason: self.revoked_hook.append(reason),),
        )

    def fresh(self) -> dict:
        return orders.get_order(self.db, ORG_A, self.order["id"])

    def event(self, kind, *, detail=None, charge_id=None, ref=True):
        self.n += 1
        return make_fake_gateway_event(
            gateway="asaas", kind=kind, event_id=f"e{self.n}", detail=detail,
            external_reference=self.order["id"] if ref else None,
            charge_id_at_gateway=charge_id or self.fresh()["gateway_charge_id"],
        )

    def send(self, kind, **kw):
        return run(handle_event(self.db, ORG_A, self.event(kind, **kw), inbox=self.inbox, deps=self.deps))


@pytest.fixture
def w(db):
    return World(db)


# ─── webhook matrix ──────────────────────────────────────────────────────────


class TestWebhookMatrix:
    def test_confirmed_pays_and_books_the_receivable_but_not_the_cash(self, w):
        pay(w.gw, w.order, confirmed_only=True)
        assert w.send("charge_paid", detail="confirmed") == PROCESSED
        assert w.fresh()["status"] == "paid"
        assert len(w.fin.entries) == 1 and w.fin.settlements == {}
        entry = next(iter(w.fin.entries.values()))
        assert entry["amount_cents"] == 10000 and entry["source_ref"] == w.order["id"]
        assert w.hooks.calls == [("paid", "paid")] and w.paid_hook == [w.order["id"]]

    def test_received_books_the_payment_settlement_with_net_and_fee(self, w):
        pay(w.gw, w.order, fee_cents=199)
        w.send("charge_paid", detail="received")
        (key, st), = w.fin.settlements.items()
        assert key[1] == "payment" and key[2] == w.order["gateway_charge_id"]
        assert (st["amount_cents"], st["fee_cents"]) == (10000, 199)

    def test_confirmed_then_received_pays_once_and_books_cash_once(self, w):
        pay(w.gw, w.order, confirmed_only=True)
        w.send("charge_paid", detail="confirmed")
        pay(w.gw, w.order, fee_cents=100)
        w.send("charge_paid", detail="received")
        w.send("charge_paid", detail="received")  # redelivery under a new event id: idempotent
        assert len(w.fin.settlements) == 1 and len(w.fin.entries) == 1
        assert [e["to_status"] for e in orders.list_events(w.db, ORG_A, w.order["id"])].count("paid") == 1

    def test_a_webhook_claiming_paid_while_the_gateway_reads_pending_is_ignored(self, w):
        assert w.send("charge_paid", detail="confirmed") == IGNORED
        assert w.fresh()["status"] == "pending_payment"

    def test_the_body_is_never_trusted_for_money(self, w):
        # raw says refunded/chargeback, kind/detail say paid, the read says received: paid wins.
        pay(w.gw, w.order)
        ev = make_fake_gateway_event(
            gateway="asaas", kind="charge_paid", event_id="x", external_reference=w.order["id"],
            charge_id_at_gateway=w.order["gateway_charge_id"], detail="received", raw={"event": "PAYMENT_CHARGEBACK_REQUESTED"},
        )
        run(handle_event(w.db, ORG_A, ev, inbox=w.inbox, deps=w.deps))
        assert w.fresh()["status"] == "paid"

    def test_overdue_expires_and_fires_on_expired(self, w):
        assert w.send("charge_failed", detail="overdue") == PROCESSED
        assert w.fresh()["status"] == "expired" and ("expired", "expired") in w.hooks.calls
        assert list_charges(w.db, ORG_A, w.order["id"])[0]["status"] == "cancelled"  # expired AND voided at the gateway

    def test_partial_refund_from_the_gateway_creates_a_gateway_row(self, w):
        pay(w.gw, w.order)
        w.send("charge_paid", detail="received")
        w.gw.charges.refund_charge(w.order["gateway_charge_id"], amount=Money(3000), description="painel")
        assert w.send("charge_partially_refunded", detail="partial") == PROCESSED
        o = w.fresh()
        assert o["status"] == "partially_refunded"
        (r,) = refunds.list_refunds(w.db, ORG_A, w.order["id"])
        assert (r["amount_cents"], r["status"], r["requested_by"], r["reason"]) == (3000, "done", None, "gateway")
        assert ("refund", r["id"]) in [(k[1], v["external_ref"]) for k, v in w.fin.settlements.items()]

    def test_full_refund_revokes(self, w):
        pay(w.gw, w.order)
        w.send("charge_paid", detail="received")
        w.gw.charges.refund_charge(w.order["gateway_charge_id"], amount=None, description="painel")
        w.send("charge_refunded")
        assert w.fresh()["status"] == "refunded" and ("revoked", "refunded") in w.hooks.calls
        assert w.revoked_hook == ["refunded"]

    def test_partial_then_rest_ends_refunded(self, w):
        pay(w.gw, w.order)
        w.send("charge_paid", detail="received")
        w.gw.charges.refund_charge(w.order["gateway_charge_id"], amount=Money(3000), description="a")
        w.send("charge_partially_refunded", detail="partial")
        w.gw.charges.refund_charge(w.order["gateway_charge_id"], amount=Money(7000), description="b")
        w.send("charge_refunded")
        assert w.fresh()["status"] == "refunded"
        assert len(refunds.list_refunds(w.db, ORG_A, w.order["id"])) == 2


class TestDisputes:
    def _paid(self, w):
        pay(w.gw, w.order)
        w.send("charge_paid", detail="received")

    def test_opened_pauses_alerts_and_won_resumes(self, w):
        self._paid(w)
        w.gw.charges.open_dispute(w.order["gateway_charge_id"])
        assert w.send("charge_refunded", detail="chargeback_opened") == PROCESSED
        assert w.fresh()["status"] == "disputed" and ("paused", "disputed") in w.hooks.calls
        assert len(w.mail.sent) == 1 and w.mail.sent[0].to == ["contato@loja.test"]
        assert "Contestação" in w.mail.sent[0].subject
        w.gw.charges.win_dispute(w.order["gateway_charge_id"])
        w.send("charge_dispute", detail="won")
        assert w.fresh()["status"] == "paid" and ("resumed", "paid") in w.hooks.calls

    def test_won_after_a_partial_refund_returns_to_partially_refunded(self, w):
        self._paid(w)
        w.gw.charges.refund_charge(w.order["gateway_charge_id"], amount=Money(2000), description="x")
        w.send("charge_partially_refunded", detail="partial")
        w.gw.charges.open_dispute(w.order["gateway_charge_id"])
        w.send("charge_refunded", detail="chargeback_opened")
        assert w.fresh()["status"] == "disputed"
        w.gw.charges.win_dispute(w.order["gateway_charge_id"])
        w.send("charge_dispute", detail="won")
        assert w.fresh()["status"] == "partially_refunded"

    def test_a_loss_is_only_visible_to_the_poll_job(self, w):
        self._paid(w)
        w.gw.charges.open_dispute(w.order["gateway_charge_id"])
        w.send("charge_refunded", detail="chargeback_opened")
        w.gw.charges.lose_dispute(w.order["gateway_charge_id"])  # no webhook for this on Asaas (W3)
        assert w.fresh()["status"] == "disputed"
        assert run(jobs_svc.commerce_dispute_poll(w.db, deps=w.deps)) == 1
        assert w.fresh()["status"] == "chargeback"
        assert ("revoked", "chargeback") in w.hooks.calls and w.revoked_hook == ["chargeback"]
        cb = [v for k, v in w.fin.settlements.items() if k[2].startswith("chargeback:")]
        assert cb and cb[0]["amount_cents"] == 10000
        run(jobs_svc.commerce_dispute_poll(w.db, deps=w.deps))  # a terminal order is no longer polled; nothing doubles
        assert len([k for k in w.fin.settlements if k[2].startswith("chargeback:")]) == 1

    def test_poll_skips_a_still_open_dispute(self, w):
        self._paid(w)
        w.gw.charges.open_dispute(w.order["gateway_charge_id"])
        w.send("charge_refunded", detail="chargeback_opened")
        run(jobs_svc.commerce_dispute_poll(w.db, deps=w.deps))
        assert w.fresh()["status"] == "disputed"

    def test_a_chargeback_event_the_read_does_not_confirm_is_retried_not_applied(self, w):
        self._paid(w)
        with pytest.raises(StaleGatewayRead):
            w.send("charge_refunded", detail="chargeback_opened")  # the gateway still reads `received`
        assert w.inbox.releases and w.fresh()["status"] == "paid"


class TestSupersededAttempts:
    def _regenerate(self, w):
        w.db.table("commerce_orders").update({"status": "expired"}).eq("id", w.order["id"]).execute()
        w.db.table("commerce_orders").update({"last_charge_attempt_at": (now() - timedelta(minutes=5)).isoformat()}).eq("id", w.order["id"]).execute()
        out = regen.regenerate_payment(
            w.db, ORG_A, CFG, w.gw, w.order["token"], payment_method="pix", installments=None, order_url_for=lambda t: f"https://x/{t}"
        )
        w.gw.sync_charges()
        return out

    def test_old_pix_paid_after_regeneration_makes_it_the_paying_attempt(self, w):
        old = w.order["gateway_charge_id"]
        self._regenerate(w)
        new = w.fresh()["gateway_charge_id"]
        assert new != old
        pay(w.gw, {"gateway_charge_id": old})
        w.send("charge_paid", detail="received", charge_id=old)
        o = w.fresh()
        assert o["status"] == "paid" and o["gateway_charge_id"] == old
        assert w.gw.charges.charges[new].status == "cancelled"  # the live newer charge is voided

    def test_extra_payment_on_a_superseded_attempt_of_a_paid_order_alerts_staff(self, w):
        old = w.order["gateway_charge_id"]
        self._regenerate(w)
        new = w.fresh()["gateway_charge_id"]
        pay(w.gw, {"gateway_charge_id": new})
        w.send("charge_paid", detail="received", charge_id=new)
        assert w.fresh()["status"] == "paid"
        pay(w.gw, {"gateway_charge_id": old})
        assert w.send("charge_paid", detail="received", charge_id=old) == PROCESSED
        assert "duplicado" in w.mail.sent[-1].subject
        assert any("EXTRA" in e["reason"] for e in orders.list_events(w.db, ORG_A, w.order["id"]))
        assert len(w.fin.settlements) == 1  # the extra cash is NOT silently booked against the order

    def test_payment_for_a_cancelled_order_is_ignored_and_alerted(self, w):
        orders.cancel_order(w.db, ORG_A, w.order["id"])
        pay(w.gw, w.order)
        assert w.send("charge_paid", detail="received") == IGNORED
        assert w.fresh()["status"] == "cancelled" and w.mail.sent


# ─── refunds ─────────────────────────────────────────────────────────────────


def refund(w, **kw):
    kw.setdefault("amount_cents", None)
    kw.setdefault("reason", "cliente pediu")
    return run(refunds.create_refund(w.db, ORG_A, w.deps, w.order["id"], requested_by=USER_ID, **kw))


class TestRefundService:
    @pytest.fixture
    def paid(self, w):
        pay(w.gw, w.order)
        w.send("charge_paid", detail="received")
        return w

    def test_partial_then_full(self, paid):
        r = refund(paid, amount_cents=4000)
        assert r["status"] == "done" and paid.fresh()["status"] == "partially_refunded"
        r2 = refund(paid)  # the rest
        assert r2["amount_cents"] == 6000 and paid.fresh()["status"] == "refunded"
        assert ("revoked", "refunded") in paid.hooks.calls
        refs = sorted(v["external_ref"] for k, v in paid.fin.settlements.items() if k[1] == "refund")
        assert refs == sorted([r["id"], r2["id"]])

    def test_above_the_refundable_balance_is_422(self, paid):
        refund(paid, amount_cents=4000)
        with pytest.raises(CommerceError) as exc:
            refund(paid, amount_cents=6001)
        assert exc.value.code == "valor_excede_saldo" and exc.value.status_code == 422

    def test_unpaid_order_is_409(self, w):
        with pytest.raises(CommerceError) as exc:
            refund(w)
        assert exc.value.code == "pedido_nao_reembolsavel" and exc.value.status_code == 409

    def test_idempotency_key_replays(self, paid):
        a = refund(paid, amount_cents=1000, idempotency_key="k1")
        b = refund(paid, amount_cents=1000, idempotency_key="k1")
        assert a["id"] == b["id"] and len(refunds.list_refunds(paid.db, ORG_A, paid.order["id"])) == 1
        assert [c for c in paid.gw.charges.calls if c[0] == "refund_charge"].__len__() == 1

    def test_gateway_error_marks_failed_and_is_502(self, paid):
        def boom(*a, **k):
            raise PaymentGatewayError("asaas", "nope", status=400, code="boom")

        paid.gw.charges.refund_charge = boom
        with pytest.raises(CommerceError) as exc:
            refund(paid, amount_cents=1000)
        assert exc.value.code == "estorno_falhou" and exc.value.status_code == 502
        (r,) = refunds.list_refunds(paid.db, ORG_A, paid.order["id"])
        assert r["status"] == "failed"
        del paid.gw.charges.refund_charge  # a failed refund does not block the next one
        assert refund(paid, amount_cents=1000)["status"] == "done"

    def test_two_concurrent_refunds_cannot_both_win(self, paid):
        """The second one waits on the order lock (modelled by the RPC mirror) and is then refused or sized to the rest."""
        results, errors = [], []
        gate = threading.Barrier(2)
        real = paid.gw.charges.refund_charge

        def slow(*a, **k):
            import time

            time.sleep(0.05)  # keep the first refund `requested` while the second arrives
            return real(*a, **k)

        paid.gw.charges.refund_charge = slow

        def go():
            gate.wait()
            try:
                results.append(refund(paid, amount_cents=7000))
            except CommerceError as exc:
                errors.append(exc.code)

        threads = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        total = sum(r["amount_cents"] for r in refunds.list_refunds(paid.db, ORG_A, paid.order["id"]) if r["status"] == "done")
        assert len(results) == 1 and total == 7000
        assert errors in (["estorno_em_andamento"], ["valor_excede_saldo"])

    def test_a_requested_refund_blocks_a_second(self, paid):
        paid.db.table("commerce_refunds").insert({
            "id": "33333333-3333-4333-8333-333333333333", "org_id": ORG_A, "order_id": paid.order["id"],
            "charge_id": list_charges(paid.db, ORG_A, paid.order["id"])[0]["id"], "amount_cents": 100, "reason": "", "status": "requested",
            "requested_by": USER_ID, "created_at": now().isoformat(),
        }).execute()
        paid.gw.charges.charges[paid.order["gateway_charge_id"]] = replace(
            paid.gw.charges.charges[paid.order["gateway_charge_id"]],
            refunds=[GatewayRefund(None, paid.order["gateway_charge_id"], Money(100), "pending", now())], refunded=Money(100),
        )
        with pytest.raises(CommerceError) as exc:
            refund(paid, amount_cents=100)
        assert exc.value.code == "estorno_em_andamento"


def installment_world(db, *, installments=3, price_cents=60000, parcelas=True):
    """A paid 3x card order whose parcelamento the fake gateway holds as three parcelas of equal value."""
    gw = FakeCheckoutGateway()
    world = World.__new__(World)
    world.db, world.gw, world.hooks = db, gw, Hooks()
    world.fin, world.mail = FakeFinanceBooking(), FakeEmailSender()
    world.paid_hook, world.revoked_hook = [], []
    world.reg, world.inbox, world.n = make_fulfillment_registry(), FakeEventInbox(), 0
    world.order = dict(place_order(db, gw, payment_method="credit_card", installments=installments, price_cents=price_cents))
    first = gw.charges.charges[world.order["gateway_charge_id"]]
    inst = first.raw["installment"]
    if parcelas:  # split the single fake charge into real parcelas (each its own payment id)
        each = first.amount.amount_cents // installments
        gw.charges.charges[first.id_at_gateway] = replace(first, amount=Money(each))
        for n in range(2, installments + 1):
            gw.charges.add_charge(f"pay_parcela_{n}", amount=Money(each), status="pending", method="credit_card",
                                  installment_count=installments, external_reference=world.order["id"], installment_id=inst)
        for pid in [first.id_at_gateway, *(f"pay_parcela_{n}" for n in range(2, installments + 1))]:
            gw.charges.mark_paid(pid, confirmed_only=True)
    else:
        gw.charges.mark_paid(first.id_at_gateway, confirmed_only=True)
    world.send("charge_paid", detail="confirmed")
    return world


class TestInstallmentRefunds:
    """D32: full AND partial refunds, with history, work for a card order paid in installments."""

    def test_the_gateway_installment_id_is_kept_at_checkout(self, db):
        w = installment_world(db)
        (row,) = list_charges(db, ORG_A, w.order["id"])
        assert row["gateway_installment_id"] == w.gw.charges.charges[w.order["gateway_charge_id"]].raw["installment"]

    def test_partial_then_full_refund_spread_over_the_parcelas(self, db):
        w = installment_world(db)
        r = refund(w, amount_cents=25000)  # more than one parcela (20000)
        assert r["status"] == "done" and r["amount_cents"] == 25000 and w.fresh()["status"] == "partially_refunded"
        r2 = refund(w)  # the rest
        assert r2["amount_cents"] == 35000 and w.fresh()["status"] == "refunded"
        assert w.revoked_hook == ["refunded"]
        assert [c[0] for c in w.gw.charges.calls if c[0] in ("refund_charge", "refund_installment")] == ["refund_installment"] * 2
        rows = refunds.list_refunds(db, ORG_A, w.order["id"])
        assert [x["status"] for x in rows] == ["done", "done"] and sum(x["amount_cents"] for x in rows) == 60000
        # finance reversal is booked once per refund, same as a single-charge order
        assert sorted(v["external_ref"] for k, v in w.fin.settlements.items() if k[1] == "refund") == sorted(x["id"] for x in rows)

    def test_a_single_parcela_gateway_also_works(self, db):
        w = installment_world(db, parcelas=False)
        assert refund(w)["amount_cents"] == 60000 and w.fresh()["status"] == "refunded"

    def test_above_the_refundable_balance_is_422_and_nothing_goes_out(self, db):
        w = installment_world(db)
        refund(w, amount_cents=50000)
        with pytest.raises(CommerceError) as exc:
            refund(w, amount_cents=10001)
        assert exc.value.code == "valor_excede_saldo" and exc.value.status_code == 422
        assert [c for c in w.gw.charges.calls if c[0] == "refund_installment"].__len__() == 1

    def test_idempotency_key_replays(self, db):
        w = installment_world(db)
        a = refund(w, amount_cents=10000, idempotency_key="k1")
        b = refund(w, amount_cents=10000, idempotency_key="k1")
        assert a["id"] == b["id"] and len(refunds.list_refunds(db, ORG_A, w.order["id"])) == 1
        assert [c for c in w.gw.charges.calls if c[0] == "refund_installment"].__len__() == 1

    def test_gateway_refusal_marks_failed_and_does_not_block_the_next(self, db):
        w = installment_world(db)

        def boom(*a, **k):
            raise PaymentGatewayError("asaas", "nope", status=400, code="boom")

        w.gw.charges.refund_installment = boom
        with pytest.raises(CommerceError) as exc:
            refund(w, amount_cents=10000)
        assert exc.value.code == "estorno_falhou" and exc.value.status_code == 502
        assert [x["status"] for x in refunds.list_refunds(db, ORG_A, w.order["id"])] == ["failed"]
        del w.gw.charges.refund_installment
        assert refund(w, amount_cents=10000)["status"] == "done"

    def test_the_installment_id_is_resolved_from_the_gateway_when_not_stored(self, db):
        w = installment_world(db)
        db.table("commerce_order_charges").update({"gateway_installment_id": None}).eq("org_id", ORG_A).execute()
        assert refund(w, amount_cents=10000)["status"] == "done"
        (row,) = list_charges(db, ORG_A, w.order["id"])
        assert row["gateway_installment_id"] == w.gw.charges.charges[w.order["gateway_charge_id"]].raw["installment"]

    def test_a_panel_refund_on_a_later_parcela_event_converges_the_order(self, db):
        """Webhook on parcela 2 (a refund made in the gateway panel) reads the whole parcelamento and books it."""
        w = installment_world(db)
        w.gw.charges.refund_installment(w.gw.charges.charges[w.order["gateway_charge_id"]].raw["installment"], amount=Money(30000), description="painel")
        assert w.send("charge_partially_refunded", charge_id="pay_parcela_2") == PROCESSED
        assert w.fresh()["status"] == "partially_refunded"
        (r,) = refunds.list_refunds(db, ORG_A, w.order["id"])
        assert r["amount_cents"] == 30000 and r["reason"] == "gateway" and r["status"] == "done"
        w.gw.charges.refund_installment(w.gw.charges.charges[w.order["gateway_charge_id"]].raw["installment"], amount=None, description="painel")
        assert w.send("charge_refunded", charge_id="pay_parcela_3") == PROCESSED
        assert w.fresh()["status"] == "refunded"
        assert sum(x["amount_cents"] for x in refunds.list_refunds(db, ORG_A, w.order["id"])) == 60000

    def test_a_refund_event_naming_a_foreign_parcela_is_not_applied(self, db):
        w = installment_world(db)
        w.gw.charges.add_charge("pay_of_order_b", amount=Money(20000), status="received", method="credit_card",
                                installment_count=3, external_reference="99999999-9999-4999-8999-999999999999")
        assert w.send("charge_refunded", charge_id="pay_of_order_b") == IGNORED
        assert w.fresh()["status"] == "paid" and refunds.list_refunds(db, ORG_A, w.order["id"]) == []

    def test_org_isolation(self, db):
        w = installment_world(db)
        with pytest.raises(NotFoundError):
            run(refunds.create_refund(db, ORG_B, w.deps, w.order["id"], amount_cents=1000, reason="x", requested_by=USER_ID))
        assert refunds.list_refunds(db, ORG_A, w.order["id"]) == []


class TestReconciliation:
    """W2: Asaas refunds have no id -- matched by amount + timestamp."""

    @pytest.fixture
    def paid(self, w):
        pay(w.gw, w.order)
        w.send("charge_paid", detail="received")
        return w

    def test_our_refund_and_the_webhook_for_it_do_not_double_count(self, paid):
        refund(paid, amount_cents=3000)
        paid.send("charge_partially_refunded", detail="partial")
        rows = refunds.list_refunds(paid.db, ORG_A, paid.order["id"])
        assert len(rows) == 1 and rows[0]["requested_by"] == USER_ID

    def test_idless_gateway_refund_matches_our_requested_row_by_amount(self, paid):
        row = paid.db.table("commerce_refunds").insert({
            "id": "44444444-4444-4444-8444-444444444444", "org_id": ORG_A, "order_id": paid.order["id"],
            "charge_id": list_charges(paid.db, ORG_A, paid.order["id"])[0]["id"], "amount_cents": 2500, "reason": "x", "status": "requested",
            "requested_by": USER_ID, "created_at": now().isoformat(),
        }).execute().data[0]
        paid.gw.charges.refund_charge(paid.order["gateway_charge_id"], amount=Money(2500), description="x")
        paid.gw.charges.charges[paid.order["gateway_charge_id"]].refunds[0].__class__  # (frozen; id stays None as in Asaas)
        paid.send("charge_partially_refunded", detail="partial")
        rows = refunds.list_refunds(paid.db, ORG_A, paid.order["id"])
        assert [(r["id"], r["status"]) for r in rows] == [(row["id"], "done")]

    def test_a_requested_row_the_gateway_never_confirms_goes_stale(self, paid):
        old = (now() - timedelta(hours=1)).isoformat()
        paid.db.table("commerce_refunds").insert({
            "id": "55555555-5555-4555-8555-555555555555", "org_id": ORG_A, "order_id": paid.order["id"],
            "charge_id": list_charges(paid.db, ORG_A, paid.order["id"])[0]["id"], "amount_cents": 900, "reason": "x", "status": "requested",
            "requested_by": USER_ID, "created_at": old,
        }).execute()
        paid.send("charge_partially_refunded", detail="partial")
        (r,) = refunds.list_refunds(paid.db, ORG_A, paid.order["id"])
        assert r["status"] == "failed"


# ─── regenerate ──────────────────────────────────────────────────────────────


def regen_call(w, *, method="pix", installments=None):
    return regen.regenerate_payment(
        w.db, ORG_A, CFG, w.gw, w.order["token"], payment_method=method, installments=installments, order_url_for=lambda t: f"https://x/{t}",
    )


def age(w, minutes=5):
    w.db.table("commerce_orders").update({"last_charge_attempt_at": (now() - timedelta(minutes=minutes)).isoformat()}).eq("id", w.order["id"]).execute()


class TestRegenerate:
    def test_same_method_on_a_live_charge_returns_the_existing_one(self, w):
        out = regen_call(w)
        assert out["checkout_url"] == w.order["checkout_url"] and w.fresh()["charge_attempts"] == 1

    def test_method_switch_creates_an_attempt_without_a_status_change(self, w):
        age(w)
        out = regen_call(w, method="boleto")
        o = w.fresh()
        assert o["status"] == "pending_payment" and o["payment_method"] == "boleto" and o["charge_attempts"] == 2
        assert out["checkout_url"] == o["checkout_url"] != w.order["checkout_url"]
        rows = list_charges(w.db, ORG_A, w.order["id"])
        assert [r["status"] for r in rows] == ["cancelled", "pending"]
        assert w.gw.charges.charges[w.order["gateway_charge_id"]].status == "cancelled"

    def test_expired_order_returns_to_pending_payment(self, w):
        w.send("charge_failed", detail="overdue")
        age(w)
        regen_call(w)
        assert w.fresh()["status"] == "pending_payment"

    def test_failed_order_without_any_charge_can_be_paid(self, db):
        gw = FakeCheckoutGateway()
        gw.checkout.create_checkout = lambda req: (_ for _ in ()).throw(PaymentGatewayError("asaas", "x", status=500))
        with pytest.raises(CommerceError):
            place_order(db, gw)
        order = db.table("commerce_orders").select("*").execute().data[0]
        assert order["status"] == "failed"
        del gw.checkout.create_checkout
        world = World.__new__(World)
        world.db, world.gw, world.order = db, gw, order
        age(world)
        out = regen_call(world)
        assert out["status"] == "pending_payment" and out["checkout_url"]

    def test_spacing_and_cap(self, w):
        with pytest.raises(CommerceError) as exc:
            regen_call(w, method="boleto")  # < 60 s after the first attempt
        assert exc.value.code == "muitas_tentativas" and exc.value.status_code == 429
        for method in ("boleto", "pix", "boleto", "pix"):
            age(w)
            regen_call(w, method=method)
        assert w.fresh()["charge_attempts"] == 5
        age(w)
        with pytest.raises(CommerceError) as exc:
            regen_call(w, method="boleto")
        assert exc.value.code == "muitas_tentativas"

    def test_two_concurrent_calls_cannot_both_create_a_charge(self, w):
        age(w)
        outcomes = []
        gate = threading.Barrier(2)

        def go():
            gate.wait()
            try:
                regen_call(w, method="boleto")
                outcomes.append("ok")
            except CommerceError as exc:
                outcomes.append(exc.code)

        ts = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert "ok" in outcomes
        # Whatever the interleaving, ONE new charge exists: the loser either re-used it or was refused.
        assert w.fresh()["charge_attempts"] == 2 and len(list_charges(w.db, ORG_A, w.order["id"])) == 2

    def test_the_claim_is_a_single_conditional_update(self, w):
        """Two callers holding the SAME stale `(status, charge_attempts)`: exactly one claim lands."""
        age(w)
        order = w.fresh()
        claimed = regen._claim(w.db, ORG_A, order, 1)
        assert claimed["charge_attempts"] == 2
        with pytest.raises(CommerceError) as exc:
            regen._claim(w.db, ORG_A, order, 1)  # same stale view: the row has moved on
        assert exc.value.code in ("pedido_alterado", "muitas_tentativas")

    def test_a_failed_cancel_refuses_and_creates_no_second_charge(self, w):
        age(w)

        def refuse(cid):
            raise PaymentGatewayError("asaas", "cannot", status=400, code="x")

        w.gw.charges.cancel_charge = refuse
        with pytest.raises(CommerceError) as exc:
            regen_call(w, method="boleto")
        assert exc.value.code == "cobranca_anterior_ativa" and exc.value.status_code == 409
        assert len(w.gw.checkout.sessions) == 1
        assert w.fresh()["gateway_charge_id"] == w.order["gateway_charge_id"]

    def test_a_paid_previous_charge_is_never_cancelled(self, w):
        pay(w.gw, w.order)
        age(w)
        with pytest.raises(CommerceError) as exc:
            regen_call(w, method="boleto")
        assert exc.value.code == "cobranca_anterior_ativa"
        assert not [c for c in w.gw.charges.calls if c[0] == "cancel_charge"]

    def test_closed_orders_are_not_payable(self, w):
        pay(w.gw, w.order)
        w.send("charge_paid", detail="received")
        with pytest.raises(CommerceError) as exc:
            regen_call(w)
        assert exc.value.code == "pedido_nao_pagavel" and exc.value.status_code == 409

    def test_installments_validated_and_quoted(self, w):
        age(w)
        with pytest.raises(CommerceError) as exc:
            regen_call(w, method="pix", installments=3)
        assert exc.value.code == "parcelamento_invalido"
        regen_call(w, method="credit_card", installments=6)
        charges = list_charges(w.db, ORG_A, w.order["id"])
        assert charges[-1]["installment_count"] == 6 and charges[-1]["amount_cents"] > 10000


# ─── jobs ────────────────────────────────────────────────────────────────────


class TestJobs:
    def test_expire_orders_is_idempotent_and_fires_on_expired(self, w):
        w.db.table("commerce_orders").update({"expires_at": (now() - timedelta(minutes=1)).isoformat()}).eq("id", w.order["id"]).execute()
        assert jobs_svc.commerce_expire_orders(w.db, fulfillment=w.reg) == 1
        assert jobs_svc.commerce_expire_orders(w.db, fulfillment=w.reg) == 0
        assert w.fresh()["status"] == "expired" and ("expired", "expired") in w.hooks.calls
        # the overdue webhook arriving afterwards is a no-op: first wins
        assert w.send("charge_failed", detail="overdue") == IGNORED

    def test_expire_leaves_unexpired_orders_alone(self, w):
        assert jobs_svc.commerce_expire_orders(w.db, fulfillment=w.reg) == 0

    def _host(self, w):
        w.db.table("commerce_storefront_hosts").insert({"hostname": "loja-a.test", "org_id": ORG_A, "is_primary": True, "created_at": now().isoformat()}).execute()

    def test_reminders_before_and_after_expiry_once_each_with_a_signed_link(self, w):
        self._host(w)
        w.db.table("commerce_orders").update({"expires_at": (now() + timedelta(hours=10)).isoformat()}).eq("id", w.order["id"]).execute()
        send = lambda at=None: run(jobs_svc.commerce_expiry_reminders(w.db, cfg=CFG, email=w.mail, link_secret="s", at=at))  # noqa: E731
        assert send() == 1 and send() == 0
        mail = w.mail.sent[0]
        assert w.order["token"] not in mail.text  # never the bare order token
        assert "https://loja-a.test/pedido/" in mail.text and "48 horas" in mail.text  # ORDER-scoped, not the all-orders link
        rows = w.db.table("commerce_order_reminders").select("*").execute().data
        assert [r["kind"] for r in rows] == ["before_expiry"]
        # the order expires; a day later the second kind goes out (the hourly spacing has passed)
        w.db.table("commerce_orders").update({"status": "expired", "expires_at": (now() - timedelta(hours=25)).isoformat()}).eq("id", w.order["id"]).execute()
        assert send(now() + timedelta(hours=2)) == 1 and send(now() + timedelta(hours=2)) == 0
        assert sorted(r["kind"] for r in w.db.table("commerce_order_reminders").select("*").execute().data) == ["after_expiry", "before_expiry"]

    def test_at_most_one_mail_per_recipient_per_hour(self, w):
        self._host(w)
        w.db.table("commerce_orders").update({"expires_at": (now() + timedelta(hours=10)).isoformat()}).eq("id", w.order["id"]).execute()
        w.db.table("commerce_order_reminders").insert({
            "order_id": "66666666-6666-4666-8666-666666666666", "kind": "before_expiry", "org_id": ORG_A, "sent_at": now().isoformat(),
        }).execute()
        w.db.table("commerce_orders").insert({**w.order, "id": "66666666-6666-4666-8666-666666666666", "token": "other"}).execute()
        assert run(jobs_svc.commerce_expiry_reminders(w.db, cfg=CFG, email=w.mail, link_secret="s")) == 0  # same buyer mailed < 1 h ago

    def test_a_failed_send_releases_the_claim_for_the_next_tick(self, w):
        self._host(w)
        w.db.table("commerce_orders").update({"expires_at": (now() + timedelta(hours=10)).isoformat()}).eq("id", w.order["id"]).execute()

        class Down:
            async def send(self, email):
                raise RuntimeError("smtp down")

        assert run(jobs_svc.commerce_expiry_reminders(w.db, cfg=CFG, email=Down(), link_secret="s")) == 0
        assert w.db.table("commerce_order_reminders").select("*").execute().data == []
        assert run(jobs_svc.commerce_expiry_reminders(w.db, cfg=CFG, email=w.mail, link_secret="s")) == 1

    def test_fiscal_purge_job_delegates(self, w):
        assert jobs_svc.commerce_fiscal_purge(w.db) == 0

    def test_register_commerce_jobs(self, w):
        calls = []
        names = jobs_svc.register_commerce_jobs(
            lambda name, fn, **kw: calls.append((name, kw)), cfg=CFG, get_db=lambda: w.db, get_deps=lambda: w.deps, get_link_secret=lambda: "s",
        )
        assert names == tuple(n for n, _ in calls)
        assert dict(calls)["commerce_dispute_poll"] == {"hours": 6}
        assert dict(calls)["commerce_fiscal_purge"] == {"cron": "30 3 * * *"}


class TestExpiredNeverLeavesALiveCharge:
    """Security blocker: expired -> regenerate must not leave two payable charges (the gateway keeps an overdue one payable)."""

    def _legacy_expired(self, w):
        """An order expired the old way: row + order `expired`, but the gateway charge was never cancelled."""
        w.db.table("commerce_orders").update({"status": "expired"}).eq("id", w.order["id"]).execute()
        w.db.table("commerce_order_charges").update({"status": "expired"}).eq("order_id", w.order["id"]).execute()
        age(w)

    def test_regenerate_cancels_an_expired_attempt_at_the_gateway(self, w):
        self._legacy_expired(w)
        old = w.order["gateway_charge_id"]
        assert w.gw.charges.charges[old].status == "pending"  # still payable at the gateway
        regen_call(w)
        w.gw.sync_charges()
        assert w.gw.charges.charges[old].status == "cancelled"
        assert [r["status"] for r in list_charges(w.db, ORG_A, w.order["id"])] == ["cancelled", "pending"]
        live = [c for c in w.gw.charges.charges.values() if c.status not in ("cancelled",)]
        assert len(live) == 1

    def test_every_non_paid_attempt_is_cancelled_not_only_the_current_one(self, w):
        age(w)
        regen_call(w, method="boleto")  # attempt 2 (attempt 1 cancelled)
        first_id = w.order["gateway_charge_id"]
        # simulate an older attempt that was left expired-but-live at the gateway
        w.gw.charges.set_status(first_id, "overdue")
        w.db.table("commerce_order_charges").update({"status": "expired", "closed_at": None}).eq("gateway_charge_id", first_id).execute()
        w.db.table("commerce_orders").update({"status": "expired"}).eq("id", w.order["id"]).execute()
        age(w)
        regen_call(w, method="pix")
        assert w.gw.charges.charges[first_id].status == "cancelled"
        assert {r["status"] for r in list_charges(w.db, ORG_A, w.order["id"])} == {"cancelled", "pending"}

    def test_a_failed_cancel_of_an_expired_attempt_is_409_and_creates_no_charge(self, w):
        self._legacy_expired(w)

        def refuse(cid):
            raise PaymentGatewayError("asaas", "cannot", status=400, code="x")

        w.gw.charges.cancel_charge = refuse
        with pytest.raises(CommerceError) as exc:
            regen_call(w)
        assert exc.value.code == "cobranca_anterior_ativa" and exc.value.status_code == 409
        assert len(w.gw.checkout.sessions) == 1 and w.fresh()["status"] == "expired"

    def test_the_expire_job_cancels_the_charge_at_the_gateway(self, w):
        w.db.table("commerce_orders").update({"expires_at": (now() - timedelta(minutes=1)).isoformat()}).eq("id", w.order["id"]).execute()
        jobs_svc.commerce_expire_orders(w.db, fulfillment=w.reg, gateway=w.gw)
        assert w.gw.charges.charges[w.order["gateway_charge_id"]].status == "cancelled"
        assert list_charges(w.db, ORG_A, w.order["id"])[0]["status"] == "cancelled"

    def test_a_failed_cancel_in_the_expire_job_is_recorded_on_the_order(self, w):
        w.db.table("commerce_orders").update({"expires_at": (now() - timedelta(minutes=1)).isoformat()}).eq("id", w.order["id"]).execute()

        def refuse(cid):
            raise PaymentGatewayError("asaas", "cannot", status=500, code="x")

        w.gw.charges.cancel_charge = refuse
        assert jobs_svc.commerce_expire_orders(w.db, fulfillment=w.reg, gateway=w.gw) == 1
        assert w.fresh()["status"] == "expired"  # the order still expires
        assert any("não pôde ser cancelada" in e["reason"] for e in orders.list_events(w.db, ORG_A, w.order["id"]))

    def test_the_overdue_webhook_cancels_too(self, w):
        w.send("charge_failed", detail="overdue")
        assert w.gw.charges.charges[w.order["gateway_charge_id"]].status == "cancelled"


class TestForgedInstallmentBody:
    """S1: an unknown charge id is a later parcela ONLY if the gateway's own read ties it to this order."""

    def _installment_world(self, db):
        gw = FakeCheckoutGateway()
        world = World.__new__(World)
        world.db, world.gw, world.hooks = db, gw, Hooks()
        world.fin, world.mail = FakeFinanceBooking(), FakeEmailSender()
        world.paid_hook, world.revoked_hook = [], []
        world.reg, world.inbox, world.n = make_fulfillment_registry(), FakeEventInbox(), 0
        world.order = dict(place_order(db, gw, payment_method="credit_card", installments=3, price_cents=60000))
        return world

    def test_a_genuine_later_parcela_is_applied(self, db):
        w = self._installment_world(db)
        pay(w.gw, w.order, confirmed_only=True)
        w.send("charge_paid", detail="confirmed")
        parcela = w.gw.charges.add_charge("pay_parcela_2", amount=Money(20000), status="received", method="credit_card",
                                          installment_count=3, external_reference=w.order["id"])
        assert w.send("charge_paid", detail="received", charge_id="pay_parcela_2") == PROCESSED
        assert any(k[2] == "pay_parcela_2" for k in w.fin.settlements)

    def test_a_forged_body_naming_order_a_with_order_bs_charge_does_nothing(self, db):
        w = self._installment_world(db)
        w.gw.charges.add_charge("pay_of_order_b", amount=Money(20000), status="received", method="credit_card",
                                installment_count=3, external_reference="99999999-9999-4999-8999-999999999999")
        assert w.send("charge_paid", detail="received", charge_id="pay_of_order_b") == IGNORED
        assert w.fresh()["status"] == "pending_payment" and w.fin.settlements == {}
        assert w.mail.sent and "não identificado" in w.mail.sent[-1].subject


class TestAdoptFailureAlerts:
    def test_failed_cancel_of_the_newer_charge_alerts_staff(self, w):
        old = w.order["gateway_charge_id"]
        w.db.table("commerce_orders").update({"status": "expired"}).eq("id", w.order["id"]).execute()
        age(w)
        regen_call(w)
        w.gw.sync_charges()

        def refuse(cid):
            raise PaymentGatewayError("asaas", "cannot", status=500, code="x")

        w.gw.charges.cancel_charge = refuse
        pay(w.gw, {"gateway_charge_id": old})
        w.send("charge_paid", detail="received", charge_id=old)
        assert w.fresh()["status"] == "paid"
        assert any("Cobrança duplicada" in m.subject for m in w.mail.sent)


class TestEmailHygiene:
    def test_alert_and_reminder_html_escape_store_and_lines(self, w):
        w.db.table("commerce_store_profiles").update({"trade_name": "<script>x</script>"}).eq("org_id", ORG_A).execute()
        run(__import__("noctusai_lib.domain.commerce.alerts", fromlist=["notify_staff"]).notify_staff(
            w.db, ORG_A, w.mail, subject="s", lines=["<b>oi</b> & tchau"]))
        html = w.mail.sent[-1].html
        assert "<script>" not in html and "&lt;script&gt;" in html and "&lt;b&gt;oi&lt;/b&gt; &amp; tchau" in html

    def test_the_hourly_recipient_limit_is_case_insensitive(self, w):
        w.db.table("commerce_storefront_hosts").insert({"hostname": "loja-a.test", "org_id": ORG_A, "is_primary": True, "created_at": now().isoformat()}).execute()
        w.db.table("commerce_orders").update({"expires_at": (now() + timedelta(hours=10)).isoformat()}).eq("id", w.order["id"]).execute()
        other_id = "77777777-7777-4777-8777-777777777777"
        w.db.table("commerce_orders").insert({**w.order, "id": other_id, "token": "other-token", "expires_at": (now() + timedelta(hours=11)).isoformat()}).execute()
        w.db.table("commerce_order_reminders").insert({"order_id": other_id, "kind": "after_expiry", "org_id": ORG_A, "sent_at": now().isoformat()}).execute()
        w.db.table("commerce_customers").update({"email": "Ana@Example.com".lower()}).eq("org_id", ORG_A).execute()
        assert run(jobs_svc.commerce_expiry_reminders(w.db, cfg=CFG, email=w.mail, link_secret="s")) == 0
