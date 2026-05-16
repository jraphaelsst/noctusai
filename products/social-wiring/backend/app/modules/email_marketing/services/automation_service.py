"""Automation lifecycle service."""
import logging

from fastapi import HTTPException

from noctusai_lib.api.crud_safety import delete_or_404

logger = logging.getLogger(__name__)


class AutomationService:
    def __init__(self, db, org_id: str):
        self.db = db
        self.org_id = org_id

    # ----- defense-in-depth org-chain guards -----

    def _assert_automation_in_org(self, automation_id: str) -> dict:
        """Raise HTTPException(404) if automation_id does not belong to org.

        Phase 1 mailing-wiring M-1 fix. RLS mitigates at the DB layer, but
        service-layer code paths that operate on automation sub-entities
        (steps, enrollments) MUST verify the parent automation belongs to
        the caller's org BEFORE proceeding. Without this, a leaked step UUID
        could allow cross-tenant write paths to surface.
        """
        row = self.get_automation(automation_id)
        if not row:
            raise HTTPException(status_code=404, detail="Automacao nao encontrada")
        return row

    def _assert_step_in_automation(self, automation_id: str, step_id: str) -> None:
        """Raise HTTPException(404) if step does not belong to automation.

        Composes with :meth:`_assert_automation_in_org` — call that first so
        the automation→org link is verified, then this one to verify the
        step→automation link.
        """
        check = (
            self.db.table("automation_steps")
            .select("id")
            .eq("id", step_id)
            .eq("automation_id", automation_id)
            .execute()
        )
        if not check.data:
            raise HTTPException(status_code=404, detail="Step nao encontrado")

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
        # Use seed helper + scope by org_id (was unscoped — RLS mitigates but
        # service-layer defense-in-depth was missing).
        delete_or_404(
            self.db, "automations",
            ("id", automation_id), ("org_id", self.org_id),
            message="Automacao nao encontrada",
        )
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

    def update_step(self, automation_id: str, step_id: str, data: dict):
        # M-1 defense-in-depth: verify automation→org chain, then step→automation.
        self._assert_automation_in_org(automation_id)
        self._assert_step_in_automation(automation_id, step_id)
        result = (
            self.db.table("automation_steps")
            .update(data)
            .eq("id", step_id)
            .eq("automation_id", automation_id)
            .execute()
        )
        return result.data[0] if result.data else None

    def delete_step(self, automation_id: str, step_id: str):
        # M-1 defense-in-depth: verify automation→org chain, then step→automation.
        self._assert_automation_in_org(automation_id)
        delete_or_404(
            self.db, "automation_steps",
            ("id", step_id), ("automation_id", automation_id),
            message="Step nao encontrado",
        )
        return True

    def reorder_steps(self, automation_id: str, step_ids: list[str]):
        # M-1 defense-in-depth: verify automation belongs to caller's org.
        # Also scope the UPDATE by `automation_id` so a leaked step UUID from
        # a different automation cannot be re-positioned via this endpoint.
        self._assert_automation_in_org(automation_id)
        for i, sid in enumerate(step_ids):
            (
                self.db.table("automation_steps")
                .update({"posicao": i + 1})
                .eq("id", sid)
                .eq("automation_id", automation_id)
                .execute()
            )
        return self.list_steps(automation_id)

    # -- Enrollments --

    def enroll_contacts(self, automation_id: str, contact_ids: list[str]):
        # M-1 defense-in-depth: verify automation belongs to caller's org.
        self._assert_automation_in_org(automation_id)
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
        # M-1 defense-in-depth: verify automation belongs to caller's org.
        self._assert_automation_in_org(automation_id)
        result = (self.db.table("automation_enrollments").select("*, contacts(nome, email)")
                  .eq("automation_id", automation_id)
                  .order("enrolled_at", desc=True).execute())
        return result.data or []
