"""
AutomationService — CRUD for automation_flows + automation_steps,
execution lifecycle management, and the run_due_actions bridge.

All methods scope queries to org_id; RLS provides the second defence.
No silent errors: every except logs at the right level and re-raises.

Engine integration:
  - start_execution(flow_id, lead_id | subject, trigger_key) → inserts the
    automation_executions row (idempotent per flow × trigger_key) and
    advances it until it blocks on a scheduled send/wait/action.
  - advance_execution(execution_id) → loads flow/steps/subject, calls
    AutomationEngine.advance() in a chain, applies each AdvanceResult.
  - run_due() → automation_engine.run_due_actions(): claims due actions,
    executes them (real send / CRM action), then advances their executions.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from app.services.automation_actions import execute_action
from app.services.automation_engine import (
    AutomationEngine,
    WhatsAppSender,
    run_due_actions,
)

logger = logging.getLogger(__name__)

_engine = AutomationEngine()

#: Hard stop for one advance chain — a backward `branch` could otherwise spin.
MAX_CHAIN_STEPS = 100

SUBJECT_TYPES = ("lead", "client", "task", "meeting")


class AutomationService:
    """DB-backed automation service.

    Args:
        db:      Supabase client (schema-scoped to orbity by the database module)
        org_id:  tenant UUID (string form used in queries)
        sender:  WhatsAppSender used by `run_due`. Default (None) is the REAL
                 sender resolved lazily from the org's WhatsApp connection —
                 the Fake is injected explicitly by tests only.
    """

    def __init__(
        self,
        db: Any,
        org_id: UUID,
        sender: WhatsAppSender | None = None,
    ) -> None:
        self._db = db
        self._org_id = str(org_id)
        self._sender_override = sender

    @property
    def _sender(self) -> WhatsAppSender:
        if self._sender_override is not None:
            return self._sender_override
        from app.services.whatsapp_sender import make_default_sender
        return make_default_sender()

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

    def start_execution(
        self,
        flow_id: str,
        lead_id: str | None = None,
        *,
        subject_type: str = "lead",
        subject_id: str | None = None,
        trigger_key: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create an execution and run it until it blocks (a scheduled send/wait)
        or ends. Returns the execution row after that first chain.

        `trigger_key` makes the start idempotent per flow: a second start with
        the same key returns the EXISTING execution untouched.
        """
        execution, _created = self.start_execution_once(
            flow_id, lead_id, subject_type=subject_type, subject_id=subject_id,
            trigger_key=trigger_key, context=context,
        )
        return execution

    def start_execution_once(
        self,
        flow_id: str,
        lead_id: str | None,
        *,
        subject_type: str = "lead",
        subject_id: str | None = None,
        trigger_key: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """(execution, created). `created=False` => the key was already used."""
        if subject_type not in SUBJECT_TYPES:
            raise ValueError(f"subject_type inválido: {subject_type}")
        if subject_type == "lead" and not lead_id:
            raise ValueError("lead_id é obrigatório para execuções de lead")
        if subject_type != "lead" and not subject_id:
            raise ValueError("subject_id é obrigatório para execuções que não são de lead")

        flow = self.get_flow(flow_id)
        if not flow:
            raise LookupError(f"Flow {flow_id} not found in org")

        if trigger_key:
            existing = self._find_by_trigger_key(flow_id, trigger_key)
            if existing:
                logger.debug(
                    "automation.start: flow=%s key=%s already started — no-op", flow_id, trigger_key
                )
                return existing, False

        exec_row: dict[str, Any] = {
            "org_id": self._org_id,
            "flow_id": flow_id,
            "lead_id": lead_id if subject_type == "lead" else None,
            "subject_type": subject_type,
            "subject_id": subject_id if subject_type != "lead" else None,
            "status": "running",
            "current_step_ord": 0,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "context": context or {},
        }
        if trigger_key:
            exec_row["trigger_key"] = trigger_key
        try:
            result = self._t("automation_executions").insert(exec_row).execute()
        except Exception as exc:
            if trigger_key and is_unique_violation(exc):
                # Lost a race against a concurrent start of the same occurrence.
                existing = self._find_by_trigger_key(flow_id, trigger_key)
                if existing:
                    return existing, False
            logger.exception(
                "automation.start_execution insert failed org=%s flow=%s subject=%s/%s",
                self._org_id, flow_id, subject_type, subject_id or lead_id,
            )
            raise
        rows = result.data or []
        if not rows:
            raise RuntimeError("Execution insert returned no data")
        execution_id = str(rows[0]["id"])
        try:
            return self.advance_execution(execution_id), True
        except Exception:
            # Never leave an orphan 'running' row nothing will ever resume.
            self._fail_execution(execution_id, "Falha ao iniciar a automação.")
            raise

    def _find_by_trigger_key(self, flow_id: str, trigger_key: str) -> dict[str, Any] | None:
        try:
            res = (
                self._t("automation_executions")
                .select("*")
                .eq("org_id", self._org_id)
                .eq("flow_id", flow_id)
                .eq("trigger_key", trigger_key)
                .execute()
            )
        except Exception:
            logger.exception("automation._find_by_trigger_key failed flow=%s", flow_id)
            raise
        rows = res.data or []
        return rows[0] if rows else None

    def advance_execution(self, execution_id: str) -> dict[str, Any]:
        """Advance the execution until it BLOCKS — it scheduled a send/wait/action
        (resumed by the drain) — or ends. condition/branch steps resolve inline,
        so a chain of them never needs a scheduler tick. Returns the execution row.
        """
        execution: dict[str, Any] | None = None
        for _ in range(MAX_CHAIN_STEPS):
            execution, blocked = self._advance_once(execution_id)
            if blocked:
                return execution
        self._fail_execution(execution_id, "Fluxo excedeu o limite de passos (laço?).")
        logger.error("automation.advance_execution: chain limit hit execution=%s", execution_id)
        return execution or {}

    def _subject_snapshot(self, execution: dict[str, Any]) -> dict[str, Any]:
        """The 'lead-shaped' dict the engine interpolates/branches on.

        lead -> the leads row. client/task/meeting -> the contact (client row, or
        the task/meeting's client) mapped to name/phone/email/company, so a send
        step reaches the client; no contact => no phone => the engine skips the
        send and the skip is recorded on the execution.
        """
        subject_type = execution.get("subject_type") or "lead"
        if subject_type == "lead":
            lead = self._fetch_one("leads", str(execution["lead_id"])) or {}
            # A soft-deleted lead has no snapshot: the engine then has no phone to send to.
            return {} if lead.get("deleted_at") else lead

        subject_id = str(execution.get("subject_id") or "")
        custom: dict[str, Any] = {}
        client: dict[str, Any] | None = None
        if subject_type == "client":
            client = self._fetch_one("clients", subject_id)
        elif subject_type == "task":
            task = self._fetch_one("tasks", subject_id) or {}
            custom["tarefa"] = task.get("title")
            if task.get("client_id"):
                client = self._fetch_one("clients", str(task["client_id"]))
        elif subject_type == "meeting":
            event = self._fetch_one("agenda_events", subject_id) or {}
            custom["data_reuniao"] = event.get("starts_at")
            if event.get("client_id"):
                client = self._fetch_one("clients", str(event["client_id"]))
        client = client or {}
        return {
            "name": client.get("name"),
            "phone": client.get("phone"),
            "email": client.get("email"),
            "company": client.get("company"),
            "custom_fields": custom,
        }

    def _fetch_one(self, table: str, row_id: str) -> dict[str, Any] | None:
        try:
            res = (
                self._t(table).select("*").eq("org_id", self._org_id).eq("id", row_id).execute()
            )
        except Exception:
            logger.exception("automation._fetch_one failed table=%s id=%s", table, row_id)
            raise
        rows = res.data or []
        return rows[0] if rows else None

    def _advance_once(self, execution_id: str) -> tuple[dict[str, Any], bool]:
        """One engine step. Returns (execution, blocked): blocked when the
        execution is no longer running or the step scheduled a pending action."""
        execution = self._fetch_one("automation_executions", execution_id)
        if not execution:
            raise LookupError(f"Execution {execution_id} not found")

        if execution["status"] != "running":
            logger.debug(
                "automation.advance_execution: execution=%s status=%s — nothing to do",
                execution_id, execution["status"],
            )
            return execution, True

        flow = self.get_flow(str(execution["flow_id"]))
        if not flow:
            self._fail_execution(execution_id, "Fluxo não encontrado.")
            raise LookupError(f"Flow {execution['flow_id']} not found")

        steps = self.list_steps(str(flow["id"]))
        lead = self._subject_snapshot(execution)

        result = _engine.advance(flow, steps, execution, lead)

        patch: dict[str, Any] = {"status": result.new_status}
        if result.next_step_ord is not None:
            patch["current_step_ord"] = result.next_step_ord
        if result.next_action_at is not None:
            patch["next_action_at"] = result.next_action_at.isoformat()
        if result.skip_reason:
            ctx = dict(execution.get("context") or {})
            ctx["skipped_steps"] = [
                *(ctx.get("skipped_steps") or []),
                {"ord": execution.get("current_step_ord"), "reason": result.skip_reason},
            ]
            patch["context"] = ctx

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
        updated_exec = upd_rows[0] if upd_rows else {**execution, **patch}

        if result.pending_action:
            try:
                self._t("automation_pending_actions").insert(result.pending_action).execute()
            except Exception:
                logger.exception(
                    "automation.advance_execution: insert pending_action failed execution=%s",
                    execution_id,
                )
                # The step is consumed but its action was not queued: stop the
                # run loudly instead of silently dropping a message.
                self._fail_execution(execution_id, "Falha ao agendar a etapa da automação.")
                raise
            return updated_exec, True

        return updated_exec, updated_exec.get("status") != "running"

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
        """Drain this org's due pending actions (claim -> execute -> advance)."""
        try:
            return run_due_actions(
                self._db,
                self._org_id,
                self._sender,
                advance=self.advance_execution,
                run_action=lambda payload: execute_action(self._db, self._org_id, payload),
            )
        except Exception:
            logger.exception("automation.run_due failed org=%s", self._org_id)
            raise

    def cancel_for_removed_lead(self, lead_id: str) -> dict[str, int]:
        """The lead was soft-deleted: cancel its running executions and skip their pending
        actions, keeping every row (audit) -- the reason lands on ``error_detail``."""
        reason = "Lead removido"
        try:
            running = (
                self._t("automation_executions")
                .select("id")
                .eq("org_id", self._org_id)
                .eq("lead_id", lead_id)
                .eq("status", "running")
                .execute()
            ).data or []
            skipped = 0
            for ex in running:
                self._t("automation_executions").update(
                    {"status": "canceled", "error_detail": reason, "next_action_at": None}
                ).eq("org_id", self._org_id).eq("id", str(ex["id"])).execute()
                pend = (
                    self._t("automation_pending_actions")
                    .update({"status": "skipped", "error_detail": reason})
                    .eq("org_id", self._org_id)
                    .eq("execution_id", str(ex["id"]))
                    .eq("status", "pending")
                    .execute()
                ).data or []
                skipped += len(pend)
        except Exception:
            logger.exception("automation.cancel_for_removed_lead failed lead=%s", lead_id)
            raise
        return {"canceled": len(running), "actions_skipped": skipped}

    def stop_on_reply(self, lead_id: str) -> int:
        """The lead answered on WhatsApp. For its RUNNING executions: cancel those
        whose flow has `stop_on_reply` (default true — the Orbity default), and
        mark the rest `context.lead_replied = true` for branch/condition steps.
        Returns the number canceled."""
        try:
            running = (
                self._t("automation_executions")
                .select("id, flow_id, context")
                .eq("org_id", self._org_id)
                .eq("lead_id", lead_id)
                .eq("status", "running")
                .execute()
            ).data or []
        except Exception:
            logger.exception("automation.stop_on_reply: fetch failed lead=%s", lead_id)
            raise
        canceled = 0
        for ex in running:
            flow = self.get_flow(str(ex["flow_id"]))
            if flow and (flow.get("stop_rules") or {}).get("stop_on_reply", True):
                if self.cancel_execution(str(ex["id"])):
                    canceled += 1
            else:
                ctx = {**(ex.get("context") or {}), "lead_replied": True}
                self._t("automation_executions").update({"context": ctx}).eq(
                    "org_id", self._org_id
                ).eq("id", str(ex["id"])).execute()
        return canceled

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

