"""Leads HTTP surface -- `create_leads_router(store_factory=..., get_current_user_org=..., config=...)` at `/api/leads`.

    GET    /api/leads?stage=&origin=&from=&to=&q=&limit=&cursor=   -> {data: [lead], next_cursor}
    POST   /api/leads                                              -> {data: lead}            (201)
    GET    /api/leads/board?origin=&from=&to=&q=                   -> {data: [column]}
    GET    /api/leads/config                                       -> {data: {stages, origins, ...}}
    GET    /api/leads/{id}  ·  PATCH /api/leads/{id}  ·  DELETE /api/leads/{id} (204)
    POST   /api/leads/{id}/move   {stage, position}                -> {data: lead}   (`position` = destination index)

Every route is org-scoped: `get_current_user_org` is the product's license-gated auth dependency yielding
`(user, token, org_id)`; unauthenticated is a strict 401 (it lives in that dependency). Any member of the org
may use every route -- a lead is fully CRUD-able. Handlers are plain `def` (the store does blocking IO), so
FastAPI runs them in its threadpool.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from noctusai_lib.primitives.responses import success_response

from .config import LeadsConfig
from .errors import FILTRO_INVALIDO, invalid
from .schemas import LeadBody, LeadMove, LeadPatch
from .service import LeadsService, present
from .store import LeadFilters, LeadsStore

MAX_PAGE = 200


def _day(value: Optional[date], *, end: bool = False) -> Optional[datetime]:
    """A calendar day as a UTC instant; `to` is inclusive of its whole day (=> exclusive next midnight)."""
    if value is None:
        return None
    d = value + timedelta(days=1) if end else value
    return datetime.combine(d, time.min, tzinfo=timezone.utc)


def create_leads_router(
    *,
    store_factory: Callable[[], LeadsStore],
    get_current_user_org: Callable[..., Any],
    config: LeadsConfig,
    prefix: str = "/api/leads",
    tags: Optional[list[str]] = None,
    resolve_org_id: Callable[[Any], str] = str,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags or ["leads"])

    def svc(auth: tuple = Depends(get_current_user_org)):
        user, _token, raw_org = auth
        return LeadsService(store_factory(), config), resolve_org_id(raw_org), str(getattr(user, "id", None) or "") or None

    def filters(q, origin, frm, to, stage=None) -> LeadFilters:
        first_from, first_to = _day(frm), _day(to, end=True)
        if first_from and first_to and first_from >= first_to:
            raise invalid("from", "A data inicial vem depois da final.", FILTRO_INVALIDO)
        return LeadFilters(stage=stage, origin=origin, first_from=first_from, first_to=first_to, q=q)

    @router.get("/config", name="leads_config")
    def config_route(_auth: tuple = Depends(get_current_user_org)) -> dict:
        return success_response(config.as_dict())

    @router.get("/board", name="leads_board")
    def board_route(
        q: Optional[str] = Query(None, max_length=100),
        origin: Optional[str] = Query(None),
        frm: Optional[date] = Query(None, alias="from"),
        to: Optional[date] = Query(None),
        ctx=Depends(svc),
    ) -> dict:
        service, org_id, _uid = ctx
        return success_response(service.board(org_id, filters(q, origin, frm, to)))

    @router.get("", name="leads_list")
    def list_route(
        stage: Optional[str] = Query(None),
        origin: Optional[str] = Query(None),
        frm: Optional[date] = Query(None, alias="from"),
        to: Optional[date] = Query(None),
        q: Optional[str] = Query(None, max_length=100),
        limit: int = Query(50, ge=1, le=MAX_PAGE),
        cursor: Optional[str] = Query(None, max_length=20),
        ctx=Depends(svc),
    ) -> dict:
        service, org_id, _uid = ctx
        try:
            offset = int(cursor) if cursor else 0
            if offset < 0:
                raise ValueError
        except ValueError:
            raise invalid("cursor", "Cursor inválido.", FILTRO_INVALIDO) from None
        rows, nxt = service.list_leads(org_id, filters(q, origin, frm, to, stage), limit=limit, offset=offset)
        return {"data": [present(r) for r in rows], "next_cursor": str(nxt) if nxt is not None else None}

    @router.post("", status_code=201, name="leads_create")
    def create_route(body: LeadBody, ctx=Depends(svc)) -> dict:
        service, org_id, uid = ctx
        return success_response(present(service.create(org_id, body.model_dump(exclude_none=True), user_id=uid)))

    @router.get("/{lead_id}", name="leads_get")
    def get_route(lead_id: UUID, ctx=Depends(svc)) -> dict:
        service, org_id, _uid = ctx
        return success_response(present(service.get(org_id, str(lead_id))))

    @router.patch("/{lead_id}", name="leads_update")
    def update_route(lead_id: UUID, body: LeadPatch, ctx=Depends(svc)) -> dict:
        service, org_id, _uid = ctx
        return success_response(present(service.update(org_id, str(lead_id), body.model_dump(exclude_unset=True))))

    @router.delete("/{lead_id}", status_code=204, name="leads_delete")
    def delete_route(lead_id: UUID, ctx=Depends(svc)) -> Response:
        service, org_id, _uid = ctx
        service.delete(org_id, str(lead_id))
        return Response(status_code=204)

    @router.post("/{lead_id}/move", name="leads_move")
    def move_route(lead_id: UUID, body: LeadMove, ctx=Depends(svc)) -> dict:
        service, org_id, _uid = ctx
        return success_response(present(service.move(org_id, str(lead_id), body.stage, body.position)))

    return router


__all__ = ["create_leads_router"]
