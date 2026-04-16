"""Analytics router — dashboard metrics, campaign stats, automation funnel."""
import logging
from typing import Optional

from fastapi import APIRouter, Header
from app.dependencies import get_current_user, get_org_id, get_admin_client
from noctusai_lib.responses import success_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/dashboard")
async def dashboard_metrics(authorization: Optional[str] = Header(None)):
    """Overview metrics: total contacts, total sent, open rate, click rate, bounces."""
    user, _ = await get_current_user(authorization)
    org_id = get_org_id(user)
    db = get_admin_client()

    # Total contacts
    contacts = db.table("contacts").select("id", count="exact").eq("org_id", org_id).execute()
    total_contacts = contacts.count or 0
    active_contacts = (db.table("contacts").select("id", count="exact")
                       .eq("org_id", org_id).eq("status", "active").execute()).count or 0

    # Send stats
    sends = db.table("send_logs").select("status").eq("org_id", org_id).execute()
    all_sends = sends.data or []
    total_sent = len([s for s in all_sends if s["status"] != "queued"])
    total_opened = len([s for s in all_sends if s["status"] in ("opened", "clicked")])
    total_clicked = len([s for s in all_sends if s["status"] == "clicked"])
    total_bounced = len([s for s in all_sends if s["status"] == "bounced"])

    open_rate = (total_opened / total_sent * 100) if total_sent > 0 else 0
    click_rate = (total_clicked / total_sent * 100) if total_sent > 0 else 0

    # Campaign count
    campaigns = db.table("campaigns").select("id", count="exact").eq("org_id", org_id).execute()
    total_campaigns = campaigns.count or 0

    return success_response({
        "total_contacts": total_contacts,
        "active_contacts": active_contacts,
        "total_sent": total_sent,
        "total_opened": total_opened,
        "total_clicked": total_clicked,
        "total_bounced": total_bounced,
        "open_rate": round(open_rate, 1),
        "click_rate": round(click_rate, 1),
        "total_campaigns": total_campaigns,
    })


@router.get("/campaigns/{campaign_id}")
async def campaign_analytics(campaign_id: str, authorization: Optional[str] = Header(None)):
    """Detailed analytics for a specific campaign."""
    user, _ = await get_current_user(authorization)
    org_id = get_org_id(user)
    db = get_admin_client()

    sends = (db.table("send_logs").select("status, sent_at, opened_at, clicked_at")
             .eq("campaign_id", campaign_id).eq("org_id", org_id).execute())

    all_sends = sends.data or []
    stats = {"total": len(all_sends), "queued": 0, "sent": 0, "delivered": 0,
             "opened": 0, "clicked": 0, "bounced": 0, "complained": 0, "failed": 0}
    for s in all_sends:
        status = s.get("status", "queued")
        if status in stats:
            stats[status] += 1

    stats["open_rate"] = round((stats["opened"] + stats["clicked"]) / max(stats["total"], 1) * 100, 1)
    stats["click_rate"] = round(stats["clicked"] / max(stats["total"], 1) * 100, 1)

    return success_response(stats)
