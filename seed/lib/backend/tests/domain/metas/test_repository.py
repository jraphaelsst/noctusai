"""Tests for `noctusai_lib.domain.metas.repository`."""

from __future__ import annotations

from datetime import date

import pytest

from noctusai_lib.domain.metas import (
    Contribution,
    Goal,
    GoalRepository,
    GoalStatus,
    InMemoryGoalRepository,
    Period,
    PeriodKind,
    Target,
)


def _goal(id: str = "g1", current: float = 0.0, status: GoalStatus = GoalStatus.PENDING) -> Goal:
    return Goal(
        id=id,
        target=Target(1000.0),
        current=current,
        period=Period(PeriodKind.MONTHLY, date(2026, 1, 1), date(2026, 1, 31)),
        status=status,
    )


def test_in_memory_implements_protocol():
    # runtime_checkable Protocol — isinstance check is the seed-wide convention.
    repo = InMemoryGoalRepository()
    assert isinstance(repo, GoalRepository)


def test_in_memory_constructs_empty():
    repo = InMemoryGoalRepository()
    assert repo.list_goals() == []


def test_in_memory_seeded_goals_listable():
    g = _goal()
    repo = InMemoryGoalRepository(goals=[g])
    assert repo.list_goals() == [g]


def test_in_memory_add_goal():
    repo = InMemoryGoalRepository()
    g = _goal()
    repo.add_goal(g)
    assert repo.fetch_goal("g1") == g


def test_in_memory_fetch_missing_raises_lookuperror():
    repo = InMemoryGoalRepository()
    with pytest.raises(LookupError, match="not found"):
        repo.fetch_goal("does-not-exist")


def test_in_memory_list_filtered_by_status():
    repo = InMemoryGoalRepository(
        goals=[
            _goal(id="g1", status=GoalStatus.IN_PROGRESS),
            _goal(id="g2", status=GoalStatus.COMPLETED),
            _goal(id="g3", status=GoalStatus.IN_PROGRESS),
        ]
    )
    in_progress = repo.list_goals(status=GoalStatus.IN_PROGRESS)
    assert {g.id for g in in_progress} == {"g1", "g3"}
    completed = repo.list_goals(status=GoalStatus.COMPLETED)
    assert [g.id for g in completed] == ["g2"]


def test_in_memory_update_goal_current():
    repo = InMemoryGoalRepository(goals=[_goal()])
    new = repo.update_goal("g1", current=500.0)
    assert new.current == 500.0
    assert repo.fetch_goal("g1").current == 500.0


def test_in_memory_update_goal_status():
    repo = InMemoryGoalRepository(goals=[_goal()])
    new = repo.update_goal("g1", status=GoalStatus.COMPLETED)
    assert new.status == GoalStatus.COMPLETED


def test_in_memory_update_missing_raises():
    repo = InMemoryGoalRepository()
    with pytest.raises(LookupError):
        repo.update_goal("missing", current=100.0)


def test_in_memory_record_contribution_appends():
    repo = InMemoryGoalRepository(goals=[_goal()])
    c = Contribution(amount=100.0, at=date(2026, 1, 5))
    repo.record_contribution("g1", c)
    g = repo.fetch_goal("g1")
    assert g.contributions == (c,)


def test_in_memory_record_contribution_preserves_history():
    repo = InMemoryGoalRepository(goals=[_goal()])
    c1 = Contribution(amount=100.0, at=date(2026, 1, 5))
    c2 = Contribution(amount=200.0, at=date(2026, 1, 15))
    repo.record_contribution("g1", c1)
    repo.record_contribution("g1", c2)
    assert repo.fetch_goal("g1").contributions == (c1, c2)


def test_in_memory_record_contribution_missing_raises():
    repo = InMemoryGoalRepository()
    with pytest.raises(LookupError):
        repo.record_contribution("missing", Contribution(amount=1.0, at=date(2026, 1, 5)))
