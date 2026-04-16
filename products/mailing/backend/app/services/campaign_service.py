"""Campaign lifecycle service."""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class CampaignService:
    def __init__(self, db, org_id: str):
        self.db = db
        self.org_id = org_id

    def list_campaigns(self, status: str = None):
        query = self.db.table("campaigns").select("*").eq("org_id", self.org_id)
        if status:
            query = query.eq("status", status)
        result = query.order("created_at", desc=True).execute()
        return result.data or []

    def get_campaign(self, campaign_id: str):
        result = (self.db.table("campaigns").select("*")
                  .eq("id", campaign_id).eq("org_id", self.org_id).execute())
        return result.data[0] if result.data else None

    def create_campaign(self, data: dict, user_id: str):
        data["org_id"] = self.org_id
        data["created_by"] = user_id
        result = self.db.table("campaigns").insert(data).execute()
        return result.data[0] if result.data else None

    def update_campaign(self, campaign_id: str, data: dict):
        campaign = self.get_campaign(campaign_id)
        if not campaign or campaign["status"] not in ("rascunho", "agendada"):
            return None
        data["updated_at"] = "now()"
        result = (self.db.table("campaigns").update(data)
                  .eq("id", campaign_id).eq("org_id", self.org_id).execute())
        return result.data[0] if result.data else None

    def delete_campaign(self, campaign_id: str):
        campaign = self.get_campaign(campaign_id)
        if not campaign or campaign["status"] != "rascunho":
            return False
        self.db.table("campaigns").delete().eq("id", campaign_id).eq("org_id", self.org_id).execute()
        return True

    def schedule_campaign(self, campaign_id: str, scheduled_at: datetime):
        return self._set_status(campaign_id, "agendada", scheduled_at=scheduled_at)

    def start_send(self, campaign_id: str):
        return self._set_status(campaign_id, "enviando",
                                started_at=datetime.now(timezone.utc).isoformat())

    def pause_campaign(self, campaign_id: str):
        return self._set_status(campaign_id, "pausada")

    def cancel_campaign(self, campaign_id: str):
        return self._set_status(campaign_id, "cancelada")

    def complete_campaign(self, campaign_id: str):
        return self._set_status(campaign_id, "enviada",
                                completed_at=datetime.now(timezone.utc).isoformat())

    def get_stats(self, campaign_id: str):
        """Get send statistics for a campaign."""
        result = self.db.table("send_logs").select("status", count="exact").eq("campaign_id", campaign_id).execute()
        logs = result.data or []
        stats = {"total": len(logs), "queued": 0, "sent": 0, "delivered": 0,
                 "opened": 0, "clicked": 0, "bounced": 0, "complained": 0, "failed": 0}
        for log in logs:
            s = log.get("status", "queued")
            if s in stats:
                stats[s] += 1
        return stats

    def _set_status(self, campaign_id: str, status: str, **extra):
        update = {"status": status, "updated_at": "now()", **extra}
        result = (self.db.table("campaigns").update(update)
                  .eq("id", campaign_id).eq("org_id", self.org_id).execute())
        return result.data[0] if result.data else None
