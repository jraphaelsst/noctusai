"""
AutomationService — CRUD for automation_flows + automation_steps,
execution lifecycle management, and the run_due_actions bridge.

All methods scope queries to org_id; RLS provides the second defence.
No silent errors: every except logs at the right level and re-raises.

Engine integration:
  - start_execution(flow_id, lead_id) → inserts automation_executions row
    + calls advance_execution() for immediate steps.
  - advance_execution(execution_id) → loads flow/steps/lead, calls
    AutomationEngine.advance(), applies the AdvanceResult to DB.
  - run_due(org_id) → delegates to automation_engine.run_due_actions().
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.services.automation_engine import (
    AutomationEngine,
    FakeWhatsAppSender,
    WhatsAppSender,
    run_due_actions,
)

logger = logging.getLogger(__name__)

_engine = AutomationEngine()


class AutomationService:
    """DB-backed automation service.

    Args:
        db:      Supabase client (schema-scoped to orbity by the database module)
        org_id:  tenant UUID (string form used in queries)
        sender:  WhatsAppSender implementation; defaults to FakeWhatsAppSender.
                 NOC-REMEDIATE[orbity-automation-live-send] — inject RealWhatsAppSender.
    """

    def __init__(
        self,
        db: Any,
        org_id: UUID,
        sender: WhatsAppSender | None = None,
    ) -> None:
        self._db = db
        self._org_id = str(org_id)
        self._sender: WhatsAppSender = sender if sender is not None else FakeWhatsAppSender()

    def _t(self, table: str):
        return self._db.table(table)

    # ------------------------------------------------------------------
    # Flow CRUD
    # ------------------------------------------------------------------

    def list_flows(self, *, active_only: bool = False) -> list[dict[str, Any]]:
        try:
            q = (
                self._t("automation_flows")
                .select("*")
                .eq("org_id", self._org_id)
                .order("created_at", desc=False)
            )
            if active_only:
                q = q.eq("active", True)
            result = q.execute()
        except Exception:
            logger.exception("automation.list_flows failed org=%s", self._org_id)
            raise
        return result.data or []

    def get_flow(self, flow_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("automation_flows")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", flow_id)
                .execute()
            )
        except Exception:
            logger.exception("automation.get_flow failed org=%s id=%s", self._org_id, flow_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def create_flow(self, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**payload, "org_id": self._org_id}
        try:
            result = self._t("automation_flows").insert(row).execute()
        except Exception:
            logger.exception("automation.create_flow failed org=%s", self._org_id)
            raise
        rows = result.data or []
        if not rows:
            logger.error("automation.create_flow returned no rows org=%s", self._org_id)
            raise RuntimeError("Flow insert returned no data")
        return rows[0]

    def update_flow(self, flow_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        payload.pop("org_id", None)
        try:
            result = (
                self._t("automation_flows")
                .update(payload)
                .eq("org_id", self._org_id)
                .eq("id", flow_id)
                .execute()
            )
        except Exception:
            logger.exception("automation.update_flow failed org=%s id=%s", self._org_id, flow_id)
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_flow(self, flow_id: str) -> bool:
        try:
            result = (
                self._t("automation_flows")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", flow_id)
                .execute()
            )
        except Exception:
            logger.exception("automation.delete_flow failed org=%s id=%s", self._org_id, flow_id)
            raise
        return bool(result.data)

    # ------------------------------------------------------------------
    # Step CRUD
    # ------------------------------------------------------------------

    def list_steps(self, flow_id: str) -> list[dict[str, Any]]:
        try:
            result = (
                self._t("automation_steps")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("flow_id", flow_id)
                .order("ord", desc=False)
                .execute()
            )
        except Exception:
            logger.exception(
                "automation.list_steps failed org=%s flow=%s", self._org_id, flow_id
            )
            raise
        return result.data or []

    def create_step(self, flow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        row = {**payload, "org_id": self._org_id, "flow_id": flow_id}
        try:
            result = self._t("automation_steps").insert(row).execute()
        except Exception:
            logger.exception(
                "automation.create_step failed org=%s flow=%s", self._org_id, flow_id
            )
            raise
        rows = result.data or []
        if not rows:
            logger.error(
                "automation.create_step returned no rows org=%s flow=%s", self._org_id, flow_id
            )
            raise RuntimeError("Step insert returned no data")
        return rows[0]

    def update_step(self, step_id: str, payload: dict[str, Any]) -> dict[str, Any] | None:
        payload.pop("org_id", None)
        payload.pop("flow_id", None)
        try:
            result = (
                self._t("automation_steps")
                .update(payload)
                .eq("org_id", self._org_id)
                .eq("id", step_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "automation.update_step failed org=%s id=%s", self._org_id, step_id
            )
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def delete_step(self, step_id: str) -> bool:
        try:
            result = (
                self._t("automation_steps")
                .delete()
                .eq("org_id", self._org_id)
                .eq("id", step_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "automation.delete_step failed org=%s id=%s", self._org_id, step_id
            )
            raise
        return bool(result.data)

    # ------------------------------------------------------------------
    # Execution lifecycle
    # ------------------------------------------------------------------

    def start_execution(self, flow_id: str, lead_id: str) -> dict[str, Any]:
        """Create a new automation_executions row and kick off the first advance.

        Returns the execution row (after first advance applied).
        """
        flow = self.get_flow(flow_id)
        if not flow:
            raise LookupError(f"Flow {flow_id} not found in org")

        exec_row = {
            "org_id": self._org_id,
            "flow_id": flow_id,
            "lead_id": lead_id,
            "status": "running",
            "current_step_ord": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "context": {},
        }
        try:
            result = self._t("automation_executions").insert(exec_row).execute()
        except Exception:
            logger.exception(
                "automation.start_execution insert failed org=%s flow=%s lead=%s",
                self._org_id, flow_id, lead_id,
            )
            raise
        rows = result.data or []
        if not rows:
            raise RuntimeError("Execution insert returned no data")
        execution = rows[0]

        # Kick off the first advance immediately
        return self.advance_execution(str(execution["id"]))

    def advance_execution(self, execution_id: str) -> dict[str, Any]:
        """Run one advance step on the given execution.

        Loads flow + steps + lead, calls AutomationEngine.advance(),
        applies AdvanceResult to the DB.
        Returns the updated execution row.
        """
        try:
            exec_res = (
                self._t("automation_executions")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", execution_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "automation.advance_execution: fetch execution failed id=%s", execution_id
            )
            raise
        exec_rows = exec_res.data or []
        if not exec_rows:
            raise LookupError(f"Execution {execution_id} not found")
        execution = exec_rows[0]

        if execution["status"] != "running":
            logger.debug(
                "automation.advance_execution: execution=%s status=%s — nothing to do",
                execution_id, execution["status"],
            )
            return execution

        flow = self.get_flow(str(execution["flow_id"]))
        if not flow:
            self._fail_execution(execution_id, "flow not found")
            raise LookupError(f"Flow {execution['flow_id']} not found")

        steps = self.list_steps(str(flow["id"]))

        # Load lead snapshot
        try:
            lead_res = (
                self._t("leads")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("id", str(execution["lead_id"]))
                .execute()
            )
        except Exception:
            logger.exception(
                "automation.advance_execution: fetch lead failed execution=%s", execution_id
            )
            raise
        lead_rows = lead_res.data or []
        lead = lead_rows[0] if lead_rows else {}

        result = _engine.advance(flow, steps, execution, lead)

        # Apply result to DB
        patch: dict[str, Any] = {"status": result.new_status}
        if result.next_step_ord is not None:
            patch["current_step_ord"] = result.next_step_ord
        if result.next_action_at is not None:
            patch["next_action_at"] = result.next_action_at.isoformat()

        try:
            upd = (
                self._t("automation_executions")
                .update(patch)
                .eq("org_id", self._org_id)
                .eq("id", execution_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "automation.advance_execution: update execution failed id=%s", execution_id
            )
            raise
        upd_rows = upd.data or []
        updated_exec = upd_rows[0] if upd_rows else execution

        # Insert pending_action if produced
        if result.pending_action:
            try:
                self._t("automation_pending_actions").insert(result.pending_action).execute()
            except Exception:
                logger.exception(
                    "automation.advance_execution: insert pending_action failed execution=%s",
                    execution_id,
                )
                raise

        return updated_exec

    def list_executions(self, *, lead_id: str | None = None) -> list[dict[str, Any]]:
        try:
            q = (
                self._t("automation_executions")
                .select("*")
                .eq("org_id", self._org_id)
                .order("started_at", desc=True)
            )
            if lead_id:
                q = q.eq("lead_id", lead_id)
            result = q.execute()
        except Exception:
            logger.exception("automation.list_executions failed org=%s", self._org_id)
            raise
        return result.data or []

    def cancel_execution(self, execution_id: str) -> dict[str, Any] | None:
        try:
            result = (
                self._t("automation_executions")
                .update({"status": "canceled"})
                .eq("org_id", self._org_id)
                .eq("id", execution_id)
                .execute()
            )
        except Exception:
            logger.exception(
                "automation.cancel_execution failed id=%s", execution_id
            )
            raise
        rows = result.data or []
        return rows[0] if rows else None

    def run_due(self) -> dict[str, int]:
        """Process due pending actions for this org.

        Delegates to automation_engine.run_due_actions() with the configured sender.
        """
        try:
            return run_due_actions(self._db, self._org_id, self._sender)
        except Exception:
            logger.exception("automation.run_due failed org=%s", self._org_id)
            raise

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fail_execution(self, execution_id: str, reason: str) -> None:
        try:
            self._t("automation_executions").update({
                "status": "failed",
                "error_detail": reason,
            }).eq("org_id", self._org_id).eq("id", execution_id).execute()
        except Exception:
            logger.exception(
                "automation._fail_execution: could not mark failed id=%s", execution_id
            )
