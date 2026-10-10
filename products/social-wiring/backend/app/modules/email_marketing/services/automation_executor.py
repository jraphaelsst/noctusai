"""Automation step executor (P1b(b)) -- one step per seed-``Worker`` job.

The 5-minute scheduler scan only ENQUEUES: one ``email_marketing.automation_step`` job per due
enrollment, idempotent on ``enrollment_id:step_id`` (the job repo's ``dedupe_key``). The handler
executes the enrollment's CURRENT step and moves it forward:

=================  ==========================================================================
``send_email``     queues ONE ``send_logs`` row; the ordinary ``SendService`` pipeline sends it,
                   so dry-run / unsubscribe / link guards all apply. Advances immediately.
                   A contact awaiting double opt-in (``email_optin='pending'``) is skipped
                   (``email_optin.receives_marketing_email``): no row, the flow continues.
``wait``           ``next_action_at = now + delay``; ``current_step_id`` = next step; the job
                   ENDS (no ``RescheduleLater``: the scan re-enqueues once due, and the next
                   step has a different dedupe key, so nothing is held in the queue).
``condition``      jumps to the step whose ``posicao`` is ``then_posicao`` / ``else_posicao``.
                   Forward jumps only (a backward one is malformed): that is what keeps
                   ``enrollment_id:step_id`` a sound idempotency key and rules out loops.
``add_tag`` /      updates ``contacts.tags``; next step.
``remove_tag``
``move_to_list``   upserts ``contact_list_members``; next step.
``webhook``        NOT supported: enrollment ``paused`` + dead letter with the reason.
=================  ==========================================================================

Exits: contact no longer ``active`` -> enrollment ``exited``; past the last step ->
``completed`` + ``completed_at``. A malformed config pauses the enrollment and dead-letters the
job with the reason (enrollments carry no reason column: the dead letter IS the record).
Every query is scoped to the org of the (``ativa``) automation.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from noctusai_lib.domain.jobs import DeadLetterError, Job, JobRepository

from .email_optin import receives_marketing_email

logger = logging.getLogger(__name__)

JOB_TYPE = "email_marketing.automation_step"
SCAN_LIMIT = 50

_POSITIVE_OPS = {"eq", "is", "has", "contains"}
_NEGATIVE_OPS = {"ne", "not", "not_has"}
_CONDITION_FIELDS = ("tag", "status", "opened_campaign")
_OPENED = ("opened", "clicked")


def dedupe_key(enrollment_id: str, step_id: Optional[str]) -> str:
    return f"{enrollment_id}:{step_id}"


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------- enqueue (scheduler side)


def scan_due_enrollments(db: Any, now: Optional[datetime] = None) -> list[dict]:
    """Active enrollments of ACTIVE (``ativa``) automations whose step is due, each carrying the
    automation's ``org_id``. A never-scheduled enrollment (``next_action_at`` NULL, as
    ``enroll_contacts`` creates it) is due immediately."""
    now_iso = (now or _now()).isoformat()
    due = (
        db.table("automation_enrollments").select("*")
        .eq("status", "active").lte("next_action_at", now_iso).limit(SCAN_LIMIT).execute().data or []
    )
    fresh = (
        db.table("automation_enrollments").select("*")
        .eq("status", "active").is_("next_action_at", "null").limit(SCAN_LIMIT).execute().data or []
    )
    enrollments = (due + fresh)[:SCAN_LIMIT]
    if not enrollments:
        return []
    automation_ids = sorted({e["automation_id"] for e in enrollments})
    automations = (
        db.table("automations").select("id, org_id, status").in_("id", automation_ids).execute().data or []
    )
    org_by_automation = {a["id"]: a["org_id"] for a in automations if a.get("status") == "ativa"}
    return [
        {**e, "org_id": org_by_automation[e["automation_id"]]}
        for e in enrollments
        if e["automation_id"] in org_by_automation
    ]


async def enqueue_enrollment(repo: JobRepository, enrollment: dict) -> Job:
    """One job per ``enrollment_id:step_id``; enqueueing the same pair twice returns the first."""
    step_id = enrollment.get("current_step_id")
    return await repo.enqueue(
        type=JOB_TYPE,
        payload={"enrollment_id": enrollment["id"], "step_id": step_id, "org_id": enrollment["org_id"]},
        dedupe_key=dedupe_key(enrollment["id"], step_id),
    )


async def enqueue_due(db: Any, repo: JobRepository) -> int:
    """Scan (off the event loop) and enqueue; returns the number of due enrollments seen."""
    due = await asyncio.to_thread(scan_due_enrollments, db)
    for enrollment in due:
        await enqueue_enrollment(repo, enrollment)
    return len(due)


# ---------------------------------------------------------------- execution (worker side)


def _rows(db: Any, table: str, **eq: Any) -> list[dict]:
    q = db.table(table).select("*")
    for col, val in eq.items():
        q = q.eq(col, val)
    return q.execute().data or []


def _update_enrollment(db: Any, enrollment_id: str, **changes: Any) -> None:
    db.table("automation_enrollments").update(changes).eq("id", enrollment_id).execute()


def _pause(db: Any, enrollment_id: str, reason: str) -> DeadLetterError:
    """Pause the enrollment and return the dead-letter error carrying ``reason`` (to be raised)."""
    # The reason is RECORDED on the enrollment (shown in Automações), never only
    # in the dead letter an operator never sees (migration 243).
    _update_enrollment(db, enrollment_id, status="paused", pause_reason=reason[:500],
                       paused_at=_now().isoformat())
    logger.warning("email_marketing automation: enrollment %s paused -- %s", enrollment_id, reason)
    return DeadLetterError(reason)


def _delay(config: dict) -> timedelta:
    for unit in ("hours", "days"):
        value = config.get(unit)
        if value is None:
            continue
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise ValueError(f"wait.{unit} must be a positive number, got {value!r}")
        return timedelta(**{unit: value})
    raise ValueError("wait needs config.hours or config.days")


def _required(config: dict, key: str, step_tipo: str) -> str:
    value = config.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{step_tipo} needs config.{key}")
    return value.strip()


def _evaluate(db: Any, org_id: str, contact: dict, config: dict) -> bool:
    field = config.get("field")
    op = config.get("op", "eq")
    if field not in _CONDITION_FIELDS:
        raise ValueError(f"condition.field must be one of {_CONDITION_FIELDS}, got {field!r}")
    if op not in _POSITIVE_OPS | _NEGATIVE_OPS:
        raise ValueError(f"condition.op {op!r} is not supported")
    value = config.get("value")
    if not isinstance(value, str) or not value:
        raise ValueError("condition needs config.value")
    if field == "tag":
        hit = value in (contact.get("tags") or [])
    elif field == "status":
        hit = contact.get("status") == value
    else:
        logs = (
            db.table("send_logs").select("id, status")
            .eq("org_id", org_id).eq("contact_id", contact["id"]).eq("campaign_id", value)
            .execute().data or []
        )
        hit = any(log.get("status") in _OPENED for log in logs)
    return hit if op in _POSITIVE_OPS else not hit


def _jump_target(steps: list[dict], current: dict, config: dict, taken: bool) -> dict:
    """The branch's step. BOTH branches are validated, so a bad ``else_posicao`` is caught on the
    run that happens to take ``then`` instead of lying dormant."""
    targets = {}
    for key in ("then_posicao", "else_posicao"):
        posicao = config.get(key)
        if isinstance(posicao, bool) or not isinstance(posicao, int):
            raise ValueError(f"condition needs an integer config.{key}")
        if posicao <= current["posicao"]:
            raise ValueError(f"condition.{key}={posicao} is not after this step (posicao {current['posicao']})")
        target = next((s for s in steps if s["posicao"] == posicao), None)
        if target is None:
            raise ValueError(f"condition.{key}={posicao} matches no step of this automation")
        targets[key] = target
    return targets["then_posicao" if taken else "else_posicao"]


def _queue_send(db: Any, org_id: str, automation_id: str, step: dict, contact: dict) -> None:
    template_id = _required(step.get("config") or {}, "template_id", "send_email")
    template = _rows(db, "templates", id=template_id, org_id=org_id)
    if not template:
        raise ValueError(f"send_email template {template_id} does not exist in this org")
    if not receives_marketing_email(contact):
        # Double opt-in send gate (P1b(d)): a contact awaiting confirmation gets
        # no marketing email; the step is skipped (no send_logs row), not retried.
        logger.info("automation %s step %s: contact %s not sendable (email_optin=%s) — send skipped",
                    automation_id, step["id"], contact["id"], contact.get("email_optin"))
        return
    already = _rows(db, "send_logs", org_id=org_id, contact_id=contact["id"], automation_step_id=step["id"])
    if already:  # a retry after a crash between queueing and advancing must not mail twice
        return
    db.table("send_logs").insert({
        "org_id": org_id,
        "contact_id": contact["id"],
        "email": contact["email"],
        "automation_id": automation_id,
        "automation_step_id": step["id"],
        "status": "queued",
    }).execute()


def _apply_side_effect(db: Any, org_id: str, automation_id: str, step: dict, contact: dict) -> None:
    config = step.get("config") or {}
    tipo = step["tipo"]
    if tipo == "send_email":
        _queue_send(db, org_id, automation_id, step, contact)
    elif tipo in ("add_tag", "remove_tag"):
        tag = _required(config, "tag", tipo)
        tags = list(contact.get("tags") or [])
        if tipo == "add_tag" and tag not in tags:
            tags.append(tag)
        elif tipo == "remove_tag":
            tags = [t for t in tags if t != tag]
        db.table("contacts").update({"tags": tags}).eq("id", contact["id"]).eq("org_id", org_id).execute()
    elif tipo == "move_to_list":
        list_id = _required(config, "list_id", tipo)
        if not _rows(db, "contact_lists", id=list_id, org_id=org_id):
            raise ValueError(f"move_to_list list {list_id} does not exist in this org")
        db.table("contact_list_members").upsert(
            {"list_id": list_id, "contact_id": contact["id"]}, on_conflict="list_id,contact_id"
        ).execute()


def run_step(db: Any, *, enrollment_id: str, step_id: Optional[str], org_id: str) -> Optional[dict]:
    """Execute the enrollment's current step. Returns the payload of the next job to enqueue
    immediately (``None`` when the enrollment waits, finished, exited, paused or the job is stale).
    Raises ``DeadLetterError`` (after pausing the enrollment) on unsupported / malformed steps."""
    enrollment = next(iter(_rows(db, "automation_enrollments", id=enrollment_id)), None)
    if enrollment is None or enrollment.get("status") != "active":
        return None
    if enrollment.get("current_step_id") != step_id:
        return None  # stale job: the enrollment already moved on
    automation = next(iter(_rows(db, "automations", id=enrollment["automation_id"], org_id=org_id)), None)
    if automation is None or automation.get("status") != "ativa":
        return None
    contact = next(iter(_rows(db, "contacts", id=enrollment["contact_id"], org_id=org_id)), None)
    if contact is None or contact.get("status") != "active":
        _update_enrollment(db, enrollment_id, status="exited", next_action_at=None)
        return None

    steps = sorted(_rows(db, "automation_steps", automation_id=automation["id"]), key=lambda s: s["posicao"])
    current = next((s for s in steps if s["id"] == step_id), None)
    if current is None:
        if step_id is None:  # an automation with no steps at enrollment time
            _update_enrollment(db, enrollment_id, status="completed", completed_at=_now().isoformat())
            return None
        raise _pause(db, enrollment_id, f"step {step_id} no longer exists in automation {automation['id']}")

    tipo = current["tipo"]
    config = current.get("config") or {}
    if tipo == "webhook":
        raise _pause(db, enrollment_id, "webhook steps are not supported: enrollment paused")
    try:
        if tipo == "wait":
            delay = _delay(config)
            target = next((s for s in steps if s["posicao"] > current["posicao"]), None)
        elif tipo == "condition":
            target = _jump_target(steps, current, config, _evaluate(db, org_id, contact, config))
        else:
            _apply_side_effect(db, org_id, automation["id"], current, contact)
            target = next((s for s in steps if s["posicao"] > current["posicao"]), None)
    except ValueError as exc:
        raise _pause(db, enrollment_id, f"malformed {tipo} step {current['id']}: {exc}") from exc

    now = _now()
    if target is None:
        _update_enrollment(db, enrollment_id, status="completed", completed_at=now.isoformat(),
                           next_action_at=None)
        return None
    if tipo == "wait":
        _update_enrollment(db, enrollment_id, current_step_id=target["id"],
                           next_action_at=(now + delay).isoformat())
        return None
    _update_enrollment(db, enrollment_id, current_step_id=target["id"], next_action_at=now.isoformat())
    return {"enrollment_id": enrollment_id, "step_id": target["id"], "org_id": org_id}


def build_handler(db: Any, repo: JobRepository):
    """The ``email_marketing.automation_step`` handler. The next immediate step is enqueued here;
    if that enqueue fails the enrollment is already due, so the scan picks it up."""

    async def handle(job: Job) -> None:
        payload = job.payload or {}
        try:
            enrollment_id, org_id = payload["enrollment_id"], payload["org_id"]
        except KeyError as exc:
            raise DeadLetterError(f"automation_step job without {exc.args[0]}") from exc
        nxt = await asyncio.to_thread(
            run_step, db, enrollment_id=enrollment_id, step_id=payload.get("step_id"), org_id=org_id
        )
        if nxt is not None:
            await repo.enqueue(type=JOB_TYPE, payload=nxt, dedupe_key=dedupe_key(nxt["enrollment_id"], nxt["step_id"]))

    return handle


__all__ = [
    "JOB_TYPE", "build_handler", "dedupe_key", "enqueue_due", "enqueue_enrollment",
    "run_step", "scan_due_enrollments",
]
