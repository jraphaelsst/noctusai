"""Billing-reminders HTTP surface -- `make_finance_reminders_router(cfg, auth_dependency, admin_dependency, ...)` at
`/api/finance/reminders`.

Authorization (same split as finance / contracts): org STAFF may read (`auth_dependency`); every write additionally
requires `admin_dependency` (the host's `require_org_admin(...)`). Unauthenticated is a strict 401 (it lives in the host's
auth dep). Every service call is org-scoped. Reminders are OPT-IN per org: until an admin PUTs `enabled=true` nothing is
ever sent; the first enable seeds the default rule ladder.

Routes
- `GET  /settings` / `PUT /settings`            -- `{enabled, timezone}` (+ `variables`, the template vocabulary)
- `GET  /rules`  / `POST /rules`                -- the rule list / a new rule
- `PATCH /rules/{id}` / `DELETE /rules/{id}`    -- edit (an unknown `{variable}` is 422 `variavel_desconhecida`) / delete (409 with history)
- `POST /rules/defaults`                        -- add the default ladder offsets the org does not have yet
- `PUT  /receivables/{entry_id}/opt-out`        -- per-receivable opt-out
- `GET  /log`                                   -- the sent log, paginated (`?status=`)
- `GET  /preview`                               -- what would go out today (or `?on=YYYY-MM-DD`); no writes, no sends

The factory takes the host's `get_ports() -> ReminderPorts` (the same object the daily job gets) so the preview renders
exactly what the job would send. 🔴 NEVER `get_admin_client().schema(...)` in here: `get_db` already returns the
product's schema-scoped client.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response

from noctusai_lib.primitives.responses import paginated_response, success_response

from . import service as svc
from .._common import Scope
from ..config import FinanceConfig, FinanceContext
from .schemas import OptOutBody, RuleBody, RulePatch, SettingsBody
from .service import ReminderPorts
from .types import STATUSES, TEMPLATE_VARIABLES


def make_finance_reminders_router(
    cfg: FinanceConfig,
    auth_dependency: Callable[..., Any],
    admin_dependency: Callable[..., Any],
    *,
    resolve_context: Callable[[Any, Any], FinanceContext],
    get_db: Callable[..., Any],
    get_ports: Callable[[], ReminderPorts],
    prefix: str = "/api/finance/reminders",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    router = APIRouter(prefix=prefix, tags=tags or ["finance-reminders"])

    def ctx_dep(auth=Depends(auth_dependency), db=Depends(get_db)) -> FinanceContext:
        return resolve_context(auth, db)

    admin = Depends(admin_dependency)

    def scope(ctx: FinanceContext) -> Scope:
        return Scope(ctx.db, cfg, str(ctx.org_id))

    def settings_view(s: Scope, row: dict) -> dict:
        return {"enabled": bool(row.get("enabled")), "timezone": row.get("timezone"), "variables": list(TEMPLATE_VARIABLES)}

    @router.get("/settings", name="finance_reminders_settings")
    async def get_settings_route(ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        s = scope(ctx)
        return success_response(settings_view(s, svc.get_settings(s)))

    @router.put("/settings", name="finance_reminders_save_settings")
    async def put_settings_route(body: SettingsBody, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        s = scope(ctx)
        return success_response(settings_view(s, svc.save_settings(s, body.model_dump(exclude_unset=True))))

    @router.get("/rules", name="finance_reminders_rules")
    async def list_rules_route(ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.list_rules(scope(ctx)))

    @router.post("/rules", status_code=201, name="finance_reminders_create_rule")
    async def create_rule_route(body: RuleBody, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.create_rule(scope(ctx), body.model_dump()))

    @router.post("/rules/defaults", name="finance_reminders_default_rules")
    async def default_rules_route(_a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.ensure_default_rules(scope(ctx)))

    @router.patch("/rules/{rule_id}", name="finance_reminders_update_rule")
    async def update_rule_route(rule_id: UUID, body: RulePatch, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        return success_response(svc.update_rule(scope(ctx), rule_id, body.model_dump(exclude_unset=True)))

    @router.delete("/rules/{rule_id}", status_code=204, name="finance_reminders_delete_rule")
    async def delete_rule_route(rule_id: UUID, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> Response:
        svc.delete_rule(scope(ctx), rule_id)
        return Response(status_code=204)

    @router.put("/receivables/{entry_id}/opt-out", name="finance_reminders_opt_out")
    async def opt_out_route(entry_id: UUID, body: OptOutBody, _a=admin, ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        row = svc.set_receivable_opt_out(scope(ctx), entry_id, body.opt_out)
        return success_response({"entry_id": str(entry_id), "reminders_opt_out": bool(row["reminders_opt_out"])})

    @router.get("/log", name="finance_reminders_log")
    async def log_route(
        status: Optional[str] = Query(None, pattern="^(" + "|".join(STATUSES) + ")$"),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        ctx: FinanceContext = Depends(ctx_dep),
    ) -> dict:
        rows, total, page, size = svc.list_log(scope(ctx), page=page, page_size=page_size, status=status)
        return paginated_response(rows, total, page, size)

    @router.get("/preview", name="finance_reminders_preview")
    async def preview_route(on: Optional[date] = Query(None), ctx: FinanceContext = Depends(ctx_dep)) -> dict:
        s = scope(ctx)
        plan = svc.preview_reminders(s, get_ports(), on=on)
        ids = sorted({x.entry_id for x in (*plan.planned, *plan.skipped)})
        names = {str(r["id"]): r.get("description") for r in s.rows("entries", refine=lambda q: q.in_("id", ids))} if ids else {}
        return success_response({
            "on": plan.on,
            "enabled": bool(svc.get_settings(s).get("enabled")),
            "planned": [{**vars(p), "description": names.get(p.entry_id)} for p in plan.planned],
            "skipped": [{**vars(k), "description": names.get(k.entry_id)} for k in plan.skipped],
        })

    return router


__all__ = ["make_finance_reminders_router"]
