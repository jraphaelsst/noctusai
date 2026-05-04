"""GET /api/agents — grid snapshot for the 11 specialists.
GET /api/agents/{name}/metrics — per-agent rollup + recent events.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query

from app.dependencies import get_current_user, get_org_id
from app.services import dev_team_proxy
from noctusai_lib.primitives.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/agents", tags=["dev-team agents"])


@router.get("")
async def list_agents(authorization: Optional[str] = Header(None)):
    """Snapshot grid: 11 cards with model + 24h events + 24h cost + success rate."""
    user, _ = await get_current_user(authorization)
    get_org_id(user)  # 403 if no org claim
    snapshot = dev_team_proxy.list_agents_snapshot()
    return success_response(snapshot)


@router.get("/{name}/metrics")
async def get_agent_metrics(
    name: str,
    scope: Optional[str] = Query(None, description="all-time | last_N_days | <project-slug>"),
    authorization: Optional[str] = Header(None),
):
    """Per-agent rollup. Wraps `dev_team.mcp_facade.agent_metrics`."""
    user, _ = await get_current_user(authorization)
    get_org_id(user)
    if name not in dev_team_proxy.AGENT_NAMES:
        raise HTTPException(status_code=404, detail=f"Unknown agent: {name}")
    metrics = dev_team_proxy.agent_metrics(name=name, scope=scope)
    return success_response(metrics)
