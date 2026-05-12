"""
Financeiro Service — Business logic for financial transactions.

Handles summaries, cash flow aggregation, and overdue detection.
"""
import logging
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from noctusai_lib.primitives.timeutil import current_day_ref

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DTO mappers (Phase 3b — operational contract, NOT response_model)
# ---------------------------------------------------------------------------
# Whitelist mirrors `frontend/src/types/financeiro.ts → interface Lancamento`.
# response_model=PydanticDTO rollout deferred per PROJECT.md §7 Q-E.
_LANCAMENTO_DTO_FIELDS: Tuple[str, ...] = (
    "id",
    "tipo",
    "categoria",
    "descricao",
    "valor",
    "data_vencimento",
    "data_pagamento",
    "status",
    "forma_pagamento",
    "imovel_id",
    "cliente_id",
    "comissao_id",
    "recorrente",
    "observacoes",
    "created_at",
    "updated_at",
)


def lancamento_row_to_dto(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Project a raw DB row to the operational Lancamento DTO contract."""
    if not row:
        return row
    return {k: row.get(k) for k in _LANCAMENTO_DTO_FIELDS if k in row}


def lancamento_rows_to_dto(rows: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Project a list of raw DB rows to Lancamento DTO shape."""
    if not rows:
        return []
    return [lancamento_row_to_dto(r) for r in rows]


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
