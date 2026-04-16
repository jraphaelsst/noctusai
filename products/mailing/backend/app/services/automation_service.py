"""Automation lifecycle service."""
import logging

logger = logging.getLogger(__name__)


class AutomationService:
    def __init__(self, db, org_id: str):
        self.db = db
        self.org_id = org_id

    def list_automations(self, status: str = None):
        query = self.db.table("automations").select("*").eq("org_id", self.org_id)
        if status:
            query = query.eq("status", status)
        result = query.order("created_at", desc=True).execute()
        return result.data or []

    def get_automation(self, automation_id: str):
        result = (self.db.table("automations").select("*")
                  .eq("id", automation_id).eq("org_id", self.org_id).execute())
        return result.data[0] if result.data else None

    def create_automation(self, data: dict, user_id: str):
        data["org_id"] = self.org_id
        data["created_by"] = user_id
        result = self.db.table("automations").insert(data).execute()
        return result.data[0] if result.data else None

    def update_automation(self, automation_id: str, data: dict):
        data["updated_at"] = "now()"
        result = (self.db.table("automations").update(data)
                  .eq("id", automation_id).eq("org_id", self.org_id).execute())
        return result.data[0] if result.data else None

    def activate(self, automation_id: str):
        return self.update_automation(automation_id, {"status": "ativa"})

    def pause(self, automation_id: str):
        return self.update_automation(automation_id, {"status": "pausada"})

    def delete_automation(self, automation_id: str):
        automation = self.get_automation(automation_id)
        if not automation or automation["status"] != "rascunho":
            return False
        self.db.table("automations").delete().eq("id", automation_id).execute()
        return True

    # -- Steps --

    def list_steps(self, automation_id: str):
        result = (self.db.table("automation_steps").select("*")
                  .eq("automation_id", automation_id)
                  .order("posicao").execute())
        return result.data or []

    def add_step(self, automation_id: str, data: dict):
        if data.get("posicao") is None:
            steps = self.list_steps(automation_id)
            data["posicao"] = len(steps) + 1
        data["automation_id"] = automation_id
        result = self.db.table("automation_steps").insert(data).execute()
        return result.data[0] if result.data else None

    def update_step(self, step_id: str, data: dict):
        result = self.db.table("automation_steps").update(data).eq("id", step_id).execute()
        return result.data[0] if result.data else None

    def delete_step(self, step_id: str):
        self.db.table("automation_steps").delete().eq("id", step_id).execute()
        return True

    def reorder_steps(self, automation_id: str, step_ids: list[str]):
        for i, sid in enumerate(step_ids):
            self.db.table("automation_steps").update({"posicao": i + 1}).eq("id", sid).execute()
        return self.list_steps(automation_id)

    # -- Enrollments --

    def enroll_contacts(self, automation_id: str, contact_ids: list[str]):
        steps = self.list_steps(automation_id)
        first_step_id = steps[0]["id"] if steps else None
        rows = [{
            "automation_id": automation_id,
            "contact_id": cid,
            "current_step_id": first_step_id,
            "status": "active",
        } for cid in contact_ids]
        result = self.db.table("automation_enrollments").upsert(
            rows, on_conflict="automation_id,contact_id"
        ).execute()
        return result.data or []

    def list_enrollments(self, automation_id: str):
        result = (self.db.table("automation_enrollments").select("*, contacts(nome, email)")
                  .eq("automation_id", automation_id)
                  .order("enrolled_at", desc=True).execute())
        return result.data or []
