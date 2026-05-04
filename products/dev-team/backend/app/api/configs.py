"""Config CRUD.

GET    /api/configs           → list of names + summary of each
GET    /api/configs/{name}    → full config dict
PATCH  /api/configs/{name}    → patch one agent's model/provider
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_org_id
from app.services import dev_team_proxy
from noctusai_lib.primitives.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/configs", tags=["dev-team configs"])


class ConfigPatch(BaseModel):
    """PATCH /api/configs/{name} body."""
    agent_name: str = Field(..., description="Which agent role to patch (e.g. 'leader')")
    model: Optional[str] = Field(None, description="New model identifier")
    provider: Optional[str] = Field(None, description="New provider (e.g. 'anthropic', 'openai')")


@router.get("")
async def list_all_configs(authorization: Optional[str] = Header(None)):
    """List config names with a one-line summary of each."""
    user, _ = await get_current_user(authorization)
    get_org_id(user)
    names = dev_team_proxy.list_configs()
    summaries: list[dict] = []
    for name in names:
        try:
            cfg = dev_team_proxy.load_config(name)
            agents = cfg.get("agents", {}) if isinstance(cfg, dict) else {}
            summaries.append({"name": name, "agent_count": len(agents)})
        except Exception as exc:
            # Surface the unreadable config as a row with an error rather
            # than 5xxing the whole list — the rest may still be useful.
            logger.warning("Failed to load config %r for summary: %s", name, exc)
            summaries.append({"name": name, "agent_count": 0, "error": str(exc)})
    return success_response(summaries)


@router.get("/{name}")
async def get_config(name: str, authorization: Optional[str] = Header(None)):
    """Full config dict for one named config."""
    user, _ = await get_current_user(authorization)
    get_org_id(user)
    try:
        cfg = dev_team_proxy.load_config(name)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return success_response(cfg)


@router.patch("/{name}")
async def patch_config(
    name: str,
    body: ConfigPatch,
    authorization: Optional[str] = Header(None),
):
    """Patch one agent's `model` / `provider` in the named config.

    Returns the updated config dict so the frontend can re-render without a
    second GET.
    """
    user, _ = await get_current_user(authorization)
    get_org_id(user)
    if body.model is None and body.provider is None:
        raise HTTPException(
            status_code=400,
            detail="At least one of model / provider must be set.",
        )
    try:
        updated = dev_team_proxy.set_agent_config(
            name,
            agent_name=body.agent_name,
            model=body.model,
            provider=body.provider,
        )
    except NotImplementedError as exc:
        # Engine D-engineer hasn't shipped save_config yet — surface
        # honestly with a 503 (service not ready) rather than 500.
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return success_response(updated)
