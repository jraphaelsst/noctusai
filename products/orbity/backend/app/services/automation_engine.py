"""
AutomationEngine — the pure-logic heart of the Orbity WhatsApp automation
flow executor.

Design:
  - AutomationEngine.advance(flow, steps, execution, lead) → AdvanceResult
    Pure-computation step machine. Given the current execution state + the
    full step list + the lead context, returns the outcome (next_step_ord,
    pending_action to schedule, status transition). No DB calls.

  - WhatsAppSender Protocol seam — the actual WAHA/chatbot send is behind
    this interface. The Fake default is used in tests and when the real
    WAHA integration is not yet attached.
    NOC-REMEDIATE[orbity-automation-live-send] — attach real send here:
      from noctusai_lib.domain.chatbot.delivery import send_reply_parts_sync
      class RealWhatsAppSender:
          def send(self, phone, message, org_id):
              send_reply_parts_sync(phone, message, org_id=org_id)

  - run_due_actions(db, org_id) — process automation_pending_actions where
    scheduled_for <= now(). Calls WhatsAppSender.send for send_message steps.
    NOC-REMEDIATE[orbity-automation-scheduler] — attach a pg_cron trigger or
      Celery beat task that calls this method every minute per org.

Step types handled:
  send_message / send_whatsapp_media → schedule a pending_action (send seam)
  wait                               → schedule a pending_action after delay
  condition                          → evaluate against lead context → branch
  action                             → schedule a pending_action (side-effect)
  branch                             → evaluate → jump to step ord
  end                                → mark execution done

Condition operators (from Orbity FE vocabulary):
  equals, not_equals, contains, not_contains, exists, not_exists,
  greater_than, less_than, is_true, is_false

Variable interpolation:
  Templates support both {{var}} and {var} (double-brace takes precedence).
  Available palette: nome, telefone, email, empresa, responsavel, origem,
    etapa, status, servico_interesse, tag, data_reuniao.
  Unknown keys → empty string (silent, per Orbity spec).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Variable interpolation
# ---------------------------------------------------------------------------

_TEMPLATE_VARIABLE_PALETTE = frozenset({
    "nome", "telefone", "email", "empresa", "responsavel",
    "origem", "etapa", "status", "servico_interesse", "tag", "data_reuniao",
})


def _interpolate_template(template: str, lead: dict[str, Any]) -> str:
    """Resolve {{var}} and {var} placeholders from lead data.

    Strategy (Orbity spec §4):
      1. Replace {{var}} first (double-brace) to avoid double-matching.
      2. Replace remaining {var} (single-brace) with look-ahead/look-behind.
      3. Unknown vars → empty string (silent).

    Lead fields mapped to palette keys:
      name → nome, phone → telefone, email → email, company → empresa,
      source → origem, custom_fields.servico_interesse → servico_interesse
      (additional fields from execution context if present).
    """
    # Build variable map from lead dict
    custom: dict[str, Any] = lead.get("custom_fields") or {}
    ctx: dict[str, str] = {
        "nome": str(lead.get("name") or ""),
        "telefone": str(lead.get("phone") or ""),
        "email": str(lead.get("email") or ""),
        "empresa": str(lead.get("company") or ""),
        "responsavel": str(lead.get("owner_id") or ""),
        "origem": str(lead.get("source") or ""),
        "etapa": str(lead.get("stage_id") or ""),
        "status": str(lead.get("temperature") or ""),
        "servico_interesse": str(custom.get("servico_interesse") or ""),
        "tag": ", ".join(lead.get("tags") or []),
        "data_reuniao": str(custom.get("data_reuniao") or ""),
    }

    def _repl(key: str) -> str:
        return ctx.get(key.lower(), "")

    # Step 1: {{var}} — case-insensitive
    result = re.sub(r"\{\{(\w+)\}\}", lambda m: _repl(m.group(1)), template)
    # Step 2: {var} — only single-brace (not preceded/followed by another brace)
    result = re.sub(
        r"(?<!\{)\{(\w+)\}(?!\})",
        lambda m: _repl(m.group(1)),
        result,
    )
    return result


# ---------------------------------------------------------------------------
# Condition evaluation
# ---------------------------------------------------------------------------

def _get_field_value(field_name: str, lead: dict[str, Any], context: dict[str, Any]) -> Any:
    """Resolve a condition field_name against lead data + execution context.

    Lookup order:
      1. execution context (runtime overrides, e.g. lead_replied)
      2. lead top-level keys
      3. lead.custom_fields
    """
    if field_name in context:
        return context[field_name]
    if field_name in lead:
        return lead[field_name]
    custom = lead.get("custom_fields") or {}
    return custom.get(field_name)


def _evaluate_condition(
    config: dict[str, Any],
    lead: dict[str, Any],
    context: dict[str, Any],
) -> bool:
    """Evaluate a single condition step config against lead + context.

    Operators: equals, not_equals, contains, not_contains,
               exists, not_exists, greater_than, less_than,
               is_true, is_false.

    Returns True if condition passes (on_true branch), False otherwise.
    Missing operator → warning + False (safe default, never silent pass).
    """
    field_name: str = config.get("field", "")
    operator: str = config.get("operator", "")
    expected: Any = config.get("value")

    actual = _get_field_value(field_name, lead, context)

    match operator:
        case "equals":
            return str(actual or "") == str(expected or "")
        case "not_equals":
            return str(actual or "") != str(expected or "")
        case "contains":
            return str(expected or "") in str(actual or "")
        case "not_contains":
            return str(expected or "") not in str(actual or "")
        case "exists":
            return actual is not None and actual != "" and actual != []
        case "not_exists":
            return actual is None or actual == "" or actual == []
        case "greater_than":
            try:
                return float(actual or 0) > float(expected or 0)
            except (TypeError, ValueError):
                return False
        case "less_than":
            try:
                return float(actual or 0) < float(expected or 0)
            except (TypeError, ValueError):
                return False
        case "is_true":
            return bool(actual)
        case "is_false":
            return not bool(actual)
        case _:
            logger.warning(
                "automation_engine: unknown condition operator=%r field=%r — defaulting to False",
                operator, field_name,
            )
            return False


# ---------------------------------------------------------------------------
# AdvanceResult — the pure output of advance()
# ---------------------------------------------------------------------------

@dataclass
class AdvanceResult:
    """Immutable result of one AutomationEngine.advance() call.

    Fields:
      next_step_ord:     ord to advance current_step_ord to (None if done/failed)
      new_status:        execution status after this advance
      pending_action:    dict to insert into automation_pending_actions (or None)
      next_action_at:    when the engine should next poll this execution
      skip_reason:       if pending_action is None and flow continues, why
    """
    next_step_ord: int | None = None
    new_status: str = "running"
    pending_action: dict[str, Any] | None = None
    next_action_at: datetime | None = None
    skip_reason: str | None = None


# ---------------------------------------------------------------------------
# WhatsAppSender Protocol seam
# ---------------------------------------------------------------------------

@runtime_checkable
class WhatsAppSender(Protocol):
    """Protocol for the actual WhatsApp send seam.

    The Fake is used by default (tests + pre-live-send state).
    The Real attaches via dependency injection in the service layer.

    NOC-REMEDIATE[orbity-automation-live-send] — real implementation:
        from noctusai_lib.domain.chatbot.delivery import send_reply_parts_sync
        class RealWhatsAppSender:
            def send(self, phone: str, message: str, org_id: str) -> None:
                send_reply_parts_sync(phone, message, org_id=org_id)
    """

    def send(self, phone: str, message: str, org_id: str) -> None:
        ...


class FakeWhatsAppSender:
    """Test-only / pre-integration WhatsApp sender.

    Records calls; never touches WAHA or the network.
    """

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    def send(self, phone: str, message: str, org_id: str) -> None:
        logger.debug(
            "FakeWhatsAppSender.send org=%s phone=%s msg_len=%d",
            org_id, phone, len(message),
        )
        self.sent.append({"phone": phone, "message": message, "org_id": org_id})


# ---------------------------------------------------------------------------
# AutomationEngine — the pure advance() state machine
# ---------------------------------------------------------------------------

class AutomationEngine:
    """Flow execution state machine.

    advance() is a pure-logic method:
      - Takes the flow, its ordered steps, the current execution row, and
        the lead snapshot.
      - Returns an AdvanceResult describing what to do next.
      - Makes NO DB calls; the caller (AutomationService.advance_execution)
        applies the result to the DB.

    Step handling:
      send_message / send_whatsapp_media → build pending_action (actual send
        happens in run_due_actions via the WhatsAppSender seam)
      wait          → build pending_action scheduled for now + duration_minutes
      condition     → evaluate inline → jump to on_true or on_false ord
      branch        → jump to on_true_step_ord or on_false_step_ord
      action        → build pending_action (side-effect; scheduler executes)
      end           → status = 'done'

    End-of-flow: if next_step_ord >= len(steps), status → 'done'.
    """

    def advance(
        self,
        flow: dict[str, Any],
        steps: list[dict[str, Any]],
        execution: dict[str, Any],
        lead: dict[str, Any],
    ) -> AdvanceResult:
        """Advance one step in the execution state machine.

        Args:
            flow:      automation_flows row
            steps:     automation_steps rows for this flow, sorted by ord ASC
            execution: automation_executions row (current state)
            lead:      orbity.leads row (snapshot)

        Returns:
            AdvanceResult — caller writes to DB.
        """
        if not steps:
            logger.warning(
                "automation_engine.advance: flow=%s has no steps — marking done",
                flow.get("id"),
            )
            return AdvanceResult(new_status="done")

        # Build step lookup by ord
        steps_by_ord: dict[int, dict[str, Any]] = {s["ord"]: s for s in steps}
        current_ord: int = execution.get("current_step_ord", 0)
        context: dict[str, Any] = execution.get("context") or {}
        org_id: str = str(execution.get("org_id") or flow.get("org_id") or "")
        execution_id: str = str(execution.get("id") or "")

        step = steps_by_ord.get(current_ord)
        if step is None:
            # ord gap or flow is already past its last step
            logger.info(
                "automation_engine.advance: execution=%s ord=%d has no matching step — done",
                execution_id, current_ord,
            )
            return AdvanceResult(new_status="done")

        step_id: str = str(step["id"])
        step_type: str = step.get("step_type", "end")
        config: dict[str, Any] = step.get("config") or {}
        now = datetime.now(timezone.utc)

        match step_type:

            # ------------------------------------------------------------------
            # end — terminal step
            # ------------------------------------------------------------------
            case "end":
                return AdvanceResult(new_status="done")

            # ------------------------------------------------------------------
            # send_message / send_whatsapp_media — enqueue a pending send
            # ------------------------------------------------------------------
            case "send_message" | "send_whatsapp_media":
                template: str = config.get("template", "")
                rendered = _interpolate_template(template, lead)
                phone: str = str(lead.get("phone") or "")
                if not phone:
                    logger.warning(
                        "automation_engine.advance: execution=%s send step=%s — lead has no phone; skipping",
                        execution_id, step_id,
                    )
                    next_ord = _next_ord(current_ord, steps_by_ord)
                    return AdvanceResult(
                        next_step_ord=next_ord,
                        new_status="running" if next_ord is not None else "done",
                        skip_reason="no_phone",
                    )

                scheduled_for = _apply_schedule_window(now, flow.get("schedule_window") or {})
                pending = {
                    "org_id": org_id,
                    "execution_id": execution_id,
                    "step_id": step_id,
                    "scheduled_for": scheduled_for.isoformat(),
                    "status": "pending",
                    "payload": {
                        "step_type": step_type,
                        "phone": phone,
                        "message": rendered,
                        "lead_id": str(lead.get("id") or ""),
                    },
                }
                next_ord = _next_ord(current_ord, steps_by_ord)
                return AdvanceResult(
                    next_step_ord=next_ord,
                    new_status="running" if next_ord is not None else "done",
                    pending_action=pending,
                    next_action_at=scheduled_for,
                )

            # ------------------------------------------------------------------
            # wait — schedule a pending_action after duration_minutes
            # ------------------------------------------------------------------
            case "wait":
                duration_min: float = float(config.get("duration_minutes", 0))
                wake_at = now + timedelta(minutes=duration_min)
                wake_at = _apply_schedule_window(wake_at, flow.get("schedule_window") or {})
                next_ord = _next_ord(current_ord, steps_by_ord)
                pending = {
                    "org_id": org_id,
                    "execution_id": execution_id,
                    "step_id": step_id,
                    "scheduled_for": wake_at.isoformat(),
                    "status": "pending",
                    "payload": {
                        "step_type": "wait",
                        "duration_minutes": duration_min,
                        "wake_at": wake_at.isoformat(),
                        "next_step_ord": next_ord,
                    },
                }
                return AdvanceResult(
                    next_step_ord=next_ord,
                    new_status="running" if next_ord is not None else "done",
                    pending_action=pending,
                    next_action_at=wake_at,
                )

            # ------------------------------------------------------------------
            # condition — inline evaluation → jump
            # ------------------------------------------------------------------
            case "condition":
                passes = _evaluate_condition(config, lead, context)
                if passes:
                    on_true = config.get("on_true", "next")
                    if on_true == "stop":
                        return AdvanceResult(new_status="canceled")
                    # "next" → fall through to next ord
                    next_ord = _next_ord(current_ord, steps_by_ord)
                else:
                    on_false = config.get("on_false", "stop")
                    if on_false == "stop":
                        return AdvanceResult(new_status="canceled")
                    # jump to a specific ord if on_false is numeric
                    try:
                        next_ord = int(on_false)
                        if next_ord not in steps_by_ord:
                            logger.warning(
                                "automation_engine.advance: condition on_false=%d not in steps — done",
                                next_ord,
                            )
                            return AdvanceResult(new_status="done")
                    except (ValueError, TypeError):
                        next_ord = _next_ord(current_ord, steps_by_ord)

                return AdvanceResult(
                    next_step_ord=next_ord,
                    new_status="running" if next_ord is not None else "done",
                )

            # ------------------------------------------------------------------
            # branch — evaluate → jump to explicit step ords
            # ------------------------------------------------------------------
            case "branch":
                passes = _evaluate_condition(config, lead, context)
                if passes:
                    next_ord = config.get("on_true_step_ord")
                else:
                    next_ord = config.get("on_false_step_ord")

                if next_ord is None or next_ord not in steps_by_ord:
                    logger.warning(
                        "automation_engine.advance: branch step=%s has no valid target ord=%s — done",
                        step_id, next_ord,
                    )
                    return AdvanceResult(new_status="done")

                return AdvanceResult(
                    next_step_ord=int(next_ord),
                    new_status="running",
                )

            # ------------------------------------------------------------------
            # action — side-effect step (create_task, add_tag, etc.)
            # ------------------------------------------------------------------
            case "action":
                action_type: str = config.get("action_type", "")
                scheduled_for = now  # actions execute immediately
                pending = {
                    "org_id": org_id,
                    "execution_id": execution_id,
                    "step_id": step_id,
                    "scheduled_for": scheduled_for.isoformat(),
                    "status": "pending",
                    "payload": {
                        "step_type": "action",
                        "action_type": action_type,
                        "config": config,
                        "lead_id": str(lead.get("id") or ""),
                    },
                }
                next_ord = _next_ord(current_ord, steps_by_ord)
                return AdvanceResult(
                    next_step_ord=next_ord,
                    new_status="running" if next_ord is not None else "done",
                    pending_action=pending,
                    next_action_at=scheduled_for,
                )

            case _:
                logger.warning(
                    "automation_engine.advance: unknown step_type=%r step=%s — skipping",
                    step_type, step_id,
                )
                next_ord = _next_ord(current_ord, steps_by_ord)
                return AdvanceResult(
                    next_step_ord=next_ord,
                    new_status="running" if next_ord is not None else "done",
                    skip_reason=f"unknown_step_type:{step_type}",
                )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _next_ord(current_ord: int, steps_by_ord: dict[int, Any]) -> int | None:
    """Return the next sequential step ord, or None if this is the last."""
    sorted_ords = sorted(steps_by_ord.keys())
    try:
        idx = sorted_ords.index(current_ord)
        if idx + 1 < len(sorted_ords):
            return sorted_ords[idx + 1]
    except ValueError:
        pass
    return None


def _apply_schedule_window(
    dt: datetime,
    window: dict[str, Any],
) -> datetime:
    """Adjust dt to respect the flow schedule window.

    If outside_window_behavior is 'schedule_next_available' and the
    proposed datetime is outside the allowed hours, push it to the next
    available window start.

    This implementation handles the hour boundary; timezone awareness is
    a NOC-REMEDIATE[orbity-automation-tz] concern — the real implementation
    should use pytz/zoneinfo to translate America/Sao_Paulo offsets.

    Current simplified behaviour (safe default):
      - If no window config or behavior != 'schedule_next_available': pass-through.
      - Otherwise: if hour < start_hour or hour >= end_hour → push to next day
        at start_hour (UTC approximation, +0).
    """
    behavior = window.get("outside_window_behavior")
    if behavior != "schedule_next_available":
        return dt

    start_str: str = window.get("start", "08:00")
    end_str: str = window.get("end", "17:00")
    try:
        start_h, start_m = (int(x) for x in start_str.split(":"))
        end_h, end_m = (int(x) for x in end_str.split(":"))
    except (ValueError, AttributeError):
        return dt

    # Ensure timezone-aware
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    h = dt.hour
    m = dt.minute
    in_window = (h * 60 + m) >= (start_h * 60 + start_m) and (h * 60 + m) < (end_h * 60 + end_m)

    if in_window:
        return dt

    # Outside window: push to next window start
    next_start = dt.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    if next_start <= dt:
        next_start = next_start + timedelta(days=1)
    return next_start


# ---------------------------------------------------------------------------
# run_due_actions — processes automation_pending_actions where scheduled_for <= now
# ---------------------------------------------------------------------------

def run_due_actions(
    db: Any,
    org_id: str,
    sender: WhatsAppSender | None = None,
    *,
    batch_size: int = 50,
) -> dict[str, int]:
    """Process pending automation actions that are due.

    Queries automation_pending_actions WHERE:
      org_id = org_id AND status = 'pending' AND scheduled_for <= now()

    For each:
      - send_message / send_whatsapp_media → call sender.send() (seam)
      - wait → mark sent (the wait is over; engine advances on next tick)
      - action → mark sent (actual side-effect NOC-REMEDIATE[orbity-automation-action-exec])

    Marks each row as 'sent' or 'failed'. Returns counts.

    NOC-REMEDIATE[orbity-automation-scheduler] — call this from pg_cron or
      a Celery beat task every minute, per-org or globally.
    """
    if sender is None:
        sender = FakeWhatsAppSender()

    now_iso = datetime.now(timezone.utc).isoformat()
    counts = {"processed": 0, "sent": 0, "skipped": 0, "failed": 0}

    try:
        result = (
            db.table("automation_pending_actions")
            .select("*")
            .eq("org_id", org_id)
            .eq("status", "pending")
            .lte("scheduled_for", now_iso)
            .limit(batch_size)
            .execute()
        )
    except Exception:
        logger.exception("run_due_actions: fetch pending failed org=%s", org_id)
        raise

    rows: list[dict[str, Any]] = result.data or []
    if not rows:
        return counts

    for row in rows:
        action_id: str = str(row["id"])
        payload: dict[str, Any] = row.get("payload") or {}
        step_type: str = payload.get("step_type", "")
        counts["processed"] += 1

        try:
            if step_type in ("send_message", "send_whatsapp_media"):
                phone: str = payload.get("phone", "")
                message: str = payload.get("message", "")
                if phone and message:
                    sender.send(phone=phone, message=message, org_id=org_id)
                    counts["sent"] += 1
                else:
                    logger.warning(
                        "run_due_actions: action=%s missing phone or message — skipping",
                        action_id,
                    )
                    counts["skipped"] += 1

            elif step_type == "wait":
                # Wait is over; mark sent so engine can advance
                counts["sent"] += 1

            elif step_type == "action":
                # NOC-REMEDIATE[orbity-automation-action-exec] — execute CRM
                # side-effects: create_task, move_lead, add_tag, etc.
                action_type = payload.get("action_type", "")
                logger.info(
                    "run_due_actions: action=%s action_type=%r — side-effects pending remediation",
                    action_id, action_type,
                )
                counts["sent"] += 1  # acknowledged; actual effect is NOC-REMEDIATE

            else:
                logger.warning(
                    "run_due_actions: action=%s unknown step_type=%r — skipping",
                    action_id, step_type,
                )
                counts["skipped"] += 1

            # Mark as sent
            db.table("automation_pending_actions").update({
                "status": "sent",
                "processed_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", action_id).execute()

        except Exception:
            logger.exception(
                "run_due_actions: action=%s failed — marking failed", action_id
            )
            counts["failed"] += 1
            try:
                db.table("automation_pending_actions").update({
                    "status": "failed",
                    "error_detail": "exception during processing",
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                }).eq("id", action_id).execute()
            except Exception:
                logger.exception(
                    "run_due_actions: could not mark action=%s as failed", action_id
                )

    return counts
