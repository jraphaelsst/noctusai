"""Finance HTTP surface -- `make_finance_router(cfg, auth_dependency, admin_dependency, ...)` at `/api/finance`.

Authorization (contract §0): org STAFF may read (`auth_dependency`); every write
(entries, settlements, reversals, transfers, recurrences, accounts, categories, cost
centers, attachments) additionally requires `admin_dependency` -- the host's org-admin
dep (`require_org_admin(...)`). RLS is the floor, never the only check: every service
call is scoped by the caller's org and every referenced id is verified to belong to it.

Factory (commerce / card_hub precedent): the seed cannot know the product's auth, its
schema-scoped database accessor or its storage, so they arrive as FastAPI DEPENDENCIES
and a product keeps its own DI seams and its tests keep using `app.dependency_overrides`.

Envelopes: `success_response` -> `{"data": ...}`; paged lists `paginated_response` ->
`{"data": [...], "pagination": {...}}`; errors go through the seed's `AppException`
handlers -> `{"error": {"code", "message", "details"}}` (pt-BR codes in `errors.py`).
`POST /entries` ALWAYS answers a LIST (one element, or the whole installment group).

Slice D adds (new files, wave 2): statement import / reconciliation, gateway sync and
exports. They are NOT here on purpose.

🔴 NEVER `get_admin_client().schema(...)` in here: `get_db` already returns the
product's schema-scoped client (re-deriving poisons the shared admin client).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile

from noctusai_lib.integrations.storage.protocol import StorageBackend
from noctusai_lib.primitives.responses import paginated_response, success_response

from . import accounts as accounts_svc
from . import attachments as attachments_svc
from . import categories as categories_svc
from . import entries as entries_svc
from . import recurrences as recurrences_svc
from . import reports as reports_svc
from . import settlements as settlements_svc
from ._common import Scope, add_months, today
from .config import FinanceConfig, FinanceContext
from .entries import API_SOURCES
from .errors import invalid
from .schemas import (
    AccountBody,
    AccountPatch,
    CategoryBody,
    CategoryPatch,
    CostCenterBody,
    CostCenterPatch,
    EntryBody,
    EntryPatch,
    RecurrenceBody,
    RecurrencePatch,
    ReverseBody,
    SettleBody,
    TransferBody,
)


def _dump(model: Any, **kw: Any) -> dict:
    return model.model_dump(mode="python", **kw)


def make_finance_router(
    cfg: FinanceConfig,
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    *,
    resolve_context: Callable[[Any, Any], FinanceContext],
    get_db: Callable[..., Any],
    get_storage: Callable[..., StorageBackend],
    prefix: str = "/api/finance",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    """Build the finance router.

    Args:
        auth_dependency: the product's license-gated `get_current_user_org` (401 / 403 live there).
        admin_dependency: the org-admin gate (`require_org_admin(...)`); raises 403 for staff.
        resolve_context: `(auth_value, db) -> FinanceContext(db, org_id, user_id, is_admin)`;
            `is_admin` is decided SERVER-SIDE and only drives LGPD masking of reads.
        get_db / get_storage: FastAPI dependencies (schema-scoped client / `StorageBackend`).
    """
    router = APIRouter(prefix=prefix, tags=tags or ["finance"])

    def ctx_dep(auth=Depends(auth_dependency), db=Depends(get_db)) -> FinanceContext:
        return resolve_context(auth, db)

    def scope(ctx: FinanceContext) -> Scope:
        return Scope(ctx.db, cfg, str(ctx.org_id))

    admin = Depends(admin_dependency)

    # ── accounts ──
    @router.get("/accounts", name="finance_list_accounts")
    async def list_accounts_route(active: Optional[bool] = Query(None), ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(accounts_svc.list_accounts(scope(ctx), active=active))

    @router.post("/accounts", status_code=201, name="finance_create_account")
    async def create_account_route(body: AccountBody, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(accounts_svc.create_account(scope(ctx), _dump(body)))

    @router.patch("/accounts/{account_id}", name="finance_update_account")
    async def update_account_route(
        account_id: UUID, body: AccountPatch, _a=admin, ctx: FinanceContext = Depends(ctx_dep)
    ) -> dict:
        return success_response(accounts_svc.update_account(scope(ctx), account_id, _dump(body, exclude_unset=True)))

    @router.get("/accounts/{account_id}/balance", name="finance_account_balance")
    async def account_balance_route(
        account_id: UUID, on: Optional[date] = Query(None), ctx: FinanceContext = Depends(ctx_dep)
    ) -> dict:
        return success_response(accounts_svc.account_balance(scope(ctx), account_id, on))

    # ── categories ──
    @router.get("/categories", name="finance_list_categories")
    async def list_categories_route(ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(categories_svc.list_categories(scope(ctx)))

    @router.post("/categories", status_code=201, name="finance_create_category")
    async def create_category_route(body: CategoryBody, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(categories_svc.create_category(scope(ctx), _dump(body)))

    @router.patch("/categories/{category_id}", name="finance_update_category")
    async def update_category_route(
        category_id: UUID, body: CategoryPatch, _a=admin, ctx: FinanceContext = Depends(ctx_dep)
    ) -> dict:
        return success_response(categories_svc.update_category(scope(ctx), category_id, _dump(body, exclude_unset=True)))

    @router.delete("/categories/{category_id}", status_code=204, name="finance_delete_category")
    async def delete_category_route(category_id: UUID, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> Response:
        categories_svc.delete_category(scope(ctx), category_id)
        return Response(status_code=204)

    # ── cost centers ──
    @router.get("/cost-centers", name="finance_list_cost_centers")
    async def list_cost_centers_route(ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(categories_svc.list_cost_centers(scope(ctx)))

    @router.post("/cost-centers", status_code=201, name="finance_create_cost_center")
    async def create_cost_center_route(body: CostCenterBody, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(categories_svc.create_cost_center(scope(ctx), _dump(body)))

    @router.patch("/cost-centers/{cost_center_id}", name="finance_update_cost_center")
    async def update_cost_center_route(
        cost_center_id: UUID, body: CostCenterPatch, _a=admin, ctx: FinanceContext = Depends(ctx_dep)
    ) -> dict:
        return success_response(
            categories_svc.update_cost_center(scope(ctx), cost_center_id, _dump(body, exclude_unset=True))
        )

    # ── entries ──
    @router.get("/entries", name="finance_list_entries")
    async def list_entries_route(
        direction: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        overdue: Optional[bool] = Query(None),
        date_from: Optional[date] = Query(None, alias="from"),
        date_to: Optional[date] = Query(None, alias="to"),
        category_id: Optional[UUID] = Query(None),
        cost_center_id: Optional[UUID] = Query(None),
        q: Optional[str] = Query(None, max_length=100),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        ctx: FinanceContext = Depends(ctx_dep),
    ) -> dict:
        rows, total, page, size = entries_svc.list_entries(
            scope(ctx), direction=direction, status=status, overdue=overdue, date_from=date_from, date_to=date_to,
            category_id=category_id, cost_center_id=cost_center_id, q=q, page=page, page_size=page_size,
        )
        on = today()
        return paginated_response(
            [entries_svc.present_entry(r, is_admin=ctx.is_admin, on=on) for r in rows], total, page, size
        )

    @router.post("/entries", status_code=201, name="finance_create_entry")
    async def create_entry_route(body: EntryBody, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        data = _dump(body)
        if data["source"] not in API_SOURCES:  # pragma: no cover - the Literal already forbids it
            raise invalid("source", "Origem reservada.", code="origem_reservada")
        rows = entries_svc.create_entry(scope(ctx), data)
        return success_response([entries_svc.present_entry(r, is_admin=ctx.is_admin) for r in rows])

    @router.get("/entries/{entry_id}", name="finance_get_entry")
    async def get_entry_route(entry_id: UUID, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(entries_svc.present_entry(entries_svc.get_entry_detail(scope(ctx), entry_id), is_admin=ctx.is_admin))

    @router.patch("/entries/{entry_id}", name="finance_update_entry")
    async def update_entry_route(
        entry_id: UUID, body: EntryPatch, _a=admin, ctx: FinanceContext = Depends(ctx_dep)
    ) -> dict:
        row = entries_svc.update_entry(scope(ctx), entry_id, _dump(body, exclude_unset=True))
        return success_response(entries_svc.present_entry(row, is_admin=ctx.is_admin))

    @router.post("/entries/{entry_id}/cancel", name="finance_cancel_entry")
    async def cancel_entry_route(entry_id: UUID, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(entries_svc.present_entry(entries_svc.cancel_entry(scope(ctx), entry_id), is_admin=ctx.is_admin))

    # ── settlements ──
    @router.post("/entries/{entry_id}/settlements", status_code=201, name="finance_settle_entry")
    async def settle_entry_route(
        entry_id: UUID, body: SettleBody, response: Response, _a=admin, ctx: FinanceContext = Depends(ctx_dep)
    ) -> dict:
        result = settlements_svc.settle_entry(scope(ctx), entry_id, _dump(body), user_id=ctx.user_id)
        if result["replayed"]:
            response.status_code = 200
        result["entry"] = entries_svc.present_entry(result["entry"], is_admin=ctx.is_admin)
        return success_response(result)

    @router.post("/settlements/{settlement_id}/reverse", name="finance_reverse_settlement")
    async def reverse_settlement_route(
        settlement_id: UUID, body: ReverseBody, _a=admin, ctx: FinanceContext = Depends(ctx_dep)
    ) -> dict:
        result = settlements_svc.reverse_settlement(scope(ctx), settlement_id, body.reason, user_id=ctx.user_id)
        result["entry"] = entries_svc.present_entry(result["entry"], is_admin=ctx.is_admin)
        return success_response(result)

    # ── recurrences ──
    @router.get("/recurrences", name="finance_list_recurrences")
    async def list_recurrences_route(ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(recurrences_svc.list_recurrences(scope(ctx)))

    @router.post("/recurrences", status_code=201, name="finance_create_recurrence")
    async def create_recurrence_route(body: RecurrenceBody, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(recurrences_svc.create_recurrence(scope(ctx), _dump(body)))

    @router.patch("/recurrences/{recurrence_id}", name="finance_update_recurrence")
    async def update_recurrence_route(
        recurrence_id: UUID, body: RecurrencePatch, _a=admin, ctx: FinanceContext = Depends(ctx_dep)
    ) -> dict:
        return success_response(
            recurrences_svc.update_recurrence(scope(ctx), recurrence_id, _dump(body, exclude_unset=True))
        )

    # ── transfers ──
    @router.post("/transfers", status_code=201, name="finance_create_transfer")
    async def create_transfer_route(body: TransferBody, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(settlements_svc.create_transfer(scope(ctx), _dump(body)))

    # ── reports ──
    @router.get("/reports/cashflow", name="finance_report_cashflow")
    async def cashflow_route(
        date_from: Optional[date] = Query(None, alias="from"),
        date_to: Optional[date] = Query(None, alias="to"),
        account_id: Optional[UUID] = Query(None),
        ctx: FinanceContext = Depends(ctx_dep),
    ) -> dict:
        start = date_from or today().replace(day=1)
        end = date_to or add_months(start, 6)
        return success_response(reports_svc.cashflow(scope(ctx), start, end, account_id=account_id))

    @router.get("/reports/dre", name="finance_report_dre")
    async def dre_route(
        date_from: Optional[date] = Query(None, alias="from"),
        date_to: Optional[date] = Query(None, alias="to"),
        ctx: FinanceContext = Depends(ctx_dep),
    ) -> dict:
        end = date_to or today()
        start = date_from or end.replace(month=1, day=1)
        return success_response(reports_svc.dre(scope(ctx), start, end))

    @router.get("/reports/aging", name="finance_report_aging")
    async def aging_route(as_of: Optional[date] = Query(None), ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(reports_svc.aging(scope(ctx), as_of=as_of, is_admin=ctx.is_admin))

    # ── attachments ──
    @router.get("/entries/{entry_id}/attachments", name="finance_list_attachments")
    async def list_attachments_route(
        entry_id: UUID, ctx: FinanceContext = Depends(ctx_dep), storage=Depends(get_storage)
    ) -> dict:
        return success_response(await attachments_svc.list_attachments(scope(ctx), storage, entry_id))

    @router.post("/entries/{entry_id}/attachments", status_code=201, name="finance_add_attachment")
    async def add_attachment_route(
        entry_id: UUID,
        file: UploadFile = File(...),
        _a=admin,
        ctx: FinanceContext = Depends(ctx_dep),
        storage=Depends(get_storage),
    ) -> dict:
        data = await file.read(attachments_svc.MAX_ATTACHMENT_BYTES + 1)  # bounded: never buffer an unbounded upload
        return success_response(
            await attachments_svc.add_attachment(
                scope(ctx), storage, entry_id,
                filename=file.filename, content_type=file.content_type or "", data=data, user_id=ctx.user_id,
            )
        )

    @router.delete("/attachments/{attachment_id}", status_code=204, name="finance_delete_attachment")
    async def delete_attachment_route(
        attachment_id: UUID, _a=admin, ctx: FinanceContext = Depends(ctx_dep), storage=Depends(get_storage)
    ) -> Response:
        await attachments_svc.delete_attachment(scope(ctx), storage, attachment_id)
        return Response(status_code=204)

    return router


__all__ = ["make_finance_router"]
