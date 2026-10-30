"""AI credit wallet services: the pricing formula, the per-minute debit
(idempotent, BYOK, charge_from), grants on the purchase path, alerts, and the
purchase webhooks. DI only (`BillingContext.credit_ledger`)."""
from __future__ import annotations

from decimal import Decimal

import pytest

from app.services.credits import debit, purchases, reports, wallets
from app.services.credits.pricing import Pricing, credits_for_usd_grant, gross_margin, load_pricing, price_usage
from tests.billing_fakes import NOW
from tests.credits_fakes import ADMIN_USER, ORG_ID, OTHER_ORG_ID, OWNER_USER, PRICING_V1, credits_ctx, usage_row, wallet_row


def _wallet(fakes, org=ORG_ID):
    return next(w for w in fakes.db.table("credit_wallets").select("*").execute().data if w["org_id"] == org)


def _entries(fakes):
    return fakes.db.table("credit_entries").select("*").execute().data


# ── pricing ─────────────────────────────────────────────────────────────


def test_price_formula_matches_the_owner_spec():
    p = Pricing.from_row(PRICING_V1)
    priced = price_usage("1", "5.00", p)
    # 1 × (5.00 + 0.10) × (1 + 0.035) ÷ (1 − 0.06 − 0.0399) × (1 + 1.0)
    expected = Decimal("1") * Decimal("5.10") * Decimal("1.035") / Decimal("0.9001") * 2
    assert priced.price_brl == expected.quantize(Decimal("0.000001"))
    assert priced.credits == (priced.price_brl / Decimal("0.01")).quantize(Decimal("0.000001"))
    assert priced.provider_cost_brl == Decimal("5.000000")


def test_seeded_pricing_clears_the_margin_floor_not_cost_plus_one():
    margin = gross_margin(Pricing.from_row(PRICING_V1))
    assert margin >= Decimal("0.45")  # ≈ 0.48 at PTAX 5.50 after IOF + Simples + gateway


def test_usd_grant_is_retail_value_without_markup():
    p = Pricing.from_row(PRICING_V1)
    assert credits_for_usd_grant(100, "5.00", p) == Decimal("50000")  # R$500 / R$0.01


def test_load_pricing_picks_the_latest_effective_version():
    ctx, fakes = credits_ctx()
    fakes.db.set_table_data("credit_pricing", [
        dict(PRICING_V1),
        {**PRICING_V1, "id": "p2", "version": 2, "margin": "1.5", "effective_from": "2026-09-01T00:00:00+00:00"},
        {**PRICING_V1, "id": "p3", "version": 3, "margin": "9", "effective_from": "2027-01-01T00:00:00+00:00"},
    ])
    assert load_pricing(fakes.db, at=NOW).version == 2


# ── debit ───────────────────────────────────────────────────────────────


def test_debit_charges_uncharged_rows_once():
    ctx, fakes = credits_ctx()
    fakes.db.set_table_data("credit_wallets", [wallet_row(balance_credits=100000, alert_base_credits=100000)])
    fakes.db.set_table_data("ai_usage", [usage_row(1), usage_row(2, cost_usd="0.5")])
    first = debit.run_debit(ctx)
    assert (first.applied, first.duplicates, first.errors) == (2, 0, [])
    expected = price_usage("1.0", "5", load_pricing(fakes.db)).credits + price_usage("0.5", "5", load_pricing(fakes.db)).credits
    assert Decimal(str(_wallet(fakes)["balance_credits"])) == Decimal(100000) - expected
    rows = fakes.db.table("ai_usage").select("*").execute().data
    assert all(r["charged_credits"] is not None for r in rows)
    second = debit.run_debit(ctx)  # idempotent: nothing left un-charged
    assert (second.rows, second.applied) == (0, 0)
    assert len([e for e in _entries(fakes) if e["kind"] == "usage_debit"]) == 2


def test_debit_replay_of_the_same_row_is_a_duplicate_not_a_double_charge():
    ctx, fakes = credits_ctx()
    fakes.db.set_table_data("credit_wallets", [wallet_row(balance_credits=1000)])
    fakes.db.set_table_data("ai_usage", [usage_row(1)])
    debit.run_debit(ctx)
    # simulate a crash between the entry and the stamp: the row reads un-charged again
    fakes.db.table("ai_usage").update({"charged_credits": None}).eq("id", 1).execute()
    again = debit.run_debit(ctx)
    assert (again.applied, again.duplicates) == (0, 1)
    assert len(_entries(fakes)) == 1


def test_debit_ignores_orgs_without_a_wallet_and_rows_before_charge_from():
    ctx, fakes = credits_ctx()
    fakes.db.set_table_data("credit_wallets", [wallet_row(charge_from="2026-09-16T10:00:00+00:00")])
    fakes.db.set_table_data("ai_usage", [
        usage_row(1, created_at="2026-09-16T09:00:00+00:00"),  # before the wallet existed
        usage_row(2, org_id=OTHER_ORG_ID),  # no wallet
        usage_row(3),
    ])
    report = debit.run_debit(ctx)
    assert report.applied == 1
    rows = {r["id"]: r for r in fakes.db.table("ai_usage").select("*").execute().data}
    assert rows[1]["charged_credits"] is None and rows[2]["charged_credits"] is None
    assert rows[3]["charged_credits"] is not None


def test_byok_org_is_stamped_zero_with_source_byok():
    ctx, fakes = credits_ctx()
    fakes.db.set_table_data("credit_wallets", [wallet_row(mode="byok", balance_credits=0)])
    fakes.db.set_table_data("ai_usage", [usage_row(1)])
    report = debit.run_debit(ctx)
    assert (report.applied, report.byok) == (1, 1)
    (entry,) = _entries(fakes)
    assert (entry["source"], entry["credits"]) == ("byok", 0)
    assert float(fakes.db.table("ai_usage").select("*").execute().data[0]["charged_credits"]) == 0
    assert float(_wallet(fakes)["balance_credits"]) == 0


def test_debit_crossing_thresholds_alerts_org_admins_and_platform_admins():
    ctx, fakes = credits_ctx()
    wallets.grant(ctx, ORG_ID, credits=Decimal("2000"), reason="teste", actor=ADMIN_USER)
    fakes.db.set_table_data("ai_usage", [  # ≈ 1173 credits → 58% consumed
        usage_row(1, cost_usd="1.0", created_at="2026-09-16T12:00:30+00:00")])
    debit.run_debit(ctx)
    notes = fakes.db.table("notifications").select("*").execute().data
    assert {n["user_id"] for n in notes} == {OWNER_USER, ADMIN_USER}
    assert all("50%" in n["title"] for n in notes)


# ── grants ──────────────────────────────────────────────────────────────


def test_grant_goes_through_the_same_ledger_path_as_a_purchase():
    ctx, fakes = credits_ctx()
    out = wallets.grant(ctx, ORG_ID, usd=Decimal("100"), reason="US$100 de teste", actor=ADMIN_USER)
    assert out["credits"] == 50000.0
    (applied,) = ctx.credit_ledger.applied
    assert (applied.kind, applied.source, applied.usd_amount) == ("grant", "admin_grant", Decimal("100"))
    w = _wallet(fakes)
    assert float(w["balance_credits"]) == 50000 and float(w["alert_base_credits"]) == 50000


def test_grant_requires_exactly_one_amount_and_a_reason():
    ctx, _ = credits_ctx()
    with pytest.raises(wallets.CreditsError):
        wallets.grant(ctx, ORG_ID, credits=Decimal(1), usd=Decimal(1), reason="x", actor=ADMIN_USER)
    with pytest.raises(wallets.CreditsError):
        wallets.grant(ctx, ORG_ID, credits=Decimal(1), reason="  ", actor=ADMIN_USER)


def test_adjustment_is_signed_and_never_zero():
    ctx, fakes = credits_ctx()
    wallets.adjust(ctx, ORG_ID, credits=Decimal("-10"), reason="correção", actor=ADMIN_USER)
    assert float(_wallet(fakes)["balance_credits"]) == -10
    with pytest.raises(wallets.CreditsError):
        wallets.adjust(ctx, ORG_ID, credits=Decimal(0), reason="x", actor=ADMIN_USER)


def test_update_settings_validates_mode():
    ctx, _ = credits_ctx()
    with pytest.raises(wallets.CreditsError):
        wallets.update_settings(ctx, ORG_ID, mode="free")
    w = wallets.update_settings(ctx, ORG_ID, mode="byok", actor=ADMIN_USER)
    assert w["mode"] == "byok"


# ── purchases ───────────────────────────────────────────────────────────


def test_purchase_opens_a_one_off_pix_charge_and_credits_only_on_the_paid_webhook():
    ctx, fakes = credits_ctx()
    out = purchases.start_purchase(
        ctx, org_id=ORG_ID, amount_brl=Decimal("100"), gateway="asaas", billing_method="pix",
        payer_email="owner@a.com", tax_id="12345678909", actor=OWNER_USER,
        success_url="https://core.example.com/creditos", cancel_url="https://core.example.com/creditos",
    )
    assert out["credits"] == 10000.0
    (req,) = [arg for name, arg in fakes.checkouts["asaas"].calls if name == "create_checkout"]
    assert req.billing_cycle is None and req.external_reference == f"credits:{out['purchase_id']}"
    assert _entries(fakes) == []  # nothing credited before payment

    payment = {"id": "pay_c1", "externalReference": req.external_reference, "value": 100.0,
               "paymentDate": "2026-09-16"}
    status, org = purchases.handle_asaas_payment(ctx, "PAYMENT_RECEIVED", payment)
    assert (status, org) == ("applied", ORG_ID)
    assert float(_wallet(fakes)["balance_credits"]) == 10000
    # a replay with the same payment id is a no-op
    status, _ = purchases.handle_asaas_payment(ctx, "PAYMENT_RECEIVED", payment)
    assert status == "duplicate"
    assert float(_wallet(fakes)["balance_credits"]) == 10000
    assert fakes.db.table("credit_purchases").select("*").execute().data[0]["status"] == "paid"


def test_underpaid_purchase_is_not_credited():
    ctx, fakes = credits_ctx()
    out = purchases.start_purchase(
        ctx, org_id=ORG_ID, amount_brl=Decimal("100"), gateway="asaas", billing_method="boleto",
        payer_email="o@a.com", tax_id="12345678909", actor=OWNER_USER,
        success_url="https://x/", cancel_url="https://x/",
    )
    status, _ = purchases.handle_asaas_payment(ctx, "PAYMENT_RECEIVED", {
        "id": "pay_low", "externalReference": f"credits:{out['purchase_id']}", "value": 50.0})
    assert status == "underpaid" and _entries(fakes) == []


def test_byok_org_cannot_buy_credits():
    ctx, fakes = credits_ctx()
    fakes.db.set_table_data("credit_wallets", [wallet_row(mode="byok")])
    with pytest.raises(wallets.CreditsError) as exc:
        purchases.start_purchase(
            ctx, org_id=ORG_ID, amount_brl=Decimal("100"), gateway="asaas", billing_method="pix",
            payer_email="o@a.com", tax_id="12345678909", actor=OWNER_USER,
            success_url="https://x/", cancel_url="https://x/",
        )
    assert exc.value.status_code == 409


def test_non_credit_payments_are_not_ours():
    ctx, _ = credits_ctx()
    assert purchases.handle_asaas_payment(ctx, "PAYMENT_RECEIVED", {"id": "p", "subscription": "s"}) is None
    assert purchases.handle_stripe_checkout(ctx, {"id": "cs", "metadata": {"subscription_id": "x"}}) is None


# ── reports ─────────────────────────────────────────────────────────────


def test_org_usage_breaks_down_product_then_feature_and_hides_cost():
    ctx, fakes = credits_ctx()
    fakes.db.set_table_data("credit_wallets", [wallet_row(balance_credits=100000)])
    fakes.db.set_table_data("ai_usage", [
        usage_row(1, product="erp-imobiliario", feature="chat"),
        usage_row(2, product="erp-imobiliario", feature="resumo"),
        usage_row(3, product="social-wiring", feature="legenda"),
        usage_row(4, org_id=OTHER_ORG_ID),
    ])
    debit.run_debit(ctx)
    pricing = load_pricing(fakes.db)
    data = reports.org_usage(fakes.db, ORG_ID, start=NOW.replace(day=1), end=NOW, pricing=pricing)
    assert data["totals"]["calls"] == 3
    erp = next(p for p in data["per_product"] if p["product"] == "erp-imobiliario")
    assert {f["feature"] for f in erp["per_feature"]} == {"chat", "resumo"}
    assert erp["brl"] == round(erp["credits"] * 0.01, 2)
    assert "provider_cost_brl" not in str(data)


def test_margin_report_compares_revenue_with_provider_cost():
    ctx, fakes = credits_ctx()
    fakes.db.set_table_data("credit_wallets", [wallet_row(balance_credits=100000)])
    fakes.db.set_table_data("ai_usage", [usage_row(1)])
    debit.run_debit(ctx)
    rep = reports.margin_report(fakes.db, start=NOW.replace(day=1), end=NOW.replace(year=2030))
    (org,) = rep["per_org"]
    assert org["provider_cost_brl"] == 5.0
    assert org["revenue_brl"] > 2 * org["provider_cost_brl"]
    assert org["gross_margin_pct"] > 0.5
