"""Billing automations — driven by a fake clock over managed subscriptions.

The legacy guarantee is tested end to end: a pre-050 subscription and a
`legacy` license survive every sweep untouched, even when their dates say
they "should" be moved.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

from noctusai_lib.integrations.payments import PaymentGatewayError

from app.services import billing_automations as auto
from tests.billing_fakes import (
    NOW,
    ORG_ID,
    PLAN_ID,
    PRODUCT_ID,
    legacy_subscription,
    make_ctx,
    managed_subscription,
    seed_catalog,
)

SUB = "66666666-6666-6666-6666-666666666666"


def _status(fakes, sub_id=SUB):
    rows = fakes.db.table("subscriptions").select("*").eq("id", sub_id).execute().data
    return rows[0]["status"]


def _licenses(fakes):
    return {r["id"]: r for r in fakes.db.table("licenses").select("*").execute().data}


def _setup(*, grace_days=5, subscriptions=(), licenses=(), **ctx_kwargs):
    ctx, fakes = make_ctx(**ctx_kwargs)
    seed_catalog(fakes.db, grace_days=grace_days)
    fakes.db.set_table_data("subscriptions", list(subscriptions))
    fakes.db.set_table_data("licenses", list(licenses))
    fakes.db.set_table_data("billing_payments", [])
    return ctx, fakes


def _sub_license(**overrides):
    row = {"id": "lic-sub", "org_id": ORG_ID, "product_id": PRODUCT_ID, "status": "active",
           "source": "subscription", "subscription_id": SUB, "fim": None}
    row.update(overrides)
    return row


def _legacy_license():
    return {"id": "lic-legacy", "org_id": ORG_ID, "product_id": "legacy-product",
            "status": "active", "source": "legacy", "subscription_id": None, "fim": None}


# ── switch ──────────────────────────────────────────────────────────────


def test_switched_off_every_sweep_is_skipped_and_nothing_is_written():
    ctx, fakes = _setup(
        automations=False,
        subscriptions=[managed_subscription(status="grace", grace_ends_at=(NOW - timedelta(days=1)).isoformat())],
        licenses=[_sub_license()],
    )
    reports = auto.run_all(ctx)
    assert all(r.skipped for r in reports)
    assert fakes.db.table("subscriptions").updated_payloads == []
    assert fakes.db.table("licenses").updated_payloads == []


# ── trial ───────────────────────────────────────────────────────────────


def test_manual_trial_ending_unpaid_goes_past_due_then_grace():
    ends = NOW - timedelta(hours=2)
    ctx, fakes = _setup(
        subscriptions=[managed_subscription(status="trial", gateway="manual", gateway_subscription_id=None,
                                            trial_ends_at=ends.isoformat(), current_period_end=ends.isoformat())],
        licenses=[_sub_license()],
    )
    auto.sweep_trials(ctx)
    assert _status(fakes) == "past_due"
    auto.sweep_past_due(ctx)
    row = fakes.db.table("subscriptions").select("*").execute().data[0]
    assert row["status"] == "grace"
    assert row["grace_ends_at"] == (ends + timedelta(days=5)).isoformat()
    assert _licenses(fakes)["lic-sub"]["status"] == "active"  # grace keeps access


def test_trial_not_yet_over_is_left_alone():
    ctx, fakes = _setup(
        subscriptions=[managed_subscription(status="trial", gateway="manual",
                                            trial_ends_at=(NOW + timedelta(days=1)).isoformat())],
    )
    report = auto.sweep_trials(ctx)
    assert report.examined == 1 and report.changed == []
    assert _status(fakes) == "trial"


def test_stripe_trial_is_reconciled_against_stripe_not_forced():
    ends = NOW - timedelta(hours=3)
    ctx, fakes = _setup(
        subscriptions=[managed_subscription(status="trial", gateway_subscription_id=None,
                                            trial_ends_at=ends.isoformat())],
    )
    gw = fakes.gateways["stripe"]
    customer = gw.ensure_customer(external_reference=ORG_ID, email="a@b.c", name="A")
    from noctusai_lib.integrations.payments.types import Money, SubscriptionRequest

    remote = gw.create_subscription(SubscriptionRequest(
        external_reference=SUB, customer_id_at_gateway=customer.id_at_gateway,
        price=Money(9900, "BRL"), plan_ref="price_x", trial_days=7))
    gw.set_status(remote.id_at_gateway, "active")
    fakes.db.table("subscriptions").update({"gateway_subscription_id": remote.id_at_gateway}).eq("id", SUB).execute()

    auto.sweep_trials(ctx)
    assert _status(fakes) == "active"


# ── grace / expiry ──────────────────────────────────────────────────────


def test_grace_ending_expires_revokes_and_stops_the_gateway():
    ctx, fakes = _setup(
        subscriptions=[managed_subscription(status="grace", grace_ends_at=(NOW - timedelta(minutes=1)).isoformat())],
        licenses=[_sub_license(), _legacy_license()],
    )
    gw = fakes.gateways["stripe"]
    gw.subscriptions["sub_gw_1"] = _remote(gw)
    report = auto.sweep_grace(ctx)
    assert report.changed == [f"{SUB}: grace → expired"]
    assert _status(fakes) == "expired"
    licenses = _licenses(fakes)
    assert licenses["lic-sub"]["status"] == "revoked"
    assert licenses["lic-legacy"]["status"] == "active"
    assert ("cancel_subscription", "sub_gw_1") in gw.calls


def _remote(gw):
    from noctusai_lib.integrations.payments.types import GatewaySubscription

    return GatewaySubscription(id_at_gateway="sub_gw_1", customer_id_at_gateway="cus_gw_1",
                               external_reference=SUB, status="past_due")


def test_grace_not_over_keeps_access():
    ctx, fakes = _setup(
        subscriptions=[managed_subscription(status="grace", grace_ends_at=(NOW + timedelta(hours=1)).isoformat())],
        licenses=[_sub_license()],
    )
    auto.sweep_grace(ctx)
    assert _status(fakes) == "grace"
    assert _licenses(fakes)["lic-sub"]["status"] == "active"


def test_no_grace_configured_past_due_expires_immediately():
    ctx, fakes = _setup(
        grace_days=0,
        subscriptions=[managed_subscription(status="past_due", gateway="manual", gateway_subscription_id=None,
                                            past_due_since=NOW.isoformat())],
        licenses=[_sub_license()],
    )
    auto.sweep_past_due(ctx)
    assert _status(fakes) == "expired"
    assert _licenses(fakes)["lic-sub"]["status"] == "revoked"


def test_failed_gateway_cancel_is_flagged_and_retried_by_reconcile():
    ctx, fakes = _setup(
        subscriptions=[managed_subscription(status="grace", grace_ends_at=(NOW - timedelta(minutes=1)).isoformat())],
        licenses=[_sub_license()],
    )

    class _Down:
        name = "stripe"
        calls: list = []

        def cancel_subscription(self, _id):
            raise PaymentGatewayError("stripe", "down", status=503, retryable=True)

    working = fakes.gateways["stripe"]
    working.subscriptions["sub_gw_1"] = _remote(working)
    ctx.gateway_factory = lambda gateway, mode: _Down()
    report = auto.sweep_grace(ctx)
    assert _status(fakes) == "expired"
    assert report.errors and "gateway cancel failed" in report.errors[0]
    row = fakes.db.table("subscriptions").select("*").execute().data[0]
    assert row["metadata"]["gateway_cancel_pending"] is True

    ctx.gateway_factory = lambda gateway, mode: working
    report = auto.reconcile(ctx)
    assert f"{SUB}: gateway cancel retried" in report.changed
    row = fakes.db.table("subscriptions").select("*").execute().data[0]
    assert "gateway_cancel_pending" not in row["metadata"]
    assert ("cancel_subscription", "sub_gw_1") in working.calls


# ── period end ──────────────────────────────────────────────────────────


def test_cancel_at_period_end_closes_the_row_when_the_period_ends():
    ctx, fakes = _setup(
        subscriptions=[managed_subscription(cancel_at_period_end=True,
                                            current_period_end=(NOW - timedelta(minutes=5)).isoformat())],
        licenses=[_sub_license()],
    )
    auto.sweep_period_end(ctx)
    assert _status(fakes) == "canceled"
    assert _licenses(fakes)["lic-sub"]["status"] == "revoked"


def test_manual_subscription_past_its_period_goes_past_due():
    ends = NOW - timedelta(days=1)
    ctx, fakes = _setup(
        subscriptions=[managed_subscription(gateway="manual", gateway_subscription_id=None,
                                            current_period_end=ends.isoformat())],
    )
    auto.sweep_period_end(ctx)
    row = fakes.db.table("subscriptions").select("*").execute().data[0]
    assert row["status"] == "past_due"
    assert row["past_due_since"] == ends.isoformat()


def test_gateway_subscription_past_period_is_left_to_the_gateway():
    ctx, fakes = _setup(
        subscriptions=[managed_subscription(current_period_end=(NOW - timedelta(days=1)).isoformat())],
    )
    auto.sweep_period_end(ctx)
    assert _status(fakes) == "active"


# ── reconcile ───────────────────────────────────────────────────────────


def test_reconcile_cancels_what_the_gateway_already_canceled():
    ctx, fakes = _setup(subscriptions=[managed_subscription()], licenses=[_sub_license()])
    gw = fakes.gateways["stripe"]
    gw.subscriptions["sub_gw_1"] = _remote(gw)
    gw.set_status("sub_gw_1", "canceled")
    auto.reconcile(ctx)
    assert _status(fakes) == "canceled"
    assert _licenses(fakes)["lic-sub"]["status"] == "revoked"


def test_reconcile_fills_a_pending_stripe_fee():
    from noctusai_lib.integrations.payments.types import FeeBreakdown, Money

    ctx, fakes = _setup(subscriptions=[managed_subscription()])
    fakes.gateways["stripe"].subscriptions["sub_gw_1"] = _remote(fakes.gateways["stripe"])
    fakes.gateways["stripe"].set_status("sub_gw_1", "active")
    fakes.db.set_table_data("cost_ledger", [])
    fakes.db.set_table_data("billing_payments", [{
        "id": "pay-1", "org_id": ORG_ID, "subscription_id": SUB, "gateway": "stripe",
        "gateway_mode": "test", "gateway_payment_id": "in_1", "gateway_charge_id": "ch_1",
        "status": "paid", "billing_method": "card", "currency": "BRL", "gross_cents": 9900,
        "fee_cents": 0, "net_cents": 9900, "fee_pending": True, "fx_pending": False,
        "paid_at": NOW.isoformat(), "created_at": NOW.isoformat(),
    }])
    fakes.gateways["stripe"].script_fee(
        "ch_1", FeeBreakdown(gross=Money(9900), fee=Money(399), net=Money(9501))
    )
    report = auto.reconcile(ctx)
    assert "payment pay-1: fee 399" in report.changed
    payment = fakes.db.table("billing_payments").select("*").execute().data[0]
    assert (payment["fee_cents"], payment["net_cents"], payment["fee_pending"]) == (399, 9501, False)
    fee_rows = fakes.db.table("cost_ledger").select("*").execute().data
    assert len(fee_rows) == 1 and fee_rows[0]["category"] == "payment_fee"
    assert fee_rows[0]["amount_brl"] == "3.99"


# ── the legacy guarantee ────────────────────────────────────────────────


def test_legacy_subscription_and_licenses_are_never_touched_by_any_sweep():
    long_ago = (NOW - timedelta(days=400)).isoformat()
    legacy = legacy_subscription(
        status="trial", trial_ends_at=long_ago, current_period_end=long_ago,
        past_due_since=long_ago, grace_ends_at=long_ago, cancel_at_period_end=True,
    )
    legacy_past_due = legacy_subscription(id="88888888-8888-8888-8888-888888888888", status="active",
                                          current_period_end=long_ago, gateway="manual")
    ctx, fakes = _setup(
        subscriptions=[legacy, legacy_past_due],
        licenses=[
            _legacy_license(),
            {"id": "lic-legacy-2", "org_id": ORG_ID, "product_id": PRODUCT_ID, "status": "active",
             "source": "legacy", "subscription_id": legacy["id"], "fim": long_ago},
        ],
    )
    for _ in range(3):
        fakes.clock.now += timedelta(days=30)
        reports = auto.run_all(ctx)
        assert not any(r.skipped for r in reports)
        assert all(r.examined == 0 for r in reports if r.name != "reconcile")
    assert fakes.db.table("subscriptions").updated_payloads == []
    assert fakes.db.table("licenses").updated_payloads == []
    assert fakes.gateways["stripe"].calls == [] and fakes.gateways["asaas"].calls == []


def test_reconcile_read_failure_is_reported_not_raised():
    ctx, fakes = _setup(subscriptions=[managed_subscription(gateway_subscription_id="sub_unknown")])
    report = auto.reconcile(ctx)
    assert report.errors and "reconcile read failed" in report.errors[0]
    assert _status(fakes) == "active"
