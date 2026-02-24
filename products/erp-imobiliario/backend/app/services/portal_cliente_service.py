"""
Portal do Cliente Service — Business logic for client portal access and data retrieval.

Handles token generation, validation, and scoped data fetching for
client-facing portal endpoints.
"""
import logging
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException

from app.dependencies import get_admin_client

logger = logging.getLogger(__name__)


class PortalClienteService:
    """Service for client portal business logic."""

    def __init__(self, db_client, user_id: Optional[str] = None):
        self.db = db_client
        self.user_id = user_id

    @classmethod
    def __from_token__(cls, token: str) -> "PortalClienteService":
        """
        Factory for token-based (public) access.

        Uses admin client (service role) since portal endpoints bypass RLS.
        No user_id is set because the caller is an unauthenticated client.
        """
        admin = get_admin_client()
        return cls(admin, user_id=None)

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def gerar_token(self) -> str:
        """Generate a cryptographically secure portal access token."""
        return secrets.token_urlsafe(32)

    def validar_token(self, token: str) -> Dict[str, Any]:
        """
        Validate a portal access token.

        Checks that the token exists, is active, and has not expired.
        Updates ultimo_acesso on successful validation.

        Returns:
            The portal_acessos record dict.

        Raises:
            HTTPException 403 if token is invalid, inactive, or expired.
        """
        result = self.db.table("portal_acessos").select("*").eq(
            "token", token
        ).eq("ativo", True).single().execute()

        if not result.data:
            raise HTTPException(
                status_code=403,
                detail="Token de acesso inválido ou revogado",
            )

        acesso = result.data

        # Check expiration if set
        if acesso.get("data_expiracao"):
            expiracao = datetime.fromisoformat(
                acesso["data_expiracao"].replace("Z", "+00:00")
            )
            if expiracao < datetime.now(timezone.utc):
                raise HTTPException(
                    status_code=403,
                    detail="Token de acesso expirado",
                )

        # Update last access timestamp
        try:
            self.db.table("portal_acessos").update(
                {"ultimo_acesso": datetime.now(timezone.utc).isoformat()}
            ).eq("id", acesso["id"]).execute()
        except Exception as e:
            logger.warning(f"Failed to update ultimo_acesso for portal token: {e}")

        return acesso

    # ------------------------------------------------------------------
    # Client-facing data retrieval
    # ------------------------------------------------------------------

    def get_dashboard(self, cliente_id: str) -> Dict[str, Any]:
        """
        Fetch the client dashboard data.

        Returns a dict with:
        - contratos: recent contracts for this client
        - financeiro: recent financial entries (last 10)
        - documentos: shared documents for this client
        """
        # Contracts
        contratos_result = self.db.table("contratos").select("*").eq(
            "cliente_id", cliente_id
        ).order("created_at", desc=True).limit(20).execute()

        # Recent financial entries
        financeiro_result = self.db.table("lancamentos").select("*").eq(
            "cliente_id", cliente_id
        ).order("data_vencimento", desc=True).limit(10).execute()

        # Shared documents
        documentos_result = self.db.table("documentos").select("*").eq(
            "cliente_id", cliente_id
        ).order("created_at", desc=True).limit(20).execute()

        return {
            "contratos": contratos_result.data or [],
            "financeiro": financeiro_result.data or [],
            "documentos": documentos_result.data or [],
        }

    def get_financeiro(self, cliente_id: str) -> List[Dict[str, Any]]:
        """
        Fetch all financial entries (lancamentos) scoped to a client.

        Returns list of lancamentos ordered by due date descending.
        """
        result = self.db.table("lancamentos").select("*").eq(
            "cliente_id", cliente_id
        ).order("data_vencimento", desc=True).execute()

        return result.data or []

    def get_chamados(
        self, cliente_id: str, portal_acesso_id: str
    ) -> List[Dict[str, Any]]:
        """
        Fetch support tickets for a client, scoped to their portal access.

        Returns list of chamados ordered by creation date descending.
        """
        result = self.db.table("chamados_portal").select("*").eq(
            "cliente_id", cliente_id
        ).eq(
            "portal_acesso_id", portal_acesso_id
        ).order("created_at", desc=True).execute()

        return result.data or []
