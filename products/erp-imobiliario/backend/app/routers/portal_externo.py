"""
Portal Externo (Tenant/Owner Portal) API endpoints.

Read-only portal for property owners and tenants accessed via secure token links.
Agents generate portal links; owners/tenants access data without full auth.

-- CREATE TABLE portal_tokens (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL,
--   tipo text NOT NULL CHECK (tipo IN ('proprietario', 'locatario')),
--   pessoa_id uuid NOT NULL,
--   token text UNIQUE NOT NULL,
--   nome text NOT NULL,
--   email text,
--   expires_at timestamptz NOT NULL DEFAULT (now() + interval '90 days'),
--   is_active boolean NOT NULL DEFAULT true,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
import secrets
from typing import Any, Dict, List, Optional, Literal
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import Field

from app.dependencies import get_current_user, get_user_client, get_admin_client, log_action, first_or_none
from app.responses import success_response, paginated_response, ok_response, calculate_pagination
from app.config import settings
from app.rate_limit import limiter
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.rate_limit_policies import DEFAULT_PORTAL_RL

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/portal", tags=["Portal Externo"])


# ---------------------------------------------------------------------------
# DTO mappers — token-leak defense (mirrors portal_cliente Phase 3b shape)
# ---------------------------------------------------------------------------
# Admin listing (`GET /api/portal/tokens`) INTENTIONALLY hides raw bearer tokens
# to prevent shoulder-surf leak from the agents UI. Re-issue via `POST /gerar-link`
# remains the one-shot share moment (which includes `token` + `link`).
_PORTAL_TOKEN_LISTING_FIELDS: tuple = (
    "id",
    "tipo",
    "pessoa_id",
    "nome",
    "email",
    "expires_at",
    "is_active",
    "created_at",
)

_PORTAL_TOKEN_ISSUED_FIELDS: tuple = (
    "id",
    "tipo",
    "pessoa_id",
    "nome",
    "email",
    "token",
    "expires_at",
    "is_active",
    "created_at",
)


def portal_token_listing_to_dto(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Project a portal_tokens row for ADMIN LISTING (token hidden)."""
    if not row:
        return row
    return {k: row.get(k) for k in _PORTAL_TOKEN_LISTING_FIELDS if k in row}


def portal_token_listing_rows_to_dto(rows: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """Project a list of portal_tokens rows for ADMIN LISTING (tokens hidden)."""
    if not rows:
        return []
    return [portal_token_listing_to_dto(r) for r in rows]


def portal_token_issued_to_dto(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Project a portal_tokens row for the ONE-SHOT ISSUE moment (token shown)."""
    if not row:
        return row
    return {k: row.get(k) for k in _PORTAL_TOKEN_ISSUED_FIELDS if k in row}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class GerarLinkBody(StrictHttpModel):
    tipo: Literal["proprietario", "locatario"]
    pessoa_id: str
    nome: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = Field(default=None, max_length=255)
    dias_validade: int = Field(default=90, ge=1, le=365)


# ---------------------------------------------------------------------------
# Helper: validate portal token and return associated data
# ---------------------------------------------------------------------------

def _get_admin():
    """Get admin client for portal access (bypasses RLS since tokens are public-facing)."""
    return get_admin_client()


def _validate_token(token: str) -> dict:
    """Validate a portal token. Returns token row or raises 401/404."""
    admin = _get_admin()
    result = admin.table("portal_tokens").select("*").eq(
        "token", token
    ).eq("is_active", True).single().execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Link de acesso inválido ou expirado")

    token_data = result.data

    # Check expiration
    expires_at = datetime.fromisoformat(token_data["expires_at"].replace("Z", "+00:00"))
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Link de acesso expirado")

    return token_data


# ---------------------------------------------------------------------------
# Authenticated endpoint: generate portal link
# ---------------------------------------------------------------------------

@router.post("/gerar-link")
async def gerar_link(body: GerarLinkBody, auth = Depends(get_current_user)):
    """Gera um link de acesso ao portal para proprietário ou locatário. Requer autenticação."""
    user, token = auth
    db = get_user_client(token)

    # Generate secure token
    portal_token = secrets.token_urlsafe(48)
    expires_at = (datetime.now(timezone.utc) + timedelta(days=body.dias_validade)).isoformat()

    data = {
        "tipo": body.tipo,
        "pessoa_id": body.pessoa_id,
        "nome": body.nome,
        "email": body.email,
        "token": portal_token,
        "expires_at": expires_at,
        "is_active": True,
    }

    result = db.table("portal_tokens").insert(data).execute()
    row = first_or_none(result)
    if not row:
        raise HTTPException(status_code=500, detail="Erro ao gerar link de acesso")

    log_action(user.id, "criar", "portal_token", row["id"],
               f"Gerou link de portal ({body.tipo}) para {body.nome}")

    issued = portal_token_issued_to_dto(row) or {}
    return success_response({
        **issued,
        "link": f"/portal/{portal_token}",
    })


@router.get("/tokens")
async def listar_tokens(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    auth = Depends(get_current_user)):
    """Lista todos os tokens de portal gerados (requer autenticação)."""
    user, token = auth
    db = get_user_client(token)

    validated_page, validated_page_size, offset = calculate_pagination(
        page, page_size, settings.max_page_size
    )

    count_result = db.table("portal_tokens").select("id", count="exact").execute()
    total = count_result.count if count_result.count is not None else 0

    result = db.table("portal_tokens").select("*").order(
        "created_at", desc=True
    ).range(offset, offset + validated_page_size - 1).execute()

    # SECURITY: listing intentionally hides raw bearer tokens. Re-issue via gerar-link.
    return paginated_response(
        portal_token_listing_rows_to_dto(result.data or []),
        total,
        validated_page,
        validated_page_size,
    )


@router.delete("/tokens/{token_id}")
async def revogar_token(token_id: str, auth = Depends(get_current_user)):
    """Revoga (desativa) um token de portal."""
    user, token = auth
    db = get_user_client(token)

    result = db.table("portal_tokens").update(
        {"is_active": False}
    ).eq("id", token_id).execute()
    row = first_or_none(result)

    if not row:
        raise HTTPException(status_code=404, detail="Token não encontrado")

    log_action(user.id, "revogar", "portal_token", token_id, f"Revogou token de portal {token_id}")
    return ok_response("Token revogado com sucesso")


# ---------------------------------------------------------------------------
# Public endpoints: accessed via portal token (NO auth required)
# ---------------------------------------------------------------------------

@router.get("/{portal_token}")
@limiter.limit(DEFAULT_PORTAL_RL)
async def validar_portal(request: Request, portal_token: str):
    """Valida um token de portal e retorna dados básicos."""
    token_data = _validate_token(portal_token)
    return success_response({
        "tipo": token_data["tipo"],
        "nome": token_data["nome"],
        "expires_at": token_data["expires_at"],
    })


@router.get("/{portal_token}/imoveis")
@limiter.limit(DEFAULT_PORTAL_RL)
async def portal_imoveis(request: Request, portal_token: str):
    """Retorna os imóveis do proprietário (via portal token)."""
    token_data = _validate_token(portal_token)
    if token_data["tipo"] != "proprietario":
        raise HTTPException(status_code=403, detail="Acesso apenas para proprietários")

    admin = _get_admin()
    result = admin.table("ativos").select(
        "id, natureza, tipo_imovel, cidade, bairro, logradouro, numero, valor, status, "
        "quartos, area_privativa, fotos, created_at"
    ).eq("org_id", token_data["org_id"]).eq("proprietario_id", token_data["pessoa_id"]).order(
        "created_at", desc=True
    ).execute()

    return success_response(result.data or [])


@router.get("/{portal_token}/financeiro")
@limiter.limit(DEFAULT_PORTAL_RL)
async def portal_financeiro(request: Request, portal_token: str):
    """Retorna o extrato financeiro do proprietário (aluguéis recebidos, taxas)."""
    token_data = _validate_token(portal_token)
    if token_data["tipo"] != "proprietario":
        raise HTTPException(status_code=403, detail="Acesso apenas para proprietários")

    admin = _get_admin()

    # Fetch financial records associated with the owner
    result = admin.table("lancamentos").select("*").eq(
        "org_id", token_data["org_id"]
    ).eq(
        "cliente_id", token_data["pessoa_id"]
    ).order("data_vencimento", desc=True).limit(100).execute()

    return success_response(result.data or [])


@router.get("/{portal_token}/contratos")
@limiter.limit(DEFAULT_PORTAL_RL)
async def portal_contratos(request: Request, portal_token: str):
    """Retorna os contratos do locatário (via portal token)."""
    token_data = _validate_token(portal_token)

    admin = _get_admin()
    result = admin.table("contratos").select("*").eq(
        "org_id", token_data["org_id"]
    ).eq(
        "cliente_id", token_data["pessoa_id"]
    ).order("created_at", desc=True).execute()

    return success_response(result.data or [])


@router.get("/{portal_token}/documentos")
@limiter.limit(DEFAULT_PORTAL_RL)
async def portal_documentos(request: Request, portal_token: str):
    """Retorna documentos COMPARTILHADOS com o proprietário ou locatário.

    LGPD gate (Art. 5 + Art. 11 + Art. 18): only rows explicitly marked
    `compartilhado_portal = true` are visible to the bearer-token holder.
    Default is FALSE (migration `031_documentos_compartilhado_portal.sql`),
    so admin must opt-in per-document via `PATCH /api/documentos/{id}/
    compartilhamento` before the cliente sees anything.

    Every successful read is logged via `log_action(..., 'documento_portal_acesso')`
    so the cliente can exercise Art. 18 right-to-know about exposure history.
    """
    token_data = _validate_token(portal_token)

    admin = _get_admin()
    result = admin.table("documentos").select("*").eq(
        "org_id", token_data["org_id"]
    ).eq(
        "cliente_id", token_data["pessoa_id"]
    ).eq(
        "compartilhado_portal", True
    ).order("created_at", desc=True).execute()

    rows = result.data or []

    # LGPD Art. 18 audit-log — record every portal-side READ. Uses the
    # token-issuing user.id is NOT available here (portal access is public-
    # by-token); we audit under the cliente's own pessoa_id so the data-
    # subject access path can reconstruct exposure history per-cliente.
    log_action(
        token_data["pessoa_id"],
        "ler",
        "documento_portal_acesso",
        token_data.get("id"),
        f"Cliente acessou {len(rows)} documento(s) via portal "
        f"({token_data['tipo']})",
        {
            "documento_ids": [r.get("id") for r in rows if r.get("id")],
            "org_id": token_data["org_id"],
            "portal_token_id": token_data.get("id"),
        },
    )

    return success_response(rows)
