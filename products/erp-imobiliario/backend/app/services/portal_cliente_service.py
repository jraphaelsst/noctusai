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


# ---------------------------------------------------------------------------
# DTO mappers (Phase 3b — operational contract, NOT response_model)
# ---------------------------------------------------------------------------
# response_model=PydanticDTO rollout deferred per PROJECT.md §7 Q-E.
#
# IMPORTANT — token-leak defense:
#   - `_PORTAL_ACESSO_LISTING_FIELDS` (used by GET /api/portal-cliente/acessos)
#     INTENTIONALLY EXCLUDES `token`. Admins listing acessos should never see
#     raw bearer tokens — re-issue via `/gerar-acesso` instead.
#   - `_PORTAL_ACESSO_ISSUED_FIELDS` (used by POST /api/portal-cliente/gerar-acesso)
#     INCLUDES `token` — it's the one-shot share moment.
_PORTAL_ACESSO_LISTING_FIELDS: tuple = (
    "id",
    "cliente_id",
    "ativo",
    "data_expiracao",
    "ultimo_acesso",
    "created_at",
)

_PORTAL_ACESSO_ISSUED_FIELDS: tuple = (
    "id",
    "cliente_id",
    "token",
    "ativo",
    "data_expiracao",
    "ultimo_acesso",
    "created_at",
)

_CHAMADO_PORTAL_FIELDS: tuple = (
    "id",
    "cliente_id",
    "portal_acesso_id",
    "assunto",
    "descricao",
    "status",
    "prioridade",
    "resposta",
    "created_at",
    "updated_at",
)


def portal_acesso_listing_to_dto(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Project a portal_acessos row for ADMIN LISTING (token hidden)."""
    if not row:
        return row
    return {k: row.get(k) for k in _PORTAL_ACESSO_LISTING_FIELDS if k in row}


def portal_acesso_listing_rows_to_dto(rows: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Project a list of portal_acessos rows for ADMIN LISTING (tokens hidden)."""
    if not rows:
        return []
    return [portal_acesso_listing_to_dto(r) for r in rows]


def portal_acesso_issued_to_dto(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Project a portal_acessos row for the ONE-SHOT ISSUE moment (token shown)."""
    if not row:
        return row
    return {k: row.get(k) for k in _PORTAL_ACESSO_ISSUED_FIELDS if k in row}


def chamado_portal_row_to_dto(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Project a chamados_portal row to operational DTO."""
    if not row:
        return row
    return {k: row.get(k) for k in _CHAMADO_PORTAL_FIELDS if k in row}


def chamado_portal_rows_to_dto(rows: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Project a list of chamados_portal rows to DTO shape."""
    if not rows:
        return []
    return [chamado_portal_row_to_dto(r) for r in rows]


class PortalClienteService:
    """Service for client portal business logic."""

    def __init__(self, db_client, user_id: Optional[str] = None, org_id: Optional[str] = None):
        self.db = db_client
        self.user_id = user_id
        self.org_id = org_id

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

        # Store org_id for scoping subsequent queries
        self.org_id = acesso.get("org_id")

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
        contratos_q = self.db.table("contratos").select("*").eq(
            "cliente_id", cliente_id
        )
        if self.org_id:
            contratos_q = contratos_q.eq("org_id", self.org_id)
        contratos_result = contratos_q.order("created_at", desc=True).limit(20).execute()

        # Recent financial entries
        financeiro_q = self.db.table("lancamentos").select("*").eq(
            "cliente_id", cliente_id
        )
        if self.org_id:
            financeiro_q = financeiro_q.eq("org_id", self.org_id)
        financeiro_result = financeiro_q.order("data_vencimento", desc=True).limit(10).execute()

        # Shared documents
        documentos_q = self.db.table("documentos").select("*").eq(
            "cliente_id", cliente_id
        )
        if self.org_id:
            documentos_q = documentos_q.eq("org_id", self.org_id)
        documentos_result = documentos_q.order("created_at", desc=True).limit(20).execute()

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
        query = self.db.table("lancamentos").select("*").eq(
            "cliente_id", cliente_id
        )
        if self.org_id:
            query = query.eq("org_id", self.org_id)
        result = query.order("data_vencimento", desc=True).execute()

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
