"""
Ativos Service — Business logic for asset management.

This service encapsulates the business rules for property/asset operations,
including the unified ativos table handling imoveis and permutas.
"""
import logging
from typing import Any, Dict, List, Optional

from app.dependencies import log_action, get_admin_client

logger = logging.getLogger(__name__)


class AtivosService:
    """Service for asset (ativo) business logic."""

    VALID_NATUREZAS = {"imovel", "permuta_imovel", "permuta_automovel"}
    SEARCH_FIELDS = [
        "id", "cidade", "bairro", "titulo_anuncio", "condominio_nome",
        "marca", "modelo", "tipo_imovel", "tipo_veiculo", "ref"
    ]

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
        Apply text search filter to asset data.

        Args:
            data: List of asset records
            query: Search query string

        Returns:
            Filtered list of assets matching the search
        """
        q = query.lower()
        return [
            d for d in data
            if any(
                q in str(d.get(f, "") or "").lower()
                for f in self.SEARCH_FIELDS
            )
        ]

    async def get_ativo(self, ativo_id: str) -> Optional[Dict]:
        """
        Get a single asset by ID.

        Args:
            ativo_id: Asset ID

        Returns:
            Asset data or None if not found
        """
        result = self.db.table("ativos").select("*").eq("id", ativo_id).single().execute()
        return result.data

    async def create_ativo(self, data: Dict) -> Dict:
        """
        Create a new asset and optionally trigger matching.

        Args:
            data: Asset data (from Pydantic model)

        Returns:
            Created asset data with optional _matches_count
        """
        data["owner_id"] = self.user_id
        result = self.db.table("ativos").insert(data).select().single().execute()

        if not result.data:
            return None

        ativo = result.data
        natureza = data.get("natureza")

        log_action(
            self.user_id,
            "criar",
            "ativo",
            ativo["id"],
            f"Criou {natureza} {ativo['id']}"
        )

        # Auto-trigger matching for properties that accept trades
        if natureza == "imovel" and data.get("aceita_permutas"):
            matches_count = await self._auto_match(ativo)
            if matches_count > 0:
                ativo["_matches_count"] = matches_count

        return ativo

    async def _auto_match(self, ativo: Dict) -> int:
        """
        Automatically generate matches for a new property.

        Args:
            ativo: The newly created asset

        Returns:
            Number of matches generated
        """
        try:
            from app.services.matching import gerar_matches_para_imovel

            admin = get_admin_client()
            permutas = admin.table("ativos").select("*").in_(
                "natureza", ["permuta_imovel", "permuta_automovel"]
            ).eq("status", "ativo").execute()

            matches = gerar_matches_para_imovel(ativo, permutas.data or [])

            for m in matches:
                admin.table("matches").upsert(
                    {**m, "status": "pendente"},
                    on_conflict="ativo_origem_id,ativo_destino_id",
                ).execute()

            return len(matches)

        except Exception as e:
            logger.warning(f"Auto-matching failed: {e}")
            return 0

    async def update_ativo(self, ativo_id: str, data: Dict) -> Optional[Dict]:
        """
        Update an existing asset.

        Args:
            ativo_id: Asset ID
            data: Fields to update

        Returns:
            Updated asset data or None if not found
        """
        result = self.db.table("ativos").update(data).eq(
            "id", ativo_id
        ).select().single().execute()

        if result.data:
            log_action(
                self.user_id,
                "editar",
                "ativo",
                ativo_id,
                f"Editou ativo {ativo_id}"
            )

        return result.data

    async def delete_ativo(self, ativo_id: str) -> bool:
        """
        Delete an asset.

        Args:
            ativo_id: Asset ID

        Returns:
            True if deleted successfully
        """
        self.db.table("ativos").delete().eq("id", ativo_id).execute()
        log_action(
            self.user_id,
            "excluir",
            "ativo",
            ativo_id,
            f"Excluiu ativo {ativo_id}"
        )
        return True

    @staticmethod
    def get_natureza_label(natureza: str) -> str:
        """Get human-readable label for asset type."""
        labels = {
            "imovel": "Imóvel",
            "permuta_imovel": "Permuta de Imóvel",
            "permuta_automovel": "Permuta de Automóvel",
        }
        return labels.get(natureza, natureza)
