"""
Clientes Service — Business logic for client management.

This service encapsulates the business rules for client operations,
keeping the router focused on HTTP handling.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.dependencies import first_or_none, log_action

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# DTO mapper (Phase 3b — operational contract, NOT response_model)
# ---------------------------------------------------------------------------
# Whitelist mirrors `frontend/src/types/clientes.ts → interface Cliente`.
# response_model=PydanticDTO rollout deferred to follow-up project
# `erp-imobiliario-dto-contract` per PROJECT.md §7 Q-E.
_CLIENTE_DTO_FIELDS: Tuple[str, ...] = (
    "id",
    "usuario_id",
    "nome",
    "email",
    "telefone",
    "origem",
    "interesse",
    "observacoes",
    "etapa_atual",
    "probabilidade",
    "valor_estimado",
    "arquivado",
    "kanban_pos",
    "lead_score",
    "lead_score_justificativa",
    "lead_score_updated_at",
    "created_at",
    "updated_at",
    "usuario",  # nested join object (id/nome/email — projected by DB select)
)


def cliente_row_to_dto(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Project a raw DB row to the operational Cliente DTO contract.

    Strips any column not in the whitelist (defense against silent schema
    drift + PII over-share). Returns None for None input (caller-safe).
    """
    if not row:
        return row
    return {k: row.get(k) for k in _CLIENTE_DTO_FIELDS if k in row}


def cliente_rows_to_dto(rows: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Project a list of raw DB rows to Cliente DTO shape."""
    if not rows:
        return []
    return [cliente_row_to_dto(r) for r in rows]


class ClientesService:
    """Service for client business logic."""

    VALID_ETAPAS = {"qualificacao", "visitas", "proposta", "negociacao", "fechado"}
    SEARCH_FIELDS = ["nome", "email", "telefone", "interesse", "observacoes"]

    def __init__(self, db_client, user_id: str):
        """
        Initialize the service.

        Args:
            db_client: Supabase client (user-authenticated)
            user_id: Current user's ID
        """
        self.db = db_client
        self.user_id = user_id

    def search_filter(self, data: List[Dict], query: str) -> List[Dict]:
        """
        Apply text search filter to client data.

        Args:
            data: List of client records
            query: Search query string

        Returns:
            Filtered list of clients matching the search
        """
        q = query.lower()
        return [
            c for c in data
            if any(
                q in str(c.get(f, "") or "").lower()
                for f in self.SEARCH_FIELDS
            )
        ]

    def validate_etapa(self, etapa: str) -> bool:
        """Check if the given pipeline stage is valid."""
        return etapa in self.VALID_ETAPAS

    async def get_cliente(self, cliente_id: str) -> Optional[Dict]:
        """
        Get a single client by ID.

        Args:
            cliente_id: Client ID

        Returns:
            Client data or None if not found
        """
        result = self.db.table("clientes").select(
            "*, usuario:profiles!clientes_usuario_id_fkey(id, nome, email)"
        ).eq("id", cliente_id).single().execute()
        return result.data

    async def create_cliente(self, data: Dict) -> Dict:
        """
        Create a new client.

        Args:
            data: Client data (from Pydantic model)

        Returns:
            Created client data
        """
        data["usuario_id"] = self.user_id
        result = self.db.table("clientes").insert(data).execute()
        row = first_or_none(result)

        if row:
            log_action(
                self.user_id,
                "criar",
                "cliente",
                row["id"],
                f"Criou cliente {data.get('nome', 'unknown')}"
            )

        return row

    async def update_cliente(self, cliente_id: str, data: Dict) -> Optional[Dict]:
        """
        Update an existing client.

        Args:
            cliente_id: Client ID
            data: Fields to update

        Returns:
            Updated client data or None if not found
        """
        result = self.db.table("clientes").update(data).eq(
            "id", cliente_id
        ).execute()
        row = first_or_none(result)

        if row:
            log_action(
                self.user_id,
                "editar",
                "cliente",
                cliente_id,
                f"Editou cliente {cliente_id}"
            )

        return row

    async def delete_cliente(self, cliente_id: str) -> bool:
        """
        Delete a client.

        Args:
            cliente_id: Client ID

        Returns:
            True if deleted successfully
        """
        self.db.table("clientes").delete().eq("id", cliente_id).execute()
        log_action(
            self.user_id,
            "excluir",
            "cliente",
            cliente_id,
            f"Excluiu cliente {cliente_id}"
        )
        return True

    async def toggle_archive(self, cliente_id: str) -> Tuple[Optional[Dict], bool]:
        """
        Toggle archive status of a client.

        Args:
            cliente_id: Client ID

        Returns:
            Tuple of (updated_data, new_archive_state) or (None, False) if not found
        """
        current = self.db.table("clientes").select(
            "arquivado, nome"
        ).eq("id", cliente_id).single().execute()

        if not current.data:
            return None, False

        novo_estado = not current.data["arquivado"]
        result = self.db.table("clientes").update(
            {"arquivado": novo_estado}
        ).eq("id", cliente_id).execute()
        row = first_or_none(result)

        if row:
            acao = "arquivar" if novo_estado else "desarquivar"
            log_action(
                self.user_id,
                acao,
                "cliente",
                cliente_id,
                f"{'Arquivou' if novo_estado else 'Desarquivou'} cliente {current.data['nome']}"
            )

        return row, novo_estado

    async def move_etapa(
        self,
        cliente_id: str,
        para_etapa: str,
        novo_indice: Optional[int] = None,
        motivo: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Move a client to a different pipeline stage.

        Args:
            cliente_id: Client ID
            para_etapa: Target stage
            novo_indice: Optional kanban position
            motivo: Optional reason for the move

        Returns:
            Updated client data or None if not found
        """
        update_data = {"etapa_atual": para_etapa}
        if novo_indice is not None:
            update_data["kanban_pos"] = novo_indice

        result = self.db.table("clientes").update(update_data).eq(
            "id", cliente_id
        ).execute()
        row = first_or_none(result)

        if row:
            log_action(
                self.user_id,
                "mover",
                "cliente",
                cliente_id,
                f"Moveu cliente para etapa {para_etapa}",
                {"para_etapa": para_etapa, "motivo": motivo}
            )

        return row
