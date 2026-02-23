"""
Clientes Service — Business logic for client management.

This service encapsulates the business rules for client operations,
keeping the router focused on HTTP handling.
"""
import logging
from typing import Any, Dict, List, Optional, Tuple

from app.dependencies import log_action

logger = logging.getLogger(__name__)


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
        result = self.db.table("clientes").insert(data).select().single().execute()

        if result.data:
            log_action(
                self.user_id,
                "criar",
                "cliente",
                result.data["id"],
                f"Criou cliente {data.get('nome', 'unknown')}"
            )

        return result.data

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
        ).select().single().execute()

        if result.data:
            log_action(
                self.user_id,
                "editar",
                "cliente",
                cliente_id,
                f"Editou cliente {cliente_id}"
            )

        return result.data

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
        ).eq("id", cliente_id).select().single().execute()

        if result.data:
            acao = "arquivar" if novo_estado else "desarquivar"
            log_action(
                self.user_id,
                acao,
                "cliente",
                cliente_id,
                f"{'Arquivou' if novo_estado else 'Desarquivou'} cliente {current.data['nome']}"
            )

        return result.data, novo_estado

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
        ).select().single().execute()

        if result.data:
            log_action(
                self.user_id,
                "mover",
                "cliente",
                cliente_id,
                f"Moveu cliente para etapa {para_etapa}",
                {"para_etapa": para_etapa, "motivo": motivo}
            )

        return result.data
