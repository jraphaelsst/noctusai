"""
Campo Service — Business logic for field operations sync and offline support.

This service handles batch synchronization of data collected offline
(checkins and vistorias) and generates offline data packs for PWA use.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


class CampoService:
    """Service for campo (field) sync and offline operations."""

    # Key fields to include in the offline properties pack (keep payload small)
    IMOVEL_OFFLINE_FIELDS = (
        "id, natureza, tipo_imovel, titulo_anuncio, valor, cidade, bairro, "
        "logradouro, numero, estado, latitude, longitude, quartos, "
        "area_privativa, fotos, status, finalidade"
    )

    def __init__(self, db_client, user_id: str):
        """
        Initialize the service.

        Args:
            db_client: Supabase client (user-authenticated)
            user_id: Current user's ID
        """
        self.db = db_client
        self.user_id = user_id

    async def processar_sync(
        self,
        checkins: List[Any],
        vistorias: List[Any],
    ) -> Dict[str, Any]:
        """
        Process a batch of offline checkins and vistorias, inserting each
        into its respective table.

        Args:
            checkins: List of SyncCheckin Pydantic models
            vistorias: List of SyncVistoria Pydantic models

        Returns:
            Summary dict with counts: checkins_criados, vistorias_criadas, erros
        """
        checkins_criados = 0
        vistorias_criadas = 0
        erros: List[Dict[str, str]] = []

        # --- Sync checkins ---
        for checkin in checkins:
            try:
                data = checkin.model_dump(exclude_none=True)
                # Remove PWA-only fields that don't map to DB columns
                offline_id = data.pop("offline_id", None)
                data.pop("created_at_local", None)

                data["corretor_id"] = self.user_id

                self.db.table("checkins").insert(data).execute()
                checkins_criados += 1
            except Exception as exc:
                identifier = offline_id or f"checkin-{checkins.index(checkin)}"
                logger.warning("Erro ao sincronizar checkin %s: %s", identifier, exc)
                erros.append({"item": identifier, "tipo": "checkin", "erro": str(exc)})

        # --- Sync vistorias ---
        for vistoria in vistorias:
            try:
                data = vistoria.model_dump(exclude_none=True)
                offline_id = data.pop("offline_id", None)
                data.pop("created_at_local", None)

                data["corretor_id"] = self.user_id

                self.db.table("vistorias_rapidas").insert(data).execute()
                vistorias_criadas += 1
            except Exception as exc:
                identifier = offline_id or f"vistoria-{vistorias.index(vistoria)}"
                logger.warning("Erro ao sincronizar vistoria %s: %s", identifier, exc)
                erros.append({"item": identifier, "tipo": "vistoria", "erro": str(exc)})

        return {
            "checkins_criados": checkins_criados,
            "vistorias_criadas": vistorias_criadas,
            "erros": erros,
        }

    async def gerar_pacote_offline(self) -> Dict[str, Any]:
        """
        Build a data pack for offline/PWA use.

        Fetches:
          - Active properties (ativos where status='ativo'), key fields only
          - Clients assigned to this user
          - Recent checkins for this user (last 100)

        Returns:
            Dict with keys: imoveis, clientes, checkins_recentes, generated_at
        """
        # Active properties — lightweight projection
        imoveis_result = (
            self.db.table("ativos")
            .select(self.IMOVEL_OFFLINE_FIELDS)
            .eq("status", "ativo")
            .execute()
        )

        # Clients assigned to this user
        clientes_result = (
            self.db.table("clientes")
            .select("id, nome, email, telefone, interesse, etapa_atual")
            .eq("usuario_id", self.user_id)
            .eq("arquivado", False)
            .execute()
        )

        # Recent checkins for this user (last 100)
        checkins_result = (
            self.db.table("checkins")
            .select("*")
            .eq("corretor_id", self.user_id)
            .order("created_at", desc=True)
            .limit(100)
            .execute()
        )

        return {
            "imoveis": imoveis_result.data or [],
            "clientes": clientes_result.data or [],
            "checkins_recentes": checkins_result.data or [],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }
