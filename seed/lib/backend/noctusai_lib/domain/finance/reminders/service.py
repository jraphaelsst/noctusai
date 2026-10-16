"""Billing reminders (dunning): rules, selection, dedup-first sending, preview.

Flow per org and day (`run_reminders_for_org`):

1. org settings gate (no row / `enabled=false` => nothing, by design: opt-in);
2. **select** open/partial RECEIVABLES whose `due_date + rule.offset_days == today` in the org timezone, for every
   enabled rule; skip opted-out receivables and anything the host's `skip_reason` hook blocks (a preserved /
   cancelled client...), resolve the contact (`resolve_contact` hook) and render the rule's template;
3. **claim** the dedup slot by INSERTing the log row (`pending`) BEFORE sending. The UNIQUE index
   `(org, entry, rule, cycle_date)` makes a lost race a skip; ANY other insert failure aborts that send and is
   logged at error -- the slot is never "best effort" (the Orbity upstream swallowed a failed dedup insert and
   re-sent forever);
4. **send** through the rule's channel; transient errors are retried in-run with backoff; the row ends `sent` or
   `failed` (generic `last_error`, never a provider body). A `failed` row is retried by later daily runs up to
   `MAX_ATTEMPTS` total attempts within `RETRY_WINDOW_DAYS`; a `pending` row (crash mid-send) is NEVER resent.

`preview_reminders` runs steps 1-2 only (no writes) -- the UI "what goes out today" and the tests share it.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable, Mapping, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.integrations.rate_limit import Clock, retry_with_backoff
from noctusai_lib.primitives.postgrest_errors import is_foreign_key_violation, is_unique_violation

from .._common import Scope, first, iso, new_id, now_iso, to_date
from ..config import FinanceConfig
from ..errors import conflict, invalid
from ..types import EntryDirection, EntryStatus
from .channel import ReminderChannel, ReminderSendError
from .templates import DEFAULT_RULES, render, validate_template, variables_for
from .types import (
    CHANNEL_WHATSAPP,
    CHANNELS,
    DEFAULT_TIMEZONE,
    MAX_ATTEMPTS,
    MAX_OFFSET_DAYS,
    MIN_OFFSET_DAYS,
    RETRY_WINDOW_DAYS,
    SKIP_BLOCKED,
    SKIP_NO_ADDRESS,
    SKIP_NO_CHANNEL,
    SKIP_NO_CONTACT,
    SKIP_OPT_OUT,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_SENT,
    PlannedReminder,
    ReminderContact,
    ReminderPlan,
    SkippedReminder,
)

logger = logging.getLogger(__name__)

REGRA_DUPLICADA = "regra_duplicada"
REGRA_COM_HISTORICO = "regra_com_historico"
_OPEN_STATUSES = [EntryStatus.OPEN.value, EntryStatus.PARTIAL.value]

#: `(scope, entry_row) -> ReminderContact | None` -- who is this receivable's client (host data: parties, a client table).
ContactResolver = Callable[[Scope, Mapping[str, Any]], Optional[ReminderContact]]
#: `(scope, entry_row) -> reason | None` -- the host's veto (preserved / cancelled / in-negotiation client...).
SkipHook = Callable[[Scope, Mapping[str, Any]], Optional[str]]


class ReminderPorts:
    """What the host plugs in: channels by name, the contact resolver, an optional veto, an optional clock."""

    def __init__(
        self,
        *,
        channels: Mapping[str, ReminderChannel],
        resolve_contact: ContactResolver,
        skip_reason: Optional[SkipHook] = None,
        clock: Optional[Clock] = None,
    ) -> None:
        self.channels = dict(channels)
        self.resolve_contact = resolve_contact
        self.skip_reason = skip_reason
        self.clock = clock


# ─── settings + rules ────────────────────────────────────────────────────────


def _tz(name: Optional[str]) -> ZoneInfo:
    try:
        return ZoneInfo(name or DEFAULT_TIMEZONE)
    except ZoneInfoNotFoundError as exc:
        raise invalid("timezone", "Fuso horário inválido.") from exc


def get_settings(s: Scope) -> dict:
    row = first(s.tbl("reminder_settings").select("*").eq("org_id", s.org_id).limit(1).execute())
    return row or {"org_id": s.org_id, "enabled": False, "timezone": DEFAULT_TIMEZONE}


def update_settings(s: Scope, data: Mapping[str, Any]) -> dict:
    current = get_settings(s)
    patch: dict[str, Any] = {"updated_at": now_iso()}
    if data.get("enabled") is not None:
        patch["enabled"] = bool(data["enabled"])
    if data.get("timezone") is not None:
        _tz(data["timezone"])
        patch["timezone"] = data["timezone"]
    exists = s.tbl("reminder_settings").select("org_id").eq("org_id", s.org_id).limit(1).execute()
    if exists.data:
        s.tbl("reminder_settings").update(patch).eq("org_id", s.org_id).execute()
    else:
        s.tbl("reminder_settings").insert({"org_id": s.org_id, "created_at": patch["updated_at"], **patch}).execute()
    return {**current, **patch}


def list_rules(s: Scope) -> list[dict]:
    rows = s.rows("reminder_rules")
    rows.sort(key=lambda r: (r["channel"], int(r["offset_days"])))
    return rows


def _clean_rule(data: Mapping[str, Any], current: Optional[Mapping[str, Any]] = None) -> dict:
    cur = current or {}
    channel = data.get("channel", cur.get("channel", CHANNEL_WHATSAPP))
    if channel not in CHANNELS:
        raise invalid("channel", "Canal inválido.")
    offset = data.get("offset_days", cur.get("offset_days"))
    if offset is None or isinstance(offset, bool) or int(offset) != offset or not MIN_OFFSET_DAYS <= int(offset) <= MAX_OFFSET_DAYS:
        raise invalid("offset_days", f"O deslocamento deve estar entre {MIN_OFFSET_DAYS} e {MAX_OFFSET_DAYS} dias.")
    template = data.get("template", cur.get("template"))
    validate_template(template)
    return {"channel": channel, "offset_days": int(offset), "template": str(template).strip(),
            "enabled": bool(data.get("enabled", cur.get("enabled", True)))}


def _offset_taken(s: Scope, channel: str, offset: int, *, except_id: Optional[str] = None) -> bool:
    rows = s.tbl("reminder_rules").select("id").eq("org_id", s.org_id).eq("channel", channel).eq("offset_days", offset).execute()
    return any(str(r["id"]) != str(except_id) for r in (rows.data or []))


def create_rule(s: Scope, data: Mapping[str, Any]) -> dict:
    clean = _clean_rule(data)
    if _offset_taken(s, clean["channel"], clean["offset_days"]):
        raise conflict(REGRA_DUPLICADA, "Já existe uma regra para este canal e deslocamento.")
    now = now_iso()
    row = {"id": new_id(), "org_id": s.org_id, **clean, "created_at": now, "updated_at": now}
    try:
        return first(s.tbl("reminder_rules").insert(row).execute()) or row
    except Exception as exc:
        if is_unique_violation(exc):  # lost a race with another writer
            raise conflict(REGRA_DUPLICADA, "Já existe uma regra para este canal e deslocamento.") from exc
        raise


def update_rule(s: Scope, rule_id: Any, data: Mapping[str, Any]) -> dict:
    current = s.get("reminder_rules", rule_id, what="Regra")
    clean = _clean_rule(data, current)
    if _offset_taken(s, clean["channel"], clean["offset_days"], except_id=current["id"]):
        raise conflict(REGRA_DUPLICADA, "Já existe uma regra para este canal e deslocamento.")
    patch = {**clean, "updated_at": now_iso()}
    s.tbl("reminder_rules").update(patch).eq("org_id", s.org_id).eq("id", str(rule_id)).execute()
    return {**current, **patch}


def delete_rule(s: Scope, rule_id: Any) -> None:
    """Delete a rule that never sent anything; one with history is refused (409) -- disable it instead."""
    s.get("reminder_rules", rule_id, what="Regra")
    try:
        s.tbl("reminder_rules").delete().eq("org_id", s.org_id).eq("id", str(rule_id)).execute()
    except Exception as exc:
        if is_foreign_key_violation(exc):
            raise conflict(REGRA_COM_HISTORICO, "A regra já enviou mensagens: desative-a em vez de excluir.") from exc
        raise


def ensure_default_rules(s: Scope, *, channel: str = CHANNEL_WHATSAPP) -> list[dict]:
    """Create the default pt-BR ladder for offsets the org does not have yet (idempotent; existing rules untouched)."""
    existing = {(r["channel"], int(r["offset_days"])) for r in list_rules(s)}
    for offset, template in DEFAULT_RULES:
        if (channel, offset) not in existing:
            create_rule(s, {"channel": channel, "offset_days": offset, "template": template})
    return list_rules(s)


def set_receivable_opt_out(s: Scope, entry_id: Any, opt_out: bool) -> dict:
    """Per-receivable opt-out: no reminder is ever sent for it while true."""
    entry = s.get("entries", entry_id, what="Lançamento")
    s.tbl("entries").update({"reminders_opt_out": bool(opt_out), "updated_at": now_iso()}).eq("org_id", s.org_id).eq("id", str(entry_id)).execute()
    return {**entry, "reminders_opt_out": bool(opt_out)}


def list_log(s: Scope, *, page: int = 1, page_size: int = 20, status: Optional[str] = None):
    """The sent log (newest first): `(rows, total, page, page_size)`."""
    return s.page("reminder_log", page=page, page_size=page_size,
                  refine=(lambda q: q.eq("status", status)) if status else None,
                  order=(("created_at", True), ("id", True)))


# ─── selection ───────────────────────────────────────────────────────────────


def org_today(settings: Mapping[str, Any], *, now: Optional[datetime] = None) -> date:
    tz = _tz(settings.get("timezone"))
    return (now.astimezone(tz) if now else datetime.now(tz)).date()


def _log_index(s: Scope, cycle_dates: list[str]) -> dict[tuple[str, str, str], dict]:
    rows = s.rows("reminder_log", refine=lambda q: q.in_("cycle_date", cycle_dates))
    return {(str(r["entry_id"]), str(r["rule_id"]), str(r["cycle_date"])[:10]): r for r in rows}


def preview_reminders(s: Scope, ports: ReminderPorts, *, on: Optional[date] = None, settings: Optional[Mapping] = None) -> ReminderPlan:
    """What `run_reminders_for_org` would attempt `on` (default: today in the org tz). No writes, no sends.

    Returns planned messages (with `already` set when the dedup ledger holds the key) and skipped ones with a
    reason code. An org whose reminders are off yields an empty plan.
    """
    settings = settings or get_settings(s)
    on = on or org_today(settings)
    plan = ReminderPlan(org_id=s.org_id, on=on.isoformat())
    if not settings.get("enabled"):
        return plan
    rules = [r for r in list_rules(s) if r.get("enabled")]
    if not rules:
        return plan
    by_due: dict[str, list[dict]] = {}
    for r in rules:
        by_due.setdefault((on - timedelta(days=int(r["offset_days"]))).isoformat(), []).append(r)
    due_dates = sorted(by_due)
    entries = s.rows(
        "entries",
        refine=lambda q: q.eq("direction", EntryDirection.RECEIVABLE.value).in_("status", _OPEN_STATUSES).in_("due_date", due_dates),
    )
    ledger = _log_index(s, due_dates)
    for entry in entries:
        due = to_date(entry["due_date"])
        assert due is not None
        for rule in by_due.get(due.isoformat(), []):
            item = _plan_one(s, ports, entry, rule, due, on, ledger)
            (plan.planned if isinstance(item, PlannedReminder) else plan.skipped).append(item)
    return plan


def _plan_one(s: Scope, ports: ReminderPorts, entry: Mapping, rule: Mapping, due: date, on: date, ledger: Mapping):
    eid, rid = str(entry["id"]), str(rule["id"])
    skip = lambda reason: SkippedReminder(eid, rid, reason)  # noqa: E731
    if rule["channel"] not in ports.channels:
        return skip(SKIP_NO_CHANNEL)
    if entry.get("reminders_opt_out"):
        return skip(SKIP_OPT_OUT)
    if ports.skip_reason is not None and ports.skip_reason(s, entry):
        return skip(SKIP_BLOCKED)
    contact = ports.resolve_contact(s, entry)
    if contact is None:
        return skip(SKIP_NO_CONTACT)
    recipient = contact.phone if rule["channel"] == CHANNEL_WHATSAPP else contact.email
    if not recipient:
        return skip(SKIP_NO_ADDRESS)
    remaining = int(entry["amount_cents"]) - int(entry.get("settled_cents") or 0)
    text = render(rule["template"], variables_for(contact, amount_cents=remaining, due=due, days_overdue=(on - due).days))
    prior = ledger.get((eid, rid, due.isoformat()))
    return PlannedReminder(eid, rid, rule["channel"], int(rule["offset_days"]), due.isoformat(), recipient, text,
                           already=prior["status"] if prior else None)


# ─── sending ─────────────────────────────────────────────────────────────────


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, ReminderSendError) and exc.transient


def _deliver(s: Scope, ports: ReminderPorts, log_id: str, channel: str, recipient: str, text: str, attempts: int) -> str:
    """Send for an already-claimed log row and settle it `sent`/`failed`. Returns the final status."""
    try:
        receipt = retry_with_backoff(
            lambda: ports.channels[channel].send(org_id=s.org_id, to=recipient, text=text),
            bucket="whatsapp", is_retryable=_is_transient, clock=ports.clock,
        )
    except ReminderSendError as exc:
        logger.warning("finance reminders: send failed org=%s log=%s attempt=%s transient=%s: %s",
                       s.org_id, log_id, attempts, exc.transient, exc)
        # permanent failures are not retried by later runs: exhaust the attempts.
        _settle(s, log_id, status=STATUS_FAILED, attempts=attempts if exc.transient else MAX_ATTEMPTS, last_error=str(exc)[:200])
        return STATUS_FAILED
    _settle(s, log_id, status=STATUS_SENT, attempts=attempts, last_error=None, provider_ref=receipt.provider_ref, sent_at=now_iso())
    return STATUS_SENT


def _settle(s: Scope, log_id: str, **fields: Any) -> None:
    s.tbl("reminder_log").update({**fields, "updated_at": now_iso()}).eq("org_id", s.org_id).eq("id", log_id).execute()


def _claim_new(s: Scope, p: PlannedReminder) -> Optional[str]:
    """INSERT the dedup row. Returns its id, or None when another run already holds the slot (unique violation).
    Any other failure PROPAGATES: no claimed slot, no send."""
    row = {
        "id": new_id(), "org_id": s.org_id, "entry_id": p.entry_id, "rule_id": p.rule_id, "channel": p.channel,
        "offset_days": p.offset_days, "cycle_date": p.cycle_date, "status": STATUS_PENDING, "attempts": 1,
        "recipient": p.recipient, "message": p.text, "created_at": now_iso(), "updated_at": now_iso(),
    }
    try:
        s.tbl("reminder_log").insert(row).execute()
    except Exception as exc:
        if is_unique_violation(exc):
            return None
        raise
    return row["id"]


def _reclaim_failed(s: Scope, log_id: Any, attempts: int) -> bool:
    """failed -> pending compare-and-set on the attempts the caller READ (only one worker wins the retry)."""
    resp = (
        s.tbl("reminder_log").update({"status": STATUS_PENDING, "attempts": attempts + 1, "updated_at": now_iso()})
        .eq("org_id", s.org_id).eq("id", str(log_id)).eq("status", STATUS_FAILED).eq("attempts", attempts).execute()
    )
    return bool(resp.data)


def run_reminders_for_org(s: Scope, ports: ReminderPorts, *, on: Optional[date] = None) -> dict:
    """Send today's reminders for one org. Returns `{planned, sent, failed, deduped, skipped, errors, retried}`."""
    settings = get_settings(s)
    on = on or org_today(settings)
    plan = preview_reminders(s, ports, on=on, settings=settings)
    out = {"planned": len(plan.planned), "sent": 0, "failed": 0, "deduped": 0, "skipped": len(plan.skipped), "errors": 0, "retried": 0}
    if not settings.get("enabled"):
        return out
    ledger = _log_index(s, sorted({p.cycle_date for p in plan.planned})) if plan.planned else {}
    for p in plan.planned:
        try:
            prior = ledger.get((p.entry_id, p.rule_id, p.cycle_date))
            if prior is None:
                log_id, attempts = _claim_new(s, p), 1
            elif prior["status"] == STATUS_FAILED and int(prior["attempts"]) < MAX_ATTEMPTS:
                read = int(prior["attempts"])
                log_id, attempts = (str(prior["id"]), read + 1) if _reclaim_failed(s, prior["id"], read) else (None, 0)
                out["retried"] += int(log_id is not None)
            else:
                log_id = None
            if log_id is None:
                out["deduped"] += 1
                continue
            _count(out, _deliver(s, ports, log_id, p.channel, p.recipient, p.text, attempts))
        except Exception:
            out["errors"] += 1
            logger.exception("finance reminders: org=%s entry=%s rule=%s aborted", s.org_id, p.entry_id, p.rule_id)
    _retry_earlier_failures(s, ports, on, out)
    return out


def _count(out: dict, status: str) -> None:
    out["sent" if status == STATUS_SENT else "failed"] += 1


def _retry_earlier_failures(s: Scope, ports: ReminderPorts, on: date, out: dict) -> None:
    """Re-send `failed` rows whose scheduled day was 1..RETRY_WINDOW_DAYS ago (the offset day itself was retried in-run)."""
    lo, hi = on - timedelta(days=RETRY_WINDOW_DAYS + 120), on  # cycle_date = due; scheduled = due + offset (offset bounded)
    rows = s.rows("reminder_log", eq={"status": STATUS_FAILED}, refine=lambda q: q.lt("attempts", MAX_ATTEMPTS).gte("cycle_date", lo.isoformat()).lte("cycle_date", hi.isoformat()))
    for row in rows:
        try:
            scheduled = to_date(row["cycle_date"]) + timedelta(days=int(row["offset_days"]))  # type: ignore[operator]
            if not 1 <= (on - scheduled).days <= RETRY_WINDOW_DAYS or row["channel"] not in ports.channels:
                continue
            entry = s.find("entries", row["entry_id"])
            if entry is None or entry["status"] not in _OPEN_STATUSES or entry.get("reminders_opt_out"):
                continue
            if ports.skip_reason is not None and ports.skip_reason(s, entry):
                continue
            read = int(row["attempts"])
            if not _reclaim_failed(s, row["id"], read):
                continue
            out["retried"] += 1
            _count(out, _deliver(s, ports, str(row["id"]), row["channel"], row["recipient"], row["message"], read + 1))
        except Exception:
            out["errors"] += 1
            logger.exception("finance reminders: retry of log %s aborted", row.get("id"))


def run_reminders_all(db: Any, cfg: FinanceConfig, ports: ReminderPorts, *, now: Optional[datetime] = None) -> dict:
    """The job body: every org with reminders enabled (service-role client). One org failing never starves the rest."""
    table = cfg.table("reminder_settings")
    orgs = list(iter_paged_rows(
        lambda start, end: db.table(table).select("*").eq("enabled", True).order("org_id").range(start, end).execute().data,
        label="finance reminder settings",
    ))
    total = {"orgs": len(orgs), "sent": 0, "failed": 0, "deduped": 0, "errors": 0, "failed_orgs": 0}
    for settings in orgs:
        s = Scope(db, cfg, str(settings["org_id"]))
        try:
            res = run_reminders_for_org(s, ports, on=org_today(settings, now=now))
        except Exception:
            total["failed_orgs"] += 1
            logger.exception("finance reminders: org %s failed", s.org_id)
            continue
        for k in ("sent", "failed", "deduped", "errors"):
            total[k] += res[k]
    return total


__all__ = [
    "ContactResolver", "REGRA_COM_HISTORICO", "REGRA_DUPLICADA", "ReminderPorts", "SkipHook",
    "create_rule", "delete_rule", "ensure_default_rules", "get_settings", "list_log", "list_rules", "org_today",
    "preview_reminders", "run_reminders_all", "run_reminders_for_org", "set_receivable_opt_out", "update_rule", "update_settings",
]
