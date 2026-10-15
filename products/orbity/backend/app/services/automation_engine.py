"""
AutomationEngine — the pure-logic heart of the Orbity WhatsApp automation
flow executor.

Design:
  - AutomationEngine.advance(flow, steps, execution, lead) → AdvanceResult
    Pure-computation step machine. Given the current execution state + the
    full step list + the lead context, returns the outcome (next_step_ord,
    pending_action to schedule, status transition). No DB calls.

  - WhatsAppSender Protocol seam — the actual WAHA send is behind this
    interface. The app default is `whatsapp_sender.RealWhatsAppSender`
    (real send, or an explicit "WhatsApp não conectado" failure); the Fake
    exists for tests / explicit injection only.

  - run_due_actions(db, org_id, sender, advance=..., run_action=...) —
    drains automation_pending_actions where scheduled_for <= now: CLAIMS each
    row atomically (pending -> processing, compare-and-set), executes it,
    marks it sent / skipped / failed (a failed send is NEVER 'sent'), then
    advances its execution so the flow does not stall after the first step.

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
from typing import Any, Callable, Protocol, runtime_checkable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.services.automation_errors import AutomationUserError

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

    `send` returns None on success and RAISES on failure
    (`whatsapp_sender.WhatsAppNotConnected` / `WhatsAppSendError` carry a
    pt-BR message that is stored on the failed action). The Real is the app
    default; the Fake is injected explicitly by tests.
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
                        "media_url": config.get("media_url") or config.get("media"),
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
                        "subject_type": execution.get("subject_type") or "lead",
                        "subject_id": str(execution.get("subject_id") or lead.get("id") or ""),
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


_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_DEFAULT_TZ = "America/Sao_Paulo"


def _apply_schedule_window(
    dt: datetime,
    window: dict[str, Any],
) -> datetime:
    """Move `dt` to the next instant inside the flow's schedule window.

    Honors the window's `tz` (default America/Sao_Paulo), `days` (mon..sun;
    default every day when absent) and `start`/`end` (HH:MM, local).
    Only `outside_window_behavior == "schedule_next_available"` reschedules;
    any other behaviour (or a malformed window) passes `dt` through unchanged.
    Returns an aware UTC datetime.
    """
    if window.get("outside_window_behavior") != "schedule_next_available":
        return dt

    try:
        start_h, start_m = (int(x) for x in str(window.get("start", "08:00")).split(":"))
        end_h, end_m = (int(x) for x in str(window.get("end", "17:00")).split(":"))
        tz = ZoneInfo(str(window.get("tz") or _DEFAULT_TZ))
    except (ValueError, AttributeError, ZoneInfoNotFoundError):
        logger.warning("automation_engine: malformed schedule_window %r — pass-through", window)
        return dt

    raw_days = window.get("days")
    days = {d for d in raw_days if d in _WEEKDAYS} if isinstance(raw_days, list) else set(_WEEKDAYS)
    if not days:
        days = set(_WEEKDAYS)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local = dt.astimezone(tz)
    start_min = start_h * 60 + start_m
    end_min = end_h * 60 + end_m

    for offset in range(0, 9):
        day = (local + timedelta(days=offset)).date()
        if _WEEKDAYS[day.weekday()] not in days:
            continue
        day_start = datetime(day.year, day.month, day.day, start_h, start_m, tzinfo=tz)
        day_end = datetime(day.year, day.month, day.day, tzinfo=tz) + timedelta(minutes=end_min)
        if offset == 0:
            minutes = local.hour * 60 + local.minute
            if start_min <= minutes < end_min:
                return dt.astimezone(timezone.utc)
            if minutes >= end_min:
                continue
        if day_end > day_start:
            return day_start.astimezone(timezone.utc)
    logger.warning("automation_engine: no open slot found in schedule_window %r — pass-through", window)
    return dt


# ---------------------------------------------------------------------------
# run_due_actions — the drain
# ---------------------------------------------------------------------------

#: A 'processing' claim older than this belongs to a drain that died mid-send.
STALE_CLAIM_MINUTES = 15

_SEND_TYPES = ("send_message", "send_whatsapp_media")


class ActionError(AutomationUserError):
    """An `action` step could not run. The message is pt-BR and is stored as
    the failed action's `error_detail` (shown in the UI)."""


class _Skip(Exception):
    """Internal: the action is intentionally not performed (reason is pt-BR)."""


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _mark_action(db: Any, org_id: str, action_id: str, status: str, detail: str | None = None) -> None:
    patch: dict[str, Any] = {"status": status, "processed_at": _now_iso()}
    if detail:
        patch["error_detail"] = detail
    db.table("automation_pending_actions").update(patch).eq("org_id", org_id).eq(
        "id", action_id
    ).execute()


def _fail_execution(db: Any, org_id: str, execution_id: str, reason: str) -> None:
    try:
        db.table("automation_executions").update(
            {"status": "failed", "error_detail": reason}
        ).eq("org_id", org_id).eq("id", execution_id).execute()
    except Exception:
        logger.exception("run_due_actions: could not fail execution=%s", execution_id)


def claim_action(db: Any, org_id: str, action_id: str) -> bool:
    """Compare-and-set pending -> processing. True only for the ONE caller whose
    UPDATE actually matched the still-'pending' row (concurrent drains lose)."""
    res = (
        db.table("automation_pending_actions")
        .update({"status": "processing", "claimed_at": _now_iso()})
        .eq("org_id", org_id)
        .eq("id", action_id)
        .eq("status", "pending")
        .execute()
    )
    return bool(res.data)


def recover_stale_claims(db: Any, org_id: str) -> int:
    """Fail 'processing' rows whose drain died. NEVER re-sends (at-most-once:
    a duplicate WhatsApp to a client is worse than a flagged failure)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=STALE_CLAIM_MINUTES)).isoformat()
    res = (
        db.table("automation_pending_actions")
        .select("id, execution_id")
        .eq("org_id", org_id)
        .eq("status", "processing")
        .lt("claimed_at", cutoff)
        .limit(200)
        .execute()
    )
    recovered = 0
    for row in res.data or []:
        reason = "Processamento interrompido; a mensagem não foi reenviada para evitar duplicidade."
        claimed = (
            db.table("automation_pending_actions")
            .update({"status": "failed", "error_detail": reason, "processed_at": _now_iso()})
            .eq("org_id", org_id)
            .eq("id", str(row["id"]))
            .eq("status", "processing")
            .execute()
        )
        if claimed.data:
            recovered += 1
            _fail_execution(db, org_id, str(row["execution_id"]), reason)
            logger.warning("run_due_actions: stale claim action=%s failed org=%s", row["id"], org_id)
    return recovered


def _execution_status(db: Any, org_id: str, execution_id: str) -> str | None:
    res = (
        db.table("automation_executions")
        .select("status")
        .eq("org_id", org_id)
        .eq("id", execution_id)
        .execute()
    )
    rows = res.data or []
    return rows[0].get("status") if rows else None


def _perform(
    payload: dict[str, Any],
    org_id: str,
    sender: WhatsAppSender,
    run_action: Callable[[dict[str, Any]], None] | None,
) -> None:
    """Execute one action. Returns on success; raises `_Skip` (not performed,
    flow continues) or any other exception (failure, flow stops)."""
    step_type = payload.get("step_type", "")
    if step_type in _SEND_TYPES:
        phone = str(payload.get("phone") or "")
        message = str(payload.get("message") or "")
        if not phone or not message:
            raise _Skip("Contato sem telefone ou mensagem vazia — envio ignorado.")
        if payload.get("media_url"):
            raise ActionError(
                "Envio de mídia pelo WhatsApp ainda não é suportado nas automações."
            )
        sender.send(phone=phone, message=message, org_id=org_id)
    elif step_type == "wait":
        return
    elif step_type == "action":
        if run_action is None:
            raise ActionError("Execução de ações indisponível neste contexto.")
        run_action(payload)
    else:
        raise _Skip(f"Tipo de etapa desconhecido: {step_type or 'vazio'}.")


def run_due_actions(
    db: Any,
    org_id: str,
    sender: WhatsAppSender | None = None,
    *,
    batch_size: int = 50,
    advance: Callable[[str], Any] | None = None,
    run_action: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, int]:
    """Drain this org's due pending actions.

    For each due row (oldest first): CLAIM it (atomic compare-and-set), skip it
    if its execution was canceled/failed meanwhile, execute it, mark it
    sent / skipped / failed, then `advance(execution_id)` so the flow moves
    on. A send failure marks the action 'failed' with a pt-BR reason and FAILS
    the execution — never 'sent'.

    `sender=None` resolves the app-default REAL sender (an unconnected org
    yields explicit failures); the Fake only exists via explicit injection.
    `advance` / `run_action` are the service's seams (`AutomationService`).
    """
    if sender is None:
        from app.services.whatsapp_sender import make_default_sender
        sender = make_default_sender()

    counts = {"processed": 0, "sent": 0, "skipped": 0, "failed": 0}

    try:
        recover_stale_claims(db, org_id)
        result = (
            db.table("automation_pending_actions")
            .select("*")
            .eq("org_id", org_id)
            .eq("status", "pending")
            .lte("scheduled_for", _now_iso())
            .order("scheduled_for", desc=False)
            .limit(batch_size)
            .execute()
        )
    except Exception:
        logger.exception("run_due_actions: fetch pending failed org=%s", org_id)
        raise

    for row in result.data or []:
        action_id = str(row["id"])
        execution_id = str(row.get("execution_id") or "")
        payload: dict[str, Any] = row.get("payload") or {}

        try:
            if not claim_action(db, org_id, action_id):
                logger.debug("run_due_actions: action=%s claimed elsewhere — skip", action_id)
                continue
        except Exception:
            logger.exception("run_due_actions: claim failed action=%s", action_id)
            counts["failed"] += 1
            continue

        counts["processed"] += 1
        try:
            status = _execution_status(db, org_id, execution_id) if execution_id else None
            if status in ("canceled", "failed"):
                _mark_action(db, org_id, action_id, "skipped", "Execução encerrada antes do envio.")
                counts["skipped"] += 1
                continue

            try:
                _perform(payload, org_id, sender, run_action)
            except _Skip as skip:
                _mark_action(db, org_id, action_id, "skipped", str(skip))
                counts["skipped"] += 1
            else:
                _mark_action(db, org_id, action_id, "sent")
                counts["sent"] += 1
        except Exception as exc:  # noqa: BLE001 — a failed action is recorded, never raised
            reason = _failure_reason(exc)
            logger.warning(
                "run_due_actions: action=%s failed org=%s: %s", action_id, org_id, reason,
                exc_info=not isinstance(exc, AutomationUserError),
            )
            counts["failed"] += 1
            try:
                _mark_action(db, org_id, action_id, "failed", reason)
            except Exception:
                logger.exception("run_due_actions: could not mark action=%s failed", action_id)
            if execution_id:
                _fail_execution(db, org_id, execution_id, reason)
            continue

        if advance is not None and execution_id:
            try:
                advance(execution_id)
            except Exception:
                logger.exception(
                    "run_due_actions: advance failed execution=%s org=%s", execution_id, org_id
                )
                _fail_execution(db, org_id, execution_id, "Falha ao avançar o fluxo de automação.")

    return counts


def _failure_reason(exc: Exception) -> str:
    """pt-BR reason for the failed action: our own typed errors carry one;
    anything unexpected gets a generic message (the traceback is in the log)."""
    if isinstance(exc, AutomationUserError) and str(exc):
        return str(exc)
    return "Falha inesperada ao executar a etapa da automação."


def orgs_with_due_work(db: Any) -> list[str]:
    """Org ids that have a due 'pending' action or a possibly-stale 'processing'
    one — paged (PostgREST caps an unbounded select at 1 000 rows silently)."""
    from noctusai_lib.integrations.persistence.paging import iter_paged_rows

    now = _now_iso()
    stale_cutoff = (datetime.now(timezone.utc) - timedelta(minutes=STALE_CLAIM_MINUTES)).isoformat()
    orgs: dict[str, None] = {}

    def _scan(status: str, col: str, op: str, bound: str):
        def fetch(start: int, end: int):
            q = db.table("automation_pending_actions").select("id, org_id").eq("status", status)
            q = q.lte(col, bound) if op == "lte" else q.lt(col, bound)
            return q.order("id").range(start, end).execute().data

        for r in iter_paged_rows(fetch, label=f"automation due ({status})"):
            orgs[str(r["org_id"])] = None

    _scan("pending", "scheduled_for", "lte", now)
    _scan("processing", "claimed_at", "lt", stale_cutoff)
    return list(orgs)
