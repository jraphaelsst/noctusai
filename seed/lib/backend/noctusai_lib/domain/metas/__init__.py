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
    `GoalRepository` (Protocol), `InMemoryGoalRepository` (tests), `SupabaseGoalRepository` + `make_goal_repository` (Real)

Mountable organ (`mount_metas` in `noctusai_seed.organs`): `metas_migration`, `create_metas_router`, `MetasService`,
`MetasStore` (Fake + Supabase), `MetasConfig`. Periods, teams, goals at three levels (individual / team / company),
point rules, scoring events, rankings and immutable period closings.

See `KB § PATTERNS/metas-seed.md` for the wiring recipe + status mapping
table. The shape mirrors `noctusai_lib.domain.scheduling`: value objects
+ Protocols + defaults + pure-function helpers, no IO.
"""

from noctusai_lib.domain.metas.config import EventType, GoalCategory, MetasConfig, Modality, RuleSeed
from noctusai_lib.domain.metas.errors import MetasError
from noctusai_lib.domain.metas.goal_repository import SupabaseGoalRepository, make_goal_repository
from noctusai_lib.domain.metas.guards import metas_guard_probes
from noctusai_lib.domain.metas.router import create_metas_router
from noctusai_lib.domain.metas.service import Actor as MetasActor
from noctusai_lib.domain.metas.service import MetasService
from noctusai_lib.domain.metas.sql import METAS_MIGRATION_HEADER, metas_migration
from noctusai_lib.domain.metas.store import FakeMetasStore, MetasStore, SupabaseMetasStore, build_metas_store, metas_table_specs
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
    # mountable organ (router + migration + Real repositories)
    "EventType",
    "FakeMetasStore",
    "GoalCategory",
    "METAS_MIGRATION_HEADER",
    "MetasActor",
    "MetasConfig",
    "MetasError",
    "MetasService",
    "MetasStore",
    "Modality",
    "RuleSeed",
    "SupabaseGoalRepository",
    "SupabaseMetasStore",
    "build_metas_store",
    "create_metas_router",
    "make_goal_repository",
    "metas_guard_probes",
    "metas_migration",
    "metas_table_specs",
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
