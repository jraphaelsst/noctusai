"""Recurrences -- templates that generate entries on a schedule.

`calcular_proxima_data` is the pure next-date rule for the 8 frequencies; month-based
ones keep an ANCHOR day (the day the series started on) clamped to each month's last
day, so Jan 31 -> Feb 28 -> Mar 31 (not -> Mar 28). The anchor lives in the template
JSON (`anchor_day`), so the table needs no extra column.

`generate_due_recurrences` is the body of the daily `finance_generate_recurrences` job
(scheduler registration is the host's, contract §6). It is idempotent on
`(recurrence_id, due_date)`: running it twice, or after a crash mid-run, never
duplicates an entry and never skips a due date.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Mapping, Optional

from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from ._common import Scope, add_months, first, iso, month_start, new_id, now_iso, to_date, today
from .config import FinanceConfig
from .entries import check_refs, normalize_doc
from .errors import invalid
from .types import EntrySource, EntryStatus, Frequency, values

logger = logging.getLogger(__name__)

#: A single run never generates more than this many occurrences per recurrence (a series
#: abandoned for years would otherwise flood the org on its first tick back).
MAX_CATCHUP_PER_RUN = 36

_MONTHS = {
    Frequency.MONTHLY.value: 1,
    Frequency.BIMONTHLY.value: 2,
    Frequency.QUARTERLY.value: 3,
    Frequency.SEMIANNUAL.value: 6,
    Frequency.ANNUAL.value: 12,
}
_DAYS = {Frequency.DAILY.value: 1, Frequency.WEEKLY.value: 7, Frequency.BIWEEKLY.value: 14}

TEMPLATE_FIELDS = (
    "direction", "description", "counterparty_name", "counterparty_doc", "category_id", "cost_center_id",
    "expected_account_id", "amount_cents", "notes", "anchor_day",
)


def calcular_proxima_data(current: date, frequency: str, anchor_day: Optional[int] = None) -> date:
    """The occurrence after `current` for `frequency` (see module docstring for the anchor)."""
    freq = getattr(frequency, "value", frequency)
    if freq in _DAYS:
        return current + timedelta(days=_DAYS[freq])
    if freq in _MONTHS:
        return add_months(current, _MONTHS[freq], anchor_day=anchor_day or current.day)
    raise ValueError(f"unknown frequency {frequency!r}")


def _clean_template(s: Scope, raw: Mapping[str, Any], next_date: date) -> dict:
    t = {k: raw[k] for k in TEMPLATE_FIELDS if k in raw and raw[k] is not None}
    t["direction"] = getattr(t.get("direction"), "value", t.get("direction"))
    if t.get("direction") not in ("payable", "receivable"):
        raise invalid("template.direction", "Direção inválida.")
    if not str(t.get("description") or "").strip():
        raise invalid("template.description", "Informe a descrição.")
    if int(t.get("amount_cents") or 0) <= 0:
        raise invalid("template.amount_cents", "O valor deve ser maior que zero.")
    t["amount_cents"] = int(t["amount_cents"])
    t["description"] = str(t["description"]).strip()
    if t.get("counterparty_doc"):
        t["counterparty_doc"] = normalize_doc(t["counterparty_doc"])
    for key in ("category_id", "cost_center_id", "expected_account_id"):
        if t.get(key):
            t[key] = str(t[key])
    check_refs(s, t, t["direction"])
    t["anchor_day"] = int(t.get("anchor_day") or next_date.day)
    return t


def list_recurrences(s: Scope) -> list[dict]:
    rows = s.rows("recurrences")
    rows.sort(key=lambda r: (str(r.get("next_date")), str(r["id"])))
    return rows


def get_recurrence(s: Scope, recurrence_id: Any) -> dict:
    return s.get("recurrences", recurrence_id, what="Recorrência")


def create_recurrence(s: Scope, data: Mapping[str, Any]) -> dict:
    freq = getattr(data["frequency"], "value", data["frequency"])
    if freq not in values(Frequency):
        raise invalid("frequency", "Frequência inválida.")
    next_date = to_date(data["next_date"])
    end_date = to_date(data.get("end_date"))
    if end_date and end_date < next_date:
        raise invalid("end_date", "A data final deve ser igual ou posterior à próxima data.")
    now = now_iso()
    row = {
        "id": new_id(),
        "org_id": s.org_id,
        "template": _clean_template(s, data["template"], next_date),
        "frequency": freq,
        "next_date": iso(next_date),
        "end_date": iso(end_date),
        "active": bool(data.get("active", True)),
        "created_at": now,
        "updated_at": now,
    }
    return first(s.tbl("recurrences").insert(row).execute()) or row


def update_recurrence(s: Scope, recurrence_id: Any, data: Mapping[str, Any]) -> dict:
    current = get_recurrence(s, recurrence_id)
    patch: dict[str, Any] = {}
    if data.get("frequency") is not None:
        freq = getattr(data["frequency"], "value", data["frequency"])
        if freq not in values(Frequency):
            raise invalid("frequency", "Frequência inválida.")
        patch["frequency"] = freq
    if data.get("next_date") is not None:
        patch["next_date"] = iso(data["next_date"])
    if "end_date" in data:
        patch["end_date"] = iso(data["end_date"])
    if data.get("active") is not None:
        patch["active"] = bool(data["active"])
    next_date = to_date(patch.get("next_date", current["next_date"]))
    if data.get("template") is not None:
        patch["template"] = _clean_template(s, {**current["template"], **data["template"]}, next_date)
    end_date = to_date(patch.get("end_date", current.get("end_date")))
    if end_date and end_date < next_date and patch.get("active", current["active"]):
        raise invalid("end_date", "A data final deve ser igual ou posterior à próxima data.")
    if not patch:
        return current
    patch["updated_at"] = now_iso()
    s.tbl("recurrences").update(patch).eq("org_id", s.org_id).eq("id", str(recurrence_id)).execute()
    return {**current, **patch}


def _occurrence_row(rec: Mapping[str, Any], due: date) -> dict:
    t = rec["template"]
    now = now_iso()
    return {
        "id": new_id(),
        "org_id": str(rec["org_id"]),
        "direction": t["direction"],
        "status": EntryStatus.OPEN.value,
        "description": t["description"],
        "counterparty_name": t.get("counterparty_name"),
        "counterparty_doc": t.get("counterparty_doc"),
        "category_id": t.get("category_id"),
        "cost_center_id": t.get("cost_center_id"),
        "expected_account_id": t.get("expected_account_id"),
        "competence_month": iso(month_start(due)),
        "due_date": iso(due),
        "amount_cents": int(t["amount_cents"]),
        "settled_cents": 0,
        "source": EntrySource.RECURRENCE.value,
        "source_ref": f"{rec['id']}:{iso(due)}",
        "recurrence_id": str(rec["id"]),
        "notes": t.get("notes"),
        "created_at": now,
        "updated_at": now,
    }


def generate_for_recurrence(db: Any, cfg: FinanceConfig, rec: Mapping[str, Any], *, on: date) -> int:
    """Generate every occurrence of `rec` due on or before `on`; returns how many entries were created."""
    s = Scope(db, cfg, str(rec["org_id"]))
    due = to_date(rec["next_date"])
    end = to_date(rec.get("end_date"))
    anchor = int((rec.get("template") or {}).get("anchor_day") or due.day)
    created = 0
    steps = 0
    while due <= on and (end is None or due <= end) and steps < MAX_CATCHUP_PER_RUN:
        existing = (
            s.tbl("entries").select("id").eq("org_id", s.org_id).eq("recurrence_id", str(rec["id"]))
            .eq("due_date", iso(due)).limit(1).execute()
        )
        if not existing.data:
            try:
                s.tbl("entries").insert(_occurrence_row(rec, due)).execute()
                created += 1
            except Exception as exc:
                if not is_unique_violation(exc):  # a concurrent run won this date: fine, move on
                    raise
        due = calcular_proxima_data(due, rec["frequency"], anchor)
        steps += 1
    patch: dict[str, Any] = {"next_date": iso(due), "updated_at": now_iso()}
    if end is not None and due > end:
        patch["active"] = False
    s.tbl("recurrences").update(patch).eq("org_id", s.org_id).eq("id", str(rec["id"])).execute()
    return created


def generate_due_recurrences(db: Any, cfg: FinanceConfig, *, on: Optional[date] = None) -> dict:
    """The `finance_generate_recurrences` job body: ALL orgs (service-role client), idempotent.

    A recurrence that fails is logged and skipped so one bad template cannot starve the rest;
    it is retried on the next tick. Returns `{"recurrences": n, "created": n, "failed": n}`.
    """
    on = on or today()
    due = _due_recurrences(db, cfg, on)
    created = failed = 0
    for rec in due:
        try:
            created += generate_for_recurrence(db, cfg, rec, on=on)
        except Exception:
            failed += 1
            logger.exception("finance: recurrence %s failed to generate; retried next tick", rec.get("id"))
    return {"recurrences": len(due), "created": created, "failed": failed}


def _due_recurrences(db: Any, cfg: FinanceConfig, on: date) -> list[dict]:
    """Active recurrences due on/before `on`, across orgs, paged past the 1 000-row cap."""
    table = cfg.table("recurrences")
    return list(
        iter_paged_rows(
            lambda start, end: (
                db.table(table).select("*").eq("active", True).lte("next_date", on.isoformat())
                .order("id").range(start, end).execute().data
            ),
            label="finance recurrences due",
        )
    )


__all__ = [
    "MAX_CATCHUP_PER_RUN",
    "calcular_proxima_data",
    "create_recurrence",
    "generate_due_recurrences",
    "generate_for_recurrence",
    "get_recurrence",
    "list_recurrences",
    "update_recurrence",
]
