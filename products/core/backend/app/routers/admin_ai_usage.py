"""Platform-admin "Uso e custo de IA" (`/api/admin/usage/ai/*`) — contract products/core/docs/ai-usage-contract.md.

Tier: platform. Strict 401 without a token, 403 `platform_admin_required` for non-admins. One source per call
(`anthropic` | `ledger`), never summed. An unavailable source is a 200 with `source.status="unavailable"` and
empty arrays; a typed 422 carries `detail.code`; a real failure is a 500 `{detail:{code,message}}`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Literal, Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.session.types import AuthContext

from app.config import settings
from app.services.ai_usage import reports
from app.services.trusted_auth import get_trusted_db, require_platform_admin_dep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/usage/ai", tags=["Admin · AI usage"], include_in_schema=False)

Source = Literal["anthropic", "ledger"]
_FROM = Query(None, alias="from", description="YYYY-MM-DD (UTC, inclusive)")
_TO = Query(None, description="YYYY-MM-DD (UTC, inclusive)")


def get_now() -> datetime:
    """Clock dependency: tests pin it via app.dependency_overrides[get_now]."""
    return datetime.now(timezone.utc)


def _key_configured() -> bool:
    return bool((settings.anthropic_admin_api_key or "").strip())


def _error(status: int, code: str, message: str) -> JSONResponse:
    # Returned, not raised: the seed handler flattens a raised dict, and the contract shape is {detail:{code,message}}.
    return JSONResponse(status_code=status, content={"detail": {"code": code, "message": message}})


async def _serve(fn: Callable[[], dict]):
    """Run a report off the loop; typed errors -> 422, anything else -> 500 with a stable code."""
    try:
        return await run_blocking(fn)
    except reports.ReportError as exc:
        return _error(422, exc.code, exc.message)
    except Exception:  # noqa: BLE001 — logged with traceback; the client gets a stable code, no internals
        logger.exception("ai usage report failed")
        return _error(500, "ai_usage_report_failed", "Falha ao consultar uso de IA")


def _status(db: Any, source: str, now: datetime) -> dict:
    return reports.source_status(db, source, key_configured=_key_configured(), now=now)


@router.get("/sources")
async def get_sources(_: AuthContext = Depends(require_platform_admin_dep), db=Depends(get_trusted_db), now: datetime = Depends(get_now)):
    return await _serve(lambda: reports.sources(db, key_configured=_key_configured(), now=now))


@router.get("/usage")
async def get_usage(
    source: Source = Query(...),
    from_: Optional[str] = _FROM,
    to: Optional[str] = _TO,
    bucket: Literal["day", "week"] = Query("day"),
    group_by: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    workspace_id: Optional[str] = Query(None),
    api_key_id: Optional[str] = Query(None),
    ambiente: Optional[str] = Query(None),
    origem: Optional[str] = Query(None),
    agent: Optional[str] = Query(None),
    _: AuthContext = Depends(require_platform_admin_dep),
    db=Depends(get_trusted_db),
    now: datetime = Depends(get_now),
):
    def run() -> dict:
        frm, end = reports.parse_window(from_, to)
        filters = {"model": model, "workspace_id": workspace_id, "api_key_id": api_key_id,
                   "ambiente": ambiente, "origem": origem, "agent": agent}
        reports.check_filters(source, filters)
        reports.check_group_by(source, group_by, reports.USAGE_GROUPS)
        return reports.usage_report(db, source=source, status=_status(db, source, now), frm=frm, to=end, bucket=bucket,
                                    group_by=group_by, filters=filters)

    return await _serve(run)


@router.get("/cost")
async def get_cost(
    source: Source = Query(...),
    from_: Optional[str] = _FROM,
    to: Optional[str] = _TO,
    bucket: Literal["day", "week"] = Query("day"),
    group_by: Optional[str] = Query(None),
    model: Optional[str] = Query(None),
    workspace_id: Optional[str] = Query(None),
    api_key_id: Optional[str] = Query(None),
    ambiente: Optional[str] = Query(None),
    origem: Optional[str] = Query(None),
    agent: Optional[str] = Query(None),
    _: AuthContext = Depends(require_platform_admin_dep),
    db=Depends(get_trusted_db),
    now: datetime = Depends(get_now),
):
    def run() -> dict:
        frm, end = reports.parse_window(from_, to)
        filters = {"model": model, "workspace_id": workspace_id, "api_key_id": api_key_id,
                   "ambiente": ambiente, "origem": origem, "agent": agent}
        return reports.cost_report(db, source=source, status=_status(db, source, now), frm=frm, to=end, bucket=bucket,
                                   group_by=group_by, filters=filters)

    return await _serve(run)


@router.get("/spend")
async def get_spend(
    source: Source = Query(...),
    month: Optional[str] = Query(None, description="YYYY-MM"),
    _: AuthContext = Depends(require_platform_admin_dep),
    db=Depends(get_trusted_db),
    now: datetime = Depends(get_now),
):
    return await _serve(lambda: reports.spend_report(
        db, source=source, status=_status(db, source, now), month=month, today=now.date()))


@router.get("/deliveries")
async def get_deliveries(
    source: Source = Query(...),
    from_: Optional[str] = _FROM,
    to: Optional[str] = _TO,
    bucket: Literal["week"] = Query("week"),
    model: Optional[str] = Query(None),
    agent: Optional[str] = Query(None),
    ambiente: Optional[str] = Query(None),
    _: AuthContext = Depends(require_platform_admin_dep),
    db=Depends(get_trusted_db),
    now: datetime = Depends(get_now),
):
    def run() -> dict:
        if source != "ledger":
            raise reports.ReportError("filter_not_supported_by_source", "deliveries exist only in the ledger source")
        frm, end = reports.parse_window(from_, to)
        return reports.deliveries_report(db, status=_status(db, "ledger", now), frm=frm, to=end, model=model,
                                         agent=agent, ambiente=ambiente)

    return await _serve(run)


@router.get("/rate-limits")
async def get_rate_limits(
    source: Source = Query(...),
    _: AuthContext = Depends(require_platform_admin_dep),
    db=Depends(get_trusted_db),
    now: datetime = Depends(get_now),
):
    def run() -> dict:
        if source != "anthropic":
            raise reports.ReportError("filter_not_supported_by_source", "rate limits exist only in the anthropic source")
        return reports.rate_limits_report(db, status=_status(db, "anthropic", now))

    return await _serve(run)
