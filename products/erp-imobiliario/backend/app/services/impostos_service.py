"""
Impostos Service — Business logic for property tax management.

Handles tax summaries, single-payment discount calculations, and overdue detection.
"""
import logging
from datetime import date
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ImpostosService:
    """Service for property tax business logic."""

    def __init__(self, db_client, user_id: str):
        """
        Initialize the service.

        Args:
            db_client: Supabase client (user-authenticated)
            user_id: Current user's ID
        """
        self.db = db_client
        self.user_id = user_id

    def get_resumo(self, impostos: List[Dict]) -> Dict[str, Any]:
        """
        Calculate tax summary from a list of tax records.

        Returns dict with total_devido, total_pago, total_pendente,
        total_atrasado, and count_by_status breakdown.
        """
        total_devido = 0.0
        total_pago = 0.0
        total_pendente = 0.0
        total_atrasado = 0.0
        count_by_status: Dict[str, int] = {
            "pendente": 0,
            "parcial": 0,
            "pago": 0,
            "atrasado": 0,
            "isento": 0,
        }

        for imposto in impostos:
            valor_total = float(imposto.get("valor_total", 0))
            valor_pago = float(imposto.get("valor_pago", 0))
            status = imposto.get("status", "pendente")

            total_devido += valor_total
            total_pago += valor_pago

            if status in count_by_status:
                count_by_status[status] += 1

            if status == "atrasado":
                total_atrasado += valor_total - valor_pago
            elif status in ("pendente", "parcial"):
                total_pendente += valor_total - valor_pago

        return {
            "total_devido": round(total_devido, 2),
            "total_pago": round(total_pago, 2),
            "total_pendente": round(total_pendente, 2),
            "total_atrasado": round(total_atrasado, 2),
            "count_by_status": count_by_status,
            "quantidade": len(impostos),
        }

    @staticmethod
    def calcular_cota_unica(valor_total: float, desconto_percentual: float) -> float:
        """
        Calculate the discounted value for single-payment (cota unica).

        Args:
            valor_total: Original total tax value
            desconto_percentual: Discount percentage (e.g. 10.0 for 10%)

        Returns:
            Discounted value rounded to 2 decimal places
        """
        if desconto_percentual <= 0:
            return round(valor_total, 2)
        if desconto_percentual >= 100:
            return 0.0
        desconto = valor_total * (desconto_percentual / 100)
        return round(valor_total - desconto, 2)

    async def check_vencidos(self) -> int:
        """
        Mark overdue taxes in the database.

        Finds all tax records with status 'pendente' or 'parcial' where
        data_vencimento is before today, and updates them to 'atrasado'.

        Returns:
            Count of records updated to 'atrasado'.
        """
        today = date.today().isoformat()

        # Fetch pending taxes with past due dates
        result_pendente = self.db.table("impostos").select("id").eq(
            "status", "pendente"
        ).lt("data_vencimento", today).execute()

        result_parcial = self.db.table("impostos").select("id").eq(
            "status", "parcial"
        ).lt("data_vencimento", today).execute()

        overdue_ids = [r["id"] for r in (result_pendente.data or [])]
        overdue_ids += [r["id"] for r in (result_parcial.data or [])]

        if not overdue_ids:
            return 0

        # Update each to 'atrasado'
        count = 0
        for imposto_id in overdue_ids:
            try:
                self.db.table("impostos").update(
                    {"status": "atrasado"}
                ).eq("id", imposto_id).execute()
                count += 1
            except Exception as e:
                logger.warning(f"Failed to mark imposto {imposto_id} as overdue: {e}")

        return count
