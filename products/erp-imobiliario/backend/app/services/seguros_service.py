"""
Seguros Service — Business logic for insurance policy management.

Handles expiration tracking, summary calculations, and automatic
status updates for expired policies.
"""
import logging
from datetime import date, timedelta
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class SegurosService:
    """Service for insurance policy business logic."""

    VALID_STATUSES = {"ativo", "vencido", "cancelado", "renovado"}
    VALID_COBERTURAS = {
        "incendio", "completo", "responsabilidade_civil",
        "vida", "fianca_locaticia", "outro",
    }

    def __init__(self, db_client, user_id: str):
        """
        Initialize the service.

        Args:
            db_client: Supabase client (user-authenticated)
            user_id: Current user's ID
        """
        self.db = db_client
        self.user_id = user_id

    def get_vencimentos(self, dias: int = 30) -> List[Dict[str, Any]]:
        """
        Return active policies expiring within the next N days.

        Args:
            dias: Number of days ahead to check (default 30)

        Returns:
            List of policies with data_vencimento between today and today + dias
        """
        hoje = date.today().isoformat()
        limite = (date.today() + timedelta(days=dias)).isoformat()

        try:
            result = (
                self.db.table("seguros")
                .select("*")
                .eq("status", "ativo")
                .gte("data_vencimento", hoje)
                .lte("data_vencimento", limite)
                .order("data_vencimento", desc=False)
                .execute()
            )
            return result.data or []
        except Exception as e:
            logger.error(f"Erro ao buscar vencimentos de seguros: {e}")
            return []

    def get_resumo(self, seguros: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Calculate a summary from a list of insurance policies.

        Args:
            seguros: List of policy dicts (typically from a list query)

        Returns:
            Dict with ativos count, total_cobertura, total_premio_anual,
            and vencendo_30d count
        """
        hoje = date.today()
        limite_30d = hoje + timedelta(days=30)

        ativos = 0
        total_cobertura = 0.0
        total_premio = 0.0
        vencendo_30d = 0

        for seguro in seguros:
            if seguro.get("status") == "ativo":
                ativos += 1
                total_cobertura += float(seguro.get("valor_cobertura", 0))
                total_premio += float(seguro.get("valor_premio", 0))

                # Check if expiring within 30 days
                data_venc_str = seguro.get("data_vencimento")
                if data_venc_str:
                    try:
                        data_venc = date.fromisoformat(str(data_venc_str)[:10])
                        if hoje <= data_venc <= limite_30d:
                            vencendo_30d += 1
                    except (ValueError, TypeError):
                        pass

        return {
            "ativos": ativos,
            "total_cobertura": round(total_cobertura, 2),
            "total_premio_anual": round(total_premio, 2),
            "vencendo_30d": vencendo_30d,
        }

    def check_vencidos(self) -> int:
        """
        Mark expired active policies as 'vencido'.

        Finds all policies where status='ativo' and data_vencimento < today,
        then updates their status to 'vencido'.

        Returns:
            Number of policies marked as expired
        """
        hoje = date.today().isoformat()

        try:
            # Find active policies past their expiration date
            expired_result = (
                self.db.table("seguros")
                .select("id")
                .eq("status", "ativo")
                .lt("data_vencimento", hoje)
                .execute()
            )

            expired = expired_result.data or []
            if not expired:
                return 0

            expired_ids = [s["id"] for s in expired]

            # Update in batch
            for seguro_id in expired_ids:
                self.db.table("seguros").update(
                    {"status": "vencido"}
                ).eq("id", seguro_id).execute()

            logger.info(
                f"Marcou {len(expired_ids)} apólice(s) como vencida(s)",
                extra={"user_id": self.user_id, "count": len(expired_ids)},
            )

            return len(expired_ids)

        except Exception as e:
            logger.error(f"Erro ao verificar seguros vencidos: {e}")
            return 0
