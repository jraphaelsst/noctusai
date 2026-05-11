"""Admin list + detail on `media_scheduling.appointments`.

Frontend contract (Phase 5 hooks `useAppointments.ts`):
  - GET /api/appointments?start_date=&end_date=&status=&condominium_id=
  - GET /api/appointments/{id}

Wire-shape note: the frontend hook surfaces `starts_at` / `ends_at` while
the schema column names are `start_at` / `end_at`. We translate both
directions so the hook gets the fields it wires.

Ghost-field enrichment (Phase 1 — media-scheduling-wiring):
The frontend ``Appointment`` type declares ``property_label`` /
``condominium_label`` / ``service_type_id`` / ``service_type_label`` /
``crew_assignee_id`` / ``crew_assignee_label`` — none of which the bare
``appointments`` table holds. We populate them via two-step joins:

  - ``property_label``        ← ``properties.code`` via ``property_id``
  - ``condominium_label``     ← ``condominiums.name`` via ``condominium_id``
  - ``service_type_id``       ← first row in ``appointment_request_services``
                                for the linked ``appointment_request_id``
  - ``service_type_label``    ← ``service_types.name`` for that service_type_id
  - ``crew_assignee_id``      ← ``route_groups.media_crew_user_id`` via
                                ``route_group_id``
  - ``crew_assignee_label``   ← ``authorized_users.name`` for that user_id

Two-step (fetch + bulk-join in Python) rather than PostgREST nested
``select`` so the result shape stays predictable across the
``MockSupabaseClient`` test surface (which does not model nested
PostgREST resource embedding).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from app.database import get_supabase_client
from app.dependencies import get_current_user_org

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/appointments", tags=["Appointments"])


_VALID_STATUSES = {
    "scheduled",
    "pending",
    "confirmed",
    "in_progress",
    "completed",
    "cancelled",
    "canceled",
}


def _wire(row: dict[str, Any]) -> dict[str, Any]:
    """Map DB shape → frontend hook shape (start_at→starts_at, end_at→ends_at)."""
    out = dict(row)
    if "start_at" in out:
        out["starts_at"] = out.pop("start_at")
    if "end_at" in out:
        out["ends_at"] = out.pop("end_at")
    return out


def _enrich(rows: list[dict[str, Any]], db: Any) -> list[dict[str, Any]]:
    """Populate ghost fields on `appointments` rows via batch joins.

    Empty input → empty output. Each lookup is wrapped in its own
    try/except + ``logger.warning`` so a join failure degrades that
    single label rather than failing the whole response — matching the
    rest of the router's "log + 400 on hard exec failure / silent-empty
    on missing data" idiom.
    """
    if not rows:
        return rows

    # Collect the FK ids we need to resolve.
    property_ids = {r.get("property_id") for r in rows if r.get("property_id")}
    condominium_ids = {r.get("condominium_id") for r in rows if r.get("condominium_id")}
    request_ids = {
        r.get("appointment_request_id")
        for r in rows
        if r.get("appointment_request_id")
    }
    route_group_ids = {
        r.get("route_group_id") for r in rows if r.get("route_group_id")
    }

    # property_id → properties.code
    property_label_by_id: dict[Any, str] = {}
    if property_ids:
        try:
            res = (
                db.table("properties")
                .select("id, code")
                .in_("id", list(property_ids))
                .execute()
            )
            for row in res.data or []:
                property_label_by_id[row["id"]] = row.get("code")
        except Exception as exc:
            logger.warning("appointments enrich: properties lookup failed: %s", exc)

    # condominium_id → condominiums.name
    condominium_label_by_id: dict[Any, str] = {}
    if condominium_ids:
        try:
            res = (
                db.table("condominiums")
                .select("id, name")
                .in_("id", list(condominium_ids))
                .execute()
            )
            for row in res.data or []:
                condominium_label_by_id[row["id"]] = row.get("name")
        except Exception as exc:
            logger.warning("appointments enrich: condominiums lookup failed: %s", exc)

    # appointment_request_id → first appointment_request_services.service_type_id
    service_type_id_by_request: dict[Any, Any] = {}
    if request_ids:
        try:
            res = (
                db.table("appointment_request_services")
                .select("appointment_request_id, service_type_id")
                .in_("appointment_request_id", list(request_ids))
                .execute()
            )
            for row in res.data or []:
                # First-wins per (appointment_request_id) — multiple
                # services on one request collapse to the primary one.
                req_id = row.get("appointment_request_id")
                if req_id is not None and req_id not in service_type_id_by_request:
                    service_type_id_by_request[req_id] = row.get("service_type_id")
        except Exception as exc:
            logger.warning(
                "appointments enrich: appointment_request_services lookup failed: %s",
                exc,
            )

    # service_type_id → service_types.name
    service_type_label_by_id: dict[Any, str] = {}
    service_type_ids = {v for v in service_type_id_by_request.values() if v}
    if service_type_ids:
        try:
            res = (
                db.table("service_types")
                .select("id, name")
                .in_("id", list(service_type_ids))
                .execute()
            )
            for row in res.data or []:
                service_type_label_by_id[row["id"]] = row.get("name")
        except Exception as exc:
            logger.warning("appointments enrich: service_types lookup failed: %s", exc)

    # route_group_id → route_groups.media_crew_user_id (the crew assignee)
    crew_assignee_id_by_route: dict[Any, Any] = {}
    if route_group_ids:
        try:
            res = (
                db.table("route_groups")
                .select("id, media_crew_user_id")
                .in_("id", list(route_group_ids))
                .execute()
            )
            for row in res.data or []:
                crew_assignee_id_by_route[row["id"]] = row.get("media_crew_user_id")
        except Exception as exc:
            logger.warning("appointments enrich: route_groups lookup failed: %s", exc)

    # crew_assignee_id → authorized_users.name
    crew_assignee_label_by_id: dict[Any, str] = {}
    crew_user_ids = {v for v in crew_assignee_id_by_route.values() if v}
    if crew_user_ids:
        try:
            res = (
                db.table("authorized_users")
                .select("id, name")
                .in_("id", list(crew_user_ids))
                .execute()
            )
            for row in res.data or []:
                crew_assignee_label_by_id[row["id"]] = row.get("name")
        except Exception as exc:
            logger.warning(
                "appointments enrich: authorized_users lookup failed: %s", exc
            )

    # Materialize the labels onto each row. We always set the field
    # (even when None) so the frontend type's optional-but-present
    # contract holds — no `undefined` surprises in TypeScript.
    enriched: list[dict[str, Any]] = []
    for row in rows:
        out = dict(row)
        out["property_label"] = property_label_by_id.get(out.get("property_id"))
        out["condominium_label"] = condominium_label_by_id.get(
            out.get("condominium_id")
        )
        service_type_id = service_type_id_by_request.get(
            out.get("appointment_request_id")
        )
        out["service_type_id"] = service_type_id
        out["service_type_label"] = (
            service_type_label_by_id.get(service_type_id) if service_type_id else None
        )
        crew_assignee_id = crew_assignee_id_by_route.get(out.get("route_group_id"))
        out["crew_assignee_id"] = crew_assignee_id
        out["crew_assignee_label"] = (
            crew_assignee_label_by_id.get(crew_assignee_id)
            if crew_assignee_id
            else None
        )
        enriched.append(out)
    return enriched


@router.get("")
async def list_appointments(
    start_date: Optional[str] = Query(None, description="ISO date YYYY-MM-DD inclusive"),
    end_date: Optional[str] = Query(None, description="ISO date YYYY-MM-DD inclusive"),
    status: Optional[str] = Query(None),
    condominium_id: Optional[str] = Query(None),
    auth=Depends(get_current_user_org),
) -> dict[str, Any]:
    if status and status not in _VALID_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed: {sorted(_VALID_STATUSES)}",
        )

    db = get_supabase_client()
    q = db.table("appointments").select("*")

    if start_date:
        # `start_at >= start_date 00:00 UTC`. Caller responsible for tz semantics.
        q = q.gte("start_at", f"{start_date}T00:00:00+00:00")
    if end_date:
        q = q.lte("start_at", f"{end_date}T23:59:59+00:00")
    if status:
        q = q.eq("status", status)
    if condominium_id:
        q = q.eq("condominium_id", condominium_id)

    q = q.order("start_at", desc=True).limit(500)
    try:
        result = q.execute()
    except Exception as exc:
        logger.warning("appointments list failed: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rows = [_wire(r) for r in (result.data or [])]
    enriched = _enrich(rows, db)
    return {"data": enriched, "total": len(enriched)}


@router.get("/{appointment_id}")
async def get_appointment(
    appointment_id: str,
    auth=Depends(get_current_user_org),
) -> dict[str, Any]:
    db = get_supabase_client()
    result = (
        db.table("appointments")
        .select("*")
        .eq("id", appointment_id)
        .limit(1)
        .execute()
    )
    rows = result.data or []
    if not rows:
        raise HTTPException(status_code=404, detail="Appointment not found")
    wired = _wire(rows[0])
    enriched = _enrich([wired], db)
    return enriched[0]
