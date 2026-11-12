"""Assignment -- who owns a lead / card / ticket: teams, members, strategies, capacity, out-of-office. An L1 seed organ.

One org picks ONE strategy (`round_robin` · `by_team` · `by_source` · `by_unit` · `manual`, or a host-registered custom name);
teams hold members with a rotation `position`, an optional `capacity` (max open subjects) and an out-of-office window; rules map a
`source` / `unit` value to a team. `keep_last` sends a returning subject back to its current owner while that person is eligible.
Every assignment or reassignment is ONE transaction that writes the assignment row, the team's cursor, an immutable intent-named
event (`asg_events`: assigned / reassigned / unassigned / closed / no_candidate) and -- when the host named its card table -- the
funnel's `responsavel_field`. Formalizes social-wiring `julia_equipes_service` + erp-imobiliario `distribuicao`
(KB § PATTERNS/backend/assignment-organ.md; roadmap crm-cms-erp-vertical-seeds-2026-11 W1-4).

Mount it from a product:

    cfg = AssignmentConfig.for_funnel("monica", funnel_cfg)               # writes funnel_cfg.responsavel_field
    sql = assignment_migration(cfg, "monica")                              # -> migrations/0NN_assignment.sql (noctus.dev.render_organ_migration)
    organ = mount_assignment(schema="monica", auth_dependency=..., get_admin_client=..., get_core_client=..., cfg=cfg,
                             strategy_hooks={"by_plantao": my_hook})       # optional: the named custom-strategy seam
    # on lead intake:  service.assign(org_id, subject_kind="card", subject_id=card_id, source="meta_ads")
"""
from .config import AssignmentConfig
from .directory import CoreUserDirectory, FakeUserDirectory, UserDirectory
from .errors import AssignmentError, CapacityFull, SubjectNotFound
from .guards import assignment_guard_probes
from .router import make_assignment_router
from .service import Actor, AssignmentService
from .sql import APPEND_ONLY_TABLES, ASSIGNMENT_MIGRATION_HEADER, ASSIGNMENT_TABLES, assignment_migration
from .store import (
    AssignmentLedger,
    AssignmentStore,
    FakeAssignmentLedger,
    SupabaseAssignmentLedger,
    build_assignment_store,
    table_specs,
)
from .strategy import (
    AssignContext,
    HookPickError,
    MemberState,
    NoPick,
    Pick,
    Rule,
    Settings,
    Snapshot,
    StrategyHook,
    TeamState,
    decide,
)
from .types import BUILTIN_STRATEGIES, EVENT_KINDS, RULE_KINDS

__all__ = [
    "APPEND_ONLY_TABLES",
    "ASSIGNMENT_MIGRATION_HEADER",
    "ASSIGNMENT_TABLES",
    "Actor",
    "AssignContext",
    "AssignmentConfig",
    "AssignmentError",
    "AssignmentLedger",
    "AssignmentService",
    "AssignmentStore",
    "BUILTIN_STRATEGIES",
    "CapacityFull",
    "CoreUserDirectory",
    "EVENT_KINDS",
    "FakeAssignmentLedger",
    "FakeUserDirectory",
    "HookPickError",
    "MemberState",
    "NoPick",
    "Pick",
    "RULE_KINDS",
    "Rule",
    "Settings",
    "Snapshot",
    "StrategyHook",
    "SubjectNotFound",
    "SupabaseAssignmentLedger",
    "TeamState",
    "UserDirectory",
    "assignment_guard_probes",
    "assignment_migration",
    "build_assignment_store",
    "decide",
    "make_assignment_router",
    "table_specs",
]
