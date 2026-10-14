"""Finance reconciliation HTTP surface -- the SECOND router a host mounts next to `make_finance_router`.

    app.include_router(make_finance_router(cfg, auth, admin, resolve_context=..., get_db=..., get_storage=...))
    app.include_router(make_finance_reconciliation_router(cfg, auth, admin, resolve_context=..., get_db=...,
                                                          get_storage=..., get_charge_operations=...))

Same dependency style and `/api/finance` prefix as the main router. Authorization (contract §0):
reads = org staff (`auth_dependency`); statement import, match / ignore and gateway sync = org admin
(`admin_dependency`); the two EXPORTS here (entries CSV, ledger OFX) = org admin OR the accountant read grant
(`accountant_dependency`, default = admin only). Each handler scopes by the caller's org and every referenced id is
checked against it.

HOST NOTES
* `POST /api/finance/statements` is an `UploadFile` route: list `STATEMENT_UPLOAD_PATH_PATTERN` in
  `max_body_path_overrides` (`{STATEMENT_UPLOAD_PATH_PATTERN: STATEMENT_UPLOAD_MAX_BYTES}`) -- the
  1 MB default would 413 a real statement silently (`create_product_app` refuses to boot otherwise).
* `get_charge_operations` is a dependency yielding the org's `ChargeOperations` -- or a callable
  `gateway_name -> ChargeOperations` when the host has several gateways.
* `get_storage` completes the signature symmetry with the main router; statements are deliberately NOT
  retained in storage (personal data: only the sha256 + the parsed lines are kept, contract §3.2).
* Register the 6-hourly job with `register_gateway_sync(...)` (`gateway_sync.py`).
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, ConfigDict

from noctusai_lib.integrations.storage.protocol import StorageBackend
from noctusai_lib.primitives.responses import paginated_response, success_response

from . import exports as exports_svc
from . import gateway_sync as sync_svc
from . import matching as matching_svc
from . import statements as statements_svc
from ._common import Scope
from .config import FinanceConfig, FinanceContext
from .entries import present_entry


class MatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entry_id: UUID


class GatewaySyncBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    #: restart the pull from this day (default: resume from the stored cursor)
    since: Optional[date] = None


def make_finance_reconciliation_router(
    cfg: FinanceConfig,
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    *,
    resolve_context: Callable[[Any, Any], FinanceContext],
    get_db: Callable[..., Any],
    get_storage: Callable[..., StorageBackend],
    get_charge_operations: Callable[..., Any],
    prefix: str = "/api/finance",
    tags: Optional[list[str]] = None,
    accountant_dependency: Optional[Callable[..., Any]] = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags or ["finance-reconciliation"])

    def ctx_dep(auth=Depends(auth_dependency), db=Depends(get_db)) -> FinanceContext:
        return resolve_context(auth, db)

    def scope(ctx: FinanceContext) -> Scope:
        return Scope(ctx.db, cfg, str(ctx.org_id))

    admin = Depends(admin_dependency)
    reader = Depends(accountant_dependency or admin_dependency)  # READ-only exports an external accountant may fetch

    # ── statements ──
    @router.post("/statements", status_code=201, name="finance_import_statement")
    async def import_statement_route(
        account_id: UUID = Form(...),
        file: UploadFile = File(...),
        column_map: Optional[str] = Form(None),
        format: Optional[str] = Form(None),
        _a=admin,
        ctx: FinanceContext = Depends(ctx_dep),
    ) -> dict:
        # bounded read: one byte past the cap is enough to refuse with 413 without buffering the rest
        data = await file.read(statements_svc.MAX_STATEMENT_BYTES + 1)
        result = statements_svc.import_statement(
            scope(ctx), account_id, filename=file.filename, data=data, fmt=format,
            column_map=statements_svc.parse_column_map(column_map), user_id=ctx.user_id,
        )
        return success_response(result)

    @router.get("/statements", name="finance_list_statements")
    async def list_statements_route(
        account_id: Optional[UUID] = Query(None),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        ctx: FinanceContext = Depends(ctx_dep),
    ) -> dict:
        rows, total, page, size = statements_svc.list_imports(scope(ctx), account_id=account_id, page=page, page_size=page_size)
        return paginated_response(rows, total, page, size)

    @router.get("/statements/{import_id}/lines", name="finance_list_statement_lines")
    async def list_lines_route(
        import_id: UUID,
        match_status: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        ctx: FinanceContext = Depends(ctx_dep),
    ) -> dict:
        rows, total, page, size = statements_svc.list_lines(
            scope(ctx), import_id, match_status=match_status, page=page, page_size=page_size
        )
        return paginated_response(rows, total, page, size)

    @router.post("/statement-lines/{line_id}/match", name="finance_match_statement_line")
    async def match_line_route(line_id: UUID, body: MatchBody, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        result = matching_svc.match_line(scope(ctx), line_id, body.entry_id, user_id=ctx.user_id)
        result["entry"] = present_entry(result["entry"], is_admin=ctx.is_admin)
        return success_response(result)

    @router.post("/statement-lines/{line_id}/ignore", name="finance_ignore_statement_line")
    async def ignore_line_route(line_id: UUID, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(matching_svc.ignore_line(scope(ctx), line_id))

    # ── gateway sync ──
    @router.post("/accounts/{account_id}/gateway-sync", name="finance_gateway_sync")
    async def gateway_sync_route(
        account_id: UUID,
        response: Response,
        body: Optional[GatewaySyncBody] = None,
        _a=admin,
        ctx: FinanceContext = Depends(ctx_dep),
        operations=Depends(get_charge_operations),
    ) -> dict:
        result = sync_svc.sync_gateway_account(
            scope(ctx), operations, account_id, since=body.since if body else None
        )
        if result["status"] == "error":
            raise sync_svc.sync_failed(result)
        if result["status"] == "partial":
            response.status_code = 202  # page budget spent: call again (or wait for the job) to continue
        return success_response(result)

    # ── exports ──
    @router.get("/exports/entries.csv", name="finance_export_entries")
    async def export_entries_route(
        direction: Optional[str] = Query(None),
        status: Optional[str] = Query(None),
        overdue: Optional[bool] = Query(None),
        date_from: Optional[date] = Query(None, alias="from"),
        date_to: Optional[date] = Query(None, alias="to"),
        category_id: Optional[UUID] = Query(None),
        cost_center_id: Optional[UUID] = Query(None),
        q: Optional[str] = Query(None, max_length=100),
        _a=reader,
        ctx: FinanceContext = Depends(ctx_dep),
    ) -> Response:
        body = exports_svc.entries_csv(
            scope(ctx), is_admin=ctx.is_admin, direction=direction, status=status, overdue=overdue,
            date_from=date_from, date_to=date_to, category_id=category_id, cost_center_id=cost_center_id, q=q,
        )
        return Response(
            content=body,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="lancamentos.csv"', "Cache-Control": "no-store"},
        )

    @router.get("/exports/ledger.ofx", name="finance_export_ledger")
    async def export_ledger_route(
        account_id: UUID = Query(...),
        date_from: Optional[date] = Query(None, alias="from"),
        date_to: Optional[date] = Query(None, alias="to"),
        _a=reader,
        ctx: FinanceContext = Depends(ctx_dep),
    ) -> Response:
        body = exports_svc.ledger_ofx(scope(ctx), account_id, date_from=date_from, date_to=date_to)
        return Response(
            content=body,
            media_type="application/x-ofx",
            headers={"Content-Disposition": 'attachment; filename="razao.ofx"', "Cache-Control": "no-store"},
        )

    return router


__all__ = ["GatewaySyncBody", "MatchBody", "make_finance_reconciliation_router"]
