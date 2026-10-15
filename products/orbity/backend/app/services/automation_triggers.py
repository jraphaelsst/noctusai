"""
Automation trigger emitters — the "an event happened" half of the engine.

`disparar(...)` is called by routers AFTER a successful write. It finds the
org's ACTIVE flows for that trigger type (matching their `trigger_config`),
and starts one execution per flow, idempotently: the execution carries a
per-occurrence `trigger_key`, UNIQUE per flow, so a retried/duplicated event
never starts the same flow twice.

It NEVER raises into the caller — the user's write already succeeded; an
automation problem must not turn it into a 5xx. Failures are logged and
recorded as a `failed` execution (visible in Automação → Execuções).

LIVE trigger types (what routers actually emit — the FE enables exactly these)
-----------------------------------------------------------------------------
  lead_created            crm create lead + public capture
  pipeline_stage_entered  lead moved/updated into a stage      config: {stage_id?}
  lead_status_changed     lead entered a FINAL stage            config: {status?: "won"|"lost"}
  task_created            task created                          (subject: task)
  task_completed          task status -> done                   (subject: task)
  client_created          client created                        (subject: client)
  meeting_created         agenda event with event_type=meeting  (subject: meeting)
  whatsapp_message_received  inbound WhatsApp from a KNOWN lead
  keyword_received        inbound text containing config.keyword (case-insensitive)
  manual                  POST /api/automation/flows/{id}/trigger

NOT live (no emitter yet; creating such a flow works but never fires):
  lead_idle, tag_added, owner_changed, proposal_sent.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import anyio

from app.services.automation_service import AutomationService

logger = logging.getLogger(__name__)

LIVE_TRIGGERS: frozenset[str] = frozenset({
    "lead_created",
    "pipeline_stage_entered",
    "lead_status_changed",
    "task_created",
    "task_completed",
    "client_created",
    "meeting_created",
    "whatsapp_message_received",
    "keyword_received",
    "manual",
})


def _matches(trigger_type: str, config: dict[str, Any], payload: dict[str, Any]) -> bool:
    """Does this flow's `trigger_config` accept the event `payload`?"""
    if trigger_type == "pipeline_stage_entered":
        want = config.get("stage_id")
        return not want or str(want) == str(payload.get("stage_id") or "")
    if trigger_type == "lead_status_changed":
        want = config.get("status")
        return not want or str(want) == str(payload.get("status") or "")
    if trigger_type == "keyword_received":
        keyword = str(config.get("keyword") or "").strip().lower()
        if not keyword:
            return False  # a keyword flow with no keyword must not fire on everything
        return keyword in str(payload.get("text") or "").lower()
    return True


def disparar(
    trigger_type: str,
    org_id: UUID | str,
    *,
    lead_id: str | UUID | None = None,
    subject_type: str | None = None,
    subject_id: str | UUID | None = None,
    payload: dict[str, Any] | None = None,
    trigger_key: str | None = None,
    db: Any = None,
) -> list[dict[str, Any]]:
    """Start every matching active flow for this event. Never raises.

    Args:
        trigger_type: one of LIVE_TRIGGERS.
        lead_id: the lead (subject_type defaults to 'lead').
        subject_type / subject_id: for non-lead subjects ('client'|'task'|'meeting').
        payload: event data used for `trigger_config` matching (stage_id, text, ...).
        trigger_key: the per-OCCURRENCE key (idempotency). Defaults to
            `<trigger_type>:<subject>`, which suits once-per-subject events
            (created); events that can recur for one subject (stage entered,
            completed, inbound message) MUST pass a key carrying the occurrence.
        db: service-role client (default: the app admin client). Tests inject a mock.

    Returns the executions started (created now), possibly empty.
    """
    started: list[dict[str, Any]] = []
    try:
        if trigger_type not in LIVE_TRIGGERS:
            logger.warning("automation.disparar: trigger %r has no emitter contract", trigger_type)
            return started
        subject_type = subject_type or ("lead" if lead_id else None)
        subject = str(subject_id or lead_id or "")
        if not subject_type or not subject:
            logger.warning("automation.disparar: %s without a subject — ignored", trigger_type)
            return started
        if db is None:
            from app.dependencies import get_admin_client
            db = get_admin_client()

        svc = AutomationService(db, org_id=UUID(str(org_id)))
        flows = (
            db.table("automation_flows")
            .select("*")
            .eq("org_id", str(org_id))
            .eq("trigger_type", trigger_type)
            .eq("active", True)
            .execute()
        ).data or []
        key = trigger_key or f"{trigger_type}:{subject}"
        event = payload or {}

        for flow in flows:
            if not _matches(trigger_type, flow.get("trigger_config") or {}, event):
                continue
            try:
                execution, created = svc.start_execution_once(
                    str(flow["id"]),
                    str(lead_id) if lead_id else None,
                    subject_type=subject_type,
                    subject_id=None if subject_type == "lead" else subject,
                    trigger_key=key,
                    context={"trigger": trigger_type, **{k: v for k, v in event.items() if k != "text"}},
                )
                if created:
                    started.append(execution)
            except Exception as exc:  # noqa: BLE001 — never into the caller; recorded below
                logger.exception(
                    "automation.disparar: flow=%s trigger=%s org=%s failed", flow.get("id"), trigger_type, org_id
                )
                _record_failure(db, str(org_id), flow, subject_type, subject, lead_id, key, exc)
    except Exception:  # noqa: BLE001 — the user's write already succeeded
        logger.exception("automation.disparar: %s org=%s failed", trigger_type, org_id)
    return started


def _record_failure(
    db: Any,
    org_id: str,
    flow: dict[str, Any],
    subject_type: str,
    subject: str,
    lead_id: Any,
    key: str,
    exc: Exception,
) -> None:
    """Persist a `failed` execution so the problem shows up in the UI. Best-effort."""
    try:
        already = (
            db.table("automation_executions").select("id")
            .eq("org_id", org_id).eq("flow_id", str(flow["id"])).eq("trigger_key", key)
            .execute()
        ).data
        if already:  # the failed start left its own (already failed) row
            return
        db.table("automation_executions").insert({
            "org_id": org_id,
            "flow_id": str(flow["id"]),
            "lead_id": str(lead_id) if lead_id else None,
            "subject_type": subject_type,
            "subject_id": None if subject_type == "lead" else subject,
            "status": "failed",
            "trigger_key": key,
            "started_at": datetime.now(timezone.utc).isoformat(),
            "error_detail": "Falha ao iniciar a automação. Tente novamente ou contate o suporte.",
        }).execute()
    except Exception:  # noqa: BLE001 — duplicate key (already recorded) or DB down
        logger.warning("automation.disparar: could not record failed execution flow=%s", flow.get("id"))


async def adisparar(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """`disparar` off the event loop (its DB work is sync). Never raises."""
    return await anyio.to_thread.run_sync(lambda: disparar(*args, **kwargs))
