"""
Meta API endpoints — Facebook/Instagram Lead Ads and Campaign sync.

Tables:
  erp.meta_config — Meta API credentials per org
  erp.meta_leads — imported leads from Lead Ads
  erp.meta_campanhas_sync — synced campaign metrics
"""
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Header, Query, Request
from pydantic import Field

from noctusai_lib.security.webhook_signatures import (
    ResolvedSecret,
    VerifiedWebhook,
    webhook_endpoint,
)

from app.config import settings
from app.dependencies import get_current_user, get_user_client, get_admin_client, get_org_id
from app.rate_limit import limiter
from app.responses import success_response, paginated_response
from app.services.meta_api_service import (
    MetaApiConfig,
    sync_leads,
    sync_campaigns,
    parse_lead_webhook,
)
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/meta", tags=["meta-api"])


async def _resolve_meta_secret(request: Request, body: bytes) -> ResolvedSecret:
    """Resolve the per-page Meta webhook secret from `meta_config`.

    Parses the (unverified) body to extract `page_id`, fetches the row,
    stashes the resolved org_id + lead_data on `extras` so the handler
    avoids re-parsing.
    """
    try:
        payload = json.loads(body) if body else {}
    except (ValueError, TypeError):
        return ResolvedSecret(secret=None, extras=None)

    lead_data = parse_lead_webhook(payload)
    if not lead_data:
        return ResolvedSecret(secret=None, extras={"lead_data": None, "org_id": None})

    page_id = lead_data.get("page_id")
    admin = get_admin_client()
    if not admin or not page_id:
        return ResolvedSecret(secret=None, extras={"lead_data": lead_data, "org_id": None})

    res = (
        admin.table("meta_config")
        .select("org_id, access_token, webhook_verify_token")
        .eq("page_id", page_id)
        .execute()
    )
    if not res.data:
        return ResolvedSecret(secret=None, extras={"lead_data": lead_data, "org_id": None})

    row = res.data[0]
    return ResolvedSecret(
        secret=row.get("webhook_verify_token") or None,
        extras={"lead_data": lead_data, "org_id": row["org_id"]},
    )


# ── Schemas ──────────────────────────────────────────────────────────

class MetaConfigCreate(StrictHttpModel):
    page_id: Optional[str] = Field(default=None, max_length=100)
    access_token: Optional[str] = None
    ad_account_id: Optional[str] = Field(default=None, max_length=100)
    webhook_verify_token: Optional[str] = Field(default=None, max_length=200)


# ── Config Endpoints ─────────────────────────────────────────────────

@router.get("/config")
async def obter_config(auth = Depends(get_current_user)):
    """Get Meta API configuration for the org."""
    user, token = auth
    sb = get_user_client(token)

    result = sb.table("meta_config").select("*").execute()
    config = result.data[0] if result.data else None

    # Mask access token for security
    if config and config.get("access_token"):
        config["access_token"] = config["access_token"][:10] + "..."

    return success_response(config)


@router.post("/config")
async def salvar_config(
    body: MetaConfigCreate,
    auth = Depends(get_current_user)):
    """Save or update Meta API configuration."""
    user, token = auth
    sb = get_user_client(token)
    org_id = get_org_id(user)

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

    return success_response(result.data[0] if result.data else data)


# ── Leads Endpoints ──────────────────────────────────────────────────

@router.get("/leads")
async def listar_leads(
    auth = Depends(get_current_user), page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    importado: Optional[bool] = None,
):
    """List imported leads from Facebook Lead Ads."""
    user, token = auth
    sb = get_user_client(token)

    query = sb.table("meta_leads").select("*", count="exact")
    if importado is not None:
        query = query.eq("importado", importado)
    query = query.order("created_at", desc=True)

    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return paginated_response(result.data or [], result.count or 0, page, page_size)


@router.post("/leads/sync")
async def sincronizar_leads(
    auth = Depends(get_current_user), form_id: Optional[str] = Query(None),
):
    """Sync leads from Facebook Lead Ads."""
    user, token = auth
    sb = get_user_client(token)
    org_id = get_org_id(user)

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

    # Batch check which leads already exist (1 query instead of N)
    lead_ids = [lead.get("id", "") for lead in leads]
    existing_result = sb.table("meta_leads").select("lead_id").in_(
        "lead_id", lead_ids
    ).execute() if lead_ids else type("R", (), {"data": []})()
    existing_ids = {r["lead_id"] for r in (existing_result.data or [])}

    # Batch insert new leads
    new_rows = []
    for lead in leads:
        lead_id = lead.get("id", "")
        if lead_id in existing_ids:
            continue
        field_data = {}
        for fd in lead.get("field_data", []):
            field_data[fd.get("name", "")] = fd.get("values", [""])[0]
        new_rows.append({
            "org_id": org_id,
            "lead_id": lead_id,
            "form_id": lead.get("form_id") or form_id,
            "form_name": lead.get("form_name"),
            "campo_data": field_data,
        })

    if new_rows:
        sb.table("meta_leads").insert(new_rows).execute()

    return success_response({"total_fetched": len(leads), "imported": len(new_rows)})


@router.post("/leads/{lead_id}/importar")
async def importar_lead_como_cliente(
    lead_id: str,
    auth = Depends(get_current_user)):
    """Import a Meta lead as a CRM client."""
    user, token = auth
    sb = get_user_client(token)
    org_id = get_org_id(user)

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
        from datetime import datetime, timezone
        sb.table("meta_leads").update({
            "importado": True,
            "importado_em": datetime.now(timezone.utc).isoformat(),
            "cliente_id": cliente_id,
        }).eq("id", lead_id).execute()

    return success_response({"cliente_id": cliente_id, "lead_id": lead_id})


# ── Campaigns Endpoints ──────────────────────────────────────────────

@router.get("/campanhas")
async def listar_campanhas(
    auth = Depends(get_current_user), page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """List synced ad campaigns with metrics."""
    user, token = auth
    sb = get_user_client(token)

    query = (
        sb.table("meta_campanhas_sync")
        .select("*", count="exact")
        .order("last_sync", desc=True)
    )
    offset = (page - 1) * page_size
    result = query.range(offset, offset + page_size - 1).execute()

    return paginated_response(result.data or [], result.count or 0, page, page_size)


@router.post("/campanhas/sync")
async def sincronizar_campanhas(auth = Depends(get_current_user)):
    """Sync campaign data from Facebook Ads Manager."""
    user, token = auth
    sb = get_user_client(token)
    org_id = get_org_id(user)

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

    from datetime import datetime, timezone
    now_iso = datetime.now(timezone.utc).isoformat()
    for camp in campaigns:
        camp["org_id"] = org_id
        camp["last_sync"] = now_iso

    if campaigns:
        sb.table("meta_campanhas_sync").upsert(
            campaigns, on_conflict="org_id,campaign_id"
        ).execute()

    return success_response({"total_synced": len(campaigns)})


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
@limiter.limit(settings.webhook_rate_limit)
async def meta_webhook_event(
    request: Request,
    verified: VerifiedWebhook = webhook_endpoint(
        secret_resolver=_resolve_meta_secret,
        scheme="sha256_prefixed",
        signature_header="X-Hub-Signature-256",
        bypass_when_unset=True,
        log_prefix="meta-webhook",
    ),
):
    """Receive Meta Lead Ads webhook events (POST)."""
    extras = verified.extras or {}
    lead_data = extras.get("lead_data")
    org_id = extras.get("org_id")

    if not lead_data:
        return {"status": "ignored"}
    if not org_id:
        return {"status": "ignored", "reason": "page_not_configured"}

    admin = get_admin_client()
    if not admin:
        raise HTTPException(status_code=503, detail="Serviço indisponível")

    # Store the lead reference (full data fetched on sync); upsert to handle duplicate webhooks
    admin.table("meta_leads").upsert({
        "org_id": org_id,
        "lead_id": lead_data["lead_id"],
        "form_id": lead_data.get("form_id"),
        "campo_data": {},
    }, on_conflict="lead_id").execute()

    logger.info(f"Meta lead webhook stored: {lead_data['lead_id']} for org {org_id}")
    return {"status": "ok"}
