"""Engagement domain — value objects.

Every rule value (points, caps, badge thresholds) is data the tenant
owner configures — nothing is hardcoded, per
`KB § CONTEXT/07-GAMIFICATION.md § 8` ("Owner-tunable. Scoring rules,
point values, and conversion rates are configurable by the tenant
owner. No hardcoded business logic."). `PointRule` / `BadgeRule` are
therefore plain data: a product loads its own rule rows from wherever
it persists them (a config table, an admin UI) and hands the resulting
`RuleSet` / `BadgeRule` list to the pure functions in `rules.py`.

`EngagementEvent.source` is intentionally a closed `Literal` — the
FOUR channels named in the wave-0 design (`platform`, `whatsapp`,
`event`, `content`). `PointRule.source`/`action` stay plain `str`: the
rule SIDE is data (an owner can point a rule at any action string their
product emits), but the EVENT side is the seed's own typed vocabulary
for where an engagement signal can originate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from noctusai_lib.domain.engagement.errors import EngagementRuleError
from noctusai_lib.domain.metas import Period

EngagementSource = Literal["platform", "whatsapp", "event", "content"]


@dataclass(frozen=True)
class PointRule:
    """One scoring rule: `points` awarded per `(source, action)`, with
    optional caps.

    `daily_cap` — the max total points a single member can earn from
    this rule within one calendar day (UTC date of `occurred_at`).
    `period_cap` — the max total points a single member can earn from
    this rule across whatever history window the caller passes to
    `evaluate()` (the caller decides what "period" means by scoping
    `history` before calling — `evaluate()` itself has no calendar
    opinion beyond the daily-cap's UTC-date comparison, which keeps it
    pure and free of any dependency on `metas.PeriodKind` bucketing).
    """

    source: str
    action: str
    points: int
    daily_cap: int | None = None
    period_cap: int | None = None

    def __post_init__(self) -> None:
        if not self.source:
            raise EngagementRuleError("PointRule.source must be non-empty")
        if not self.action:
            raise EngagementRuleError("PointRule.action must be non-empty")
        if self.points <= 0:
            raise EngagementRuleError(
                f"PointRule.points must be positive, got {self.points!r}"
            )
        if self.daily_cap is not None and self.daily_cap <= 0:
            raise EngagementRuleError(
                f"PointRule.daily_cap must be positive when set, got {self.daily_cap!r}"
            )
        if self.period_cap is not None and self.period_cap <= 0:
            raise EngagementRuleError(
                f"PointRule.period_cap must be positive when set, got {self.period_cap!r}"
            )
        if (
            self.daily_cap is not None
            and self.period_cap is not None
            and self.daily_cap > self.period_cap
        ):
            raise EngagementRuleError(
                "PointRule.daily_cap must not exceed period_cap "
                f"(daily_cap={self.daily_cap!r}, period_cap={self.period_cap!r})"
            )


@dataclass(frozen=True)
class RuleSet:
    """An immutable collection of `PointRule`, indexed by
    `(source, action)`. Construction raises `EngagementRuleError` for a
    duplicate `(source, action)` pair — an ambiguous config (which rule
    wins?) is a fail-fast error, never a silent last-one-wins overwrite.
    """

    rules: tuple[PointRule, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        seen: set[tuple[str, str]] = set()
        for rule in self.rules:
            key = (rule.source, rule.action)
            if key in seen:
                raise EngagementRuleError(
                    "duplicate PointRule for "
                    f"(source={rule.source!r}, action={rule.action!r})"
                )
            seen.add(key)

    @classmethod
    def from_rules(cls, rules: "list[PointRule] | tuple[PointRule, ...]") -> "RuleSet":
        """Convenience constructor — builds from any iterable of rules
        (e.g. a list a caller mapped from config rows)."""
        return cls(tuple(rules))

    def for_action(self, source: str, action: str) -> PointRule | None:
        """The configured rule for `(source, action)`, or `None` if the
        tenant has not configured points for that action — `None` is a
        normal outcome, not an error (see module docstring)."""
        for rule in self.rules:
            if rule.source == source and rule.action == action:
                return rule
        return None


@dataclass(frozen=True)
class EngagementEvent:
    """One observed engagement signal — a member did something,
    somewhere. `idempotency_key` MUST be stable across redeliveries of
    the same underlying event (e.g. a WAHA webhook retry, a duplicate
    platform-side dispatch) — `evaluate()` uses it to detect a replay.
    """

    member_id: str
    source: EngagementSource
    action: str
    occurred_at: datetime
    idempotency_key: str

    def __post_init__(self) -> None:
        if not self.member_id:
            raise EngagementRuleError("EngagementEvent.member_id must be non-empty")
        if not self.action:
            raise EngagementRuleError("EngagementEvent.action must be non-empty")
        if not self.idempotency_key:
            raise EngagementRuleError(
                "EngagementEvent.idempotency_key must be non-empty"
            )
        if self.occurred_at.tzinfo is None:
            raise EngagementRuleError(
                "EngagementEvent.occurred_at must be timezone-aware "
                "(a naive datetime is ambiguous for daily-cap UTC-date comparison)"
            )


@dataclass(frozen=True)
class PointAward:
    """The result of a `PointRule` firing for one `EngagementEvent` —
    also the shape `PointsLedger.record`/`history` persists + returns.
    `points` may be less than `PointRule.points` when a cap partially
    clips the award (see `rules.evaluate`)."""

    member_id: str
    source: str
    action: str
    points: int
    occurred_at: datetime
    idempotency_key: str


@dataclass(frozen=True)
class DuplicateEvent:
    """Non-error result: `evaluate()` returns this instead of a
    `list[PointAward]` when `event.idempotency_key` already appears in
    `history`. A caller branches on `isinstance(result, DuplicateEvent)`
    — the union return type keeps a replayed event from silently
    costing zero points (which would read identically to "no rule
    matched") and keeps the duplicate signal visible for logging/
    metrics rather than swallowed."""

    member_id: str
    idempotency_key: str


@dataclass(frozen=True)
class BadgeRule:
    """A threshold on a metric — data-driven, no lambda conditions (the
    erp `gamificacao_service.py` shape this module replaces hardcoded
    `condicao: lambda stats: ...` per rule; this is the seed-side,
    owner-tunable equivalent: `metric` is a key into whatever totals
    mapping the caller supplies to `rules.evaluate_badges`)."""

    badge_id: str
    metric: str
    threshold: int

    def __post_init__(self) -> None:
        if not self.badge_id:
            raise EngagementRuleError("BadgeRule.badge_id must be non-empty")
        if not self.metric:
            raise EngagementRuleError("BadgeRule.metric must be non-empty")


@dataclass(frozen=True)
class LeaderboardEntry:
    """One ranked row. Ties share a rank (standard competition ranking:
    1, 1, 3 — not 1, 1, 2)."""

    member_id: str
    points: int
    rank: int


@dataclass(frozen=True)
class LeaderboardResult:
    """`leaderboard()`'s return value. Carries the `metas.Period` it was
    computed for — reusing the SAME period value object `metas` uses
    means a product's period selector (day/week/fortnight/month/...)
    drives both the metas goal view and the engagement leaderboard
    without a second, parallel period vocabulary. `leaderboard()` does
    NOT use `period` to filter `totals` — the caller is responsible for
    scoping `totals` to that window (e.g. via
    `metas.periods.period_bounds`) before calling; `period` here is
    carried through purely so the result is self-describing."""

    period: Period
    entries: tuple[LeaderboardEntry, ...]


__all__ = [
    "BadgeRule",
    "DuplicateEvent",
    "EngagementEvent",
    "EngagementSource",
    "LeaderboardEntry",
    "LeaderboardResult",
    "PointAward",
    "PointRule",
    "RuleSet",
]
