"""Operação — platform-admin read surface for routines, runs, models, costs
and the owner daily brief.

  GET  /api/admin/operations/routines         → every product's jobs + last run + missing flags + brief dead-man
  GET  /api/admin/operations/runs             → run history (?product=&job=&status=&limit=)
  GET  /api/admin/operations/models           → effective seed model catalog
  GET  /api/admin/operations/costs            → LLM spend yesterday + cost_ledger (yesterday, month)
  GET  /api/admin/operations/briefs           → brief history (?limit=)
  POST /api/admin/operations/briefs           → generate a brief now (?deliver=false by default)

Health lives on the existing `GET /api/fleet`; LLM usage detail on
`GET /api/admin/llm-usage` — the page links to both, nothing is duplicated.

Access: strict platform admin (`require_platform_admin_dep`: 401 without a
valid bearer, 403 for anyone whose trusted `noctus_users.role` is not
`admin`). Code only, zero LLM / paid-API spend (a delivered manual brief
sends one Resend e-mail, the same as the 07:00 job).
"""
from __future__ import annotations

from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Query

from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.primitives.timeutil import now_utc

from app.services import operations_service, owner_brief_service
from app.services.trusted_auth import get_trusted_db, require_platform_admin_dep

router = APIRouter(prefix="/api/admin/operations", tags=["Admin · Operação"])


def get_llm_source():
    """DI seam: the LLM-spend reader shared by the costs tab and the brief."""
    return operations_service.default_llm_spend


def get_fleet_source():
    """DI seam: the container-status reader the brief uses."""
    return owner_brief_service.default_fleet_status


@router.get("/routines")
async def get_routines(
    _: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    data = await run_blocking(operations_service.list_routines, db, now_utc())
    return {"data": data}


@router.get("/runs")
async def get_runs(
    _: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
    product: Optional[str] = Query(None, max_length=100),
    job: Optional[str] = Query(None, max_length=200),
    status: Optional[Literal["ok", "error", "skipped"]] = Query(None),
    limit: int = Query(100, ge=1, le=500),
):
    rows = await run_blocking(
        lambda: operations_service.list_runs(db, product=product, job=job, status=status, limit=limit)
    )
    return {"data": rows}


@router.get("/models")
async def get_models(_: AuthContext = Depends(require_platform_admin_dep)):
    return {"data": operations_service.model_catalog()}


@router.get("/costs")
async def get_costs(
    _: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
    llm_source=Depends(get_llm_source),
):
    data = await run_blocking(lambda: operations_service.costs_summary(db, now_utc(), llm_source=llm_source))
    return {"data": data}


@router.get("/briefs")
async def get_briefs(
    _: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
    limit: int = Query(30, ge=1, le=100),
):
    rows = await run_blocking(lambda: owner_brief_service.list_briefs(db, limit=limit))
    return {"data": rows}


@router.post("/briefs")
async def create_brief(
    _: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
    deliver: bool = Query(False),
    llm_source=Depends(get_llm_source),
    fleet_source=Depends(get_fleet_source),
):
    """Generate (and store) a brief now; `deliver=true` also notifies + e-mails.
    Answers with the stored brief row (the same shape `GET /briefs` lists)."""

    def _generate() -> dict:
        result = owner_brief_service.run_owner_brief(
            db, now_utc(), trigger="manual", deliver=deliver,
            llm_source=llm_source, fleet_source=fleet_source,
        )
        return owner_brief_service.get_brief(db, result.brief_id) or vars(result)

    return {"data": await run_blocking(_generate)}
