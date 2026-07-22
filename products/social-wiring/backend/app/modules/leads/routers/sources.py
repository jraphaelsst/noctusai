"""Sources CRUD + alias map — /api/leads/sources/*.

``GET /sources`` is NOT paginated per the contract (``success_response``).
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from noctusai_lib.primitives.exceptions import NotFoundError
from noctusai_lib.primitives.responses import deleted_response, success_response

from app.dependencies import coerce_org_uuid, get_current_user_org_unified
from app.modules.leads.deps import get_leads_client
from app.modules.leads.schemas import (
    LeadSourceAliasCreate,
    LeadSourceCreate,
    LeadSourceUpdate,
)
from app.modules.leads.services import dimensions_service

router = APIRouter(prefix="/api/leads/sources", tags=["leads-sources"])


@router.get("")
def list_sources(
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return success_response(dimensions_service.list_sources(client, org_id))


@router.post("", status_code=201)
def create_source(
    body: LeadSourceCreate,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    row = dimensions_service.create_source(client, org_id, **body.model_dump())
    return success_response(row)


# NOTE: `/aliases*` registered before `/{source_id}` — same
# route-order-matters footgun as `routers/leads.py`'s `/facets`.
@router.get("/aliases")
def list_aliases(
    unmapped: bool = Query(default=False),
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    if unmapped:
        return success_response(dimensions_service.list_unmapped_origens(client, org_id))
    return success_response(dimensions_service.list_source_aliases(client, org_id))


@router.post("/aliases", status_code=201)
def create_alias(
    body: LeadSourceAliasCreate,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    row = dimensions_service.create_source_alias(
        client, org_id, alias=body.alias, source_id=body.source_id
    )
    return success_response(row)


@router.delete("/aliases/{alias_id}")
def delete_alias(
    alias_id: UUID,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    deleted = dimensions_service.delete_source_alias(client, org_id, alias_id)
    if not deleted:
        raise NotFoundError("lead_source_aliases", str(alias_id))
    return deleted_response("lead_source_alias", str(alias_id))


@router.patch("/{source_id}")
def update_source(
    source_id: UUID,
    body: LeadSourceUpdate,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    row = dimensions_service.update_source(client, org_id, source_id, **body.model_dump())
    if row is None:
        raise NotFoundError("lead_sources", str(source_id))
    return success_response(row)


@router.delete("/{source_id}")
def delete_source(
    source_id: UUID,
    reassign_to: Optional[UUID] = Query(default=None),
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    deleted = dimensions_service.delete_source(client, org_id, source_id, reassign_to=reassign_to)
    if not deleted:
        raise NotFoundError("lead_sources", str(source_id))
    return deleted_response("lead_source", str(source_id))


__all__ = ["router"]
