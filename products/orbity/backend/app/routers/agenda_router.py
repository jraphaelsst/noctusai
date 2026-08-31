"""
Agenda router — agenda_events CRUD + optional GCal sync.

Auth boundary:
  All /api/agenda/* → Depends(get_current_user_org) → strict 401.

Endpoints:
  GET    /api/agenda/events                       paginated event list (filter: from, to, type, client, assignee)
  POST   /api/agenda/events                       create event → 201
  GET    /api/agenda/events/{id}                  event detail
  PATCH  /api/agenda/events/{id}                  update event
  DELETE /api/agenda/events/{id}                  delete event
  POST   /api/agenda/events/{id}/sync-gcal        sync event to Google Calendar → 200

GCal sync:
  The sync endpoint wires through AgendaService.sync_to_gcal(), which
  uses the injected CalendarAdapter (FakeCalendarAdapter by default).
  When real GCal credentials are configured, the Real adapter fires.
  NOC-REMEDIATE[orbity-agenda-gcal]: see agenda_service.py for wiring notes. — 2026-06-03
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
from app.schemas.agenda import (
    AgendaEventCreate,
    AgendaEventOut,
    AgendaEventUpdate,
)
from app.services.agenda_service import AgendaService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agenda"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _svc(token: str, org_id: UUID) -> AgendaService:
    # Wires the FakeCalendarAdapter by default.
    # NOC-REMEDIATE[orbity-agenda-gcal]: pass calendar_adapter=get_calendar_adapter(resolver, ...) — 2026-06-03
    return AgendaService(get_user_client(token), org_id=org_id)


# ---------------------------------------------------------------------------
# Agenda events CRUD
# ---------------------------------------------------------------------------

@router.get("/api/agenda/events", status_code=status.HTTP_200_OK)
async def list_events(
    from_dt: str | None = Query(default=None, alias="from"),
    to_dt: str | None = Query(default=None, alias="to"),
    event_type: str | None = Query(default=None),
    client_id: str | None = Query(default=None),
    assignee_user_id: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        return _svc(token, org_id).list_events(
            from_dt=from_dt,
            to_dt=to_dt,
            event_type=event_type,
            client_id=client_id,
            assignee_user_id=assignee_user_id,
            page=page,
            page_size=page_size,
        )
    except Exception:
        logger.exception("agenda.list_events failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao listar eventos")


@router.post(
    "/api/agenda/events",
    response_model=AgendaEventOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_event(
    payload: AgendaEventCreate,
    auth: tuple = Depends(get_current_user_org),
) -> AgendaEventOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).create_event(payload.model_dump(exclude_none=True))
    except Exception:
        logger.exception("agenda.create_event failed org=%s", org_id)
        raise HTTPException(status_code=502, detail="Falha ao criar evento")
    return AgendaEventOut(**row)


@router.get(
    "/api/agenda/events/{event_id}",
    response_model=AgendaEventOut,
    status_code=status.HTTP_200_OK,
)
async def get_event(
    event_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> AgendaEventOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).get_event(event_id)
    except Exception:
        logger.exception("agenda.get_event failed org=%s id=%s", org_id, event_id)
        raise HTTPException(status_code=502, detail="Falha ao buscar evento")
    if not row:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return AgendaEventOut(**row)


@router.patch(
    "/api/agenda/events/{event_id}",
    response_model=AgendaEventOut,
    status_code=status.HTTP_200_OK,
)
async def update_event(
    event_id: str,
    payload: AgendaEventUpdate,
    auth: tuple = Depends(get_current_user_org),
) -> AgendaEventOut:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    data = payload.model_dump(exclude_none=True)
    if not data:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")
    try:
        row = _svc(token, org_id).update_event(event_id, data)
    except Exception:
        logger.exception("agenda.update_event failed org=%s id=%s", org_id, event_id)
        raise HTTPException(status_code=502, detail="Falha ao atualizar evento")
    if not row:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return AgendaEventOut(**row)


@router.delete("/api/agenda/events/{event_id}", status_code=status.HTTP_200_OK)
async def delete_event(
    event_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict:
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        ok = _svc(token, org_id).delete_event(event_id)
    except Exception:
        logger.exception("agenda.delete_event failed org=%s id=%s", org_id, event_id)
        raise HTTPException(status_code=502, detail="Falha ao deletar evento")
    if not ok:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return {"ok": True, "id": event_id}


# ---------------------------------------------------------------------------
# GCal sync seam
# ---------------------------------------------------------------------------

@router.post(
    "/api/agenda/events/{event_id}/sync-gcal",
    response_model=AgendaEventOut,
    status_code=status.HTTP_200_OK,
)
async def sync_gcal(
    event_id: str,
    auth: tuple = Depends(get_current_user_org),
) -> AgendaEventOut:
    """Sync event to Google Calendar via the injected CalendarAdapter.

    With the default FakeCalendarAdapter, assigns a deterministic fake
    gcal_event_id (no network call, safe in tests and dev). With a real
    adapter, creates the event in the org's Google Calendar and persists
    gcal_event_id.

    NOC-REMEDIATE[orbity-agenda-gcal]: real adapter requires credential
    wiring — see agenda_service.py for instructions. — 2026-06-03
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        row = _svc(token, org_id).sync_to_gcal(event_id)
    except Exception:
        logger.exception("agenda.sync_gcal failed org=%s id=%s", org_id, event_id)
        raise HTTPException(status_code=502, detail="Falha ao sincronizar com Google Calendar")
    if not row:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return AgendaEventOut(**row)
