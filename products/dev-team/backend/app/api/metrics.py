"""GET /api/metrics — global rollup."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, Query

from app.dependencies import get_current_user, get_org_id
from app.services import dev_team_proxy
from noctusai_lib.primitives.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/metrics", tags=["dev-team metrics"])


@router.get("")
async def get_metrics(
    scope: Optional[str] = Query(None, description="all-time | last_N_days | <project-slug>"),
    authorization: Optional[str] = Header(None),
):
    """Global rollup. Wraps `dev_team.mcp_facade.metrics_snapshot`."""
    user, _ = await get_current_user(authorization)
    get_org_id(user)
    snapshot = dev_team_proxy.metrics_snapshot(scope=scope)
    return success_response(snapshot)
