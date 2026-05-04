"""Tests for `noctusai_lib.domain.metas.value_objects`."""

from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.metas import (
    Contribution,
    Goal,
    GoalStatus,
    Period,
    PeriodKind,
    Progress,
    ProgressTransition,
    Target,
)


# ── Target ────────────────────────────────────────────────────────────


def test_target_accepts_zero():
    Target(0.0)  # boundary case for habit-check-yes/no goals


def test_target_accepts_positive():
    t = Target(1000.0)
    assert t.amount == 1000.0


def test_target_rejects_negative():
    with pytest.raises(ValueError, match="non-negative"):
        Target(-1.0)


def test_target_is_frozen():
    t = Target(100.0)
    with pytest.raises(Exception):  # FrozenInstanceError
        t.amount = 200.0  # type: ignore[misc]


# ── Period ────────────────────────────────────────────────────────────


def test_period_with_end_after_start_is_valid():
    Period(PeriodKind.MONTHLY, date(2026, 1, 1), date(2026, 1, 31))


def test_period_with_end_before_start_raises():
    with pytest.raises(ValueError, match="must be >= start"):
        Period(PeriodKind.MONTHLY, date(2026, 1, 15), date(2026, 1, 14))


def test_period_with_no_end_is_valid():
    p = Period(PeriodKind.OPEN_ENDED, date(2026, 1, 1))
    assert p.end is None


def test_period_kind_string_values():
    # Products may persist the .value directly.
    assert PeriodKind.DAILY.value == "daily"
    assert PeriodKind.MONTHLY.value == "monthly"
    assert PeriodKind.OPEN_ENDED.value == "open_ended"


# ── Contribution ──────────────────────────────────────────────────────


def test_contribution_yyyymm_formats_correctly():
    c = Contribution(amount=500.0, at=date(2026, 3, 15))
    assert c.yyyymm == "2026-03"


def test_contribution_yyyymm_pads_month():
    c = Contribution(amount=100.0, at=date(2026, 1, 5))
    assert c.yyyymm == "2026-01"


# ── Goal ──────────────────────────────────────────────────────────────


def test_goal_constructs_with_defaults():
    g = Goal(
        id="g1",
        target=Target(1000.0),
        current=250.0,
        period=Period(PeriodKind.MONTHLY, date(2026, 1, 1), date(2026, 1, 31)),
    )
    assert g.status == GoalStatus.PENDING
    assert g.contributions == ()


def test_goal_is_frozen():
    g = Goal(
        id="g1",
        target=Target(1000.0),
        current=0.0,
        period=Period(PeriodKind.MONTHLY, date(2026, 1, 1)),
    )
    with pytest.raises(Exception):  # FrozenInstanceError
        g.current = 500.0  # type: ignore[misc]


# ── Progress + ProgressTransition ─────────────────────────────────────


def test_progress_value_object():
    p = Progress(
        percent_complete=25.0,
        remaining=750.0,
        projected_completion_date=date(2027, 1, 1),
        status=GoalStatus.IN_PROGRESS,
    )
    assert p.percent_complete == 25.0


def test_progress_transition_default():
    pt = ProgressTransition(new_current=500.0, completed=False)
    assert pt.crossed_threshold_pct is None


# ── GoalStatus ────────────────────────────────────────────────────────


def test_goal_status_string_values():
    assert GoalStatus.IN_PROGRESS.value == "in_progress"
    assert GoalStatus.COMPLETED.value == "completed"
    assert GoalStatus.PENDING.value == "pending"


def test_goal_status_round_trips_via_string():
    # Products persisting the string can rehydrate to the enum.
    assert GoalStatus("completed") == GoalStatus.COMPLETED
