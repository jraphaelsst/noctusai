"""Progress derivation — pure functions over (target, current, contributions).

Lifted from PF (`metas_service.obter_progresso`) and Daily Life
(`goals_service.register_checkin`) on 2026-05-03.

Public surface:
- `compute_progress(target, current, *, contributions=(), today=None) -> Progress`
- `accumulate_contribution(target, current, increment) -> ProgressTransition`
- `project_completion_date(target, current, contributions, today) -> date | None`
"""

from __future__ import annotations

import calendar
from collections.abc import Iterable
from datetime import date

from noctusai_lib.domain.metas.value_objects import (
    Contribution,
    GoalStatus,
    Progress,
    ProgressTransition,
    Target,
)


def _percent_complete(target: float, current: float) -> float:
    """Capped at 100; 0 when target is 0 (avoids ZeroDivisionError)."""
    if target <= 0:
        return 0.0
    return min(current / target * 100.0, 100.0)


def _add_months(ref: date, months: int) -> date:
    """Stdlib-only month math (avoids the `dateutil` 3rd-party dep PF uses).

    Clamps to last-day-of-month when the source day doesn't exist in the
    target month (Jan-31 + 1 month → Feb-28/29).
    """
    if months == 0:
        return ref
    new_month_index = ref.month - 1 + months
    new_year = ref.year + new_month_index // 12
    new_month = new_month_index % 12 + 1
    last_day_in_new_month = calendar.monthrange(new_year, new_month)[1]
    new_day = min(ref.day, last_day_in_new_month)
    return date(new_year, new_month, new_day)


def project_completion_date(
    target: float,
    current: float,
    contributions: Iterable[Contribution],
    today: date,
) -> date | None:
    """Estimate when the goal will hit `target` if monthly cadence holds.

    Lifted verbatim (math preserved) from PF `obter_progresso` — `total_contrib /
    months_with_contrib` gives a monthly average; remaining / monthly average
    gives the ETA in months. None when there's no contribution history,
    when current already meets target, or when monthly average is zero.
    """
    if current >= target:
        return None
    contribs = list(contributions)
    if not contribs:
        return None
    total = sum(c.amount for c in contribs)
    months_with_contrib = len({c.yyyymm for c in contribs})
    if months_with_contrib == 0:
        return None
    monthly_avg = total / months_with_contrib
    if monthly_avg <= 0:
        return None
    months_remaining = (target - current) / monthly_avg
    return _add_months(today, int(months_remaining))


def compute_progress(
    target: Target,
    current: float,
    *,
    contributions: Iterable[Contribution] = (),
    today: date | None = None,
    period_remaining_pct: float | None = None,
) -> Progress:
    """Derive a Progress view from inputs. None of these are persisted on
    Progress — products may persist `current` for query speed but the
    Progress object is always recomputed.

    `period_remaining_pct` is optional: when provided, status uses it to
    distinguish on-track vs at-risk (matches ERP's "no_prazo" / "atrasada"
    framing). Without it, status is the simpler completed / in-progress
    pair (matches PF / daily-life today).
    """
    pct = _percent_complete(target.amount, current)
    remaining = max(target.amount - current, 0.0)
    eta = (
        project_completion_date(target.amount, current, contributions, today)
        if today is not None
        else None
    )

    if pct >= 100.0:
        status = GoalStatus.COMPLETED
    elif current <= 0:
        status = GoalStatus.PENDING
    elif period_remaining_pct is None:
        status = GoalStatus.IN_PROGRESS
    elif pct >= (100.0 - period_remaining_pct):
        # Progress is keeping pace with time elapsed → on track.
        status = GoalStatus.ON_TRACK
    elif period_remaining_pct <= 0:
        # Period ended without hitting target → overdue.
        status = GoalStatus.OVERDUE
    else:
        status = GoalStatus.AT_RISK

    return Progress(
        percent_complete=pct,
        remaining=remaining,
        projected_completion_date=eta,
        status=status,
    )


def accumulate_contribution(
    target: float,
    current: float,
    increment: float,
) -> ProgressTransition:
    """Apply a single contribution. Returns the new value, whether the
    threshold was crossed in this transition, and the percent the value
    actually crossed at (for milestone notifications).

    Mirrors PF's `adicionar_contribuicao` (which sets `status = "concluida"`
    when `valor_atual >= valor_alvo`) and Daily Life's `register_checkin`
    (which accumulates check-in values into `valor_atual`).
    """
    if target < 0:
        raise ValueError(f"target must be non-negative, got {target}")
    new_current = current + increment
    completed = current < target <= new_current

    crossed_threshold_pct: float | None = None
    if target > 0:
        # Detect crossings of 25 / 50 / 75 / 100 percent.
        new_pct = new_current / target * 100.0
        old_pct = current / target * 100.0
        for milestone in (25.0, 50.0, 75.0, 100.0):
            if old_pct < milestone <= new_pct:
                crossed_threshold_pct = milestone
                break

    return ProgressTransition(
        new_current=new_current,
        completed=completed,
        crossed_threshold_pct=crossed_threshold_pct,
    )


__all__ = [
    "accumulate_contribution",
    "compute_progress",
    "project_completion_date",
]
