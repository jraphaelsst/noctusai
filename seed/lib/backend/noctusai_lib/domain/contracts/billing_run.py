"""Billing: turn a contract's schedule into finance receivables, idempotently.

Every receivable is booked through the `ContractsBilling` seam with `source='contracts'` and
`source_ref = <contract_id>:<period_key>[:<kind>]`; the `contract_billings` row (UNIQUE contract /
period / kind) is the contract-side record. Order per item: BOOK (idempotent in finance) -> RECORD ->
advance the cursor, so a crash at any point re-runs to the same end state and never double-bills.

- `bill_contract` is the unit (used by activate / resume and by the job);
- `contracts_generate_billing` is the body of the daily `contracts_generate_billing` job (ALL orgs, or
  one when `org_id` is given): renews / expires lapsed contracts, then bills what is due within
  `cfg.billing_lead_days`. A contract that fails is logged and skipped; it is retried next tick.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any, Callable, Optional

from noctusai_lib.integrations.persistence.paging import iter_paged_rows
from noctusai_lib.primitives.postgrest_errors import is_unique_violation

from . import schedule as sched
from ._common import Scope, iso, new_id, now_iso, to_date, today
from .config import ContractsConfig
from .schedule import ScheduleItem
from .types import BillingKind, BillingModel, ContractStatus

logger = logging.getLogger(__name__)

JOB_ID = "contracts_generate_billing"
PENALTY_CATEGORY = "Outras receitas"


def billed_map(s: Scope, contract_id: Any) -> dict[tuple[str, str], dict]:
    return {(r["period_key"], r["kind"]): r for r in s.rows("contract_billings", eq={"contract_id": str(contract_id)})}


def _category(cfg: ContractsConfig, c: dict, item: ScheduleItem) -> str:
    if item.kind == BillingKind.PENALTY.value:
        return PENALTY_CATEGORY
    if item.kind == BillingKind.FIXED.value and c["billing_model"] in (BillingModel.RECURRING.value, BillingModel.RETAINER.value):
        return cfg.receivable_category
    return cfg.service_category


def _book(s: Scope, c: dict, item: ScheduleItem, billing: Any, billed: dict) -> bool:
    """Book one item; True when it was newly recorded. Idempotent on every layer."""
    if (item.period_key, item.kind) in billed:
        return False
    ref = sched.source_ref(c["id"], item.period_key, item.kind)
    entry_id = billing.book_receivable(
        s.org_id, source_ref=ref, description=item.description, counterparty_name=c.get("party_name"),
        counterparty_doc=c.get("party_doc"), amount_cents=item.amount_cents, competence_month=item.competence_month,
        due_date=item.due_date, category_hint=_category(s.cfg, c, item),
    )
    row = {"id": new_id(), "org_id": s.org_id, "contract_id": str(c["id"]), "period_key": item.period_key, "kind": item.kind,
           "entry_id": entry_id, "source_ref": ref, "amount_cents": item.amount_cents, "due_date": iso(item.due_date),
           "created_at": now_iso()}
    try:
        s.tbl("contract_billings").insert(row).execute()
    except Exception as exc:
        if not is_unique_violation(exc):  # a concurrent run recorded it first: fine
            raise
        return False
    billed[(item.period_key, item.kind)] = row
    return True


def bill_contract(s: Scope, c: dict, billing: Any, *, on: Optional[date] = None) -> dict:
    """Book everything due for an ACTIVE contract. Returns `{"created": n}`."""
    on = on or today()
    if c.get("status") != ContractStatus.ACTIVE.value:
        return {"created": 0}
    billed = billed_map(s, c["id"])
    created = 0
    model = c["billing_model"]
    if model in (BillingModel.ONE_TIME.value, BillingModel.INSTALLMENTS.value):
        for item in sched.finite_schedule(c):  # the whole schedule at once: finance sees every parcela from day one
            created += _book(s, c, item, billing, billed)
        return {"created": created}
    horizon = on + timedelta(days=s.cfg.billing_lead_days)
    cursor = to_date(c.get("next_period_on")) or to_date(c.get("first_due_date"))
    end = to_date(c.get("end_date"))
    steps = 0
    while cursor is not None and cursor <= horizon and (end is None or cursor <= end) and steps < sched.MAX_PERIODS_PER_RUN:
        item = ScheduleItem(iso(cursor), BillingKind.FIXED.value, cursor, cursor.replace(day=1), int(c["amount_cents"]),
                            sched.label(c, cursor))
        created += _book(s, c, item, billing, billed)
        cursor = sched.next_due(c, cursor)
        steps += 1
    s.tbl("contracts").update({"next_period_on": iso(cursor), "updated_at": now_iso()}).eq("org_id", s.org_id).eq("id", str(c["id"])).execute()
    if model == BillingModel.RETAINER.value:
        from .contracts import usage_by_month

        this_month = on.replace(day=1)
        for key, minutes in sorted(usage_by_month(s, c["id"]).items()):
            month = date.fromisoformat(f"{key}-01")
            if month >= this_month:
                continue  # the month is still running: its excess is not final
            item = sched.excess_item(c, month, minutes)
            if item is not None:
                created += _book(s, c, item, billing, billed)
    return {"created": created}


def book_penalty(s: Scope, c: dict, billing: Any, cents: int, *, due: date) -> None:
    item = ScheduleItem("termination", BillingKind.PENALTY.value, due, due.replace(day=1), cents,
                        f"{str(c.get('title') or 'Contrato').strip()} — multa rescisória")
    _book(s, c, item, billing, billed_map(s, c["id"]))


def cancel_after(s: Scope, c: dict, billing: Any, effective: date) -> dict:
    """Cancel the not-yet-settled receivables due AFTER `effective` (a settled one is kept, never reversed here)."""
    cancelled = kept = 0
    for (key, kind), row in billed_map(s, c["id"]).items():
        if kind == BillingKind.PENALTY.value or to_date(row["due_date"]) <= effective:
            continue
        outcome = billing.cancel_receivable(s.org_id, source_ref=row["source_ref"])
        if outcome == "kept_settled":
            kept += 1
            continue
        s.tbl("contract_billings").delete().eq("org_id", s.org_id).eq("id", str(row["id"])).execute()
        cancelled += 1
    return {"cancelled": cancelled, "kept": kept}


def billing_preview(s: Scope, contract_id: Any, count: int = 6) -> dict:
    """The next `count` fixed items not yet billed + (retainer) the running month's excess estimate."""
    from .contracts import get_contract, usage_by_month

    c = get_contract(s, contract_id)
    billed = billed_map(s, contract_id)
    items = sched.preview(c, {k for (k, kind) in billed if kind == BillingKind.FIXED.value}, count)
    out: dict[str, Any] = {"items": [i.as_dict() for i in items], "billed": len([1 for (_, k) in billed if k == "fixed"])}
    if c["billing_model"] == BillingModel.RETAINER.value:
        key = today().replace(day=1)
        minutes = usage_by_month(s, contract_id).get(f"{key.year}-{key.month:02d}", 0)
        out["running_month"] = {"month": f"{key.year}-{key.month:02d}", "minutes": minutes,
                                "included_minutes": c.get("retainer_minutes"), "excess_cents": sched.excess_cents(c, minutes)}
    return out


def list_billings(s: Scope, contract_id: Any) -> list[dict]:
    from .contracts import get_contract

    get_contract(s, contract_id)
    rows = s.rows("contract_billings", eq={"contract_id": str(contract_id)})
    rows.sort(key=lambda r: (str(r["due_date"]), str(r["kind"])))
    return rows


def _active_contracts(db: Any, cfg: ContractsConfig, org_id: Optional[str]) -> list[dict]:
    table = cfg.table("contracts")

    def page(start: int, end: int):
        q = db.table(table).select("*").eq("status", ContractStatus.ACTIVE.value)
        if org_id:
            q = q.eq("org_id", str(org_id))
        return q.order("id").range(start, end).execute().data

    return list(iter_paged_rows(page, label="contracts active"))


#: Renewals one contract may take in a single run (5 years of monthly renewals; the rest waits for the next tick).
MAX_RENEWALS_PER_TICK = 60


def contracts_generate_billing(db: Any, cfg: ContractsConfig, billing: Any, *, org_id: Optional[str] = None,
                               on: Optional[date] = None) -> dict:
    """The `contracts_generate_billing` job body (ALL orgs, or `org_id`'s): renew / expire, then bill. Idempotent."""
    from .contracts import expire_contract, renew_contract

    on = on or today()
    summary = {"contracts": 0, "created": 0, "renewed": 0, "expired": 0, "failed": 0}
    for c in _active_contracts(db, cfg, org_id):
        summary["contracts"] += 1
        s = Scope(db, cfg, str(c["org_id"]))
        try:
            end = to_date(c.get("end_date"))
            if end is not None and end < on and c.get("auto_renew"):
                renewals = 0
                # A long-dormant contract catches up, but bounded per tick: a corrupt `end_date` (year 1900) or a
                # 1-month renewal must not turn one row into an unbounded write loop; the next tick continues.
                while end is not None and end < on and renewals < MAX_RENEWALS_PER_TICK:
                    c = renew_contract(s, c)
                    end = to_date(c["end_date"])
                    renewals += 1
                summary["renewed"] += 1
            summary["created"] += bill_contract(s, c, billing, on=on)["created"]
            if end is not None and end < on and not c.get("auto_renew"):
                expire_contract(s, c)
                summary["expired"] += 1
        except Exception:
            summary["failed"] += 1
            logger.exception("contracts: billing of %s failed; retried next tick", c.get("id"))
    return summary


def register_contracts_billing(cfg: ContractsConfig, *, get_db: Callable[[], Any], get_billing: Callable[[Any], Any],
                               scheduler: Any = None, job_id: str = JOB_ID, hours: int = 24) -> str:
    """Register the daily job on the seed scheduler (call before `start_scheduler()`).

    `get_db` / `get_billing(db)` are called PER RUN (never captured). Every exception is logged and swallowed: a failed
    tick must neither crash the scheduler nor de-register the job. Re-registering the same `job_id` replaces it.
    """
    import asyncio

    from noctusai_lib.api import scheduler as seed_scheduler

    async def _job() -> None:
        try:
            def run() -> dict:
                db = get_db()
                return contracts_generate_billing(db, cfg, get_billing(db))

            logger.info("contracts billing: %s", await asyncio.to_thread(run))
        except Exception:
            logger.error("contracts billing job %s failed", job_id, exc_info=True)

    (scheduler or seed_scheduler).register(job_id, _job, hours=hours)
    return job_id


__all__ = [
    "JOB_ID", "PENALTY_CATEGORY", "bill_contract", "billed_map", "billing_preview", "book_penalty", "cancel_after",
    "contracts_generate_billing", "list_billings", "register_contracts_billing",
]
