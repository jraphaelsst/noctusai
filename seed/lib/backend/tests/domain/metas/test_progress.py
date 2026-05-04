"""Tests for `noctusai_lib.domain.metas.progress`."""

from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.metas import (
    Contribution,
    GoalStatus,
    Target,
    accumulate_contribution,
    compute_progress,
    project_completion_date,
)


# ── compute_progress ─────────────────────────────────────────────────


def test_compute_progress_zero_target_returns_zero_pct():
    # PF semantics: percent capped + zero-target safety.
    p = compute_progress(target=Target(0), current=0)
    assert p.percent_complete == 0.0
    assert p.remaining == 0.0


def test_compute_progress_25_pct():
    # PF financial goal: target 50_000, current 12_500 → 25%.
    p = compute_progress(target=Target(50_000), current=12_500)
    assert p.percent_complete == 25.0
    assert p.remaining == 37_500.0
    assert p.status == GoalStatus.IN_PROGRESS


def test_compute_progress_capped_at_100():
    # PF: min(atual/alvo*100, 100).
    p = compute_progress(target=Target(100), current=150)
    assert p.percent_complete == 100.0
    assert p.remaining == 0.0  # max(target-current, 0)
    assert p.status == GoalStatus.COMPLETED


def test_compute_progress_pending_when_zero_current():
    p = compute_progress(target=Target(1000), current=0)
    assert p.status == GoalStatus.PENDING


def test_compute_progress_completed_when_at_target():
    p = compute_progress(target=Target(1000), current=1000)
    assert p.status == GoalStatus.COMPLETED


def test_compute_progress_with_period_remaining_on_track():
    # 60% complete, 40% of period remaining → on-track (60 >= 100-40 = 60).
    p = compute_progress(
        target=Target(1000),
        current=600,
        period_remaining_pct=40.0,
    )
    assert p.status == GoalStatus.ON_TRACK


def test_compute_progress_with_period_remaining_at_risk():
    # 30% complete, 40% of period remaining → at-risk (30 < 60).
    p = compute_progress(
        target=Target(1000),
        current=300,
        period_remaining_pct=40.0,
    )
    assert p.status == GoalStatus.AT_RISK


def test_compute_progress_with_period_remaining_overdue():
    # 30% complete, 0% of period remaining → overdue.
    p = compute_progress(
        target=Target(1000),
        current=300,
        period_remaining_pct=0.0,
    )
    assert p.status == GoalStatus.OVERDUE


def test_compute_progress_eta_present_when_history_supports():
    # Two months of contributions, room to project.
    contribs = [
        Contribution(amount=1000, at=date(2026, 1, 15)),
        Contribution(amount=1000, at=date(2026, 2, 15)),
    ]
    p = compute_progress(
        target=Target(10_000),
        current=2_000,
        contributions=contribs,
        today=date(2026, 3, 1),
    )
    assert p.projected_completion_date is not None
    # Monthly avg 1000 → 8 months remaining → ~2026-11.
    assert p.projected_completion_date.year in (2026, 2027)


def test_compute_progress_no_today_means_no_eta():
    contribs = [Contribution(amount=1000, at=date(2026, 1, 15))]
    p = compute_progress(
        target=Target(10_000),
        current=2_000,
        contributions=contribs,
        today=None,
    )
    assert p.projected_completion_date is None


# ── project_completion_date ──────────────────────────────────────────


def test_project_completion_date_no_history_returns_none():
    assert project_completion_date(1000, 250, [], date(2026, 5, 1)) is None


def test_project_completion_date_already_complete_returns_none():
    contribs = [Contribution(amount=500, at=date(2026, 1, 15))]
    assert project_completion_date(1000, 1000, contribs, date(2026, 5, 1)) is None


def test_project_completion_date_zero_avg_returns_none():
    # Single zero-amount contribution: monthly avg 0.
    contribs = [Contribution(amount=0, at=date(2026, 1, 15))]
    assert project_completion_date(1000, 0, contribs, date(2026, 5, 1)) is None


def test_project_completion_date_calculates_eta():
    # Total $1000 over 2 distinct months → monthly avg $500. Remaining
    # $5000 / $500 = 10 months. Today 2026-05-01 + 10 months = 2027-03-01.
    contribs = [
        Contribution(amount=500, at=date(2026, 1, 15)),
        Contribution(amount=500, at=date(2026, 2, 15)),
    ]
    eta = project_completion_date(10_000, 5_000, contribs, date(2026, 5, 1))
    assert eta is not None
    assert eta == date(2027, 3, 1)


def test_project_completion_date_handles_month_overflow():
    # 1 month with a single contribution; from late January with month
    # overflow at end-of-Feb.
    contribs = [Contribution(amount=200, at=date(2026, 1, 31))]
    # Avg 200/month, remaining 200, ~1 month from 2026-01-31. Stdlib clamp
    # to 2026-02-28 (Feb has no 31st).
    eta = project_completion_date(400, 200, contribs, date(2026, 1, 31))
    assert eta is not None
    assert eta == date(2026, 2, 28)


def test_project_completion_date_groups_by_yyyymm():
    # 5 contributions in 2 months → monthly avg = total/2, not total/5.
    contribs = [
        Contribution(amount=100, at=date(2026, 1, 5)),
        Contribution(amount=100, at=date(2026, 1, 15)),
        Contribution(amount=100, at=date(2026, 1, 25)),
        Contribution(amount=100, at=date(2026, 2, 5)),
        Contribution(amount=100, at=date(2026, 2, 15)),
    ]
    # total=500, months=2 → avg=250/month, remaining=500, months=2.
    eta = project_completion_date(1000, 500, contribs, date(2026, 3, 1))
    assert eta == date(2026, 5, 1)


# ── accumulate_contribution ──────────────────────────────────────────


def test_accumulate_contribution_simple_increment():
    pt = accumulate_contribution(target=30, current=12, increment=1)
    assert pt.new_current == 13
    assert pt.completed is False


def test_accumulate_contribution_completes_at_threshold():
    # PF: status = "concluida" when valor_atual >= valor_alvo.
    pt = accumulate_contribution(target=100, current=99, increment=1)
    assert pt.new_current == 100
    assert pt.completed is True


def test_accumulate_contribution_overflow_still_completes():
    pt = accumulate_contribution(target=100, current=50, increment=200)
    assert pt.new_current == 250
    assert pt.completed is True


def test_accumulate_contribution_already_complete_does_not_recomplete():
    # If you contribute again to an already-complete goal, completed=False
    # (the *transition* didn't cross the threshold; goal was already done).
    pt = accumulate_contribution(target=100, current=150, increment=10)
    assert pt.new_current == 160
    assert pt.completed is False


def test_accumulate_contribution_crossed_threshold_25():
    pt = accumulate_contribution(target=100, current=20, increment=10)
    assert pt.crossed_threshold_pct == 25.0


def test_accumulate_contribution_crossed_threshold_50():
    pt = accumulate_contribution(target=100, current=40, increment=15)
    assert pt.crossed_threshold_pct == 50.0


def test_accumulate_contribution_no_threshold_crossed():
    pt = accumulate_contribution(target=100, current=60, increment=5)
    assert pt.crossed_threshold_pct is None


def test_accumulate_contribution_crossed_threshold_100_alongside_completed():
    pt = accumulate_contribution(target=100, current=80, increment=25)
    assert pt.completed is True
    assert pt.crossed_threshold_pct == 100.0


def test_accumulate_contribution_zero_target_no_threshold():
    pt = accumulate_contribution(target=0, current=0, increment=1)
    assert pt.new_current == 1
    assert pt.crossed_threshold_pct is None
    assert pt.completed is False  # target=0 means no completion semantics


def test_accumulate_contribution_negative_target_raises():
    with pytest.raises(ValueError, match="non-negative"):
        accumulate_contribution(target=-1, current=0, increment=1)
