"""Platform-admin "Uso & Custos" dev-side reads (``public.dev_telemetry_*`` core 097 + ``fx_rates``).

Our own development work, NOT the product ledger (that is ``/api/admin/llm-usage``): Claude Code at the
API list price (never an invoice, never product credits), machine samples, heavy-job admissions, the
latest PTAX. Platform admin only (strict 401 without a token, 403 otherwise). Counts only, no text.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.session.types import AuthContext

from app.services import dev_usage
from app.services.trusted_auth import get_trusted_db, require_platform_admin_dep

router = APIRouter(prefix="/api/admin/usage", tags=["Admin · Usage"])

_FROM = Query(None, alias="from", description="ISO-8601 start (default now-7d)")
_TO = Query(None, description="ISO-8601 end (default now)")


@router.get("/dev")
async def dev_usage_report(
    _: AuthContext = Depends(require_platform_admin_dep),
    db=Depends(get_trusted_db),
    host: Optional[str] = Query(None),
    project: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None, description="'main' = the main session"),
    model: Optional[str] = Query(None),
    from_: Optional[str] = _FROM,
    to: Optional[str] = _TO,
):
    win = dev_usage.resolve_window(from_, to)
    return await run_blocking(
        lambda: dev_usage.dev_report(
            db, win, host=host, project=project, session_id=session_id, agent_id=agent_id, model=model
        )
    )


@router.get("/machine")
async def machine_usage_report(
    _: AuthContext = Depends(require_platform_admin_dep),
    db=Depends(get_trusted_db),
    host: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
    from_: Optional[str] = _FROM,
    to: Optional[str] = _TO,
):
    win = dev_usage.resolve_window(from_, to)
    return await run_blocking(lambda: dev_usage.machine_report(db, win, host=host, phase=phase))


@router.get("/jobs")
async def jobs_usage_report(
    _: AuthContext = Depends(require_platform_admin_dep),
    db=Depends(get_trusted_db),
    host: Optional[str] = Query(None),
    phase: Optional[str] = Query(None),
    kind: Optional[str] = Query(None),
    target: Optional[str] = Query(None),
    event: Optional[str] = Query(None),
    from_: Optional[str] = _FROM,
    to: Optional[str] = _TO,
):
    win = dev_usage.resolve_window(from_, to)
    return await run_blocking(
        lambda: dev_usage.jobs_report(db, win, host=host, phase=phase, kind=kind, target=target, event=event)
    )


@router.get("/fx")
async def usage_fx(
    _: AuthContext = Depends(require_platform_admin_dep),
    db=Depends(get_trusted_db),
    from_: Optional[str] = _FROM,
    to: Optional[str] = _TO,
):
    win = dev_usage.resolve_window(from_, to)

    def build() -> dict:
        fx = dev_usage.latest_fx(db)
        return {
            "usd_brl": fx["usd_brl"], "date": fx["date"],
            "window": win.as_dict(), "freshness": {"fx_rates": fx["created_at"]},
        }

    return await run_blocking(build)
