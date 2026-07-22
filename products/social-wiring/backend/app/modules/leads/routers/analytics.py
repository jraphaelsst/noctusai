"""Analytics — /api/leads/analytics/*. All four accept the canonical
filter set (§5.1) via the shared ``get_lead_filters`` dependency, and all
four respond via ``success_response`` (§5.2: "Single-item + analytics ->
success_response")."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from noctusai_lib.primitives.responses import success_response

from app.dependencies import coerce_org_uuid, get_current_user_org_unified
from app.modules.leads.deps import get_leads_client
from app.modules.leads.routers.params import get_lead_filters
from app.modules.leads.services import analytics_service, leads_service
from app.modules.leads.services.query import LeadFilters

router = APIRouter(prefix="/api/leads/analytics", tags=["leads-analytics"])


@router.get("/summary")
def get_summary(
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
    filters: LeadFilters = Depends(get_lead_filters),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    refs = leads_service.build_refs(client, org_id)
    return success_response(analytics_service.summary(client, org_id, filters, refs))


@router.get("/timeseries")
def get_timeseries(
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
    filters: LeadFilters = Depends(get_lead_filters),
    grain: str = Query(default="mes"),
    split: Optional[str] = Query(default=None),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    refs = leads_service.build_refs(client, org_id)
    return success_response(
        analytics_service.timeseries(client, org_id, filters, refs, grain=grain, split=split)
    )


@router.get("/by-dimension")
def get_by_dimension(
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
    filters: LeadFilters = Depends(get_lead_filters),
    dim: str = Query(...),
    limit: int = Query(default=15, ge=1, le=100),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    refs = leads_service.build_refs(client, org_id)
    return success_response(
        analytics_service.by_dimension(client, org_id, filters, refs, dim=dim, limit=limit)
    )


@router.get("/heatmap")
def get_heatmap(
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
    filters: LeadFilters = Depends(get_lead_filters),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return success_response(analytics_service.heatmap(client, org_id, filters))


__all__ = ["router"]
