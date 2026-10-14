"""Pure P4 units: installment math (D33/D41), fulfillment lifecycle hooks, the money DDL generator, profile rules."""
from __future__ import annotations

import pytest

from noctusai_lib.domain.commerce import (
    COMMERCE_MONEY_TABLES,
    CommerceConfig,
    CommerceError,
    FulfillmentType,
    commerce_money_migration,
    installments as inst,
    make_fulfillment_registry,
    profile,
)

from .conftest import CFG, ORG_A, USER_ID, seed_profile


class TestInstallmentMath:
    def test_split_last_absorbs_the_remainder(self):
        assert inst.split_installments(10000, 3) == [3333, 3333, 3334]
        assert inst.split_installments(100, 1) == [100]
        for total in (1, 99, 12345, 999999):
            for n in range(1, 13):
                assert sum(inst.split_installments(total, n)) == total

    def test_price_table_known_values(self):
        # R$ 1.000,00 in 6x at 1.99 % a.m.: PMT = 1000*i/(1-(1+i)^-6) = 178.4655... -> total 1070.79
        assert inst.price_table_total(100000, 6, 199) == 107079
        assert inst.price_table_total(100000, 1, 199) == 100000
        assert inst.price_table_total(100000, 12, 0) == 100000

    def test_interest_free_up_to_the_limit_then_price_table(self):
        opts = inst.installment_options(100000, {"installments_max": 12, "installments_interest_free": 3, "installment_interest_monthly_bps": 199})
        assert [o["interest_free"] for o in opts[:5]] == [True, True, True, False, False]
        assert all(o["total_cents"] == 100000 for o in opts[:3])
        assert opts[3]["total_cents"] == inst.price_table_total(100000, 4, 199)
        totals = [o["total_cents"] for o in opts]
        assert totals == sorted(totals)  # more parcelas never cost less

    def test_options_below_the_gateway_minimum_are_not_offered(self):
        opts = inst.installment_options(2000, None)  # R$ 20: 2x = 10,00 ok ... 12x < 5,00 no
        assert opts[0]["count"] == 1 and max(o["count"] for o in opts) <= 4

    def test_nothing_to_quote_for_a_zero_total(self):
        assert inst.installment_options(0, None) == []

    def test_option_for_exact_count(self):
        assert inst.option_for(30000, 6, None)["count"] == 6
        assert inst.option_for(30000, 13, None) is None


class TestRateResolution:
    """D41: store value -> platform credential -> constant 199."""

    def test_store_value_wins(self):
        assert inst.resolve_interest_bps({"installment_interest_monthly_bps": 250}, resolver=lambda *_: "999") == 250
        assert inst.resolve_interest_bps({"installment_interest_monthly_bps": 0}, resolver=lambda *_: "999") == 0  # 0 is a value, not "unset"

    def test_null_store_value_follows_the_platform(self):
        seen = []

        def resolver(name, org):
            seen.append((name, org))
            return "175"

        assert inst.resolve_interest_bps({"installment_interest_monthly_bps": None}, resolver=resolver) == 175
        assert seen == [("commerce_installment_interest_bps", None)]  # PLATFORM tier

    def test_constant_is_the_floor(self):
        assert inst.resolve_interest_bps(None, resolver=lambda *_: None) == inst.DEFAULT_INSTALLMENT_INTEREST_BPS == 199

    @pytest.mark.parametrize("bad", ["abc", "-5", "99999", " "])
    def test_a_junk_platform_value_is_logged_and_skipped_never_priced(self, bad, caplog):
        assert inst.resolve_interest_bps({}, resolver=lambda *_: bad) == 199

    def test_a_failing_lookup_falls_to_the_constant(self):
        def boom(*_):
            raise RuntimeError("db down")

        assert inst.resolve_interest_bps({}, resolver=boom) == 199

    def test_changing_the_platform_value_affects_new_quotes_only(self):
        before = inst.installment_options(100000, {}, resolver=lambda *_: "100")
        after = inst.installment_options(100000, {}, resolver=lambda *_: "300")
        assert before[5]["total_cents"] < after[5]["total_cents"]


class Legacy:
    """A pre-P4 handler: only `on_paid`."""

    def __init__(self):
        self.paid = 0

    def on_paid(self, order, items):
        self.paid += 1


class TestFulfillmentLifecycle:
    ITEMS = [{"fulfillment_type": "digital_delivery"}, {"fulfillment_type": "shipping"}]

    def test_every_hook_defaults_to_noop_for_the_default_handler(self):
        reg = make_fulfillment_registry()
        for hook in (reg.dispatch_paused, reg.dispatch_resumed, reg.dispatch_revoked, reg.dispatch_expired):
            assert hook({"id": "o"}, self.ITEMS) == [FulfillmentType.DIGITAL_DELIVERY, FulfillmentType.SHIPPING]

    def test_a_pre_p4_handler_without_hooks_is_not_an_error(self):
        legacy = Legacy()
        reg = make_fulfillment_registry({FulfillmentType.DIGITAL_DELIVERY: legacy})
        reg.dispatch_revoked({"id": "o"}, self.ITEMS)
        reg.dispatch_paid({"id": "o"}, self.ITEMS)
        assert legacy.paid == 1

    def test_each_hook_routes_to_its_method_once_per_type(self):
        calls = []

        class H:
            def on_paid(self, o, i): ...

            def on_paused(self, o, i): calls.append("paused")
            def on_resumed(self, o, i): calls.append("resumed")
            def on_revoked(self, o, i): calls.append("revoked")
            def on_expired(self, o, i): calls.append("expired")

        reg = make_fulfillment_registry({FulfillmentType.DIGITAL_DELIVERY: H()})
        reg.dispatch_paused({}, self.ITEMS); reg.dispatch_resumed({}, self.ITEMS); reg.dispatch_revoked({}, self.ITEMS); reg.dispatch_expired({}, self.ITEMS)
        assert calls == ["paused", "resumed", "revoked", "expired"]


class TestMoneyDdl:
    SQL = commerce_money_migration(CFG, "commerce")

    def test_tables_have_org_id_and_rls_and_the_bypass(self):
        for t in COMMERCE_MONEY_TABLES:
            assert f"CREATE TABLE IF NOT EXISTS commerce.{t} (" in self.SQL
            assert f"ALTER TABLE commerce.{t} ENABLE ROW LEVEL SECURITY;" in self.SQL
            assert f'CREATE POLICY "service_role_bypass" ON commerce.{t}' in self.SQL
            block = self.SQL.split(f"CREATE TABLE IF NOT EXISTS commerce.{t} (")[1].split("\n);")[0]
            assert "org_id" in block

    def test_the_rpc_is_secdef_with_revoked_execute_and_a_pinned_search_path(self):
        assert "SECURITY DEFINER" in self.SQL and "SET search_path = pg_catalog, commerce, pg_temp" in self.SQL
        assert "REVOKE ALL ON FUNCTION commerce.commerce_create_refund(UUID, UUID, BIGINT, TEXT, UUID, TEXT) FROM PUBLIC, anon, authenticated;" in self.SQL
        assert "GRANT EXECUTE ON FUNCTION commerce.commerce_create_refund(UUID, UUID, BIGINT, TEXT, UUID, TEXT) TO service_role;" in self.SQL
        assert "FOR UPDATE" in self.SQL

    def test_no_fiscal_columns_here_that_is_slice_b2(self):
        for word in ("commerce_invoices", "nfse_mode", "inscricao_municipal", "invoice_company_ref", "certificate_"):
            assert word not in self.SQL

    def test_deterministic_and_schema_parametric(self):
        assert commerce_money_migration(CFG, "commerce") == self.SQL
        other = commerce_money_migration(CommerceConfig(schema="shop"), "shop")
        assert "shop.commerce_refunds" in other and "commerce.commerce_refunds" not in other

    def test_base_migration_is_untouched_so_the_host_012_parity_holds(self):
        from noctusai_lib.domain.commerce import commerce_migration

        base = commerce_migration(CFG, "commerce")
        assert "partially_refunded" not in base and "charge_attempts" not in base and "commerce_refunds" not in base


class TestProfileRules:
    def _body(self, db, **over):
        cur = profile.get_profile(db, ORG_A)
        base = {k: cur[k] for k in profile.PROFILE_FIELDS}
        return profile.put_profile(db, ORG_A, USER_ID, {**base, **over}, expected_version=cur["version"], is_platform_admin=False)

    def test_installment_settings_are_saved_and_validated(self, db):
        seed_profile(db)
        saved = self._body(db, installments_max=6, installments_interest_free=2, installment_interest_monthly_bps=None)
        assert (saved["installments_max"], saved["installments_interest_free"], saved["installment_interest_monthly_bps"]) == (6, 2, None)
        with pytest.raises(CommerceError) as exc:
            self._body(db, installments_max=2, installments_interest_free=5)
        assert exc.value.code == "parcelamento_invalido"

    def test_a_regime_change_clears_nfse_mode(self, db):
        """B2's CHECK forbids nfse_mode='municipal' under mei/simples: moving regime must reset it to NULL (regime default)."""
        from noctusai_lib.testing import _schema_cache

        cols = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
        cols["commerce.commerce_store_profiles"] = set(cols.get("commerce.commerce_store_profiles", set())) | {"nfse_mode"}
        cols["commerce_store_profiles"] = set(cols.get("commerce_store_profiles", set())) | {"nfse_mode"}
        _schema_cache.set_cache_for_tests(cols)
        seed_profile(db, tax_regime="lucro_presumido")
        db.table("commerce_store_profiles").update({"nfse_mode": "municipal"}).eq("org_id", ORG_A).execute()
        saved = self._body(db, tax_regime="simples")
        assert saved["tax_regime"] == "simples" and saved["nfse_mode"] is None

    def test_the_same_regime_keeps_nfse_mode(self, db):
        from noctusai_lib.testing import _schema_cache

        cols = {t: set(c) for t, c in _schema_cache.get_schema_map().items()}
        for key in ("commerce.commerce_store_profiles", "commerce_store_profiles"):
            cols[key] = set(cols.get(key, set())) | {"nfse_mode"}
        _schema_cache.set_cache_for_tests(cols)
        seed_profile(db, tax_regime="lucro_presumido")
        db.table("commerce_store_profiles").update({"nfse_mode": "municipal"}).eq("org_id", ORG_A).execute()
        saved = self._body(db, trade_name="Outro Nome")
        assert saved.get("nfse_mode") == "municipal"
