"""Clients HTTP surface -- `create_clients_router(...)` at `/api/clients`.

    GET    /config                         -> {data: config}
    GET    ""  ?q=&status=&tag=&lead_id=&cursor=&limit=   -> {data: [client], next_cursor}   (name asc)
    GET    /tags                           -> {data: [tag]}
    POST   ""                              -> 201 {data: client}
    GET    /sessions ?from=&to=            -> {data: [session]}   (every client, starts_at asc, <= 62 days)
    PATCH  /sessions/{id} · DELETE /sessions/{id} (204; 409 SESSAO_COM_PAGAMENTO)
    PATCH  /schedules/{id} · DELETE /schedules/{id} (204)
    GET    /{id} · PATCH /{id} · DELETE /{id} [admin] (204; 409 CLIENTE_COM_FINANCEIRO)
    GET    /{id}/sessions ?from=&to=&status=   -> {data: [session]}  (starts_at desc)
    POST   /{id}/sessions                  -> 201 {data: session}
    GET    /{id}/schedules · POST /{id}/schedules (201)
    GET    /{id}/finance                   -> {data: finance}
    POST   /{id}/payments [admin]          -> {data: {settlement_ids, finance}}

`get_current_user_org` is the product's license-gated auth dependency yielding `(user, token, org_id)` (an
`OrganAuth` carries `.is_admin`; absent => not admin, documents masked). Unauthenticated is a strict 401 (it lives in
that dependency). `admin_dependency` guards the [admin] routes (the finance-touching deletes/payments). Handlers are
plain `def` (the store does blocking IO), so FastAPI runs them in its threadpool. The fixed paths (`/config`, `/tags`,
`/sessions`, `/schedules/...`) are declared before `/{client_id}` so they are never read as an id.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from noctusai_lib.domain.finance.booking import FinanceBooking
from noctusai_lib.primitives.responses import success_response

from .config import ClientsConfig
from .errors import FILTRO_INVALIDO, invalid
from .schemas import ClientBody, ClientPatch, PaymentBody, ScheduleBody, SchedulePatch, SessionBody, SessionPatch
from .service import ClientsService
from .store import ClientFilters, ClientsStore

MAX_PAGE = 200


def create_clients_router(
    *,
    store_factory: Callable[[], ClientsStore],
    get_current_user_org: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    config: ClientsConfig,
    booking_factory: Optional[Callable[[], FinanceBooking]] = None,
    prefix: str = "/api/clients",
    tags: Optional[list[str]] = None,
    resolve_org_id: Callable[[Any], str] = str,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags or ["clients"])

    def _ctx(auth: Any) -> tuple:
        user, _token, raw_org = auth
        service = ClientsService(store_factory(), config, booking_factory() if booking_factory else None)
        uid = str(getattr(user, "id", None) or "") or None
        return service, resolve_org_id(raw_org), uid, bool(getattr(auth, "is_admin", False))

    def svc(auth: Any = Depends(get_current_user_org)) -> tuple:
        return _ctx(auth)

    def admin_svc(auth: Any = Depends(admin_dependency)) -> tuple:
        return _ctx(auth)

    # -- fixed paths first ----------------------------------------------------------------------

    @router.get("/config", name="clients_config")
    def config_route(_auth: Any = Depends(get_current_user_org)) -> dict:
        return success_response(config.as_dict())

    @router.get("", name="clients_list")
    def list_route(
        q: Optional[str] = Query(None, max_length=100),
        status: Optional[str] = Query(None, max_length=60),
        tag: Optional[str] = Query(None, max_length=100),
        lead_id: Optional[UUID] = Query(None),
        limit: int = Query(50, ge=1, le=MAX_PAGE),
        cursor: Optional[str] = Query(None, max_length=20),
        ctx=Depends(svc),
    ) -> dict:
        service, org_id, _uid, is_admin = ctx
        try:
            offset = int(cursor) if cursor else 0
            if offset < 0:
                raise ValueError
        except ValueError:
            raise invalid("cursor", "Cursor inválido.", FILTRO_INVALIDO) from None
        f = ClientFilters(q=q, status=status, tag=tag, lead_id=str(lead_id) if lead_id else None)
        rows, nxt = service.list_clients(org_id, f, limit=limit, offset=offset, is_admin=is_admin)
        return {"data": rows, "next_cursor": str(nxt) if nxt is not None else None}

    @router.get("/tags", name="clients_tags")
    def tags_route(ctx=Depends(svc)) -> dict:
        service, org_id, _uid, _admin = ctx
        return success_response(service.tags(org_id))

    @router.post("", status_code=201, name="clients_create")
    def create_route(body: ClientBody, ctx=Depends(svc)) -> dict:
        service, org_id, uid, is_admin = ctx
        return success_response(service.create(org_id, body.model_dump(exclude_none=True), user_id=uid, is_admin=is_admin))

    @router.get("/sessions", name="clients_agenda")
    def agenda_route(
        frm: date = Query(..., alias="from"),
        to: date = Query(...),
        ctx=Depends(svc),
    ) -> dict:
        service, org_id, _uid, _admin = ctx
        return success_response(service.agenda(org_id, frm, to))

    @router.patch("/sessions/{session_id}", name="clients_session_update")
    def session_update_route(session_id: UUID, body: SessionPatch, ctx=Depends(svc)) -> dict:
        service, org_id, _uid, _admin = ctx
        return success_response(service.update_session(org_id, str(session_id), body.model_dump(exclude_unset=True)))

    @router.delete("/sessions/{session_id}", status_code=204, name="clients_session_delete")
    def session_delete_route(session_id: UUID, ctx=Depends(svc)) -> Response:
        service, org_id, _uid, _admin = ctx
        service.delete_session(org_id, str(session_id))
        return Response(status_code=204)

    @router.patch("/schedules/{schedule_id}", name="clients_schedule_update")
    def schedule_update_route(schedule_id: UUID, body: SchedulePatch, ctx=Depends(svc)) -> dict:
        service, org_id, _uid, _admin = ctx
        return success_response(service.update_schedule(org_id, str(schedule_id), body.model_dump(exclude_unset=True)))

    @router.delete("/schedules/{schedule_id}", status_code=204, name="clients_schedule_delete")
    def schedule_delete_route(schedule_id: UUID, ctx=Depends(svc)) -> Response:
        service, org_id, _uid, _admin = ctx
        service.delete_schedule(org_id, str(schedule_id))
        return Response(status_code=204)

    # -- one client -------------------------------------------------------------------------------

    @router.get("/{client_id}", name="clients_get")
    def get_route(client_id: UUID, ctx=Depends(svc)) -> dict:
        service, org_id, _uid, is_admin = ctx
        return success_response(service.get(org_id, str(client_id), is_admin=is_admin))

    @router.patch("/{client_id}", name="clients_update")
    def update_route(client_id: UUID, body: ClientPatch, ctx=Depends(svc)) -> dict:
        service, org_id, _uid, is_admin = ctx
        return success_response(service.update(org_id, str(client_id), body.model_dump(exclude_unset=True), is_admin=is_admin))

    @router.delete("/{client_id}", status_code=204, name="clients_delete")
    def delete_route(client_id: UUID, ctx=Depends(admin_svc)) -> Response:
        service, org_id, _uid, _admin = ctx
        service.delete(org_id, str(client_id))
        return Response(status_code=204)

    @router.get("/{client_id}/sessions", name="clients_sessions")
    def sessions_route(
        client_id: UUID,
        frm: Optional[date] = Query(None, alias="from"),
        to: Optional[date] = Query(None),
        status: Optional[str] = Query(None, max_length=60),
        ctx=Depends(svc),
    ) -> dict:
        service, org_id, _uid, _admin = ctx
        return success_response(service.client_sessions(org_id, str(client_id), start=frm, end=to, status=status))

    @router.post("/{client_id}/sessions", status_code=201, name="clients_session_create")
    def session_create_route(client_id: UUID, body: SessionBody, ctx=Depends(svc)) -> dict:
        service, org_id, _uid, _admin = ctx
        return success_response(service.create_session(org_id, str(client_id), body.model_dump(exclude_none=True)))

    @router.get("/{client_id}/schedules", name="clients_schedules")
    def schedules_route(client_id: UUID, ctx=Depends(svc)) -> dict:
        service, org_id, _uid, _admin = ctx
        return success_response(service.list_schedules(org_id, str(client_id)))

    @router.post("/{client_id}/schedules", status_code=201, name="clients_schedule_create")
    def schedule_create_route(client_id: UUID, body: ScheduleBody, ctx=Depends(svc)) -> dict:
        service, org_id, _uid, _admin = ctx
        return success_response(service.create_schedule(org_id, str(client_id), body.model_dump(exclude_none=True)))

    @router.get("/{client_id}/finance", name="clients_finance")
    def finance_route(client_id: UUID, ctx=Depends(svc)) -> dict:
        service, org_id, _uid, _admin = ctx
        return success_response(service.client_finance(org_id, str(client_id)))

    @router.post("/{client_id}/payments", name="clients_payment")
    def payment_route(client_id: UUID, body: PaymentBody, ctx=Depends(admin_svc)) -> dict:
        service, org_id, uid, _admin = ctx
        return success_response(service.record_payment(org_id, str(client_id), body.model_dump(exclude_none=True), user_id=uid))

    return router


__all__ = ["MAX_PAGE", "create_clients_router"]
