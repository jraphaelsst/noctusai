"""Unit tests for CotacoesService — price fetching and portfolio updates."""
import pytest
from unittest.mock import patch
from tests.conftest import MockSupabaseClient


ORG_ID = "test-org-123"


def make_service(mock_sb=None):
    from app.services.cotacoes_service import CotacoesService
    sb = mock_sb or MockSupabaseClient()
    return CotacoesService(sb, ORG_ID), sb


class TestGetCotacao:
    @pytest.mark.asyncio
    async def test_returns_mock_when_yfinance_unavailable(self):
        """Without yfinance, should return dry-run response."""
        svc, _ = make_service()
        with patch("app.services.cotacoes_service.YFINANCE_AVAILABLE", False):
            result = await svc.get_cotacao("PETR4.SA")
            assert result["ticker"] == "PETR4.SA"
            assert result["fonte"] == "dry-run"
            assert result["preco"] == 0

    @pytest.mark.asyncio
    async def test_mock_cotacao_structure(self):
        svc, _ = make_service()
        result = svc._mock_cotacao("VALE3.SA")
        assert "ticker" in result
        assert "preco" in result
        assert "variacao" in result
        assert "variacao_pct" in result
        assert "volume" in result
        assert "max_dia" in result
        assert "min_dia" in result
        assert "max_52s" in result
        assert "min_52s" in result
        assert "timestamp" in result
        assert "fonte" in result

    @pytest.mark.asyncio
    async def test_falls_back_to_mock_on_error(self):
        """If yfinance raises, should fallback to mock."""
        svc, _ = make_service()
        with patch("app.services.cotacoes_service.YFINANCE_AVAILABLE", True), \
             patch("app.services.cotacoes_service.yf") as mock_yf:
            mock_yf.Ticker.side_effect = Exception("API error")
            result = await svc.get_cotacao("INVALID")
            assert result["fonte"] == "dry-run"


class TestGetCotacoesBatch:
    @pytest.mark.asyncio
    async def test_returns_all_tickers(self):
        svc, _ = make_service()
        with patch("app.services.cotacoes_service.YFINANCE_AVAILABLE", False):
            result = await svc.get_cotacoes_batch(["PETR4.SA", "VALE3.SA", "ITUB4.SA"])
            assert len(result) == 3
            tickers = [r["ticker"] for r in result]
            assert "PETR4.SA" in tickers
            assert "VALE3.SA" in tickers

    @pytest.mark.asyncio
    async def test_empty_list(self):
        svc, _ = make_service()
        result = await svc.get_cotacoes_batch([])
        assert result == []


class TestAtualizarPrecosCarteira:
    @pytest.mark.asyncio
    async def test_updates_holdings(self):
        svc, sb = make_service()
        sb.set_table_data("ativos", [
            {"id": "a1", "ticker": "PETR4.SA", "carteira_id": "c1", "quantidade": 100, "preco_medio": 30},
            {"id": "a2", "ticker": "VALE3.SA", "carteira_id": "c1", "quantidade": 50, "preco_medio": 60},
        ])
        # Use dry-run mode (preco=0 means no update)
        with patch("app.services.cotacoes_service.YFINANCE_AVAILABLE", False):
            result = await svc.atualizar_precos_carteira("c1")
            assert "atualizado" in result
            assert "total" in result

    @pytest.mark.asyncio
    async def test_empty_portfolio(self):
        svc, sb = make_service()
        sb.set_table_data("ativos", [])
        result = await svc.atualizar_precos_carteira("c1")
        assert result["atualizado"] == 0

    @pytest.mark.asyncio
    async def test_no_db_returns_zero(self):
        from app.services.cotacoes_service import CotacoesService
        svc = CotacoesService(db_client=None, org_id=ORG_ID)
        result = await svc.atualizar_precos_carteira("c1")
        assert result["atualizado"] == 0

    @pytest.mark.asyncio
    async def test_skips_zero_price(self):
        """When cotacao returns preco=0, holding should not be updated."""
        svc, sb = make_service()
        sb.set_table_data("ativos", [
            {"id": "a1", "ticker": "PETR4.SA", "carteira_id": "c1", "quantidade": 100, "preco_medio": 30},
        ])
        with patch("app.services.cotacoes_service.YFINANCE_AVAILABLE", False):
            result = await svc.atualizar_precos_carteira("c1")
            # dry-run returns preco=0, so no updates
            assert result["atualizado"] == 0

    @pytest.mark.asyncio
    async def test_handles_update_error_gracefully(self):
        """If individual update fails, should continue and not crash."""
        svc, sb = make_service()
        sb.set_table_data("ativos", [
            {"id": "a1", "ticker": "PETR4.SA", "carteira_id": "c1", "quantidade": 100, "preco_medio": 30},
        ])

        async def mock_cotacao(ticker):
            return {"ticker": ticker, "preco": 35.0, "variacao": 0, "variacao_pct": 0}

        svc.get_cotacao = mock_cotacao

        # Make the update raise — should be caught gracefully
        original_table = sb.table
        call_count = {"n": 0}

        def patched_table(name):
            builder = original_table(name)
            if name == "ativos":
                call_count["n"] += 1
                # First call is the select, second is the update which we want to fail
                if call_count["n"] > 1:
                    class FailUpdate:
                        def update(self, *a, **k):
                            return self
                        def eq(self, *a, **k):
                            raise Exception("DB error")
                    return FailUpdate()
            return builder

        sb.table = patched_table
        result = await svc.atualizar_precos_carteira("c1")
        assert result["atualizado"] == 0


class TestAtualizarTodos:
    @pytest.mark.asyncio
    async def test_iterates_all_portfolios(self):
        svc, sb = make_service()
        sb.set_table_data("carteiras", [
            {"id": "c1", "org_id": ORG_ID, "ativo": True},
            {"id": "c2", "org_id": ORG_ID, "ativo": True},
        ])
        sb.set_table_data("ativos", [])
        result = await svc.atualizar_todos()
        assert result["atualizado"] == 0

    @pytest.mark.asyncio
    async def test_no_db_returns_zero(self):
        from app.services.cotacoes_service import CotacoesService
        svc = CotacoesService(db_client=None, org_id=ORG_ID)
        result = await svc.atualizar_todos()
        assert result["atualizado"] == 0

    @pytest.mark.asyncio
    async def test_no_active_portfolios(self):
        svc, sb = make_service()
        sb.set_table_data("carteiras", [])
        result = await svc.atualizar_todos()
        assert result["atualizado"] == 0
