"""
Site Imóveis (Property Website Builder) API endpoints.

Allows organizations to configure and publish a simple property microsite
with their branding, colors, and contact info.

-- CREATE TABLE site_config (
--   id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
--   org_id uuid NOT NULL UNIQUE,
--   nome_site text NOT NULL,
--   slug text UNIQUE NOT NULL,
--   logo_url text,
--   cor_primaria text NOT NULL DEFAULT '#6366f1',
--   cor_secundaria text NOT NULL DEFAULT '#1a1a2e',
--   telefone text,
--   whatsapp text,
--   email_contato text,
--   sobre text,
--   is_active boolean NOT NULL DEFAULT true,
--   created_at timestamptz NOT NULL DEFAULT now()
-- );
"""
import logging
import re
from typing import Optional

from fastapi import APIRouter, HTTPException, Header, Query
from pydantic import BaseModel, Field, field_validator

from app.dependencies import get_current_user, get_user_client, get_admin_client, log_action
from app.responses import success_response


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/site", tags=["Site Imóveis"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class SiteConfigUpdate(BaseModel):
    nome_site: Optional[str] = Field(default=None, min_length=1, max_length=100)
    slug: Optional[str] = Field(default=None, min_length=3, max_length=60)
    logo_url: Optional[str] = Field(default=None, max_length=500)
    cor_primaria: Optional[str] = Field(default=None, max_length=9)
    cor_secundaria: Optional[str] = Field(default=None, max_length=9)
    telefone: Optional[str] = Field(default=None, max_length=20)
    whatsapp: Optional[str] = Field(default=None, max_length=20)
    email_contato: Optional[str] = Field(default=None, max_length=255)
    sobre: Optional[str] = Field(default=None, max_length=2000)
    is_active: Optional[bool] = None

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', v):
                raise ValueError(
                    "Slug deve conter apenas letras minúsculas, números e hífens"
                )
        return v

    @field_validator("cor_primaria", "cor_secundaria")
    @classmethod
    def validate_color(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            if not re.match(r'^#[0-9a-fA-F]{6}$', v):
                raise ValueError("Cor deve estar no formato hexadecimal (#RRGGBB)")
        return v


class SiteConfigCreate(BaseModel):
    nome_site: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=3, max_length=60)
    logo_url: Optional[str] = Field(default=None, max_length=500)
    cor_primaria: str = Field(default="#6366f1", max_length=9)
    cor_secundaria: str = Field(default="#1a1a2e", max_length=9)
    telefone: Optional[str] = Field(default=None, max_length=20)
    whatsapp: Optional[str] = Field(default=None, max_length=20)
    email_contato: Optional[str] = Field(default=None, max_length=255)
    sobre: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("slug")
    @classmethod
    def validate_slug(cls, v: str) -> str:
        if not re.match(r'^[a-z0-9]+(?:-[a-z0-9]+)*$', v):
            raise ValueError(
                "Slug deve conter apenas letras minúsculas, números e hífens"
            )
        return v

    @field_validator("cor_primaria", "cor_secundaria")
    @classmethod
    def validate_color(cls, v: str) -> str:
        if not re.match(r'^#[0-9a-fA-F]{6}$', v):
            raise ValueError("Cor deve estar no formato hexadecimal (#RRGGBB)")
        return v


# ---------------------------------------------------------------------------
# Authenticated endpoints (agent/admin manages site config)
# ---------------------------------------------------------------------------

@router.get("/config")
async def obter_config(authorization: Optional[str] = Header(None)):
    """Retorna a configuração do site da organização do usuário."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    result = db.table("site_config").select("*").limit(1).execute()
    data = result.data[0] if result.data else None
    return success_response(data)


@router.post("/config")
async def criar_config(body: SiteConfigCreate, authorization: Optional[str] = Header(None)):
    """Cria a configuração do site (primeira vez)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    # Check if config already exists
    existing = db.table("site_config").select("id").limit(1).execute()
    if existing.data:
        raise HTTPException(status_code=409, detail="Configuração de site já existe. Use PATCH para atualizar.")

    # Check slug uniqueness across all orgs
    admin = get_admin_client()
    slug_check = admin.table("site_config").select("id").eq("slug", body.slug).execute()
    if slug_check.data:
        raise HTTPException(status_code=409, detail="Este slug já está em uso por outra organização")

    data = body.model_dump(exclude_none=True)
    result = db.table("site_config").insert(data).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar configuração do site")

    log_action(user.id, "criar", "site_config", result.data["id"],
               f"Criou site '{body.nome_site}' com slug '{body.slug}'")
    return success_response(result.data)


@router.patch("/config")
async def atualizar_config(body: SiteConfigUpdate, authorization: Optional[str] = Header(None)):
    """Atualiza a configuração do site da organização."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    data = body.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    # Find existing config
    existing = db.table("site_config").select("id").limit(1).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Configuração de site não encontrada. Crie primeiro via POST.")

    config_id = existing.data[0]["id"]
    result = db.table("site_config").update(data).eq("id", config_id).select().single().execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao atualizar configuração")

    log_action(user.id, "editar", "site_config", config_id, "Atualizou configuração do site")
    return success_response(result.data)


@router.get("/preview")
async def preview_site(authorization: Optional[str] = Header(None)):
    """Retorna dados de preview do site (config + imóveis publicáveis)."""
    user, token = await get_current_user(authorization)
    db = get_user_client(token)

    config_result = db.table("site_config").select("*").limit(1).execute()
    config = config_result.data[0] if config_result.data else None

    # Get properties marked as ready for portals
    imoveis_result = db.table("ativos").select(
        "id, natureza, tipo_imovel, titulo_anuncio, descricao_seo, valor, cidade, bairro, "
        "logradouro, estado, quartos, suites, banheiros, vagas, area_privativa, area_total, "
        "fotos, tour_virtual_url, finalidade, status"
    ).eq("pronto_para_portais", True).eq("status", "ativo").order(
        "created_at", desc=True
    ).limit(100).execute()

    return success_response({
        "config": config,
        "imoveis": imoveis_result.data or [],
    })


# ---------------------------------------------------------------------------
# Public endpoints (no auth — accessed by visitors on the published site)
# ---------------------------------------------------------------------------

@router.get("/public/{slug}")
async def site_publico(slug: str):
    """Endpoint público: retorna dados do site por slug para renderização."""
    admin = get_admin_client()

    config_result = admin.table("site_config").select("*").eq(
        "slug", slug
    ).eq("is_active", True).single().execute()

    if not config_result.data:
        raise HTTPException(status_code=404, detail="Site não encontrado")

    config = config_result.data
    org_id = config.get("org_id")

    # Fetch published properties for this org
    imoveis_result = admin.table("ativos").select(
        "id, natureza, tipo_imovel, titulo_anuncio, descricao_seo, valor, cidade, bairro, "
        "logradouro, estado, quartos, suites, banheiros, vagas, area_privativa, area_total, "
        "fotos, tour_virtual_url, finalidade, latitude, longitude"
    ).eq("org_id", org_id).eq("pronto_para_portais", True).eq("status", "ativo").order(
        "valor", desc=True
    ).limit(200).execute()

    # Remove sensitive fields from config
    safe_config = {k: v for k, v in config.items() if k not in ("id", "org_id", "created_at")}

    return success_response({
        "config": safe_config,
        "imoveis": imoveis_result.data or [],
    })


@router.get("/public/{slug}/imovel/{imovel_id}")
async def site_imovel_detalhe(slug: str, imovel_id: str):
    """Endpoint público: retorna detalhes de um imóvel no site publicado."""
    admin = get_admin_client()

    # Validate slug exists and is active
    config_result = admin.table("site_config").select("id, org_id, whatsapp, telefone, email_contato").eq(
        "slug", slug
    ).eq("is_active", True).single().execute()
    if not config_result.data:
        raise HTTPException(status_code=404, detail="Site não encontrado")

    # Fetch property scoped to this org
    org_id = config_result.data["org_id"]
    imovel_result = admin.table("ativos").select(
        "id, natureza, tipo_imovel, titulo_anuncio, descricao_seo, valor, cidade, bairro, "
        "logradouro, estado, quartos, suites, banheiros, vagas, area_privativa, area_total, "
        "fotos, tour_virtual_url, finalidade, latitude, longitude, descricao"
    ).eq("id", imovel_id).eq("org_id", org_id).eq(
        "pronto_para_portais", True
    ).eq("status", "ativo").single().execute()

    if not imovel_result.data:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")

    # Provide contact info from site config
    imovel = imovel_result.data
    contato = {
        "whatsapp": config_result.data.get("whatsapp"),
        "telefone": config_result.data.get("telefone"),
        "email": config_result.data.get("email_contato"),
    }

    return success_response({
        "imovel": imovel,
        "contato": contato,
    })
