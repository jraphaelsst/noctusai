"""Period date math — pure stdlib helpers.

Lifted verbatim (math preserved) from
`products/erp-imobiliario/backend/app/services/metas_service.py` 2026-05-03.
The ERP module computed all date math in Python to avoid N+1 RPC round-trips
to the database; the same logic now lives at the seed layer so PF and
daily-life can reuse it without copy-paste.

Public surface:
- `period_bounds(kind, ref) -> (start, end)` — inclusive period bounds.
- `count_business_days(start, end) -> int` — Mon-Fri count, inclusive.
- `working_days_total_in_month(ref) -> int`
- `working_days_remaining_in_week(ref) -> int`
- `working_days_remaining_in_month(ref) -> int`
- `working_days_total_in_year(ref) -> int`
- `working_days_remaining_in_year(ref) -> int`
- `proportional_target(monthly_target, kind, ref) -> int` — ERP's
  `_calcular_meta_proporcional` lifted as-is.
"""

from __future__ import annotations

import calendar
import math
from datetime import date, timedelta

from noctusai_lib.domain.metas.value_objects import PeriodKind


def period_bounds(kind: PeriodKind, ref: date) -> tuple[date, date]:
    """Return (start, end) inclusive bounds of the period containing `ref`.

    `OPEN_ENDED` returns `(ref, ref)` — callers that need a different
    semantic should not use this for OPEN_ENDED kinds.

    Quinzena (FORTNIGHTLY) convention matches ERP: days 1-15 and
    16-<last day of month>.

    ISO-week convention for WEEKLY: Monday is day 1, Sunday is day 7
    (matches ERP's `_period_end_date` which used `isoweekday()`).
    """
    if kind == PeriodKind.DAILY:
        return ref, ref
    if kind == PeriodKind.WEEKLY:
        # ISO week: Monday → Sunday. Sunday end = ref + (7 - isoweekday()).
        end = ref + timedelta(days=7 - ref.isoweekday())
        start = end - timedelta(days=6)
        return start, end
    if kind == PeriodKind.FORTNIGHTLY:
        if ref.day <= 15:
            return ref.replace(day=1), ref.replace(day=15)
        last_day = calendar.monthrange(ref.year, ref.month)[1]
        return ref.replace(day=16), ref.replace(day=last_day)
    if kind == PeriodKind.MONTHLY:
        first = ref.replace(day=1)
        last_day = calendar.monthrange(ref.year, ref.month)[1]
        return first, ref.replace(day=last_day)
    if kind == PeriodKind.QUARTERLY:
        # Q1 = Jan-Mar, Q2 = Apr-Jun, Q3 = Jul-Sep, Q4 = Oct-Dec.
        quarter = (ref.month - 1) // 3 + 1
        start_month = 3 * (quarter - 1) + 1
        end_month = start_month + 2
        last_day = calendar.monthrange(ref.year, end_month)[1]
        return date(ref.year, start_month, 1), date(ref.year, end_month, last_day)
    if kind == PeriodKind.YEARLY:
        return date(ref.year, 1, 1), date(ref.year, 12, 31)
    if kind == PeriodKind.OPEN_ENDED:
        return ref, ref
    raise ValueError(f"Unknown PeriodKind: {kind!r}")


def count_business_days(start: date, end: date) -> int:
    """Mon-Fri count between `start` and `end`, inclusive on both ends.

    Returns 0 if `end < start` (matches "nothing remaining" semantics).
    """
    if end < start:
        return 0
    count = 0
    d = start
    while d <= end:
        if d.isoweekday() <= 5:
            count += 1
        d += timedelta(days=1)
    return count


def working_days_total_in_month(ref: date) -> int:
    """Total Mon-Fri count in the month of `ref`."""
    first, last = period_bounds(PeriodKind.MONTHLY, ref)
    return count_business_days(first, last)


def working_days_remaining_in_week(ref: date) -> int:
    """Mon-Fri count from `ref` through Sunday of the same ISO week.

    Includes `ref` itself if `ref` is a weekday.
    """
    end = ref + timedelta(days=7 - ref.isoweekday())
    return count_business_days(ref, end)


def working_days_remaining_in_month(ref: date) -> int:
    """Mon-Fri count from `ref` through last day of the month.

    Includes `ref` itself if `ref` is a weekday.
    """
    _, last = period_bounds(PeriodKind.MONTHLY, ref)
    return count_business_days(ref, last)


def working_days_total_in_year(ref: date) -> int:
    """Total Mon-Fri count in the year of `ref`."""
    return count_business_days(date(ref.year, 1, 1), date(ref.year, 12, 31))


def working_days_remaining_in_year(ref: date) -> int:
    """Mon-Fri count from `ref` through Dec 31 of the same year."""
    return count_business_days(ref, date(ref.year, 12, 31))


def proportional_target(monthly_target: float, kind: PeriodKind, ref: date) -> int:
    """Translate a monthly target into a per-period target.

    Lifted from ERP's `_calcular_meta_proporcional`. Returns an integer
    (math.ceil of the per-period share); products that need fractional
    targets can re-derive from `working_days_*` themselves.

    DAILY: monthly / business-days-in-month.
    WEEKLY: daily * business-days-remaining-in-week.
    MONTHLY: monthly * business-days-remaining-in-month / business-days-in-month.
    QUARTERLY: monthly * 3 * remaining-in-quarter / total-in-quarter (extension; ERP
        had no QUARTERLY in `_calcular_meta_proporcional`, so we project the same shape).
    YEARLY: monthly * 12 * business-days-remaining-in-year / business-days-in-year.
    FORTNIGHTLY / OPEN_ENDED: monthly target returned unchanged.
    """
    if kind == PeriodKind.DAILY:
        total = working_days_total_in_month(ref)
        return math.ceil(monthly_target / max(total, 1))
    if kind == PeriodKind.WEEKLY:
        total = working_days_total_in_month(ref)
        remaining = working_days_remaining_in_week(ref)
        daily = monthly_target / max(total, 1)
        return math.ceil(daily * remaining)
    if kind == PeriodKind.MONTHLY:
        total = working_days_total_in_month(ref)
        remaining = working_days_remaining_in_month(ref)
        return math.ceil(monthly_target * remaining / max(total, 1))
    if kind == PeriodKind.QUARTERLY:
        # Quarter share of business-days-remaining vs business-days-total in the quarter.
        q_start, q_end = period_bounds(PeriodKind.QUARTERLY, ref)
        total = count_business_days(q_start, q_end)
        remaining = count_business_days(ref, q_end)
        return math.ceil(monthly_target * 3 * remaining / max(total, 1))
    if kind == PeriodKind.YEARLY:
        total = working_days_total_in_year(ref)
        remaining = working_days_remaining_in_year(ref)
        return math.ceil(monthly_target * 12 * remaining / max(total, 1))
    if kind in (PeriodKind.FORTNIGHTLY, PeriodKind.OPEN_ENDED):
        return math.ceil(monthly_target)
    raise ValueError(f"Unknown PeriodKind: {kind!r}")


__all__ = [
    "count_business_days",
    "period_bounds",
    "proportional_target",
    "working_days_remaining_in_month",
    "working_days_remaining_in_week",
    "working_days_remaining_in_year",
    "working_days_total_in_month",
    "working_days_total_in_year",
]
