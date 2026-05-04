"""Metas / goals / targets — value objects + enums.

Pure-domain primitives extracted from PF (`metas_service.py`,
`orcamentos_service.py`), ERP (`metas_service.py`, `meta_periodos_service.py`)
and Daily Life (`goals_service.py`) on 2026-05-03 per the N=3 recurrence
rule (`KB § PATTERNS/project-execution.md § 2.7`).

Vocabulary is platform-neutral. Products map their schema names ↔ these
value objects at the service-layer boundary; persistence + RLS stay
product-side.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Optional


class PeriodKind(str, Enum):
    """Period flavor. `OPEN_ENDED` exists for goals without a recurring
    cadence (a savings goal toward a target with no deadline shape).

    String-valued so products can persist the enum directly if they want.
    """

    DAILY = "daily"
    WEEKLY = "weekly"
    FORTNIGHTLY = "fortnightly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    OPEN_ENDED = "open_ended"


class GoalStatus(str, Enum):
    """Status state machine. Products map their own status strings
    (PF "ativa"/"concluida"; ERP "no_prazo"/"atrasada") ↔ this enum
    at the service boundary.

    String-valued so products can persist the enum directly if they want.
    """

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    OVERDUE = "overdue"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


@dataclass(frozen=True)
class Target:
    """The objective amount. `amount` is whatever the product measures
    in (BRL, deals, habit-checkins, kilometers — seed has no opinion).
    """

    amount: float

    def __post_init__(self) -> None:
        # Allow zero (boundary case for habit-check-yes/no goals); reject negative.
        if self.amount < 0:
            raise ValueError(f"Target.amount must be non-negative, got {self.amount}")


@dataclass(frozen=True)
class Period:
    """Time window the goal is tracked against. `kind=OPEN_ENDED` is valid
    when the goal has no recurring shape — `start` is then the goal's
    creation date and `end` is the target completion date (or None).

    `start` and `end` are inclusive (matches PF/ERP semantics).
    """

    kind: PeriodKind
    start: date
    end: Optional[date] = None

    def __post_init__(self) -> None:
        if self.end is not None and self.end < self.start:
            raise ValueError(
                f"Period.end ({self.end}) must be >= start ({self.start})"
            )


@dataclass(frozen=True)
class Contribution:
    """A single increment toward a goal. `amount` is the contribution value;
    `at` is the date it was applied. PF stores these as `meta_contribuicoes`
    rows; daily-life as `checkins`. Seed-side it's a flat value object.
    """

    amount: float
    at: date

    @property
    def yyyymm(self) -> str:
        """`YYYY-MM` key for monthly bucketing in projection math."""
        return self.at.strftime("%Y-%m")


@dataclass(frozen=True)
class Progress:
    """Derived view of (target, current, contributions). Always computed,
    never stored — products may persist `current` for query speed but the
    seed never assumes that's canonical. Call `compute_progress(...)` to
    refresh.
    """

    percent_complete: float
    remaining: float
    projected_completion_date: Optional[date]
    status: GoalStatus


@dataclass(frozen=True)
class Goal:
    """The goal itself. `current` mirrors what the product persists in its
    `valor_atual` / `meta_realizada` / accumulator column; the seed treats
    it as input to `compute_progress`, never as authoritative.

    `id` is opaque — a UUID, an int, anything the product uses. The seed
    never inspects it.
    """

    id: str
    target: Target
    current: float
    period: Period
    status: GoalStatus = GoalStatus.PENDING
    contributions: tuple[Contribution, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProgressTransition:
    """Result of `accumulate_contribution(...)` — the new `current` value
    plus a flag for whether this contribution crossed the completion
    threshold. Products use the flag to fire side-effects (status flip,
    notification, gamification confetti — seed has no opinion).
    """

    new_current: float
    completed: bool
    crossed_threshold_pct: Optional[float] = None


__all__ = [
    "Contribution",
    "Goal",
    "GoalStatus",
    "Period",
    "PeriodKind",
    "Progress",
    "ProgressTransition",
    "Target",
]
