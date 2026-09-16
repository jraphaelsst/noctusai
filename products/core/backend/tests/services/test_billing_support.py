"""Billing config, FX, storage cost, MRR and the price guard — unit level."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from noctusai_lib.integrations.fx import FakeFxRateAdapter
from noctusai_lib.security.app_config import FakeAppConfigStore
from noctusai_lib.testing import MockSupabaseClient

from app.services import billing_metrics, fx_service, storage_cost_service
from app.services import billing_subscriptions as subs
from app.services.billing_config import (
    BillingConfig,
    EncryptionNotConfigured,
    InvalidSecret,
    build_config_store,
    validate_secret,
)
from tests.billing_fakes import NOW, ORG_ID, PLAN_ID, PRICE_ID, make_ctx, seed_catalog


# ── config: env fallback never answers for the wrong mode ──────────────


def _config(env_key="", env_whsec="", store=None, encrypted=True):
    db = MockSupabaseClient()
    db.set_table_data("platform_settings", [])

    def factory():
        if not encrypted:
            raise EncryptionNotConfigured("no key")
        return store if store is not None else FakeAppConfigStore()

    return BillingConfig(db, store_factory=factory, env_stripe_secret_key=env_key,
                         env_stripe_webhook_secret=env_whsec)


def test_env_live_key_serves_live_only():
    cfg = _config(env_key="sk_live_env", env_whsec="whsec_env")
    assert cfg.get_secret("stripe", "secret_key", "live") == "sk_live_env"
    assert cfg.get_secret("stripe", "webhook_secret", "live") == "whsec_env"
    assert cfg.get_secret("stripe", "secret_key", "test") is None
    assert cfg.secret_status("stripe", "secret_key", "live").source == "env"


def test_env_test_key_serves_test_only():
    cfg = _config(env_key="sk_test_env")
    assert cfg.get_secret("stripe", "secret_key", "test") == "sk_test_env"
    assert cfg.get_secret("stripe", "secret_key", "live") is None


def test_db_value_wins_over_env():
    store = FakeAppConfigStore()
    store.put("billing.stripe.secret_key.live", "sk_live_db")
    cfg = _config(env_key="sk_live_env", store=store)
    assert cfg.get_secret("stripe", "secret_key", "live") == "sk_live_db"
    assert cfg.secret_status("stripe", "secret_key", "live").source == "db"


def test_without_encryption_reads_fall_back_to_env_and_writes_refuse():
    cfg = _config(env_key="sk_live_env", encrypted=False)
    assert cfg.get_secret("stripe", "secret_key", "live") == "sk_live_env"
    assert cfg.encryption_configured() is False
    with pytest.raises(EncryptionNotConfigured):
        cfg.set_secret("stripe", "secret_key", "live", "sk_live_new")


def test_build_config_store_refuses_missing_or_bad_key():
    with pytest.raises(EncryptionNotConfigured):
        build_config_store(MockSupabaseClient(), "")
    with pytest.raises(EncryptionNotConfigured):
        build_config_store(MockSupabaseClient(), "not-a-fernet-key")


@pytest.mark.parametrize(
    "gateway,field,mode,value",
    [
        ("stripe", "secret_key", "test", "sk_live_x"),
        ("stripe", "secret_key", "live", "pk_live_x"),
        ("stripe", "webhook_secret", "test", "secret"),
        ("asaas", "api_key", "test", "$aact_prod_0000000000000000"),
        ("asaas", "api_key", "live", "short"),
        ("asaas", "webhook_token", "live", "tiny"),
    ],
)
def test_validate_secret_refuses_wrong_shapes(gateway, field, mode, value):
    with pytest.raises(InvalidSecret):
        validate_secret(gateway, field, mode, value)


def test_invalid_mode_setting_reads_as_test():
    cfg = _config()
    cfg._db.set_table_data("platform_settings", [{"key": "billing_gateway_mode", "value": "prod"}])
    assert cfg.mode() == "test"


# ── FX ───────────────────────────────────────────────────────────────────


def test_conversion_walks_back_to_the_last_bulletin_and_stores_it():
    db = MockSupabaseClient()
    db.set_table_data("fx_rates", [])
    fx = FakeFxRateAdapter(bulletins={date(2026, 9, 11): Decimal("5.43210")})  # a Friday
    conversion = fx_service.conversion_for(db, fx, "USD", date(2026, 9, 13))  # Sunday
    assert (conversion.pending, conversion.fx_rate, conversion.fx_quote_date) == (
        False, Decimal("5.43210"), date(2026, 9, 11))
    assert db.table("fx_rates").inserted_payloads[0]["quote_date"] == "2026-09-11"
    # Second lookup uses the stored row, not the adapter.
    fx_service.conversion_for(db, fx, "USD", date(2026, 9, 13))
    assert fx.lookups == [date(2026, 9, 13)]


def test_no_bulletin_is_pending_never_a_default_rate():
    db = MockSupabaseClient()
    db.set_table_data("fx_rates", [])
    conversion = fx_service.conversion_for(db, FakeFxRateAdapter(), "USD", date(2026, 9, 13))
    assert conversion.pending is True and conversion.to_brl(Decimal("1")) is None


def test_brl_needs_no_rate_and_unknown_currency_raises():
    db = MockSupabaseClient()
    assert fx_service.conversion_for(db, None, "BRL", date.today()).pending is False
    with pytest.raises(ValueError):
        fx_service.conversion_for(db, None, "EUR", date.today())


def test_pending_payment_is_priced_once_the_bulletin_exists():
    db = MockSupabaseClient()
    db.set_table_data("fx_rates", [])
    db.set_table_data("billing_payments", [{
        "id": "p1", "currency": "USD", "gross_cents": 1000, "fee_cents": 59,
        "created_at": "2026-09-16T10:00:00+00:00", "fx_pending": True,
    }])
    assert fx_service.resolve_pending_payments(db, FakeFxRateAdapter()) == 0
    fx = FakeFxRateAdapter(bulletins={date(2026, 9, 16): Decimal("5.00000")})
    assert fx_service.resolve_pending_payments(db, fx) == 1
    row = db.table("billing_payments").select("*").execute().data[0]
    assert (row["gross_brl"], row["fee_brl"], row["fx_pending"]) == ("50.00", "2.95", False)


# ── storage cost ─────────────────────────────────────────────────────────


def test_daily_storage_cost_prorates_the_monthly_price():
    cost = storage_cost_service.daily_cost_usd(30 * 1024 ** 3, Decimal("0.030"), date(2026, 9, 1))
    assert cost == Decimal("0.030000")  # 30 GiB × $0.03 / 30 days


def test_storage_snapshot_books_org_rows_once_and_skips_unattributed():
    ctx, fakes = make_ctx(ptax={date(2026, 9, 16): Decimal("5.00000")}, storage_price="0.030")
    fakes.db.set_table_data("fx_rates", [])
    fakes.db.set_table_data("cost_ledger", [])
    fakes.db.set_table_data("storage_usage_snapshots", [])
    fakes.db.set_rpc_data("storage_usage_by_prefix", [
        {"bucket_id": "edicao-fotos", "org_id": ORG_ID, "total_bytes": 30 * 1024 ** 3},
        {"bucket_id": "public-assets", "org_id": None, "total_bytes": 5 * 1024 ** 3},
    ])
    report = storage_cost_service.snapshot_storage_costs(ctx)
    assert (report.buckets, report.booked, report.unattributed_bytes) == (2, 1, 5 * 1024 ** 3)
    entry = fakes.db.table("cost_ledger").inserted_payloads[0]
    assert entry["currency"] == "USD" and entry["category"] == "supabase_storage"
    assert Decimal(entry["amount_native"]) == Decimal("0.030000")
    assert Decimal(entry["amount_brl"]) == Decimal("0.150000")
    again = storage_cost_service.snapshot_storage_costs(ctx)
    assert again.booked == 0 and again.already_booked == 1


def test_storage_snapshot_without_a_price_books_nothing():
    ctx, fakes = make_ctx(storage_price=None)
    fakes.db.set_table_data("storage_usage_snapshots", [])
    fakes.db.set_table_data("cost_ledger", [])
    fakes.db.set_rpc_data("storage_usage_by_prefix", [
        {"bucket_id": "b", "org_id": ORG_ID, "total_bytes": 10}])
    report = storage_cost_service.snapshot_storage_costs(ctx)
    assert report.skipped_reason and report.booked == 0
    assert fakes.db.table("cost_ledger").inserted_payloads == []


# ── MRR ──────────────────────────────────────────────────────────────────


def test_mrr_counts_paying_statuses_only_and_normalizes_yearly():
    rows = [
        {"status": "active", "amount_cents": 120000, "billing_cycle": "yearly", "currency": "BRL"},
        {"status": "past_due", "amount_cents": 5000, "billing_cycle": "monthly", "currency": "BRL"},
        {"status": "trial", "amount_cents": 9900, "billing_cycle": "monthly", "currency": "BRL"},
        {"status": "canceled", "amount_cents": 9900, "currency": "BRL"},
        {"status": "active", "plan_id": "legacy-plan"},
        {"status": "active", "amount_cents": 1000, "billing_cycle": "monthly", "currency": "USD"},
    ]
    result = billing_metrics.compute_mrr(rows, {"legacy-plan": 30})
    assert result.mrr_brl == Decimal("180")  # 100 + 50 + 30
    assert result.non_brl == {"USD": Decimal("10")}
    assert result.counted == 4


def test_mrr_reads_past_the_postgrest_row_cap():
    db = MockSupabaseClient()
    db.set_table_data("subscriptions", [
        {"id": f"s{i:05d}", "status": "active", "amount_cents": 100, "billing_cycle": "monthly", "currency": "BRL"}
        for i in range(1500)
    ])
    db.set_table_data("plans", [])
    assert billing_metrics.current_mrr(db).mrr_brl == Decimal("1500")


# ── price guard + small pieces ──────────────────────────────────────────


def test_price_guard_rejects_inactive_and_wrong_audience():
    db = MockSupabaseClient()
    seed_catalog(db, audience="company")
    with pytest.raises(subs.BillingError) as info:
        subs.validate_price_for_org_type(db, PRICE_ID, "individual")
    assert info.value.status_code == 422
    assert subs.validate_price_for_org_type(db, PRICE_ID, "company")["plan"]["id"] == PLAN_ID
    with pytest.raises(subs.BillingError) as missing:
        subs.validate_price_for_org_type(db, "nope", "company")
    assert missing.value.status_code == 404


@pytest.mark.parametrize(
    "start,cycle,expected",
    [(date(2026, 1, 31), "monthly", date(2026, 2, 28)),
     (date(2026, 12, 15), "monthly", date(2027, 1, 15)),
     (date(2028, 2, 29), "yearly", date(2029, 2, 28))],
)
def test_add_cycle_clamps_month_end(start, cycle, expected):
    assert subs.add_cycle(start, cycle) == expected


def test_failed_checkout_closes_the_pending_row():
    from noctusai_lib.integrations.payments import PaymentGatewayError

    class _Refusing:
        name = "stripe"

        def create_checkout(self, request):
            raise PaymentGatewayError("stripe", "No such price", status=400)

    ctx, fakes = make_ctx()
    seed_catalog(fakes.db)
    fakes.db.set_table_data("subscriptions", [])
    fakes.db.set_table_data("licenses", [])
    ctx.checkout_factory = lambda gateway, mode: _Refusing()
    with pytest.raises(subs.BillingError) as info:
        subs.start_checkout(ctx, org_id=ORG_ID, payer_email="o@a.com", plan_price_id=PRICE_ID,
                            gateway="stripe", billing_method="card", tax_id=None,
                            success_url="https://x/s", cancel_url="https://x/c")
    assert info.value.status_code == 502
    row = fakes.db.table("subscriptions").select("*").execute().data[0]
    assert row["status"] == "canceled"
    assert fakes.db.table("licenses").inserted_payloads == []


def test_unmanaged_rows_are_refused_by_apply_status():
    ctx, fakes = make_ctx()
    with pytest.raises(subs.UnmanagedSubscription):
        subs.apply_status(ctx, {"id": "x", "status": "active", "automation_managed": False}, "canceled")
