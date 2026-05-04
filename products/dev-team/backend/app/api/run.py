"""POST /api/run — fire the team."""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from app.dependencies import get_current_user, get_org_id
from app.services import dev_team_proxy
from noctusai_lib.primitives.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/run", tags=["dev-team run"])


class RunRequest(BaseModel):
    """POST /api/run body."""
    task: str = Field(..., min_length=1, description="Free-form task for the team")
    project: Optional[str] = Field(None, description="Optional project slug for telemetry grouping")
    config: Optional[str] = Field("default", description="Named YAML config to use")


@router.post("")
async def run_team(body: RunRequest, authorization: Optional[str] = Header(None)):
    """Fire the team.

    The engine returns one of:
      - `{status: "ok", summary, task, project, config}` — real LLM call.
      - `{status: "switch-not-flipped", summary, task}` — no ANTHROPIC_API_KEY.
      - `{status: "dry-run", summary, members}` — only when caller passed dry_run.

    All three are treated as 200 here; the `status` field discriminates.
    """
    user, _ = await get_current_user(authorization)
    get_org_id(user)  # 403 if no org claim
    envelope = dev_team_proxy.run_team(
        task=body.task,
        project=body.project,
        config=body.config or "default",
    )
    return success_response(envelope)
