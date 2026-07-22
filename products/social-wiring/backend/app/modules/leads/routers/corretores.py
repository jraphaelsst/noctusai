"""Brokers CRUD + alias map — /api/leads/corretores/*. Mirrors
``routers/sources.py`` (same shape, no ``categoria``/``ordem``/``slug``
concepts — see the schema)."""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from noctusai_lib.primitives.exceptions import NotFoundError
from noctusai_lib.primitives.responses import deleted_response, success_response

from app.dependencies import coerce_org_uuid, get_current_user_org_unified
from app.modules.leads.deps import get_leads_client
from app.modules.leads.schemas import (
    LeadCorretorAliasCreate,
    LeadCorretorCreate,
    LeadCorretorUpdate,
)
from app.modules.leads.services import dimensions_service

router = APIRouter(prefix="/api/leads/corretores", tags=["leads-corretores"])


@router.get("")
def list_corretores(
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return success_response(dimensions_service.list_corretores_with_lead_count(client, org_id))


@router.post("", status_code=201)
def create_corretor(
    body: LeadCorretorCreate,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    row = dimensions_service.create_corretor(client, org_id, **body.model_dump())
    return success_response(row)


# NOTE: `/aliases*` registered before `/{corretor_id}` — same
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
        return success_response(dimensions_service.list_unmapped_corretores(client, org_id))
    return success_response(dimensions_service.list_corretor_aliases(client, org_id))


@router.post("/aliases", status_code=201)
def create_alias(
    body: LeadCorretorAliasCreate,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    row = dimensions_service.create_corretor_alias(
        client, org_id, alias=body.alias, corretor_id=body.corretor_id
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
    deleted = dimensions_service.delete_corretor_alias(client, org_id, alias_id)
    if not deleted:
        raise NotFoundError("lead_corretor_aliases", str(alias_id))
    return deleted_response("lead_corretor_alias", str(alias_id))


@router.patch("/{corretor_id}")
def update_corretor(
    corretor_id: UUID,
    body: LeadCorretorUpdate,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    # `exclude_unset=True` — see `routers/sources.py`'s update_source for
    # why (an explicit null now genuinely means "clear this field" where
    # the column allows it).
    row = dimensions_service.update_corretor(
        client, org_id, corretor_id, **body.model_dump(exclude_unset=True)
    )
    if row is None:
        raise NotFoundError("lead_corretores", str(corretor_id))
    return success_response(row)


@router.delete("/{corretor_id}")
def delete_corretor(
    corretor_id: UUID,
    reassign_to: Optional[UUID] = Query(default=None),
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    deleted = dimensions_service.delete_corretor(client, org_id, corretor_id, reassign_to=reassign_to)
    if not deleted:
        raise NotFoundError("lead_corretores", str(corretor_id))
    return deleted_response("lead_corretor", str(corretor_id))


__all__ = ["router"]
