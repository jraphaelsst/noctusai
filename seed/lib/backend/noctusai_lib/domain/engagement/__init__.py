"""Engagement points — pure-domain seed module.

Built 2026-09-16 for `products/community` (wave-0 design, Slice E), per
`KB § CONTEXT/07-GAMIFICATION.md § 8` (owner-tunable rules, nothing
hardcoded). Community is the sole consumer at this phase; erp-imobiliario's
`gamificacao_service.py` (hardcoded `PONTOS_POR_ACAO` dict + lambda badge
conditions) is a second, would-be N=2 candidate for the same shape, but
the re-point is deliberately DEFERRED (triage, not a forced extraction
off a single consumer) — see the `NOC-REMEDIATE[seed-lift]` marker in
that file and `project-history/roadmaps/erp-gamificacao-seed-lift-2026-09.md`.

The seed surface is scoring rules + badge thresholds + leaderboard
ranking + a points ledger. Persistence + RLS + which actions map to
which points stay product-side; the product loads its own `PointRule`/
`BadgeRule` rows and calls the pure functions here.

Public surface:

Value objects / errors:
    `PointRule`, `RuleSet`, `EngagementEvent`, `EngagementSource`,
    `PointAward`, `DuplicateEvent`, `BadgeRule`, `LeaderboardEntry`,
    `LeaderboardResult`, `EngagementRuleError`

Functions (pure):
    `evaluate(event, rules, history) -> list[PointAward] | DuplicateEvent`
    `evaluate_badges(totals, rules) -> list[str]`
    `leaderboard(totals, period) -> LeaderboardResult`

Mountable organ (`mount_engagement` in `noctusai_seed.organs`): `engagement_migration`, `create_engagement_router`,
`OrgPointsLedger` (org-scoped Real, SQL-SUM totals, append-only + LGPD erase), `EngagementService`.

Ledger seam:
    `PointsLedger` (Protocol), `InMemoryPointsLedger`,
    `RealSupabasePointsLedger`, `make_points_ledger`

The shape mirrors `noctusai_lib.domain.payments.event_inbox`: Protocol +
Fake + RealSupabase (shape-only, no migration shipped here) + factory,
idempotent-on-insert via a unique-constraint no-op instead of a raise.
`leaderboard` reuses `noctusai_lib.domain.metas.Period` rather than
inventing a second period vocabulary.
"""
from noctusai_lib.domain.engagement.config import EngagementConfig
from noctusai_lib.domain.engagement.errors import EngagementRuleError
from noctusai_lib.domain.engagement.guards import engagement_guard_probes
from noctusai_lib.domain.engagement.organ_errors import EngagementError
from noctusai_lib.domain.engagement.organ_ledger import FakeOrgPointsLedger, OrgPointsLedger, make_org_points_ledger
from noctusai_lib.domain.engagement.router import create_engagement_router
from noctusai_lib.domain.engagement.service import Actor as EngagementActor
from noctusai_lib.domain.engagement.service import EngagementService
from noctusai_lib.domain.engagement.sql import ENGAGEMENT_MIGRATION_HEADER, engagement_migration
from noctusai_lib.domain.engagement.store import build_engagement_store, engagement_table_specs
from noctusai_lib.domain.engagement.ledger import (
    InMemoryPointsLedger,
    PointsLedger,
    RealSupabasePointsLedger,
    make_points_ledger,
)
from noctusai_lib.domain.engagement.leaderboard import leaderboard
from noctusai_lib.domain.engagement.rules import evaluate, evaluate_badges
from noctusai_lib.domain.engagement.value_objects import (
    BadgeRule,
    DuplicateEvent,
    EngagementEvent,
    EngagementSource,
    LeaderboardEntry,
    LeaderboardResult,
    PointAward,
    PointRule,
    RuleSet,
)

__all__ = [
    # mountable organ (router + migration + org-scoped ledger)
    "ENGAGEMENT_MIGRATION_HEADER",
    "EngagementActor",
    "EngagementConfig",
    "EngagementError",
    "EngagementService",
    "FakeOrgPointsLedger",
    "OrgPointsLedger",
    "build_engagement_store",
    "create_engagement_router",
    "engagement_guard_probes",
    "engagement_migration",
    "engagement_table_specs",
    "make_org_points_ledger",
    # value objects + errors
    "BadgeRule",
    "DuplicateEvent",
    "EngagementEvent",
    "EngagementRuleError",
    "EngagementSource",
    "LeaderboardEntry",
    "LeaderboardResult",
    "PointAward",
    "PointRule",
    "RuleSet",
    # functions
    "evaluate",
    "evaluate_badges",
    "leaderboard",
    # ledger
    "InMemoryPointsLedger",
    "PointsLedger",
    "RealSupabasePointsLedger",
    "make_points_ledger",
]
