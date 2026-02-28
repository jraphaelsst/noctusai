"""
Meta API endpoints — Facebook/Instagram Lead Ads and Campaign sync.

Tables:
  erp.meta_config — Meta API credentials per org
  erp.meta_leads — imported leads from Lead Ads
  erp.meta_campanhas_sync — synced campaign metrics
"""
import logging
from typing import Optional
from fastapi import APIRouter, Header, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_user_client, get_admin_client
from app.services.meta_api_service import (
    MetaApiConfig,
    sync_leads,
    sync_campaigns,
    parse_lead_webhook,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/meta", tags=["meta-api"])


# ── Schemas ──────────────────────────────────────────────────────────

class MetaConfigCreate(BaseModel):
    page_id: Optional[str] = Field(default=None, max_length=100)
    access_token: Optional[str] = None
    ad_account_id: Optional[str] = Field(default=None, max_length=100)
    webhook_verify_token: Optional[str] = Field(default=None, max_length=200)


# ── Config Endpoints ─────────────────────────────────────────────────

@router.get("/config")
async def obter_config(authorization: Optional[str] = Header(None)):
    """Get Meta API configuration for the org."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)

    result = sb.table("meta_config").select("*").execute()
    config = result.data[0] if result.data else None

    # Mask access token for security
    if config and config.get("access_token"):
        config["access_token"] = config["access_token"][:10] + "..."

    return {"status": "success", "data": config}


@router.post("/config")
async def salvar_config(
    body: MetaConfigCreate,
    authorization: Optional[str] = Header(None),
):
    """Save or update Meta API configuration."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)
    org_id = user.user_metadata.get("org_id")

    data = {
        "org_id": org_id,
        "page_id": body.page_id,
        "access_token": body.access_token,
        "ad_account_id": body.ad_account_id,
        "webhook_verify_token": body.webhook_verify_token,
    }

    result = (
        sb.table("meta_config")
        .upsert(data, on_conflict="org_id")
        .execute()
    )

    return {"status": "success", "data": result.data[0] if result.data else data}


# ── Leads Endpoints ──────────────────────────────────────────────────

@router.get("/leads")
async def listar_leads(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    importado: Optional[bool] = None,
):
    """List imported leads from Facebook Lead Ads."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)

    query = sb.table("meta_leads").select("*", count="exact")
    if importado is not None:
        query = query.eq("importado", importado)
    query = query.order("created_at", desc=True)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return {
        "status": "success",
        "data": result.data or [],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": result.count or 0,
        },
    }


@router.post("/leads/sync")
async def sincronizar_leads(
    authorization: Optional[str] = Header(None),
    form_id: Optional[str] = Query(None),
):
    """Sync leads from Facebook Lead Ads."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)
    org_id = user.user_metadata.get("org_id")

    # Get config
    config_result = sb.table("meta_config").select("*").execute()
    if not config_result.data:
        raise HTTPException(status_code=400, detail="Configuração Meta não encontrada")

    cfg = config_result.data[0]
    config = MetaApiConfig(
        access_token=cfg.get("access_token"),
        page_id=cfg.get("page_id"),
        ad_account_id=cfg.get("ad_account_id"),
    )

    leads = await sync_leads(config, form_id)
    imported = 0

    for lead in leads:
        lead_id = lead.get("id", "")
        # Check if already exists
        existing = (
            sb.table("meta_leads")
            .select("id")
            .eq("lead_id", lead_id)
            .execute()
        )
        if existing.data:
            continue

        # Extract field data
        field_data = {}
        for fd in lead.get("field_data", []):
            field_data[fd.get("name", "")] = fd.get("values", [""])[0]

        sb.table("meta_leads").insert({
            "org_id": org_id,
            "lead_id": lead_id,
            "form_id": lead.get("form_id") or form_id,
            "form_name": lead.get("form_name"),
            "campo_data": field_data,
        }).execute()
        imported += 1

    return {
        "status": "success",
        "data": {"total_fetched": len(leads), "imported": imported},
    }


@router.post("/leads/{lead_id}/importar")
async def importar_lead_como_cliente(
    lead_id: str,
    authorization: Optional[str] = Header(None),
):
    """Import a Meta lead as a CRM client."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)
    org_id = user.user_metadata.get("org_id")

    # Get lead
    lead_result = (
        sb.table("meta_leads").select("*").eq("id", lead_id).single().execute()
    )
    if not lead_result.data:
        raise HTTPException(status_code=404, detail="Lead não encontrado")

    lead = lead_result.data
    campo = lead.get("campo_data", {})

    # Create client from lead data
    cliente_data = {
        "org_id": org_id,
        "nome": campo.get("full_name") or campo.get("nome", "Lead Facebook"),
        "email": campo.get("email"),
        "telefone": campo.get("phone_number") or campo.get("telefone"),
        "origem": "facebook",
        "etapa_atual": "lead",
        "usuario_id": user.id,
    }

    cliente_result = sb.table("clientes").insert(cliente_data).execute()
    cliente_id = cliente_result.data[0]["id"] if cliente_result.data else None

    # Mark lead as imported
    if cliente_id:
        sb.table("meta_leads").update({
            "importado": True,
            "importado_em": "now()",
            "cliente_id": cliente_id,
        }).eq("id", lead_id).execute()

    return {
        "status": "success",
        "data": {"cliente_id": cliente_id, "lead_id": lead_id},
    }


# ── Campaigns Endpoints ──────────────────────────────────────────────

@router.get("/campanhas")
async def listar_campanhas(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List synced ad campaigns with metrics."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)

    query = (
        sb.table("meta_campanhas_sync")
        .select("*", count="exact")
        .order("last_sync", desc=True)
    )
    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return {
        "status": "success",
        "data": result.data or [],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": result.count or 0,
        },
    }


@router.post("/campanhas/sync")
async def sincronizar_campanhas(authorization: Optional[str] = Header(None)):
    """Sync campaign data from Facebook Ads Manager."""
    user, token = await get_current_user(authorization)
    sb = get_user_client(token)
    org_id = user.user_metadata.get("org_id")

    config_result = sb.table("meta_config").select("*").execute()
    if not config_result.data:
        raise HTTPException(status_code=400, detail="Configuração Meta não encontrada")

    cfg = config_result.data[0]
    config = MetaApiConfig(
        access_token=cfg.get("access_token"),
        page_id=cfg.get("page_id"),
        ad_account_id=cfg.get("ad_account_id"),
    )

    campaigns = await sync_campaigns(config)
    synced = 0

    for camp in campaigns:
        camp["org_id"] = org_id
        camp["last_sync"] = "now()"
        sb.table("meta_campanhas_sync").upsert(
            camp, on_conflict="org_id,campaign_id"
        ).execute()
        synced += 1

    return {
        "status": "success",
        "data": {"total_synced": synced},
    }


# ── Webhook (unauthenticated — called by Meta) ──────────────────────

@router.get("/webhook")
async def meta_webhook_verify(
    request: Request,
    hub_mode: Optional[str] = Query(None, alias="hub.mode"),
    hub_verify_token: Optional[str] = Query(None, alias="hub.verify_token"),
    hub_challenge: Optional[str] = Query(None, alias="hub.challenge"),
):
    """Meta webhook verification (GET)."""
    if hub_mode == "subscribe" and hub_verify_token:
        # Verify against any org's config
        admin = get_admin_client()
        result = (
            admin.table("meta_config")
            .select("org_id")
            .eq("webhook_verify_token", hub_verify_token)
            .execute()
        )
        if result.data:
            return int(hub_challenge) if hub_challenge else ""

    raise HTTPException(status_code=403, detail="Verification failed")


@router.post("/webhook")
async def meta_webhook_event(request: Request):
    """Receive Meta Lead Ads webhook events (POST)."""
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    lead_data = parse_lead_webhook(payload)
    if not lead_data:
        return {"status": "ignored"}

    admin = get_admin_client()
    if not admin:
        raise HTTPException(status_code=503, detail="Serviço indisponível")

    page_id = lead_data.get("page_id")
    config_result = (
        admin.table("meta_config")
        .select("org_id, access_token")
        .eq("page_id", page_id)
        .execute()
    )
    if not config_result.data:
        return {"status": "ignored", "reason": "page_not_configured"}

    org_id = config_result.data[0]["org_id"]

    # Store the lead reference (full data fetched on sync)
    admin.table("meta_leads").insert({
        "org_id": org_id,
        "lead_id": lead_data["lead_id"],
        "form_id": lead_data.get("form_id"),
        "campo_data": {},
    }).execute()

    logger.info(f"Meta lead webhook stored: {lead_data['lead_id']} for org {org_id}")
    return {"status": "ok"}
