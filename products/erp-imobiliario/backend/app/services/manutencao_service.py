"""
Manutencao Service — Business logic for maintenance & work orders.

Handles summaries, overdue detection, and resolution time calculations
for property maintenance work orders.
"""
import logging
from datetime import date, datetime
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class ManutencaoService:
    """Service for maintenance work order business logic."""

    ACTIVE_STATUSES = {"aberto", "em_andamento", "aguardando"}

    def __init__(self, db_client, user_id: str):
        self.db = db_client
        self.user_id = user_id

    def get_resumo(self, ordens: List[Dict]) -> Dict[str, Any]:
        """
        Calculate maintenance summary from a list of work orders.

        Returns dict with:
        - por_status: count of orders per status
        - tempo_medio_resolucao: avg days from data_abertura to data_conclusao (concluidos only)
        - atrasados: count of overdue orders (active + past data_previsao)
        - custo_total: sum of custo_real for concluido orders
        """
        por_status: Dict[str, int] = {
            "aberto": 0,
            "em_andamento": 0,
            "aguardando": 0,
            "concluido": 0,
            "cancelado": 0,
        }

        total_dias_resolucao = 0
        count_concluidos = 0
        custo_total = 0.0
        atrasados = 0
        today = date.today().isoformat()

        for ordem in ordens:
            status = ordem.get("status", "aberto")
            if status in por_status:
                por_status[status] += 1

            # Calculate resolution time for completed orders
            if status == "concluido":
                custo_real = ordem.get("custo_real")
                if custo_real is not None:
                    custo_total += float(custo_real)

                data_abertura = ordem.get("data_abertura")
                data_conclusao = ordem.get("data_conclusao")
                if data_abertura and data_conclusao:
                    try:
                        dt_abertura = datetime.strptime(data_abertura[:10], "%Y-%m-%d").date()
                        dt_conclusao = datetime.strptime(data_conclusao[:10], "%Y-%m-%d").date()
                        dias = (dt_conclusao - dt_abertura).days
                        if dias >= 0:
                            total_dias_resolucao += dias
                            count_concluidos += 1
                    except (ValueError, TypeError):
                        pass

            # Check overdue: active status + past data_previsao
            if status in self.ACTIVE_STATUSES:
                data_previsao = ordem.get("data_previsao")
                if data_previsao and data_previsao[:10] < today:
                    atrasados += 1

        tempo_medio = (
            round(total_dias_resolucao / count_concluidos, 1)
            if count_concluidos > 0
            else 0
        )

        return {
            "por_status": por_status,
            "tempo_medio_resolucao": tempo_medio,
            "atrasados": atrasados,
            "custo_total": custo_total,
        }

    def check_overdue(self, ordens: List[Dict]) -> List[str]:
        """
        Identify overdue work orders (status in aberto/em_andamento and data_previsao < today).

        Returns list of IDs that are overdue.
        """
        today = date.today().isoformat()
        overdue_ids = []

        for ordem in ordens:
            status = ordem.get("status", "")
            if status in ("aberto", "em_andamento"):
                data_previsao = ordem.get("data_previsao", "")
                if data_previsao and data_previsao[:10] < today:
                    overdue_ids.append(ordem["id"])

        return overdue_ids

    async def mark_overdue(self) -> int:
        """
        Identify overdue orders in the database and return count.

        Fetches active orders with past data_previsao for awareness.
        Returns count of overdue records found.
        """
        today = date.today().isoformat()

        # Fetch active orders with past predicted dates
        result = self.db.table("ordens_servico").select("id").in_(
            "status", ["aberto", "em_andamento"]
        ).lt("data_previsao", today).execute()

        overdue_ids = [r["id"] for r in (result.data or [])]
        if not overdue_ids:
            return 0

        # Batch update all overdue ordens
        self.db.table("ordens_servico").update(
            {"prioridade": "urgente"}
        ).in_("id", overdue_ids).execute()

        return len(overdue_ids)
