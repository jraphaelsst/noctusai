"""Metas / goals / targets — pure-domain seed module.

Lifted 2026-05-03 from PF (`metas_service.py`, `orcamentos_service.py`),
ERP (`metas_service.py`, `meta_periodos_service.py`), and Daily Life
(`goals_service.py`) per N=3 MUST-FORMALIZE
(`KB § PATTERNS/project-execution.md § 2.7`).

The seed surface is the cross-cutting math + state machine + value
objects. Persistence + RLS + schema-naming + status vocabulary stay
product-side; products map to/from these seed value objects at the
service-layer boundary.

Public surface:

Value objects:
    `Goal`, `Target`, `Progress`, `Period`, `Contribution`,
    `ProgressTransition`

Enums:
    `GoalStatus`, `PeriodKind`

Functions:
    `compute_progress`, `accumulate_contribution`, `project_completion_date`
    `period_bounds`, `count_business_days`, `proportional_target`
    `working_days_*` family
    `next_status`, `can_transition`, `from_pt_string`, `to_pt_string`

Repository seam:
    `GoalRepository` (Protocol), `InMemoryGoalRepository` (default)

See `KB § PATTERNS/metas-seed.md` for the wiring recipe + status mapping
table. The shape mirrors `noctusai_lib.domain.scheduling`: value objects
+ Protocols + defaults + pure-function helpers, no IO.
"""

from noctusai_lib.domain.metas.periods import (
    count_business_days,
    period_bounds,
    proportional_target,
    working_days_remaining_in_month,
    working_days_remaining_in_week,
    working_days_remaining_in_year,
    working_days_total_in_month,
    working_days_total_in_year,
)
from noctusai_lib.domain.metas.progress import (
    accumulate_contribution,
    compute_progress,
    project_completion_date,
)
from noctusai_lib.domain.metas.repository import (
    GoalRepository,
    InMemoryGoalRepository,
)
from noctusai_lib.domain.metas.status import (
    can_transition,
    from_pt_string,
    next_status,
    to_pt_string,
)
from noctusai_lib.domain.metas.value_objects import (
    Contribution,
    Goal,
    GoalStatus,
    Period,
    PeriodKind,
    Progress,
    ProgressTransition,
    Target,
)

__all__ = [
    # value objects + enums
    "Contribution",
    "Goal",
    "GoalStatus",
    "GoalRepository",
    "InMemoryGoalRepository",
    "Period",
    "PeriodKind",
    "Progress",
    "ProgressTransition",
    "Target",
    # progress
    "accumulate_contribution",
    "compute_progress",
    "project_completion_date",
    # periods
    "count_business_days",
    "period_bounds",
    "proportional_target",
    "working_days_remaining_in_month",
    "working_days_remaining_in_week",
    "working_days_remaining_in_year",
    "working_days_total_in_month",
    "working_days_total_in_year",
    # status
    "can_transition",
    "from_pt_string",
    "next_status",
    "to_pt_string",
]
