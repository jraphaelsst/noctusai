"""`ChargeOperations` -- Fake, Asaas (httpx.MockTransport), Stripe (SDK double).

Same seams as the neighbouring suites: Asaas runs the real `_request` path over
`httpx.MockTransport`; Stripe substitutes `sys.modules["stripe"]` with a scripted
double returning REAL `StripeObject`s (external-SDK DI seam, never a patch of
our own code).
"""
from __future__ import annotations

import datetime as dt
import json as json_lib
import sys
import types
from typing import Any, Callable

import httpx
import pytest
from stripe import StripeObject

from noctusai_lib.integrations.payments.charges import (
    AsaasChargeOperations,
    ChargeOperations,
    FakeChargeOperations,
    StripeChargeOperations,
    make_charge_operations,
)
from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.real_asaas import AsaasPaymentGateway
from noctusai_lib.integrations.payments.real_stripe import StripePaymentGateway
from noctusai_lib.integrations.payments.types import BalanceTransaction, Money

BRL = "BRL"


# ── Fake ─────────────────────────────────────────────────────────────────


def test_fake_satisfies_protocol_and_factory_builds_it() -> None:
    assert isinstance(make_charge_operations(use_fake=True), ChargeOperations)


def test_fake_factory_refuses_without_provider_or_key() -> None:
    with pytest.raises(ValueError):
        make_charge_operations()
    with pytest.raises(ValueError):
        make_charge_operations(provider="asaas")
    with pytest.raises(ValueError):
        make_charge_operations(provider="stripe")
    with pytest.raises(ValueError):
        make_charge_operations(provider="mercadopago", stripe_api_key="x")


def test_factory_builds_real_adapters() -> None:
    assert isinstance(make_charge_operations(provider="asaas", asaas_api_key="k"), AsaasChargeOperations)
    assert isinstance(make_charge_operations(provider="stripe", stripe_api_key="k"), StripeChargeOperations)


def test_fake_partial_then_full_refund_walks_the_status() -> None:
    ops = FakeChargeOperations()
    ops.add_charge("pay_1", amount=Money(10000), status="received")
    first = ops.refund_charge("pay_1", amount=Money(2500), description="x")
    assert first.status == "done" and first.amount == Money(2500)
    charge = ops.get_charge("pay_1")
    assert charge.status == "partially_refunded" and charge.refunded == Money(2500)
    ops.refund_charge("pay_1", amount=None, description="rest")  # None = full remaining
    charge = ops.get_charge("pay_1")
    assert charge.status == "refunded" and charge.refunded == Money(10000)
    assert [r.amount.amount_cents for r in charge.refunds] == [2500, 7500]


def test_fake_refund_exceeds_balance_raises_and_records_nothing() -> None:
    ops = FakeChargeOperations()
    ops.add_charge("pay_1", amount=Money(10000), status="received")
    with pytest.raises(PaymentGatewayError) as exc:
        ops.refund_charge("pay_1", amount=Money(10001), description="x")
    assert exc.value.code == "refund_exceeds_balance"
    assert ops.get_charge("pay_1").refunds == []


def test_fake_cancel_unpaid_ok_paid_refused() -> None:
    ops = FakeChargeOperations()
    ops.add_charge("a", amount=Money(100))
    assert ops.cancel_charge("a").status == "cancelled"
    ops.add_charge("b", amount=Money(100), status="received")
    with pytest.raises(PaymentGatewayError) as exc:
        ops.cancel_charge("b")
    assert exc.value.code == "charge_already_paid"


def test_fake_dispute_lifecycle() -> None:
    ops = FakeChargeOperations()
    ops.add_charge("a", amount=Money(100), status="received")
    assert ops.open_dispute("a").status == "disputed"
    assert ops.win_dispute("a").status == "received"
    ops.open_dispute("a")
    assert ops.lose_dispute("a").status == "chargeback"


def test_fake_statement_pages_by_cursor() -> None:
    ops = FakeChargeOperations()
    base = dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc)
    for i in range(150):
        ops.add_balance_transaction(
            BalanceTransaction(
                id_at_gateway=f"t{i:03d}",
                occurred_at=base + dt.timedelta(minutes=i),
                kind="charge",
                amount=Money(100),
            )
        )
    page1 = ops.list_balance_transactions(since=dt.date(2026, 10, 1))
    assert len(page1.items) == 100 and page1.next_cursor
    page2 = ops.list_balance_transactions(since=dt.date(2026, 10, 1), cursor=page1.next_cursor)
    assert len(page2.items) == 50 and page2.next_cursor is None
    assert ops.list_balance_transactions(since=dt.date(2026, 10, 2)).items == []


# ── Asaas ────────────────────────────────────────────────────────────────


def _payment(**over: Any) -> dict:
    base = {
        "object": "payment",
        "id": "pay_1",
        "value": 100.0,
        "netValue": 96.5,
        "billingType": "CREDIT_CARD",
        "status": "RECEIVED",
        "dueDate": "2026-10-20",
        "paymentDate": "2026-10-13",
        "creditDate": "2026-11-13",
        "externalReference": "order-1",
        "deleted": False,
        "refunds": None,
        "chargeback": None,
    }
    base.update(over)
    return base


def _asaas(routes: dict[str, Callable[[httpx.Request], httpx.Response]], seen: list[str] | None = None) -> AsaasChargeOperations:
    def handler(request: httpx.Request) -> httpx.Response:
        key = f"{request.method} {request.url.path}"
        if seen is not None:
            seen.append(key)
        route = routes.get(key)
        if route is None:
            return httpx.Response(404, json={"errors": [{"description": "no route"}]})
        return route(request)

    return AsaasChargeOperations(AsaasPaymentGateway(api_key="k", transport=httpx.MockTransport(handler)))


def _ok(body: dict) -> Callable[[httpx.Request], httpx.Response]:
    return lambda request: httpx.Response(200, content=json_lib.dumps(body).encode())


def test_asaas_get_charge_maps_money_dates_and_fee() -> None:
    ops = _asaas({"GET /v3/payments/pay_1": _ok(_payment())})
    charge = ops.get_charge("pay_1")
    assert charge.status == "received" and charge.method == "credit_card"
    assert charge.amount == Money(10000) and charge.net == Money(9650) and charge.fee == Money(350)
    assert charge.due_date == dt.date(2026, 10, 20) and charge.credit_date == dt.date(2026, 11, 13)
    assert charge.paid_at is not None and charge.paid_at.date() == dt.date(2026, 10, 13)
    assert charge.external_reference == "order-1" and charge.installment_count == 1


@pytest.mark.parametrize(
    "raw_status,expected",
    [
        ("PENDING", "pending"), ("AWAITING_RISK_ANALYSIS", "pending"), ("CONFIRMED", "confirmed"),
        ("RECEIVED", "received"), ("RECEIVED_IN_CASH", "received"), ("OVERDUE", "overdue"),
        ("REFUNDED", "refunded"), ("REFUND_REQUESTED", "received"), ("REFUND_IN_PROGRESS", "received"),
        ("CHARGEBACK_REQUESTED", "disputed"), ("CHARGEBACK_DISPUTE", "disputed"),
        ("AWAITING_CHARGEBACK_REVERSAL", "disputed"), ("DUNNING_REQUESTED", "overdue"),
        ("DUNNING_RECEIVED", "received"),
    ],
)
def test_asaas_status_table(raw_status: str, expected: str) -> None:
    ops = _asaas({"GET /v3/payments/pay_1": _ok(_payment(status=raw_status))})
    assert ops.get_charge("pay_1").status == expected


def test_asaas_unknown_status_raises() -> None:
    ops = _asaas({"GET /v3/payments/pay_1": _ok(_payment(status="BRAND_NEW"))})
    with pytest.raises(PaymentGatewayError) as exc:
        ops.get_charge("pay_1")
    assert exc.value.code == "unknown_charge_status"


def test_asaas_unknown_billing_type_raises() -> None:
    ops = _asaas({"GET /v3/payments/pay_1": _ok(_payment(billingType="CRYPTO"))})
    with pytest.raises(PaymentGatewayError) as exc:
        ops.get_charge("pay_1")
    assert exc.value.code == "unknown_payment_method"


def test_asaas_deleted_reads_cancelled_and_partial_refund_detected() -> None:
    ops = _asaas({"GET /v3/payments/pay_1": _ok(_payment(deleted=True, status="PENDING"))})
    assert ops.get_charge("pay_1").status == "cancelled"
    refunds = [{"status": "DONE", "value": 40, "dateCreated": "2026-10-14 10:00:00"},
               {"status": "CANCELLED", "value": 5}]
    ops = _asaas({"GET /v3/payments/pay_1": _ok(_payment(refunds=refunds))})
    charge = ops.get_charge("pay_1")
    assert charge.status == "partially_refunded"
    assert charge.refunded == Money(4000) and len(charge.refunds) == 1
    assert charge.refunds[0].id_at_gateway is None and charge.refunds[0].status == "done"


def test_asaas_chargeback_status_decides_lost_vs_won() -> None:
    def status_for(cb: str) -> str:
        payment = _payment(status="RECEIVED", chargeback={"status": cb, "reason": "FRAUD"})
        return _asaas({"GET /v3/payments/pay_1": _ok(payment)}).get_charge("pay_1").status

    assert status_for("REQUESTED") == "disputed"
    assert status_for("IN_DISPUTE") == "disputed"
    assert status_for("DISPUTE_LOST") == "chargeback"  # the only "lost" signal Asaas has
    assert status_for("REVERSED") == "received"  # dispute won -> underlying status stands
    with pytest.raises(PaymentGatewayError):
        status_for("SOMETHING_NEW")


def test_asaas_installment_count_comes_from_the_parcelamento() -> None:
    ops = _asaas(
        {
            "GET /v3/payments/pay_1": _ok(_payment(installment="ins_1", installmentNumber=1)),
            "GET /v3/installments/ins_1": _ok({"id": "ins_1", "installmentCount": 6}),
        }
    )
    assert ops.get_charge("pay_1").installment_count == 6


def test_asaas_refund_exceeding_balance_raises_before_calling_out() -> None:
    seen: list[str] = []
    ops = _asaas({"GET /v3/payments/pay_1": _ok(_payment())}, seen)
    with pytest.raises(PaymentGatewayError) as exc:
        ops.refund_charge("pay_1", amount=Money(10001), description="x")
    assert exc.value.code == "refund_exceeds_balance"
    assert "POST /v3/payments/pay_1/refund" not in seen


def test_asaas_refund_after_partial_is_checked_against_remaining() -> None:
    seen: list[str] = []
    refunds = [{"status": "DONE", "value": 90}]
    ops = _asaas({"GET /v3/payments/pay_1": _ok(_payment(refunds=refunds))}, seen)
    with pytest.raises(PaymentGatewayError) as exc:
        ops.refund_charge("pay_1", amount=Money(1500), description="x")
    assert exc.value.code == "refund_exceeds_balance" and len(seen) == 1


def test_asaas_refund_unpaid_charge_is_refused() -> None:
    ops = _asaas({"GET /v3/payments/pay_1": _ok(_payment(status="PENDING"))})
    with pytest.raises(PaymentGatewayError) as exc:
        ops.refund_charge("pay_1", amount=None, description="x")
    assert exc.value.code == "charge_not_refundable"


def test_asaas_refund_posts_value_and_description_and_returns_new_refund() -> None:
    bodies: list[dict] = []

    def refund(request: httpx.Request) -> httpx.Response:
        bodies.append(json_lib.loads(request.content))
        return httpx.Response(
            200,
            content=json_lib.dumps(
                _payment(status="RECEIVED", refunds=[{"status": "DONE", "value": 25.5, "dateCreated": "2026-10-14 09:00:00"}])
            ).encode(),
        )

    ops = _asaas({"GET /v3/payments/pay_1": _ok(_payment()), "POST /v3/payments/pay_1/refund": refund})
    result = ops.refund_charge("pay_1", amount=Money(2550), description="pedido cancelado")
    assert bodies == [{"value": 25.5, "description": "pedido cancelado"}]
    assert result.amount == Money(2550) and result.status == "done" and result.charge_id_at_gateway == "pay_1"


def test_asaas_refund_full_remaining_sends_the_computed_value() -> None:
    bodies: list[dict] = []

    def refund(request: httpx.Request) -> httpx.Response:
        bodies.append(json_lib.loads(request.content))
        return httpx.Response(200, content=json_lib.dumps(_payment(status="REFUNDED")).encode())

    ops = _asaas({"GET /v3/payments/pay_1": _ok(_payment()), "POST /v3/payments/pay_1/refund": refund})
    result = ops.refund_charge("pay_1", amount=None, description="d")
    assert bodies[0]["value"] == 100.0
    assert result.amount == Money(10000) and result.status == "pending"  # accepted, no refund row listed yet


def _split(**over: Any) -> dict:
    base = {"id": "split_1", "walletId": "w_platform", "percentualValue": 10.0, "totalValue": 9.65, "status": "DONE"}
    base.update(over)
    return base


def _refund_bodies(payment: dict) -> tuple[AsaasChargeOperations, list[dict]]:
    bodies: list[dict] = []

    def refund(request: httpx.Request) -> httpx.Response:
        bodies.append(json_lib.loads(request.content))
        return httpx.Response(200, content=json_lib.dumps(payment).encode())

    return _asaas({"GET /v3/payments/pay_1": _ok(payment), "POST /v3/payments/pay_1/refund": refund}), bodies


def test_asaas_partial_refund_takes_the_split_share_back_proportionally() -> None:
    ops, bodies = _refund_bodies(_payment(split=[_split()]))
    ops.refund_charge("pay_1", amount=Money(5000), description="d")
    # half of R$100 refunded -> half of the R$9,65 split (floored to the cent) comes back from the platform
    assert bodies == [{"value": 50.0, "description": "d", "splitRefunds": [{"id": "split_1", "value": 4.82}]}]


def test_asaas_split_shares_are_cumulative_so_a_stepwise_full_refund_returns_the_whole_split() -> None:
    # 50 already refunded took 4,82 back; the remaining 50 takes 9,65 - 4,82 = 4,83, never a drifting 4,82
    ops, bodies = _refund_bodies(
        _payment(split=[_split()], refunds=[{"status": "DONE", "value": 50.0, "dateCreated": "2026-10-14 09:00:00"}])
    )
    ops.refund_charge("pay_1", amount=None, description="d")
    assert bodies[0]["value"] == 50.0 and bodies[0]["splitRefunds"] == [{"id": "split_1", "value": 4.83}]


def test_asaas_refund_skips_splits_that_moved_no_money_and_sends_none_without_a_live_split() -> None:
    ops, bodies = _refund_bodies(_payment(split=[_split(status="CANCELLED"), _split(id="split_2", status="REFUSED")]))
    ops.refund_charge("pay_1", amount=Money(5000), description="d")
    assert "splitRefunds" not in bodies[0]


def test_asaas_refund_with_unknown_split_status_raises_before_calling_out() -> None:
    seen: list[str] = []
    ops = _asaas({"GET /v3/payments/pay_1": _ok(_payment(split=[_split(status="NEW_THING")]))}, seen)
    with pytest.raises(PaymentGatewayError) as exc:
        ops.refund_charge("pay_1", amount=Money(5000), description="d")
    assert exc.value.code == "unknown_charge_status"
    assert seen == ["GET /v3/payments/pay_1"]


def _parcelas_routes(refunds_by_payment: dict[str, list[dict]], bodies: list[dict] | None = None, status: str = "RECEIVED"):
    def listing(request: httpx.Request) -> httpx.Response:
        data = [
            _payment(id=pid, value=20.0, installment="ins_1", status=status, refunds=refs or None)
            for pid, refs in refunds_by_payment.items()
        ]
        return httpx.Response(200, content=json_lib.dumps({"hasMore": False, "data": data}).encode())

    def refund(request: httpx.Request) -> httpx.Response:
        if bodies is not None:
            bodies.append(json_lib.loads(request.content or b"{}"))
        for refs in refunds_by_payment.values():  # the gateway spreads the value over the parcelas
            refs.append({"status": "DONE", "value": 20.0, "dateCreated": "2026-10-14 09:00:00"})
        return httpx.Response(200, content=json_lib.dumps({"id": "ins_1"}).encode())

    return {"GET /v3/installments/ins_1/payments": listing, "POST /v3/installments/ins_1/refund": refund}


def test_asaas_get_installment_folds_the_parcelas_and_groups_refunds_by_operation() -> None:
    done = {"status": "DONE", "dateCreated": "2026-10-14 09:00:00"}
    ops = _asaas(_parcelas_routes({"pay_1": [{**done, "value": 20.0}], "pay_2": [{**done, "value": 10.0}], "pay_3": []}))
    whole = ops.get_installment("ins_1")
    assert whole.amount == Money(6000) and whole.refunded == Money(3000) and whole.installment_count == 3
    assert whole.status == "partially_refunded" and whole.id_at_gateway == "ins_1"
    assert len(whole.refunds) == 1 and whole.refunds[0].amount == Money(3000) and whole.refunds[0].id_at_gateway is None


def test_asaas_refund_installment_partial_posts_value_and_reads_the_refund_back() -> None:
    bodies: list[dict] = []
    refs = {"pay_1": [], "pay_2": [], "pay_3": []}
    ops = _asaas(_parcelas_routes(refs, bodies))
    result = ops.refund_installment("ins_1", amount=Money(4000), description="d")
    assert bodies == [{"value": 40.0}]  # no description field exists on this endpoint
    assert result.status == "done" and result.charge_id_at_gateway == "ins_1"


def test_asaas_refund_installment_read_back_failure_after_the_post_is_pending_not_an_error() -> None:
    reads = []

    def listing(request: httpx.Request) -> httpx.Response:
        reads.append(1)
        if len(reads) > 1:  # the read-back after the POST times out
            raise httpx.ReadTimeout("slow", request=request)
        data = [_payment(id=pid, value=20.0, installment="ins_1", status="RECEIVED") for pid in ("pay_1", "pay_2")]
        return httpx.Response(200, content=json_lib.dumps({"hasMore": False, "data": data}).encode())

    routes = {"GET /v3/installments/ins_1/payments": listing, "POST /v3/installments/ins_1/refund": _ok({"id": "ins_1"})}
    result = _asaas(routes).refund_installment("ins_1", amount=Money(1000), description="d")
    assert result.status == "pending" and result.amount == Money(1000)


def test_asaas_refund_installment_success_is_decided_from_the_totals_not_the_group_count() -> None:
    # A second same-date refund merges into the existing group: the group count does not move, the total does.
    refs = {"pay_1": [{"status": "DONE", "value": 10.0, "dateCreated": "2026-10-14 09:00:00"}], "pay_2": []}

    def listing(request: httpx.Request) -> httpx.Response:
        data = [_payment(id=pid, value=20.0, installment="ins_1", status="RECEIVED", refunds=r or None) for pid, r in refs.items()]
        return httpx.Response(200, content=json_lib.dumps({"hasMore": False, "data": data}).encode())

    def post(request: httpx.Request) -> httpx.Response:
        refs["pay_1"].append({"status": "DONE", "value": 10.0, "dateCreated": "2026-10-14 09:00:00"})
        return httpx.Response(200, content=b"{}")

    routes = {"GET /v3/installments/ins_1/payments": listing, "POST /v3/installments/ins_1/refund": post}
    result = _asaas(routes).refund_installment("ins_1", amount=Money(1000), description="d")
    assert result.status == "done" and result.amount == Money(1000)


def test_asaas_refund_installment_full_sends_no_value() -> None:
    bodies: list[dict] = []
    ops = _asaas(_parcelas_routes({"pay_1": [], "pay_2": []}, bodies))
    ops.refund_installment("ins_1", amount=None, description="d")
    assert bodies == [{}]


def test_asaas_refund_installment_exceeding_balance_raises_before_calling_out() -> None:
    seen: list[str] = []
    ops = _asaas(_parcelas_routes({"pay_1": [], "pay_2": []}), seen)
    with pytest.raises(PaymentGatewayError) as exc:
        ops.refund_installment("ins_1", amount=Money(4001), description="d")
    assert exc.value.code == "refund_exceeds_balance" and "POST /v3/installments/ins_1/refund" not in seen


def test_asaas_refund_installment_unpaid_parcelamento_is_refused() -> None:
    ops = _asaas(_parcelas_routes({"pay_1": [], "pay_2": []}, status="PENDING"))
    with pytest.raises(PaymentGatewayError) as exc:
        ops.refund_installment("ins_1", amount=None, description="d")
    assert exc.value.code == "charge_not_refundable"


def test_fake_installment_refund_spreads_over_the_parcelas_and_reads_as_one_operation() -> None:
    ops = FakeChargeOperations()
    for n in (1, 2, 3):
        ops.add_charge(f"pay_{n}", amount=Money(2000), status="received", method="credit_card", installment_count=3, installment_id="ins_1")
    first = ops.refund_installment("ins_1", amount=Money(2500), description="a")
    assert ops.charges["pay_1"].status == "refunded" and ops.charges["pay_2"].status == "partially_refunded"
    whole = ops.get_installment("ins_1")
    assert whole.refunded == Money(2500) and [r.amount for r in whole.refunds] == [Money(2500)] and first.amount == Money(2500)
    ops.refund_installment("ins_1", amount=None, description="b")
    whole = ops.get_installment("ins_1")
    assert whole.status == "refunded" and [r.amount for r in whole.refunds] == [Money(2500), Money(3500)]
    with pytest.raises(PaymentGatewayError) as exc:
        ops.refund_installment("ins_1", amount=Money(1), description="c")
    assert exc.value.code in ("refund_exceeds_balance", "charge_not_refundable")


def test_fake_get_installment_unknown_is_404() -> None:
    with pytest.raises(PaymentGatewayError) as exc:
        FakeChargeOperations().get_installment("nope")
    assert exc.value.status == 404


def test_asaas_cancel_unpaid_deletes_and_reads_cancelled() -> None:
    seen: list[str] = []
    ops = _asaas(
        {
            "GET /v3/payments/pay_1": _ok(_payment(status="PENDING")),
            "DELETE /v3/payments/pay_1": _ok({"deleted": True, "id": "pay_1"}),
        },
        seen,
    )
    assert ops.cancel_charge("pay_1").status == "cancelled"
    assert "DELETE /v3/payments/pay_1" in seen


@pytest.mark.parametrize("raw_status", ["CONFIRMED", "RECEIVED", "REFUNDED", "CHARGEBACK_REQUESTED"])
def test_asaas_cancel_paid_charge_refused_without_delete(raw_status: str) -> None:
    seen: list[str] = []
    ops = _asaas({"GET /v3/payments/pay_1": _ok(_payment(status=raw_status))}, seen)
    with pytest.raises(PaymentGatewayError) as exc:
        ops.cancel_charge("pay_1")
    assert exc.value.code == "charge_already_paid"
    assert not any(s.startswith("DELETE") for s in seen)


def test_asaas_balance_transactions_map_kinds_and_page() -> None:
    queries: list[dict] = []

    def statement(request: httpx.Request) -> httpx.Response:
        queries.append(dict(request.url.params))
        rows = [
            {"id": "ftn_1", "value": 100.0, "type": "PAYMENT_RECEIVED", "date": "2026-10-13", "paymentId": "pay_1", "description": "Cobrança"},
            {"id": "ftn_2", "value": -3.5, "type": "PAYMENT_FEE", "date": "2026-10-13", "paymentId": "pay_1"},
            {"id": "ftn_3", "value": -25.5, "type": "PAYMENT_REVERSAL", "date": "2026-10-14", "paymentId": "pay_1"},
            {"id": "ftn_4", "value": -100.0, "type": "CHARGEBACK", "date": "2026-10-15", "paymentId": "pay_1"},
            {"id": "ftn_5", "value": -50.0, "type": "TRANSFER", "date": "2026-10-16"},
            {"id": "ftn_6", "value": 1.0, "type": "PAYMENT_FEE_REVERSAL", "date": "2026-10-16"},
            {"id": "ftn_7", "value": 9.0, "type": "SOME_FUTURE_TYPE", "date": "2026-10-16"},
        ]
        return httpx.Response(200, content=json_lib.dumps({"hasMore": True, "data": rows}).encode())

    ops = _asaas({"GET /v3/financialTransactions": statement})
    page = ops.list_balance_transactions(since=dt.date(2026, 10, 1))
    assert [i.kind for i in page.items] == ["charge", "fee", "refund", "chargeback", "transfer", "adjustment", "other"]
    assert page.items[1].amount == Money(-350) and page.items[0].charge_id_at_gateway == "pay_1"
    assert page.next_cursor == "100" and queries[0]["startDate"] == "2026-10-01"
    ops.list_balance_transactions(since=dt.date(2026, 10, 1), cursor=page.next_cursor)
    assert queries[1]["offset"] == "100"


# ── Stripe ───────────────────────────────────────────────────────────────


class _StripeErr(Exception):
    def __init__(self, message: str, *, http_status: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.code = code


@pytest.fixture
def stripe_double(monkeypatch: pytest.MonkeyPatch) -> Any:
    calls: list[tuple[str, Any]] = []
    store: dict[str, dict[str, dict]] = {
        "sessions": {}, "intents": {}, "charges": {}, "refunds": {}, "txns": {},
    }
    real_stripe = sys.modules["stripe"]
    module = types.ModuleType("stripe")
    module.__path__ = real_stripe.__path__
    module.__getattr__ = lambda name: getattr(real_stripe, name)
    module.api_key = None
    module.StripeError = _StripeErr

    def obj(record: dict) -> StripeObject:
        return StripeObject.construct_from(record, "sk_test_double")

    def fetch(kind: str, rid: str) -> dict:
        if rid not in store[kind]:
            raise _StripeErr("No such object", http_status=404, code="resource_missing")
        return store[kind][rid]

    def expanded_charge(cid: str) -> dict:
        charge = dict(fetch("charges", cid))
        charge["balance_transaction"] = store["txns"].get(charge.get("balance_transaction"), charge.get("balance_transaction"))
        return charge

    class _Session:
        @staticmethod
        def retrieve(sid: str, **kw: Any) -> StripeObject:
            calls.append(("Session.retrieve", sid))
            rec = dict(fetch("sessions", sid))
            pi = rec.get("payment_intent")
            if pi:
                intent = dict(fetch("intents", pi))
                if intent.get("latest_charge"):
                    intent["latest_charge"] = expanded_charge(intent["latest_charge"])
                rec["payment_intent"] = intent
            return obj(rec)

        @staticmethod
        def expire(sid: str) -> StripeObject:
            calls.append(("Session.expire", sid))
            store["sessions"][sid] = {**fetch("sessions", sid), "status": "expired"}
            return obj(store["sessions"][sid])

    module.checkout = types.SimpleNamespace(Session=_Session)

    class _PaymentIntent:
        @staticmethod
        def retrieve(pid: str, **kw: Any) -> StripeObject:
            calls.append(("PaymentIntent.retrieve", pid))
            rec = dict(fetch("intents", pid))
            if rec.get("latest_charge"):
                rec["latest_charge"] = expanded_charge(rec["latest_charge"])
            return obj(rec)

        @staticmethod
        def cancel(pid: str) -> StripeObject:
            calls.append(("PaymentIntent.cancel", pid))
            store["intents"][pid] = {**fetch("intents", pid), "status": "canceled"}
            return obj(store["intents"][pid])

    module.PaymentIntent = _PaymentIntent

    class _Charge:
        @staticmethod
        def retrieve(cid: str, **kw: Any) -> StripeObject:
            calls.append(("Charge.retrieve", cid))
            return obj(expanded_charge(cid))

    module.Charge = _Charge

    class _Refund:
        @staticmethod
        def list(**kw: Any) -> Any:
            calls.append(("Refund.list", kw))
            rows = [r for r in store["refunds"].values() if r["charge"] == kw["charge"]]
            return types.SimpleNamespace(data=[obj(r) for r in rows])

        @staticmethod
        def create(**kw: Any) -> StripeObject:
            calls.append(("Refund.create", kw))
            rid = f"re_{len(store['refunds']) + 1}"
            rec = {"id": rid, "charge": kw["charge"], "amount": kw["amount"], "currency": "brl",
                   "status": "succeeded", "created": 1760400000}
            store["refunds"][rid] = rec
            charge = store["charges"][kw["charge"]]
            charge["amount_refunded"] += kw["amount"]
            charge["refunded"] = charge["amount_refunded"] >= charge["amount"]
            return obj(rec)

    module.Refund = _Refund

    class _BalanceTransaction:
        @staticmethod
        def list(**kw: Any) -> Any:
            calls.append(("BalanceTransaction.list", kw))
            return types.SimpleNamespace(
                data=[obj(t) for t in store["txns"].values()], has_more=kw.get("starting_after") is None
            )

    module.BalanceTransaction = _BalanceTransaction
    monkeypatch.setitem(sys.modules, "stripe", module)
    return types.SimpleNamespace(calls=calls, store=store)


NOW = dt.datetime(2026, 10, 13, 12, tzinfo=dt.timezone.utc)


def _stripe_ops() -> StripeChargeOperations:
    return StripeChargeOperations(StripePaymentGateway(api_key="sk_test"), now=lambda: NOW)


def _seed_paid_charge(double: Any, *, available_on: int = 1760000000, **charge_over: Any) -> None:
    double.store["txns"]["txn_1"] = {
        "id": "txn_1", "object": "balance_transaction", "amount": 10000, "fee": 399, "net": 9601,
        "currency": "brl", "available_on": available_on, "created": 1759900000,
        "type": "charge", "reporting_category": "charge", "source": "ch_1", "description": "pay",
    }
    double.store["charges"]["ch_1"] = {
        "id": "ch_1", "object": "charge", "status": "succeeded", "amount": 10000, "currency": "brl",
        "amount_refunded": 0, "refunded": False, "dispute": None, "created": 1759900000,
        "balance_transaction": "txn_1", "payment_method_details": {"type": "card"},
        "metadata": {"external_reference": "order-1"}, **charge_over,
    }
    double.store["intents"]["pi_1"] = {"id": "pi_1", "status": "succeeded", "amount": 10000,
                                       "currency": "brl", "latest_charge": "ch_1", "metadata": {}}
    double.store["sessions"]["cs_1"] = {"id": "cs_1", "status": "complete", "payment_status": "paid",
                                        "payment_intent": "pi_1", "currency": "brl", "amount_total": 10000,
                                        "client_reference_id": "order-1", "payment_method_types": ["card"]}


def test_stripe_get_charge_via_session_maps_everything(stripe_double: Any) -> None:
    _seed_paid_charge(stripe_double)
    charge = _stripe_ops().get_charge("cs_1")
    assert charge.id_at_gateway == "cs_1" and charge.status == "received"
    assert charge.method == "credit_card" and charge.amount == Money(10000)
    assert charge.fee == Money(399) and charge.net == Money(9601)
    assert charge.external_reference == "order-1" and charge.paid_at is not None
    assert charge.credit_date == dt.datetime.fromtimestamp(1760000000, tz=dt.timezone.utc).date()


def test_stripe_confirmed_until_the_balance_is_available(stripe_double: Any) -> None:
    _seed_paid_charge(stripe_double, available_on=int((NOW + dt.timedelta(days=30)).timestamp()))
    assert _stripe_ops().get_charge("ch_1").status == "confirmed"


def test_stripe_charge_id_forms_all_resolve(stripe_double: Any) -> None:
    _seed_paid_charge(stripe_double)
    ops = _stripe_ops()
    assert {ops.get_charge(i).status for i in ("cs_1", "pi_1", "ch_1")} == {"received"}
    with pytest.raises(PaymentGatewayError) as exc:
        ops.get_charge("zz_1")
    assert exc.value.code == "unsupported_charge_id"


def test_stripe_refund_states_and_dispute_states(stripe_double: Any) -> None:
    _seed_paid_charge(stripe_double, amount_refunded=2500)
    assert _stripe_ops().get_charge("ch_1").status == "partially_refunded"
    _seed_paid_charge(stripe_double, amount_refunded=10000, refunded=True)
    assert _stripe_ops().get_charge("ch_1").status == "refunded"
    for dispute_status, expected in [("needs_response", "disputed"), ("under_review", "disputed"),
                                     ("lost", "chargeback"), ("won", "received")]:
        _seed_paid_charge(stripe_double, dispute={"id": "dp_1", "status": dispute_status})
        assert _stripe_ops().get_charge("ch_1").status == expected
    _seed_paid_charge(stripe_double, dispute={"id": "dp_1", "status": "brand_new"})
    with pytest.raises(PaymentGatewayError) as exc:
        _stripe_ops().get_charge("ch_1")
    assert exc.value.code == "unknown_charge_status"


def test_stripe_unknown_charge_status_raises(stripe_double: Any) -> None:
    _seed_paid_charge(stripe_double, status="exotic")
    with pytest.raises(PaymentGatewayError) as exc:
        _stripe_ops().get_charge("ch_1")
    assert exc.value.code == "unknown_charge_status"


def test_stripe_open_and_expired_sessions(stripe_double: Any) -> None:
    stripe_double.store["sessions"]["cs_open"] = {"id": "cs_open", "status": "open", "payment_status": "unpaid",
                                                  "payment_intent": None, "currency": "brl", "amount_total": 500,
                                                  "payment_method_types": ["card"], "client_reference_id": "o"}
    stripe_double.store["sessions"]["cs_exp"] = {**stripe_double.store["sessions"]["cs_open"], "id": "cs_exp", "status": "expired"}
    ops = _stripe_ops()
    assert ops.get_charge("cs_open").status == "pending"
    assert ops.get_charge("cs_exp").status == "cancelled"


def test_stripe_refund_exceeds_balance_raises_before_refund_create(stripe_double: Any) -> None:
    _seed_paid_charge(stripe_double)
    with pytest.raises(PaymentGatewayError) as exc:
        _stripe_ops().refund_charge("cs_1", amount=Money(10001), description="x")
    assert exc.value.code == "refund_exceeds_balance"
    assert not any(name == "Refund.create" for name, _ in stripe_double.calls)


def test_stripe_refund_creates_against_the_charge(stripe_double: Any) -> None:
    _seed_paid_charge(stripe_double)
    result = _stripe_ops().refund_charge("cs_1", amount=Money(4000), description="devolução")
    create = [kw for name, kw in stripe_double.calls if name == "Refund.create"][0]
    assert create["charge"] == "ch_1" and create["amount"] == 4000
    assert result.id_at_gateway == "re_1" and result.amount == Money(4000) and result.status == "done"
    after = _stripe_ops().get_charge("cs_1")
    assert after.status == "partially_refunded" and after.refunded == Money(4000)
    assert [r.id_at_gateway for r in after.refunds] == ["re_1"]


def test_stripe_cancel_expires_unpaid_session_and_refuses_paid(stripe_double: Any) -> None:
    stripe_double.store["sessions"]["cs_open"] = {"id": "cs_open", "status": "open", "payment_status": "unpaid",
                                                  "payment_intent": None, "currency": "brl", "amount_total": 500,
                                                  "payment_method_types": ["card"], "client_reference_id": "o"}
    ops = _stripe_ops()
    assert ops.cancel_charge("cs_open").status == "cancelled"
    assert ("Session.expire", "cs_open") in stripe_double.calls
    _seed_paid_charge(stripe_double)
    with pytest.raises(PaymentGatewayError) as exc:
        ops.cancel_charge("cs_1")
    assert exc.value.code == "charge_already_paid"


def test_stripe_cancel_payment_intent(stripe_double: Any) -> None:
    stripe_double.store["intents"]["pi_9"] = {"id": "pi_9", "status": "requires_payment_method", "amount": 500,
                                              "currency": "brl", "latest_charge": None, "metadata": {},
                                              "payment_method_types": ["card"]}
    assert _stripe_ops().cancel_charge("pi_9").status == "cancelled"
    assert ("PaymentIntent.cancel", "pi_9") in stripe_double.calls


def test_stripe_balance_transactions_split_the_fee_and_map_kinds(stripe_double: Any) -> None:
    _seed_paid_charge(stripe_double)
    stripe_double.store["txns"]["txn_2"] = {
        "id": "txn_2", "amount": -4000, "fee": 0, "currency": "brl", "created": 1759950000,
        "type": "refund", "reporting_category": "refund", "source": {"object": "refund", "id": "re_1", "charge": "ch_1"},
    }
    stripe_double.store["txns"]["txn_3"] = {
        "id": "txn_3", "amount": -10000, "fee": 1500, "currency": "brl", "created": 1759960000,
        "type": "adjustment", "reporting_category": "dispute", "source": {"object": "dispute", "id": "dp_1", "charge": "ch_1"},
    }
    page = _stripe_ops().list_balance_transactions(since=dt.date(2026, 10, 1))
    by_id = {i.id_at_gateway: i for i in page.items}
    assert by_id["txn_1"].kind == "charge" and by_id["txn_1"].amount == Money(10000)
    assert by_id["txn_1:fee"].kind == "fee" and by_id["txn_1:fee"].amount == Money(-399)
    assert by_id["txn_2"].kind == "refund" and by_id["txn_2"].charge_id_at_gateway == "ch_1"
    assert by_id["txn_3"].kind == "chargeback" and "txn_3:fee" not in by_id  # only charges split a fee
    assert page.next_cursor == "txn_3"
    call = [kw for name, kw in stripe_double.calls if name == "BalanceTransaction.list"][0]
    assert call["created"]["gte"] == int(dt.datetime(2026, 10, 1, tzinfo=dt.timezone.utc).timestamp())


def test_stripe_has_no_parcelamento_so_installment_ops_are_refused(stripe_double: Any) -> None:
    ops = _stripe_ops()  # a Stripe card installment is one PaymentIntent: refund_charge is the right call
    with pytest.raises(PaymentGatewayError) as got:
        ops.get_installment("x")
    assert got.value.code == "installments_unsupported"
    with pytest.raises(PaymentGatewayError) as got:
        ops.refund_installment("x", amount=None, description="d")
    assert got.value.code == "installments_unsupported"
