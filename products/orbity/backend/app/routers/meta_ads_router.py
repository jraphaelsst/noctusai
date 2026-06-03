"""
Meta Ads router — ad accounts, campaigns, campaign metrics, sync seam,
and spend-vs-leads aggregate.

Auth boundary:
  - All /api/meta-ads/* → Depends(get_current_user_org) → strict 401

Endpoints:
  GET    /api/meta-ads/ad-accounts                  list ad accounts (paginated)
  POST   /api/meta-ads/ad-accounts                  connect an ad account → 201
  GET    /api/meta-ads/ad-accounts/{id}             ad account detail
  PATCH  /api/meta-ads/ad-accounts/{id}             update ad account
  DELETE /api/meta-ads/ad-accounts/{id}             disconnect ad account

  GET    /api/meta-ads/campaigns                    list campaigns (paginated)
  POST   /api/meta-ads/campaigns                    create campaign → 201
  GET    /api/meta-ads/campaigns/{id}               campaign detail
  PATCH  /api/meta-ads/campaigns/{id}               update campaign
  DELETE /api/meta-ads/campaigns/{id}               delete campaign
  PATCH  /api/meta-ads/campaigns/{id}/situation     update gestor situation signal

  GET    /api/meta-ads/campaigns/{id}/metrics       list daily metrics
  POST   /api/meta-ads/sync                         trigger campaign sync (seam)
  GET    /api/meta-ads/aggregate                    spend vs leads per client/month

Live-integration seams (NOC-REMEDIATE[orbity-meta-ads-live]):
  - OAuth initiate/callback: not in this router — the real OAuth connect flow
    goes through noctusai_lib.security.oauth + a dedicated connect endpoint.
    The router here covers CRUD against the already-connected accounts.
  - POST /api/meta-ads/sync: calls MetaAdsService.sync_campaigns() which
    defaults to FakeMetaAdsClient. Wire the real client at service construction
    when vault/credentials are ready.
  - CAPI lead-quality feedback: not in this router — owned by the CRM sync
    pipeline (lead scored → CAPI dispatch). NOC-REMEDIATE[orbity-meta-ads-live].
"""
from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    coerce_org_uuid,
    get_current_user_org,
    get_user_client,
)
from app.schemas.meta_ads import (
    AdAccountCreate,
    AdAccountOut,
    AdAccountUpdate,
    CampaignCreate,
    CampaignMetricOut,
    CampaignMetricUpsert,
    CampaignOut,
    CampaignUpdate,
    SituationUpdateRequest,
    SpendLeadsAggregate,
    SyncCampaignsRequest,
    SyncCampaignsResponse,
)
from app.services.meta_ads_service import MetaAdsService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Meta Ads"])


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _svc(token: str, org_id: UUID) -> MetaAdsService:
    return MetaAdsService(get_user_client(token), org_id=org_id)


# ---------------------------------------------------------------------------
# Ad accounts
# ---------------------------------------------------------------------------

@router.get("/api/meta-ads/ad-accounts", status_code=status.HTTP_200_OK)
async def list_ad_accounts(
    client_id: str | None = Query(default=None),
    account_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_ad_accounts(
            client_id=client_id,
            status=account_status,
            page=page,
            page_size=page_size,
        )
    except Exception:
        logger.exception("meta_ads.list_ad_accounts failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar contas de anúncio")


@router.post(
    "/api/meta-ads/ad-accounts",
    response_model=AdAccountOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_ad_account(
    payload: AdAccountCreate,
    auth: tuple = Depends(get_current_user_org),
) -> AdAccountOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_ad_account(payload.model_dump(exclude_none=True))
    except Exception:
        logger.exception("meta_ads.create_ad_account failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao conectar conta de anúncio")
    return AdAccountOut(**row)


@router.get(
    "/api/meta-ads/ad-accounts/{account_id}",
    response_model=AdAccountOut,
    status_code=status.HTTP_200_OK,
)
async def get_ad_account(
    account_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> AdAccountOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_ad_account(account_id)
    except Exception:
        logger.exception("meta_ads.get_ad_account failed org=%s id=%s", org_id, account_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar conta de anúncio")
    if not row:
        raise HTTPException(status_code=404, detail="Conta de anúncio não encontrada")
    return AdAccountOut(**row)


@router.patch(
    "/api/meta-ads/ad-accounts/{account_id}",
    response_model=AdAccountOut,
    status_code=status.HTTP_200_OK,
)
async def update_ad_account(
    account_id: str,
    payload: AdAccountUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> AdAccountOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _svc(token, org_id).update_ad_account(account_id, data)
    except Exception:
        logger.exception(
            "meta_ads.update_ad_account failed org=%s id=%s", org_id, account_id
        )
        raise HTTPException(status_code=502, detail="Falha ao atualizar conta de anúncio")
    if not row:
        raise HTTPException(status_code=404, detail="Conta de anúncio não encontrada")
    return AdAccountOut(**row)


@router.delete(
    "/api/meta-ads/ad-accounts/{account_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_ad_account(
    account_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _svc(token, org_id).delete_ad_account(account_id)
    except Exception:
        logger.exception(
            "meta_ads.delete_ad_account failed org=%s id=%s", org_id, account_id
        )
        raise HTTPException(status_code=502, detail="Falha ao desconectar conta de anúncio")
    if not ok:
        raise HTTPException(status_code=404, detail="Conta de anúncio não encontrada")
    return {"ok": True, "id": account_id}


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

@router.get("/api/meta-ads/campaigns", status_code=status.HTTP_200_OK)
async def list_campaigns(
    ad_account_id: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    situation: str | None = Query(default=None),
    campaign_status: str | None = Query(default=None, alias="status"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_campaigns(
            ad_account_id=ad_account_id,
            client_id=client_id,
            situation=situation,
            status=campaign_status,
            page=page,
            page_size=page_size,
        )
    except Exception:
        logger.exception("meta_ads.list_campaigns failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar campanhas")


@router.post(
    "/api/meta-ads/campaigns",
    response_model=CampaignOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_campaign(
    payload: CampaignCreate,
    auth: tuple = Depends(get_current_user_org),
) -> CampaignOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_campaign(
            payload.model_dump(exclude_none=True, mode="json")
        )
    except Exception:
        logger.exception("meta_ads.create_campaign failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar campanha")
    return CampaignOut(**row)


@router.get(
    "/api/meta-ads/campaigns/{campaign_id}",
    response_model=CampaignOut,
    status_code=status.HTTP_200_OK,
)
async def get_campaign(
    campaign_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> CampaignOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_campaign(campaign_id)
    except Exception:
        logger.exception(
            "meta_ads.get_campaign failed org=%s id=%s", org_id, campaign_id
        )
        raise HTTPException(status_code=502, detail="Falha ao buscar campanha")
    if not row:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    return CampaignOut(**row)


@router.patch(
    "/api/meta-ads/campaigns/{campaign_id}",
    response_model=CampaignOut,
    status_code=status.HTTP_200_OK,
)
async def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> CampaignOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _svc(token, org_id).update_campaign(campaign_id, data)
    except Exception:
        logger.exception(
            "meta_ads.update_campaign failed org=%s id=%s", org_id, campaign_id
        )
        raise HTTPException(status_code=502, detail="Falha ao atualizar campanha")
    if not row:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    return CampaignOut(**row)


@router.delete(
    "/api/meta-ads/campaigns/{campaign_id}",
    status_code=status.HTTP_200_OK,
)
async def delete_campaign(
    campaign_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _svc(token, org_id).delete_campaign(campaign_id)
    except Exception:
        logger.exception(
            "meta_ads.delete_campaign failed org=%s id=%s", org_id, campaign_id
        )
        raise HTTPException(status_code=502, detail="Falha ao deletar campanha")
    if not ok:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    return {"ok": True, "id": campaign_id}


@router.patch(
    "/api/meta-ads/campaigns/{campaign_id}/situation",
    response_model=CampaignOut,
    status_code=status.HTTP_200_OK,
)
async def update_situation(
    campaign_id: str,
    payload: SituationUpdateRequest,
    auth: tuple = Depends(get_current_user_org),
) -> CampaignOut:
    """Update the gestor situation signal (on-track / attention / off)."""
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).update_situation(campaign_id, payload.situation)
    except Exception:
        logger.exception(
            "meta_ads.update_situation failed org=%s id=%s", org_id, campaign_id
        )
        raise HTTPException(status_code=502, detail="Falha ao atualizar situação da campanha")
    if not row:
        raise HTTPException(status_code=404, detail="Campanha não encontrada")
    return CampaignOut(**row)


# ---------------------------------------------------------------------------
# Campaign metrics
# ---------------------------------------------------------------------------

@router.get(
    "/api/meta-ads/campaigns/{campaign_id}/metrics",
    status_code=status.HTTP_200_OK,
)
async def list_campaign_metrics(
    campaign_id: str,
    date_from: str | None = Query(default=None, description="ISO date YYYY-MM-DD"),
    date_to: str | None = Query(default=None, description="ISO date YYYY-MM-DD"),
    auth: tuple = Depends(get_current_user_org),
) -> list:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_campaign_metrics(
            campaign_id,
            date_from=date_from,
            date_to=date_to,
        )
    except Exception:
        logger.exception(
            "meta_ads.list_campaign_metrics failed org=%s campaign=%s",
            org_id, campaign_id,
        )
        raise HTTPException(status_code=502, detail="Falha ao listar métricas de campanha")


# ---------------------------------------------------------------------------
# Sync seam (NOC-REMEDIATE[orbity-meta-ads-live])
# ---------------------------------------------------------------------------

@router.post(
    "/api/meta-ads/sync",
    response_model=SyncCampaignsResponse,
    status_code=status.HTTP_200_OK,
)
async def sync_campaigns(
    payload: SyncCampaignsRequest,
    auth: tuple = Depends(get_current_user_org),
) -> SyncCampaignsResponse:
    """Trigger a campaign sync from Meta for a given ad account.

    NOC-REMEDIATE[orbity-meta-ads-live]: The service defaults to FakeMetaAdsClient.
    The response includes `source: "fake" | "live"` so the caller knows which
    adapter ran. Wire the real client once the vault/credential store is available.

    CAPI lead-quality feedback is a separate seam — owned by the CRM pipeline
    and not triggered here. NOC-REMEDIATE[orbity-meta-ads-live].
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        result = _svc(token, org_id).sync_campaigns(str(payload.ad_account_id))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception:
        logger.exception(
            "meta_ads.sync_campaigns failed org=%s account=%s",
            org_id, payload.ad_account_id,
        )
        raise HTTPException(status_code=502, detail="Falha ao sincronizar campanhas")
    return SyncCampaignsResponse(**result)


# ---------------------------------------------------------------------------
# Aggregate — spend vs leads per client/month
# ---------------------------------------------------------------------------

@router.get(
    "/api/meta-ads/aggregate",
    response_model=SpendLeadsAggregate,
    status_code=status.HTTP_200_OK,
)
async def get_aggregate(
    period_start: str = Query(..., description="ISO date YYYY-MM-DD"),
    period_end: str = Query(..., description="ISO date YYYY-MM-DD"),
    client_id: str | None = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
) -> SpendLeadsAggregate:
    """Spend vs leads grouped by client × month (cash-flow style).

    Used by the gestor overview dashboard to assess ROI per client
    over a period.
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        result = _svc(token, org_id).get_spend_leads_aggregate(
            period_start=period_start,
            period_end=period_end,
            client_id=client_id,
        )
    except Exception:
        logger.exception("meta_ads.aggregate failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao calcular agregado")
    return SpendLeadsAggregate(**result)
