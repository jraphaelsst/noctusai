"""Unit tests for the PF monthly financial narrative service (Phase 10)."""
import pytest
from unittest.mock import AsyncMock, patch

from noctusai_lib.integrations.email.digest import DigestSendResult


class TestAggregatePeriod:
    def test_splits_receita_despesa_and_groups_by_categoria(self):
        from app.services.monthly_narrative_service import _aggregate_period
        rows = [
            {"valor": 1000, "tipo": "receita", "categoria": {"nome": "Salário"}},
            {"valor": 500, "tipo": "despesa", "categoria": {"nome": "Alimentação"}},
            {"valor": 200, "tipo": "despesa", "categoria": {"nome": "Alimentação"}},
            {"valor": 300, "tipo": "despesa", "categoria": {"nome": "Transporte"}},
            {"valor": 100, "tipo": "despesa", "categoria": None},  # → "Sem categoria"
        ]
        receita, despesa, by_cat, count = _aggregate_period(rows)
        assert receita == 1000.0
        assert despesa == 1100.0
        assert by_cat["Alimentação"] == 700.0
        assert by_cat["Transporte"] == 300.0
        assert by_cat["Sem categoria"] == 100.0
        assert count == 5

    def test_empty_returns_zeros(self):
        from app.services.monthly_narrative_service import _aggregate_period
        receita, despesa, by_cat, count = _aggregate_period([])
        assert receita == 0.0
        assert despesa == 0.0
        assert by_cat == {}
        assert count == 0


class TestBuildNarrative:
    @pytest.mark.asyncio
    async def test_happy_path_assembles_digest_and_summary(self):
        from app.services import monthly_narrative_service

        async def _fake_fetch(db, org_id, period_days):
            return (
                [
                    {"valor": 5000, "tipo": "receita", "categoria": {"nome": "Salário"}},
                    {"valor": 1500, "tipo": "despesa", "categoria": {"nome": "Aluguel"}},
                    {"valor": 800, "tipo": "despesa", "categoria": {"nome": "Mercado"}},
                ],
                {"id": org_id, "nome": "Família"},
            )

        with patch(
            "app.services.monthly_narrative_service._fetch_window",
            side_effect=_fake_fetch,
        ), patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
            return_value="Panorama.\n\nObservações.\n\nDica.",
        ):
            digest, summary = await monthly_narrative_service.build_narrative(
                db=object(), org_id="org-1", period_days=30
            )
        assert "Família" in digest.subject
        assert "Panorama." in digest.html
        assert summary["receita_total"] == 5000.0
        assert summary["despesa_total"] == 2300.0
        assert summary["fluxo_liquido"] == 2700.0
        assert summary["taxa_poupanca"] == 54.0
        assert summary["top_categorias"][0]["nome"] == "Aluguel"

    @pytest.mark.asyncio
    async def test_zero_receita_yields_zero_savings_rate(self):
        from app.services import monthly_narrative_service

        async def _fake_fetch(db, org_id, period_days):
            return (
                [{"valor": 100, "tipo": "despesa", "categoria": {"nome": "X"}}],
                {"id": org_id, "nome": "Org"},
            )

        with patch(
            "app.services.monthly_narrative_service._fetch_window",
            side_effect=_fake_fetch,
        ), patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
            return_value="Resumo",
        ):
            _, summary = await monthly_narrative_service.build_narrative(
                db=object(), org_id="org-1"
            )
        assert summary["taxa_poupanca"] == 0.0

    @pytest.mark.asyncio
    async def test_llm_failure_uses_template_fallback(self):
        from app.services import monthly_narrative_service

        async def _fake_fetch(db, org_id, period_days):
            return (
                [{"valor": 100, "tipo": "receita", "categoria": None}],
                {"id": org_id, "nome": "Org"},
            )

        with patch(
            "app.services.monthly_narrative_service._fetch_window",
            side_effect=_fake_fetch,
        ), patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ):
            _, summary = await monthly_narrative_service.build_narrative(
                db=object(), org_id="org-1"
            )
        assert "LLM indisponível" in summary["narrative"]


class TestSendMonthlyNarrative:
    @pytest.mark.asyncio
    async def test_passes_through_send_digest_result(self):
        from app.services import monthly_narrative_service

        async def _fake_fetch(db, org_id, period_days):
            return ([], {"id": org_id, "nome": "Org"})

        with patch(
            "app.services.monthly_narrative_service._fetch_window",
            side_effect=_fake_fetch,
        ), patch(
            "noctusai_lib.domain.digest.narrative.chat_completion",
            new_callable=AsyncMock,
            return_value="Narrativa.",
        ), patch(
            "noctusai_lib.domain.digest.orchestrate.send_digest",
            new_callable=AsyncMock,
            return_value=DigestSendResult(sent=True, external_id="abc", subject="x"),
        ):
            result = await monthly_narrative_service.send_monthly_narrative(
                db=object(), org_id="org-1", recipient="user@x.com"
            )
        assert result["sent"] is True
        assert result["external_id"] == "abc"
        assert "summary" in result
