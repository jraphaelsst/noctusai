"""The billing schedule of a contract -- PURE (no I/O), the single source of the dates and amounts.

`billing_model` decides the shape:

- `one_time`      one receivable of `amount_cents` at `first_due_date`;
- `installments`  `installments_count` receivables splitting `amount_cents` (the last absorbs the
                  remainder, like finance's `split_installments`), monthly from `first_due_date`;
- `recurring`     one receivable per `frequency` period (monthly / quarterly / yearly) at
                  `due_day` (clamped to short months), open-ended unless `end_date` is set;
- `retainer`      like a monthly `recurring` fixed fee, plus EXCESS billing: usage beyond
                  `retainer_minutes` in a month is billed at `excess_rate_cents` per hour, in arrears.

Money is integer cents; the excess rounds half up to the cent.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Iterator, Mapping, Optional

from noctusai_lib.domain.finance.entries import split_installments

from ._common import add_months, iso, month_start, to_date
from .types import BillingFrequency, BillingKind, BillingModel

_PERIOD_MONTHS = {BillingFrequency.MONTHLY.value: 1, BillingFrequency.QUARTERLY.value: 3, BillingFrequency.YEARLY.value: 12}

#: A single call never walks more than this many periods (an abandoned series cannot flood the org).
MAX_PERIODS_PER_RUN = 36


@dataclass(frozen=True)
class ScheduleItem:
    period_key: str
    kind: str
    due_date: date
    competence_month: date
    amount_cents: int
    description: str

    def as_dict(self) -> dict:
        return {"period_key": self.period_key, "kind": self.kind, "due_date": iso(self.due_date),
                "competence_month": iso(self.competence_month), "amount_cents": self.amount_cents,
                "description": self.description}


def _plain(v: Any) -> Any:
    return getattr(v, "value", v)


def step_months(c: Mapping[str, Any]) -> int:
    model = _plain(c["billing_model"])
    if model == BillingModel.RETAINER.value:
        return 1
    return _PERIOD_MONTHS.get(_plain(c.get("frequency")) or BillingFrequency.MONTHLY.value, 1)


def anchor_day(c: Mapping[str, Any]) -> int:
    first_due = to_date(c.get("first_due_date"))
    return int(c.get("due_day") or (first_due.day if first_due else 1))


def next_due(c: Mapping[str, Any], current: date) -> date:
    return add_months(current, step_months(c), anchor_day=anchor_day(c))


def source_ref(contract_id: Any, period_key: str, kind: str = BillingKind.FIXED.value) -> str:
    """The finance `source_ref` of one billed item (idempotency key together with `source='contracts'`)."""
    suffix = "" if kind == BillingKind.FIXED.value else f":{kind}"
    return f"{contract_id}:{period_key}{suffix}"


def label(c: Mapping[str, Any], due: date, index: Optional[int] = None, total: Optional[int] = None) -> str:
    title = str(c.get("title") or "Contrato").strip()
    if index is not None and total:
        return f"{title} (parcela {index}/{total})"
    if _plain(c["billing_model"]) == BillingModel.ONE_TIME.value:
        return title
    return f"{title} — {due.month:02d}/{due.year}"


def finite_schedule(c: Mapping[str, Any]) -> list[ScheduleItem]:
    """The whole schedule of a `one_time` / `installments` contract ([] for the open-ended models)."""
    model = _plain(c["billing_model"])
    first_due = to_date(c.get("first_due_date"))
    if first_due is None:
        return []
    amount = int(c.get("amount_cents") or 0)
    if model == BillingModel.ONE_TIME.value:
        return [ScheduleItem("one", BillingKind.FIXED.value, first_due, month_start(first_due), amount, label(c, first_due))]
    if model == BillingModel.INSTALLMENTS.value:
        n = int(c.get("installments_count") or 1)
        out = []
        for i, part in enumerate(split_installments(amount, n)):
            due = add_months(first_due, i, anchor_day=anchor_day(c))
            out.append(ScheduleItem(f"i{i + 1}", BillingKind.FIXED.value, due, month_start(due), part, label(c, due, i + 1, n)))
        return out
    return []


def periods(c: Mapping[str, Any], cursor: Optional[date] = None, *, limit: int = MAX_PERIODS_PER_RUN) -> Iterator[ScheduleItem]:
    """Open-ended `recurring` / `retainer` periods from `cursor` (default `first_due_date`), bounded by `end_date`."""
    due = cursor or to_date(c.get("first_due_date"))
    end = to_date(c.get("end_date"))
    amount = int(c.get("amount_cents") or 0)
    count = 0
    while due is not None and count < limit and (end is None or due <= end):
        yield ScheduleItem(iso(due), BillingKind.FIXED.value, due, month_start(due), amount, label(c, due))
        due = next_due(c, due)
        count += 1


def excess_cents(c: Mapping[str, Any], used_minutes: int) -> int:
    """Retainer excess for one month: minutes beyond the franchise x hourly rate, half-up to the cent."""
    over = max(int(used_minutes) - int(c.get("retainer_minutes") or 0), 0)
    rate = int(c.get("excess_rate_cents") or 0)
    return (over * rate + 30) // 60


def excess_item(c: Mapping[str, Any], month: date, used_minutes: int) -> Optional[ScheduleItem]:
    """The excess receivable of `month` (billed in arrears, due the following month at the contract's day)."""
    amount = excess_cents(c, used_minutes)
    if amount <= 0:
        return None
    month = month_start(month)
    due = add_months(month, 1, anchor_day=anchor_day(c))
    key = f"{month.year}-{month.month:02d}"
    over = max(int(used_minutes) - int(c.get("retainer_minutes") or 0), 0)
    desc = f"{str(c.get('title') or 'Contrato').strip()} — excedente {key} ({over // 60}h{over % 60:02d})"
    return ScheduleItem(key, BillingKind.EXCESS.value, due, month, amount, desc)


def preview(c: Mapping[str, Any], billed_keys: set[str], count: int = 6) -> list[ScheduleItem]:
    """The next `count` fixed items not yet billed (the `BillingPreview` data)."""
    model = _plain(c["billing_model"])
    if model in (BillingModel.ONE_TIME.value, BillingModel.INSTALLMENTS.value):
        return [i for i in finite_schedule(c) if i.period_key not in billed_keys][:count]
    cursor = to_date(c.get("next_period_on")) or to_date(c.get("first_due_date"))
    out: list[ScheduleItem] = []
    for item in periods(c, cursor, limit=count + len(billed_keys)):
        if item.period_key not in billed_keys:
            out.append(item)
        if len(out) >= count:
            break
    return out


def remaining_value(c: Mapping[str, Any], after: date) -> int:
    """Value of the fixed items due AFTER `after`, billed or not (finite models; open-ended ones only when bounded by `end_date`).

    What an early termination forfeits: those receivables are cancelled, the penalty is computed on them.
    """
    model = _plain(c["billing_model"])
    if model in (BillingModel.ONE_TIME.value, BillingModel.INSTALLMENTS.value):
        return sum(i.amount_cents for i in finite_schedule(c) if i.due_date > after)
    if to_date(c.get("end_date")) is None:
        return 0
    return sum(i.amount_cents for i in periods(c, None, limit=MAX_PERIODS_PER_RUN * 4) if i.due_date > after)


__all__ = [
    "MAX_PERIODS_PER_RUN", "ScheduleItem", "anchor_day", "excess_cents", "excess_item", "finite_schedule",
    "label", "next_due", "periods", "preview", "remaining_value", "source_ref", "step_months",
]
