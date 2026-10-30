"""Unit tests for `noctusai_lib.llm.budget` (Phase 18 X4)."""
from __future__ import annotations

import os
import pytest
from unittest.mock import MagicMock

from noctusai_lib.integrations.llm import budget as budget_module
from noctusai_lib.integrations.llm.budget import (
    compute_status,
    configure_budget_module,
    enforce_budget,
    fetch_budget_brl,
)
from noctusai_lib.integrations.llm.exceptions import LLMBudgetExceeded


@pytest.fixture(autouse=True)
def _reset_module():
    """Reset module-level state + threshold env vars between tests."""
    configure_budget_module(admin_client_factory=None)
    for key in ("LLM_BUDGET_SOFT_PCT", "LLM_BUDGET_HARD_PCT", "LLM_USD_TO_BRL"):
        os.environ.pop(key, None)
    yield
    configure_budget_module(admin_client_factory=None)


def _build_admin(*, settings_rows=None, usage_by_schema=None):
    """Return a mock admin client with chainable .table()/.schema() builders.

    `settings_rows` mocks the `org_settings` SELECT response shape.
    `usage_by_schema` is a `{product_schema: [{cost_estimate_usd: ...}, ...]}` dict —
    kept per product for readability; since D25 every product's rows live in ONE
    `public.ai_usage` ledger, so the fake serves their union (as `cost_usd`) there.
    """

    def admin():
        sb = MagicMock()
        # org_settings select chain.
        org_settings_chain = MagicMock()
        org_settings_chain.select.return_value = org_settings_chain
        org_settings_chain.eq.return_value = org_settings_chain
        org_settings_chain.limit.return_value = org_settings_chain
        org_settings_chain.execute.return_value = MagicMock(data=settings_rows or [])

        # default db.table('<x>') for non-schema lookups.
        sb.table.return_value = org_settings_chain

        # db.schema('<schema>') chain.
        def schema(name):
            schema_obj = MagicMock()

            def table(_table_name):
                if _table_name == "org_settings":
                    assert name == "public", "budget storage is public.org_settings"
                    return org_settings_chain
                t = MagicMock()
                t.select.return_value = t
                t.eq.return_value = t
                t.gte.return_value = t
                t.lte.return_value = t
                t.limit.return_value = t
                t.order.return_value = t
                # The spend read is paged (`.order("id").range(a, b)`), so the fake honours the
                # inclusive range the way PostgREST does; rows get ids to order by.
                assert (name, _table_name) == ("public", "ai_usage"), "spend reads the central ledger"
                ledger = [r for rows_ in (usage_by_schema or {}).values() for r in rows_]
                rows = [
                    {"id": f"{i:06d}", "cost_usd": r["cost_estimate_usd"], "cost_brl": r.get("cost_brl")}
                    for i, r in enumerate(ledger)
                ]

                def _range(start, end):
                    t.execute.return_value = MagicMock(data=rows[start : end + 1])
                    return t

                t.range.side_effect = _range
                t.execute.return_value = MagicMock(data=rows)
                return t

            schema_obj.table.side_effect = table
            return schema_obj

        sb.schema.side_effect = schema
        return sb

    return admin


class TestMissingBudgetTable:
    @pytest.fixture(autouse=True)
    def _fresh(self):
        budget_module._reset_config_error_for_tests()

    @staticmethod
    def _admin_raising(message):
        def admin():
            sb = MagicMock()
            chain = MagicMock()
            for m in ("select", "eq", "limit"):
                getattr(chain, m).return_value = chain
            chain.execute.side_effect = Exception(message)
            sb.schema.return_value.table.return_value = chain
            return sb
        return admin

    @pytest.mark.asyncio
    async def test_reads_public_schema_not_the_product_schema(self):
        admin = _build_admin(settings_rows=[{"value": "100"}])
        configure_budget_module(admin_client_factory=admin)
        assert await fetch_budget_brl("org-1") == 100.0

    @pytest.mark.asyncio
    async def test_missing_table_is_a_configuration_error_not_no_budget(self):
        from noctusai_lib.integrations.llm.exceptions import LLMBudgetNotConfigured
        configure_budget_module(admin_client_factory=self._admin_raising(
            "PGRST205 Could not find the table 'x.org_settings'"))
        with pytest.raises(LLMBudgetNotConfigured):
            await fetch_budget_brl("org-1")
        with pytest.raises(LLMBudgetNotConfigured):
            await enforce_budget("org-1")

    @pytest.mark.asyncio
    async def test_missing_table_logs_error_once_per_process(self, caplog):
        from noctusai_lib.integrations.llm.exceptions import LLMBudgetNotConfigured
        configure_budget_module(admin_client_factory=self._admin_raising("PGRST205 boom"))
        with caplog.at_level("ERROR"):
            for _ in range(3):
                with pytest.raises(LLMBudgetNotConfigured):
                    await fetch_budget_brl("org-1")
        assert len([r for r in caplog.records if r.levelname == "ERROR"]) == 1

    @pytest.mark.asyncio
    async def test_transient_error_stays_fail_open(self):
        configure_budget_module(admin_client_factory=self._admin_raising("connection reset"))
        assert await fetch_budget_brl("org-1") is None
        await enforce_budget("org-1")


class TestFetchBudgetBrl:
    @pytest.mark.asyncio
    async def test_returns_none_when_module_not_configured(self):
        assert await fetch_budget_brl("org-1") is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_setting_row(self):
        configure_budget_module(admin_client_factory=_build_admin(settings_rows=[]))
        assert await fetch_budget_brl("org-1") is None

    @pytest.mark.asyncio
    async def test_parses_string_value_to_float(self):
        configure_budget_module(
            admin_client_factory=_build_admin(settings_rows=[{"value": "500.00"}])
        )
        assert await fetch_budget_brl("org-1") == 500.0

    @pytest.mark.asyncio
    async def test_returns_none_on_malformed_value(self):
        configure_budget_module(
            admin_client_factory=_build_admin(settings_rows=[{"value": "not-a-number"}])
        )
        assert await fetch_budget_brl("org-1") is None


class TestComputeStatus:
    @pytest.mark.asyncio
    async def test_unset_when_no_budget(self):
        configure_budget_module(admin_client_factory=_build_admin(settings_rows=[]))
        s = await compute_status("org-1")
        assert s["status"] == "unset"
        assert s["budget_brl"] == 0.0
        assert s["spent_brl"] == 0.0

    @pytest.mark.asyncio
    async def test_ok_under_soft_threshold(self):
        os.environ["LLM_USD_TO_BRL"] = "5"
        configure_budget_module(
            admin_client_factory=_build_admin(
                settings_rows=[{"value": "1000"}],   # 1000 BRL budget
                usage_by_schema={"erp": [{"cost_estimate_usd": 50}]},  # 50 USD = 250 BRL
            )
        )
        s = await compute_status("org-1")
        assert s["budget_brl"] == 1000.0
        assert s["spent_brl"] == 250.0
        assert s["used_pct"] == 0.25
        assert s["status"] == "ok"

    @pytest.mark.asyncio
    async def test_warn_above_soft(self):
        os.environ["LLM_USD_TO_BRL"] = "5"
        configure_budget_module(
            admin_client_factory=_build_admin(
                settings_rows=[{"value": "1000"}],
                # 170 USD * 5 = 850 BRL = 85% (above 80%, below 100%)
                usage_by_schema={"erp": [{"cost_estimate_usd": 170}]},
            )
        )
        s = await compute_status("org-1")
        assert s["status"] == "warn"

    @pytest.mark.asyncio
    async def test_hard_stop_at_or_above_100pct(self):
        os.environ["LLM_USD_TO_BRL"] = "5"
        configure_budget_module(
            admin_client_factory=_build_admin(
                settings_rows=[{"value": "1000"}],
                # 250 USD * 5 = 1250 BRL = 125% → hard_stop
                usage_by_schema={"erp": [{"cost_estimate_usd": 250}]},
            )
        )
        s = await compute_status("org-1")
        assert s["status"] == "hard_stop"

    @pytest.mark.asyncio
    async def test_aggregates_multiple_product_schemas(self):
        os.environ["LLM_USD_TO_BRL"] = "5"
        configure_budget_module(
            admin_client_factory=_build_admin(
                settings_rows=[{"value": "1000"}],
                usage_by_schema={
                    "erp": [{"cost_estimate_usd": 50}, {"cost_estimate_usd": 50}],
                    "therapy": [{"cost_estimate_usd": 100}],
                },
            )
        )
        s = await compute_status("org-1")
        # 200 USD * 5 = 1000 BRL = 100% → hard_stop (>= 1.0)
        assert s["spent_brl"] == 1000.0
        assert s["status"] == "hard_stop"

    @pytest.mark.asyncio
    async def test_thresholds_overridable_via_env(self):
        os.environ["LLM_USD_TO_BRL"] = "5"
        os.environ["LLM_BUDGET_SOFT_PCT"] = "0.5"
        os.environ["LLM_BUDGET_HARD_PCT"] = "0.9"
        configure_budget_module(
            admin_client_factory=_build_admin(
                settings_rows=[{"value": "1000"}],
                # 100 USD * 5 = 500 BRL = 50% → warn (>= 0.5 soft)
                usage_by_schema={"erp": [{"cost_estimate_usd": 100}]},
            )
        )
        s = await compute_status("org-1")
        assert s["soft_pct"] == 0.5
        assert s["hard_pct"] == 0.9
        assert s["status"] == "warn"


class TestEnforceBudget:
    @pytest.mark.asyncio
    async def test_no_op_when_module_unconfigured(self):
        await enforce_budget("org-1")  # does not raise

    @pytest.mark.asyncio
    async def test_no_op_when_org_id_none(self):
        configure_budget_module(admin_client_factory=_build_admin(settings_rows=[]))
        await enforce_budget(None)  # does not raise

    @pytest.mark.asyncio
    async def test_no_op_when_unset(self):
        configure_budget_module(admin_client_factory=_build_admin(settings_rows=[]))
        await enforce_budget("org-1")  # status=unset → silent

    @pytest.mark.asyncio
    async def test_warns_silently_at_soft(self, caplog):
        os.environ["LLM_USD_TO_BRL"] = "5"
        configure_budget_module(
            admin_client_factory=_build_admin(
                settings_rows=[{"value": "1000"}],
                usage_by_schema={"erp": [{"cost_estimate_usd": 170}]},
            )
        )
        import logging
        with caplog.at_level(logging.WARNING):
            await enforce_budget("org-1")  # status=warn → logs, no raise
        assert any("budget.warn" in rec.message for rec in caplog.records)

    @pytest.mark.asyncio
    async def test_raises_at_hard(self):
        os.environ["LLM_USD_TO_BRL"] = "5"
        configure_budget_module(
            admin_client_factory=_build_admin(
                settings_rows=[{"value": "1000"}],
                usage_by_schema={"erp": [{"cost_estimate_usd": 250}]},
            )
        )
        with pytest.raises(LLMBudgetExceeded) as exc_info:
            await enforce_budget("org-1")
        assert exc_info.value.details["org_id"] == "org-1"
        assert exc_info.value.details["spent_brl"] == 1250.0
        assert exc_info.value.status_code == 429

    @pytest.mark.asyncio
    async def test_fails_open_on_db_error(self):
        # Admin factory raises → enforce_budget swallows + logs.
        def raising():
            raise RuntimeError("DB down")

        configure_budget_module(admin_client_factory=raising)
        await enforce_budget("org-1")  # does not raise


class TestLedgerBrl:
    @pytest.mark.asyncio
    async def test_prefers_the_row_cost_brl_over_the_env_rate(self):
        os.environ["LLM_USD_TO_BRL"] = "5"
        configure_budget_module(
            admin_client_factory=_build_admin(
                settings_rows=[{"value": "1000"}],
                # priced at PTAX 5.5 at write time → 55 BRL, not 50 USD x 5
                usage_by_schema={"any": [{"cost_estimate_usd": 10, "cost_brl": 55}]},
            )
        )
        s = await compute_status("org-1")
        assert s["spent_brl"] == 55.0
