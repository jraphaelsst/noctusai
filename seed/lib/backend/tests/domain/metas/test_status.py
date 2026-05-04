"""Tests for `noctusai_lib.domain.metas.status`."""

from __future__ import annotations

import pytest

from noctusai_lib.domain.metas import (
    GoalStatus,
    can_transition,
    from_pt_string,
    next_status,
    to_pt_string,
)


# ── PT mapping ───────────────────────────────────────────────────────


def test_from_pt_string_pf_ativa():
    assert from_pt_string("ativa") == GoalStatus.IN_PROGRESS


def test_from_pt_string_pf_concluida():
    assert from_pt_string("concluida") == GoalStatus.COMPLETED


def test_from_pt_string_erp_no_prazo():
    assert from_pt_string("no_prazo") == GoalStatus.ON_TRACK


def test_from_pt_string_erp_atrasada():
    assert from_pt_string("atrasada") == GoalStatus.AT_RISK


def test_from_pt_string_strips_and_lowercases():
    assert from_pt_string("  ATIVA  ") == GoalStatus.IN_PROGRESS


def test_from_pt_string_unknown_raises():
    with pytest.raises(ValueError, match="Unknown"):
        from_pt_string("not_a_status")


def test_to_pt_string_canonical():
    assert to_pt_string(GoalStatus.IN_PROGRESS) == "ativa"
    assert to_pt_string(GoalStatus.COMPLETED) == "concluida"
    assert to_pt_string(GoalStatus.ON_TRACK) == "no_prazo"
    assert to_pt_string(GoalStatus.AT_RISK) == "atrasada"
    assert to_pt_string(GoalStatus.OVERDUE) == "vencida"
    assert to_pt_string(GoalStatus.PENDING) == "pendente"
    assert to_pt_string(GoalStatus.ABANDONED) == "abandonada"


# ── can_transition ───────────────────────────────────────────────────


def test_can_transition_self_always_true():
    for s in GoalStatus:
        assert can_transition(s, s) is True


def test_can_transition_pending_to_anywhere():
    assert can_transition(GoalStatus.PENDING, GoalStatus.IN_PROGRESS)
    assert can_transition(GoalStatus.PENDING, GoalStatus.COMPLETED)


def test_can_transition_completed_is_terminal():
    assert not can_transition(GoalStatus.COMPLETED, GoalStatus.IN_PROGRESS)
    assert not can_transition(GoalStatus.COMPLETED, GoalStatus.AT_RISK)


def test_can_transition_overdue_only_to_completed_or_abandoned():
    assert can_transition(GoalStatus.OVERDUE, GoalStatus.COMPLETED)
    assert can_transition(GoalStatus.OVERDUE, GoalStatus.ABANDONED)
    assert not can_transition(GoalStatus.OVERDUE, GoalStatus.ON_TRACK)


def test_can_transition_abandoned_can_resume():
    # User restarts a previously-abandoned goal.
    assert can_transition(GoalStatus.ABANDONED, GoalStatus.PENDING)
    assert can_transition(GoalStatus.ABANDONED, GoalStatus.IN_PROGRESS)


# ── next_status ──────────────────────────────────────────────────────


def test_next_status_completed_at_100_pct():
    s = next_status(GoalStatus.IN_PROGRESS, percent_complete=100.0)
    assert s == GoalStatus.COMPLETED


def test_next_status_pending_at_zero_pct():
    s = next_status(GoalStatus.IN_PROGRESS, percent_complete=0.0)
    assert s == GoalStatus.PENDING


def test_next_status_in_progress_without_period_signal():
    s = next_status(GoalStatus.IN_PROGRESS, percent_complete=50.0)
    assert s == GoalStatus.IN_PROGRESS


def test_next_status_on_track_with_period_signal():
    # 60% complete, 40% period remaining → on-track (60 >= 60).
    s = next_status(
        GoalStatus.IN_PROGRESS,
        percent_complete=60.0,
        period_remaining_pct=40.0,
    )
    assert s == GoalStatus.ON_TRACK


def test_next_status_at_risk_with_period_signal():
    s = next_status(
        GoalStatus.IN_PROGRESS,
        percent_complete=30.0,
        period_remaining_pct=40.0,
    )
    assert s == GoalStatus.AT_RISK


def test_next_status_overdue_when_period_ended():
    s = next_status(
        GoalStatus.IN_PROGRESS,
        percent_complete=30.0,
        period_remaining_pct=0.0,
    )
    assert s == GoalStatus.OVERDUE


def test_next_status_completed_is_sticky():
    # Completed → COMPLETED, regardless of progress signal.
    s = next_status(GoalStatus.COMPLETED, percent_complete=10.0)
    assert s == GoalStatus.COMPLETED


def test_next_status_abandoned_is_sticky():
    # Abandoned → ABANDONED until caller explicitly transitions.
    s = next_status(GoalStatus.ABANDONED, percent_complete=50.0)
    assert s == GoalStatus.ABANDONED
