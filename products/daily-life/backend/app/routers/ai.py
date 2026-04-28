"""Daily Life AI endpoints — D6 weekly review (ai-expansion Phase 11)."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from noctusai_lib.ai import consent_required
from noctusai_lib.responses import success_response

from app.dependencies import get_current_user, get_org_id, get_user_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI"])


class WeeklyReviewSendRequest(BaseModel):
    recipient: str
    user_id: Optional[str] = None  # defaults to caller's id
    user_label: Optional[str] = None
    period_days: int = 7


@router.get("/weekly-review")
async def weekly_review_endpoint(
    period_days: int = 7,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("daily_life.weekly_review")),
):
    """D6 — build the past-week review for the calling user. Returns body
    + structured summary. No email send. Used by the dashboard widget."""
    user, token = await get_current_user(authorization)
    org_id = get_org_id(user)
    db = get_user_client(token)

    user_label = (
        (user.user_metadata or {}).get("nome")
        or (user.user_metadata or {}).get("name")
        or "Você"
    )

    from app.services.weekly_review_service import build_review
    digest, summary = await build_review(
        db,
        user_id=user.id,
        user_label=user_label,
        org_id=org_id,
        period_days=period_days,
    )
    return success_response({
        "subject": digest.subject,
        "html": digest.html,
        "text": digest.text,
        "summary": summary,
    })


@router.post("/weekly-review/send")
async def weekly_review_send_endpoint(
    body: WeeklyReviewSendRequest,
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("daily_life.weekly_review")),
):
    """D6 — build + email the past-week review. Cron / n8n posts here on
    Friday afternoon. The cron caller passes the target `user_id` and a
    Resend-deliverable `recipient` email."""
    user, token = await get_current_user(authorization)
    org_id = get_org_id(user)
    db = get_user_client(token)

    target_user_id = body.user_id or user.id
    user_label = body.user_label or "Você"

    if target_user_id != user.id:
        # If a cron caller acts on behalf of another user, it must hold a
        # service-role-equivalent token. The seed `get_current_user` already
        # asserts auth; we just refuse cross-user requests from regular sessions.
        raise HTTPException(
            status_code=403,
            detail="Cross-user weekly-review send requires admin/service token.",
        )

    from app.services.weekly_review_service import send_weekly_review
    result = await send_weekly_review(
        db,
        user_id=target_user_id,
        recipient=body.recipient,
        user_label=user_label,
        org_id=org_id,
        period_days=body.period_days,
    )
    return success_response(result)


@router.get("/daily-brief")
async def daily_brief_endpoint(
    authorization: Optional[str] = Header(None),
    _consent: None = Depends(consent_required("daily_life.daily_brief")),
):
    """D1 — today's brief badge. Returns `{chip, summary, tasks_today,
    events_today, habits_pending, yesterday_completed}`. Consumed by the
    `useDailyBrief` hook + `<DailyBriefBadge>` mounted via
    `LayoutEnrichment.aiBadge`."""
    user, token = await get_current_user(authorization)
    org_id = get_org_id(user)
    db = get_user_client(token)
    user_label = (
        (user.user_metadata or {}).get("nome")
        or (user.user_metadata or {}).get("name")
        or "Você"
    )

    from app.services.daily_brief_service import build_brief
    result = await build_brief(
        db, user_id=user.id, user_label=user_label, org_id=org_id
    )
    return success_response(result)
