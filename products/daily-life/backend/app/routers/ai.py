"""Daily Life AI endpoints — D6 weekly review (ai-expansion Phase 11)."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends

from noctusai_lib.domain.ai import consent_required
from noctusai_lib.primitives.responses import success_response

from app.dependencies import get_user_client, get_current_user_org

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ai", tags=["AI"])


@router.get("/weekly-review")
async def weekly_review_endpoint(
    period_days: int = 7,
    auth: tuple = Depends(get_current_user_org),
    _consent: None = Depends(consent_required("daily_life.weekly_review")),
):
    """D6 — build the past-week review for the calling user. Returns body
    + structured summary. No email send. Used by the dashboard widget."""
    user, token, org_id = auth
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


@router.get("/daily-brief")
async def daily_brief_endpoint(
    auth: tuple = Depends(get_current_user_org),
    _consent: None = Depends(consent_required("daily_life.daily_brief")),
):
    """D1 — today's brief badge. Returns `{chip, summary, tasks_today,
    events_today, habits_pending, yesterday_completed}`. Consumed by the
    `useDailyBrief` hook + `<DailyBriefBadge>` mounted via
    `LayoutEnrichment.aiBadge`."""
    user, token, org_id = auth
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
