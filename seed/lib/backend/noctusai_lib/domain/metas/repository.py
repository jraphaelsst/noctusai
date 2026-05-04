"""Repository seam — Protocol over Callable.

When a consumer (a product, a seed-level integration test) wants to
inject a goal-storage backend, this is the seam. Per
`KB § PATTERNS/seed-lib-layout.md § Consumer-injection seams — Protocol
over Callable`.

`InMemoryGoalRepository` is provided as a default for tests + seed-side
demos; products keep their own Supabase-backed implementations and never
import the in-memory class in production.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from noctusai_lib.domain.metas.value_objects import (
    Contribution,
    Goal,
    GoalStatus,
)


@runtime_checkable
class GoalRepository(Protocol):
    """Storage seam for goals + contributions.

    Implementations are responsible for org/user scoping (RLS); the seed
    never looks at access control. Methods raise `LookupError` when a
    goal is not found, to match seed-wide convention.
    """

    def fetch_goal(self, goal_id: str) -> Goal:
        """Return the goal or raise LookupError."""
        ...

    def list_goals(self, *, status: GoalStatus | None = None) -> list[Goal]:
        """Return goals, optionally filtered by status."""
        ...

    def update_goal(
        self,
        goal_id: str,
        *,
        current: float | None = None,
        status: GoalStatus | None = None,
    ) -> Goal:
        """Patch the goal's `current` and/or `status`. Raises LookupError."""
        ...

    def record_contribution(self, goal_id: str, contribution: Contribution) -> None:
        """Append a contribution. Raises LookupError if goal missing."""
        ...


class InMemoryGoalRepository:
    """Reference / testing implementation. Not for production.

    Stores goals + contributions in dicts. Concurrency-unsafe by design;
    suitable for unit tests and seed-side demos.
    """

    def __init__(self, goals: list[Goal] | None = None) -> None:
        self._goals: dict[str, Goal] = {g.id: g for g in (goals or [])}

    def add_goal(self, goal: Goal) -> None:
        """Test helper — seed a goal into the repo."""
        self._goals[goal.id] = goal

    def fetch_goal(self, goal_id: str) -> Goal:
        try:
            return self._goals[goal_id]
        except KeyError:
            raise LookupError(f"goal not found: {goal_id!r}") from None

    def list_goals(self, *, status: GoalStatus | None = None) -> list[Goal]:
        if status is None:
            return list(self._goals.values())
        return [g for g in self._goals.values() if g.status == status]

    def update_goal(
        self,
        goal_id: str,
        *,
        current: float | None = None,
        status: GoalStatus | None = None,
    ) -> Goal:
        goal = self.fetch_goal(goal_id)
        from dataclasses import replace

        kwargs: dict = {}
        if current is not None:
            kwargs["current"] = current
        if status is not None:
            kwargs["status"] = status
        new = replace(goal, **kwargs) if kwargs else goal
        self._goals[goal_id] = new
        return new

    def record_contribution(self, goal_id: str, contribution: Contribution) -> None:
        goal = self.fetch_goal(goal_id)
        from dataclasses import replace

        new = replace(goal, contributions=goal.contributions + (contribution,))
        self._goals[goal_id] = new


__all__ = [
    "GoalRepository",
    "InMemoryGoalRepository",
]
