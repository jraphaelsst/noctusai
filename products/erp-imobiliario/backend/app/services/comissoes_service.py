"""
Comissoes Service — Business logic for commission management.

Handles commission calculations, split validation, and agent summaries.
"""
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class ComissoesService:
    """Service for commission business logic."""

    VALID_STATUSES = {"pendente", "aprovada", "paga", "cancelada"}

    def __init__(self, db_client, user_id: str):
        """
        Initialize the service.

        Args:
            db_client: Supabase client (user-authenticated)
            user_id: Current user's ID
        """
        self.db = db_client
        self.user_id = user_id

    @staticmethod
    def calculate_commission(valor_venda: float, percentual: float) -> float:
        """
        Calculate the commission amount from sale value and percentage.

        Args:
            valor_venda: Sale value
            percentual: Commission percentage (e.g. 6.0 for 6%)

        Returns:
            Calculated commission value
        """
        return round(valor_venda * (percentual / 100), 2)

    @staticmethod
    def calculate_splits(valor_comissao: float, splits_data: List[Dict]) -> List[Dict]:
        """
        Calculate and validate commission splits.

        Validates that percentages sum to 100% and computes each agent's value.

        Args:
            valor_comissao: Total commission value to split
            splits_data: List of dicts with corretor_id, corretor_nome, percentual

        Returns:
            List of validated split dicts with computed valor

        Raises:
            ValueError: If splits don't sum to 100% or contain invalid data
        """
        if not splits_data:
            return []

        total_percentual = sum(s.get("percentual", 0) for s in splits_data)

        # Allow small floating point tolerance
        if abs(total_percentual - 100.0) > 0.01:
            raise ValueError(
                f"Os percentuais dos splits devem somar 100%. "
                f"Total atual: {total_percentual}%"
            )

        validated_splits = []
        for split in splits_data:
            if not split.get("corretor_id"):
                raise ValueError("Cada split deve ter um corretor_id")
            if not split.get("corretor_nome"):
                raise ValueError("Cada split deve ter um corretor_nome")
            if split.get("percentual", 0) <= 0:
                raise ValueError("O percentual de cada split deve ser maior que 0")

            validated_splits.append({
                "corretor_id": split["corretor_id"],
                "corretor_nome": split["corretor_nome"],
                "percentual": split["percentual"],
                "valor": round(valor_comissao * (split["percentual"] / 100), 2),
            })

        return validated_splits

    def get_agent_summary(self, supabase) -> List[Dict]:
        """
        Aggregate commission data by agent.

        Args:
            supabase: Supabase client to use for queries

        Returns:
            List of dicts with agent name, total pending, total paid, total commissions
        """
        try:
            # Fetch all splits with their parent commission status
            splits_result = supabase.table("comissoes_splits").select(
                "*, comissao:comissoes!comissoes_splits_comissao_id_fkey(status, valor_comissao)"
            ).execute()

            splits = splits_result.data or []

            # Aggregate by agent
            agent_map: Dict[str, Dict[str, Any]] = {}
            for split in splits:
                corretor_id = split.get("corretor_id")
                corretor_nome = split.get("corretor_nome", "Desconhecido")
                comissao = split.get("comissao", {})
                status = comissao.get("status", "pendente") if comissao else "pendente"
                valor = split.get("valor", 0)

                if corretor_id not in agent_map:
                    agent_map[corretor_id] = {
                        "corretor_id": corretor_id,
                        "corretor_nome": corretor_nome,
                        "total_pendente": 0,
                        "total_aprovada": 0,
                        "total_paga": 0,
                        "total_geral": 0,
                        "quantidade": 0,
                    }

                agent = agent_map[corretor_id]
                agent["quantidade"] += 1
                agent["total_geral"] += valor

                if status == "pendente":
                    agent["total_pendente"] += valor
                elif status == "aprovada":
                    agent["total_aprovada"] += valor
                elif status == "paga":
                    agent["total_paga"] += valor

            # Round all values
            for agent in agent_map.values():
                agent["total_pendente"] = round(agent["total_pendente"], 2)
                agent["total_aprovada"] = round(agent["total_aprovada"], 2)
                agent["total_paga"] = round(agent["total_paga"], 2)
                agent["total_geral"] = round(agent["total_geral"], 2)

            return list(agent_map.values())

        except Exception as e:
            logger.error(f"Error fetching agent summary: {e}")
            return []
