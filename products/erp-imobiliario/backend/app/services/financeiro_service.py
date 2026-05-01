"""
Financeiro Service — Business logic for financial transactions.

Handles summaries, cash flow aggregation, and overdue detection.
"""
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional

from noctusai_lib.primitives.timeutil import current_day_ref

logger = logging.getLogger(__name__)


class FinanceiroService:
    """Service for financial business logic."""

    def __init__(self, db_client, user_id: str):
        self.db = db_client
        self.user_id = user_id

    def get_resumo(self, lancamentos: List[Dict]) -> Dict[str, Any]:
        """
        Calculate financial summary from a list of transactions.

        Returns dict with receitas, despesas, saldo, and atrasados count.
        """
        receitas = 0.0
        despesas = 0.0
        atrasados = 0

        for l in lancamentos:
            valor = float(l.get("valor", 0))
            if l.get("tipo") == "receita" and l.get("status") == "pago":
                receitas += valor
            elif l.get("tipo") == "despesa" and l.get("status") == "pago":
                despesas += valor
            if l.get("status") == "atrasado":
                atrasados += 1

        return {
            "receitas": receitas,
            "despesas": despesas,
            "saldo": receitas - despesas,
            "atrasados": atrasados,
        }

    def get_fluxo_caixa(self, lancamentos: List[Dict]) -> List[Dict[str, Any]]:
        """
        Aggregate cash flow by month from paid transactions.

        Returns list of monthly summaries sorted by month ascending.
        Each entry: { mes: "2026-01", receitas: float, despesas: float, saldo: float }
        """
        monthly: Dict[str, Dict[str, float]] = {}

        for l in lancamentos:
            # Use data_pagamento if paid, otherwise data_vencimento
            date_str = l.get("data_pagamento") or l.get("data_vencimento")
            if not date_str:
                continue

            # Extract YYYY-MM
            mes = date_str[:7]
            if mes not in monthly:
                monthly[mes] = {"receitas": 0.0, "despesas": 0.0}

            valor = float(l.get("valor", 0))
            if l.get("tipo") == "receita":
                monthly[mes]["receitas"] += valor
            elif l.get("tipo") == "despesa":
                monthly[mes]["despesas"] += valor

        result = []
        for mes in sorted(monthly.keys()):
            entry = monthly[mes]
            result.append({
                "mes": mes,
                "receitas": entry["receitas"],
                "despesas": entry["despesas"],
                "saldo": entry["receitas"] - entry["despesas"],
            })

        return result

    def check_overdue(self, lancamentos: List[Dict]) -> List[str]:
        """
        Identify transactions that are overdue (pendente + past due date).

        Returns list of IDs that should be marked as 'atrasado'.
        """
        today = current_day_ref()
        overdue_ids = []

        for l in lancamentos:
            if l.get("status") == "pendente":
                vencimento = l.get("data_vencimento", "")
                if vencimento and vencimento < today:
                    overdue_ids.append(l["id"])

        return overdue_ids

    async def mark_overdue(self) -> int:
        """
        Mark all overdue pending transactions in the database.
        Returns count of updated records.
        """
        today = current_day_ref()

        # Bulk update all pending transactions past due date in a single query
        result = self.db.table("lancamentos").update(
            {"status": "atrasado"}
        ).eq("status", "pendente").lt("data_vencimento", today).execute()

        count = len(result.data) if result.data else 0
        if count:
            logger.info(f"Marked {count} lancamentos as overdue")

        return count
