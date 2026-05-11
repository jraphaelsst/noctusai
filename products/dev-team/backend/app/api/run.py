"""POST /api/run — fire the team.

Note: `from __future__ import annotations` is intentionally absent. Combining
PEP 563 string annotations with slowapi's `@limiter.limit` decorator triggers
`PydanticUndefinedAnnotation` at import time — `@functools.wraps` does not
propagate `__globals__`, so FastAPI/Pydantic resolve the BaseModel forward-ref
in slowapi's module namespace where `RunRequest` is undefined. Same shape as
AUTH-RL's fix on core/sso.py + media-scheduling/oauth.py.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, Request
from pydantic import Field

from app.dependencies import get_current_user, get_org_id
from app.rate_limit import limiter
from app.services import dev_team_proxy
from noctusai_lib.primitives.responses import success_response
from noctusai_lib.api import StrictHttpModel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/run", tags=["dev-team run"])


class RunRequest(StrictHttpModel):
    """POST /api/run body."""
    task: str = Field(..., min_length=1, description="Free-form task for the team")
    project: Optional[str] = Field(None, description="Optional project slug for telemetry grouping")
    config: Optional[str] = Field("default", description="Named YAML config to use")


@router.post("")
@limiter.limit("10/minute")
async def run_team(request: Request, body: RunRequest, authorization: Optional[str] = Header(None)):
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
