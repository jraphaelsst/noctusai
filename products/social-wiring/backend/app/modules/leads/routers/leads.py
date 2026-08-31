"""Leads CRUD + facets — /api/leads/*, /api/leads/facets.

Auth: ``Depends(get_current_user_org_unified)`` throughout (admin/service-role
client for all reads/writes, RLS is defense-in-depth, same shape as
``marcas_router``). Errors: ``AppException`` subclasses only.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, Query

from noctusai_lib.primitives.exceptions import NotFoundError
from noctusai_lib.primitives.responses import (
    deleted_response,
    paginated_response,
    success_response,
)

from app.dependencies import coerce_org_uuid, get_current_user_org_unified
from app.modules.leads.deps import get_leads_client
from app.modules.leads.routers.params import get_lead_filters
from app.modules.leads.schemas import LeadCreate, LeadOut, LeadUpdate
from app.modules.leads.services import leads_service
from app.modules.leads.services.query import LeadFilters
from app.services import clientes_backfill_job

router = APIRouter(prefix="/api/leads", tags=["leads"])


def get_person_layer_sweep():
    """DI seam: the person-layer sweep `create_lead` schedules.

    Tests override via `app.dependency_overrides[get_person_layer_sweep]` so
    the scheduling itself is asserted without running a real org-wide pass.
    → KB § PATTERNS/backend/di-test-seam.md.
    """
    return clientes_backfill_job.run_now


def _out(row: dict, refs: dict) -> dict:
    return LeadOut.model_validate(leads_service.resolve_lead_out(row, refs)).model_dump(mode="json")


@router.get("")
def list_leads(
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
    filters: LeadFilters = Depends(get_lead_filters),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    sort: str = Query(default="data_entrada"),
    order: str = Query(default="desc"),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    refs = leads_service.build_refs(client, org_id)
    rows, total = leads_service.list_leads(
        client, org_id, filters, page=page, page_size=page_size, sort=sort, order=order, refs=refs
    )
    data = [_out(r, refs) for r in rows]
    return paginated_response(data, total, page, page_size)


@router.post("", status_code=201)
def create_lead(
    body: LeadCreate,
    background: BackgroundTasks,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
    sweep=Depends(get_person_layer_sweep),
) -> dict:
    """Create a lead. Migration 034's trigger spawns its funil card.

    🔴 The card is spawned, but it is NOT yet WORKABLE, and that is why this
    route schedules a person-layer sweep (found in prod 2026-08-31).

    `atendimentos.cliente_id` is attached only by `clientes_backfill`, an
    interval job — no trigger does it. So a hand-created lead got a card that
    `stage_gate` then refused to move, for up to
    `clientes_backfill_interval_hours`, while the operator looked at a name and
    a phone they had just typed in. Scheduling the sweep here closes that
    window to the couple of seconds the sweep takes.

    Scheduled as a BackgroundTask, so it runs AFTER the 201 is returned and
    never delays lead creation. It is lease-guarded (`run_now`), so repeated
    creates coalesce into one pass instead of piling up sweeps — which is what
    makes it safe to hang off a per-row write at all. The BULK paths (the
    workbook importer, the Meta Lead-Ads sync) deliberately do NOT do this:
    one sweep per imported row would be quadratic, and they are already
    covered by the scheduled pass plus the startup catch-up.
    """
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    row = leads_service.create_lead(client, org_id, body.model_dump(exclude_unset=True))
    refs = leads_service.build_refs(client, org_id)
    background.add_task(sweep)
    return success_response(_out(row, refs))


@router.get("/facets")
def get_facets(
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
    filters: LeadFilters = Depends(get_lead_filters),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    return success_response(leads_service.facets(client, org_id, filters))


# NOTE: `/facets` MUST be registered before `/{lead_id}` — otherwise
# Starlette tries `/{lead_id}` first and 422s attempting to parse
# "facets" as a UUID. Route-registration-order matters whenever a
# static path segment shares a prefix with a param path.
@router.get("/{lead_id}")
def get_lead(
    lead_id: UUID,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    row = leads_service.get_lead(client, org_id, lead_id)
    if row is None:
        raise NotFoundError("lead", str(lead_id))
    refs = leads_service.build_refs(client, org_id)
    return success_response(_out(row, refs))


@router.patch("/{lead_id}")
def update_lead(
    lead_id: UUID,
    body: LeadUpdate,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    row = leads_service.update_lead(client, org_id, lead_id, body.model_dump(exclude_unset=True))
    if row is None:
        raise NotFoundError("lead", str(lead_id))
    refs = leads_service.build_refs(client, org_id)
    return success_response(_out(row, refs))


@router.delete("/{lead_id}")
def delete_lead(
    lead_id: UUID,
    auth: tuple = Depends(get_current_user_org_unified),
    client: Any = Depends(get_leads_client),
) -> dict:
    _, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    deleted = leads_service.delete_lead(client, org_id, lead_id)
    if not deleted:
        raise NotFoundError("lead", str(lead_id))
    return deleted_response("lead", str(lead_id))


__all__ = ["router"]
