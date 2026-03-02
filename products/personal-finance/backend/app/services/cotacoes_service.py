"""Stock quotes service — real-time price fetching via yfinance."""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Try to import yfinance; dry-run if unavailable
try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False
    logger.warning("yfinance not installed. Stock quotes will use dry-run mode.")


class CotacoesService:
    def __init__(self, db_client=None, org_id: str = None):
        self.db = db_client
        self.org_id = org_id

    async def get_cotacao(self, ticker: str) -> Dict:
        """Get current price for a single ticker."""
        if not YFINANCE_AVAILABLE:
            return self._mock_cotacao(ticker)

        try:
            tk = yf.Ticker(ticker)
            info = tk.fast_info
            hist = tk.history(period="2d")

            preco_atual = float(info.get("lastPrice", 0) if hasattr(info, "get") else getattr(info, "last_price", 0))
            preco_anterior = float(hist["Close"].iloc[-2]) if len(hist) >= 2 else preco_atual

            variacao = preco_atual - preco_anterior
            variacao_pct = (variacao / preco_anterior * 100) if preco_anterior > 0 else 0

            return {
                "ticker": ticker,
                "preco": round(preco_atual, 4),
                "variacao": round(variacao, 4),
                "variacao_pct": round(variacao_pct, 2),
                "volume": int(getattr(info, "last_volume", 0) or 0),
                "max_dia": round(float(getattr(info, "day_high", 0) or 0), 4),
                "min_dia": round(float(getattr(info, "day_low", 0) or 0), 4),
                "max_52s": round(float(getattr(info, "year_high", 0) or 0), 4),
                "min_52s": round(float(getattr(info, "year_low", 0) or 0), 4),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "fonte": "yfinance",
            }
        except Exception as e:
            logger.warning(f"Failed to fetch quote for {ticker}: {e}")
            return self._mock_cotacao(ticker)

    async def get_cotacoes_batch(self, tickers: List[str]) -> List[Dict]:
        """Get prices for multiple tickers."""
        results = []
        for ticker in tickers:
            cotacao = await self.get_cotacao(ticker)
            results.append(cotacao)
        return results

    async def atualizar_precos_carteira(self, carteira_id: str) -> Dict:
        """Update all holdings in a portfolio with current prices."""
        if not self.db:
            return {"atualizado": 0}

        ativos = self.db.table("ativos").select("id,ticker,quantidade,preco_medio").eq("carteira_id", carteira_id).execute()
        holdings = ativos.data or []

        if not holdings:
            return {"atualizado": 0}

        tickers = [h["ticker"] for h in holdings]
        cotacoes = await self.get_cotacoes_batch(tickers)
        cotacoes_map = {c["ticker"]: c for c in cotacoes}

        atualizados = 0
        for holding in holdings:
            cotacao = cotacoes_map.get(holding["ticker"])
            if not cotacao or cotacao["preco"] == 0:
                continue

            preco_atual = cotacao["preco"]
            quantidade = float(holding.get("quantidade", 0))
            preco_medio = float(holding.get("preco_medio", 0))

            valor_atual = round(preco_atual * quantidade, 2)
            ganho_perda = round((preco_atual - preco_medio) * quantidade, 2)
            ganho_perda_pct = round(((preco_atual / preco_medio) - 1) * 100, 4) if preco_medio > 0 else 0

            try:
                self.db.table("ativos").update({
                    "preco_atual": preco_atual,
                    "valor_atual": valor_atual,
                    "ganho_perda": ganho_perda,
                    "ganho_perda_pct": ganho_perda_pct,
                    "last_update": datetime.now(timezone.utc).isoformat(),
                }).eq("id", holding["id"]).execute()
                atualizados += 1
            except Exception as e:
                logger.error(f"Failed to update {holding['ticker']}: {e}")

        return {"atualizado": atualizados, "total": len(holdings)}

    async def atualizar_todos(self) -> Dict:
        """Update all org's holdings across all portfolios."""
        if not self.db:
            return {"atualizado": 0}

        carteiras = self.db.table("carteiras").select("id").eq("org_id", self.org_id).eq("ativo", True).execute()
        total = 0
        for carteira in (carteiras.data or []):
            result = await self.atualizar_precos_carteira(carteira["id"])
            total += result.get("atualizado", 0)

        return {"atualizado": total}

    def _mock_cotacao(self, ticker: str) -> Dict:
        """Return mock data when yfinance is unavailable."""
        return {
            "ticker": ticker,
            "preco": 0,
            "variacao": 0,
            "variacao_pct": 0,
            "volume": 0,
            "max_dia": 0,
            "min_dia": 0,
            "max_52s": 0,
            "min_52s": 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "fonte": "dry-run",
        }
