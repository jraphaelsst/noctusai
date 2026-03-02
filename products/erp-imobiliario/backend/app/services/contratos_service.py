"""
Contratos Service — Business logic for sale and rental contracts.

Handles installment generation, summary aggregation, overdue detection,
and inadimplencia tracking.
"""
import logging
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
from typing import Any, Dict, List, Optional

from app.dependencies import first_or_none

logger = logging.getLogger(__name__)


class ContratosService:
    """Service for contract business logic."""

    def __init__(self, db_client, user_id: str):
        self.db = db_client
        self.user_id = user_id

    async def gerar_parcelas(
        self,
        contrato_id: str,
        valor_total: float,
        valor_entrada: float,
        num_parcelas: int,
        data_inicio: str,
    ) -> List[Dict[str, Any]]:
        """
        Generate installment schedule for a contract.

        Calculates installment amounts by distributing the remaining value
        (valor_total - valor_entrada) across num_parcelas, with any rounding
        remainder added to the last installment.

        Args:
            contrato_id: The contract ID to attach installments to.
            valor_total: Total contract value.
            valor_entrada: Down payment amount.
            num_parcelas: Number of installments to generate.
            data_inicio: Start date string (YYYY-MM-DD) for the first installment.

        Returns:
            List of created installment records.
        """
        # Delete existing parcelas for this contract before regenerating
        self.db.table("parcelas_contrato").delete().eq(
            "contrato_id", contrato_id
        ).execute()

        valor_financiado = valor_total - valor_entrada
        if valor_financiado <= 0:
            return []

        # Calculate installment value with rounding
        valor_parcela = round(valor_financiado / num_parcelas, 2)
        valor_ultima = round(valor_financiado - (valor_parcela * (num_parcelas - 1)), 2)

        # Parse data_inicio to generate monthly due dates
        inicio = datetime.strptime(data_inicio, "%Y-%m-%d").date()

        parcelas_criadas = []
        for i in range(num_parcelas):
            numero = i + 1
            data_vencimento = inicio + relativedelta(months=i)
            valor = valor_ultima if numero == num_parcelas else valor_parcela

            parcela_data = {
                "contrato_id": contrato_id,
                "numero": numero,
                "valor": valor,
                "data_vencimento": data_vencimento.isoformat(),
                "status": "pendente",
            }

            result = self.db.table("parcelas_contrato").insert(
                parcela_data
            ).execute()
            row = first_or_none(result)

            if row:
                parcelas_criadas.append(row)

        return parcelas_criadas

    def get_resumo(self, contratos: List[Dict]) -> Dict[str, Any]:
        """
        Calculate contract summary from a list of contracts.

        Returns dict with total counts by status, valor_total sum,
        and contract type breakdown.
        """
        por_status = {
            "rascunho": 0,
            "ativo": 0,
            "concluido": 0,
            "cancelado": 0,
            "distratado": 0,
        }
        valor_total_sum = 0.0
        por_tipo = {"venda": 0, "locacao": 0}

        for c in contratos:
            status = c.get("status", "rascunho")
            if status in por_status:
                por_status[status] += 1

            tipo = c.get("tipo")
            if tipo in por_tipo:
                por_tipo[tipo] += 1

            # Only sum value for active/concluded contracts
            if status in ("ativo", "concluido"):
                valor_total_sum += float(c.get("valor_total", 0))

        return {
            "total": len(contratos),
            "por_status": por_status,
            "por_tipo": por_tipo,
            "valor_total": valor_total_sum,
        }

    def check_inadimplencia(self, parcelas: List[Dict]) -> Dict[str, Any]:
        """
        Identify overdue installments and calculate inadimplencia metrics.

        Returns dict with count of overdue parcelas, total overdue amount,
        and list of overdue parcela IDs.
        """
        today = date.today().isoformat()
        atrasadas = []
        valor_atrasado = 0.0

        for p in parcelas:
            status = p.get("status")
            if status == "atrasado":
                atrasadas.append(p["id"])
                valor_atrasado += float(p.get("valor", 0))
            elif status == "pendente":
                vencimento = p.get("data_vencimento", "")
                if vencimento and vencimento < today:
                    atrasadas.append(p["id"])
                    valor_atrasado += float(p.get("valor", 0))

        total_parcelas = len(parcelas)
        taxa = (len(atrasadas) / total_parcelas * 100) if total_parcelas > 0 else 0.0

        return {
            "total_atrasadas": len(atrasadas),
            "valor_atrasado": valor_atrasado,
            "taxa_inadimplencia": round(taxa, 2),
            "parcelas_ids": atrasadas,
        }

    async def mark_overdue(self) -> int:
        """
        Mark all overdue pending installments in the database.
        Returns count of updated records.
        """
        today = date.today().isoformat()

        # Fetch pending parcelas with past due dates
        result = self.db.table("parcelas_contrato").select("id").eq(
            "status", "pendente"
        ).lt("data_vencimento", today).execute()

        overdue_ids = [r["id"] for r in (result.data or [])]
        if not overdue_ids:
            return 0

        # Update each to 'atrasado'
        count = 0
        for pid in overdue_ids:
            try:
                self.db.table("parcelas_contrato").update(
                    {"status": "atrasado"}
                ).eq("id", pid).execute()
                count += 1
            except Exception as e:
                logger.warning(f"Failed to mark parcela {pid} as overdue: {e}")

        return count
