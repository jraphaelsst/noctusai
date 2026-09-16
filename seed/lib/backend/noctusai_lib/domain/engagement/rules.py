"""Engagement domain — pure evaluation functions.

Both `evaluate` and `evaluate_badges` are pure: no IO, no wall-clock
reads, no randomness. Every fact they need (the event, the rules, prior
history / current totals) is a parameter — the same purity discipline
`noctusai_lib.domain.metas.progress` and `.payments.subscription` use,
so a product can unit-test its scoring config without a database.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime, timezone

from noctusai_lib.domain.engagement.value_objects import (
    BadgeRule,
    DuplicateEvent,
    EngagementEvent,
    PointAward,
    RuleSet,
)


def _utc_date(moment: datetime) -> date:
    """Calendar date in UTC. `.date()` on an aware datetime returns the date
    in ITS OWN offset, so a -03:00 event near midnight would land on the
    wrong cap day."""
    return moment.astimezone(timezone.utc).date()


def evaluate(
    event: EngagementEvent,
    rules: RuleSet,
    history: Sequence[PointAward],
) -> list[PointAward] | DuplicateEvent:
    """Score one `event` against `rules`, enforcing caps from `history`.

    Idempotency: if `event.idempotency_key` already appears in
    `history` (any member — a key collision across members would be a
    caller bug, but checking globally costs nothing and never produces
    a false negative), this is a replay and `DuplicateEvent` is
    returned — the event is NOT re-scored, and this is not an error.

    No configured rule for `(event.source, event.action)`: returns `[]`
    (zero points is a normal outcome — not every action is scored;
    KB § 07-GAMIFICATION.md § 3).

    Caps: `daily_cap` limits points earned from this rule by this
    member on the same UTC calendar date as `event.occurred_at`.
    `period_cap` limits points earned from this rule by this member
    across the entirety of `history` handed in (the caller pre-scopes
    `history` to represent whatever period it cares about). Awardable
    points are clipped to the tightest remaining cap; if a cap is
    already exhausted the award is `0` and `evaluate` returns `[]`
    rather than a zero-point `PointAward` (a zero-point award would be
    indistinguishable from "no rule matched" downstream, so omitting it
    entirely is the honest signal).
    """
    if any(award.idempotency_key == event.idempotency_key for award in history):
        return DuplicateEvent(
            member_id=event.member_id, idempotency_key=event.idempotency_key
        )

    rule = rules.for_action(event.source, event.action)
    if rule is None:
        return []

    scoped = [
        award
        for award in history
        if award.member_id == event.member_id
        and award.source == event.source
        and award.action == event.action
    ]

    awardable = rule.points

    if rule.daily_cap is not None:
        same_day_total = sum(
            award.points
            for award in scoped
            if _utc_date(award.occurred_at) == _utc_date(event.occurred_at)
        )
        remaining_daily = max(rule.daily_cap - same_day_total, 0)
        awardable = min(awardable, remaining_daily)

    if rule.period_cap is not None:
        period_total = sum(award.points for award in scoped)
        remaining_period = max(rule.period_cap - period_total, 0)
        awardable = min(awardable, remaining_period)

    if awardable <= 0:
        return []

    return [
        PointAward(
            member_id=event.member_id,
            source=event.source,
            action=event.action,
            points=awardable,
            occurred_at=event.occurred_at,
            idempotency_key=event.idempotency_key,
        )
    ]


def evaluate_badges(
    totals: Mapping[str, int], rules: Sequence[BadgeRule]
) -> list[str]:
    """`badge_id`s whose `BadgeRule.threshold` is met/exceeded by the
    matching key in `totals` (e.g. `{"total_pontos": 620, "total_vendas": 6}`).
    A missing key reads as `0` (a badge with no matching metric in
    `totals` simply hasn't been earned yet — not an error). Order
    matches `rules`' order; duplicates are not de-duped (a caller
    passing a rule twice gets the badge_id twice — `rules` is the
    caller's data, `evaluate_badges` does not second-guess it)."""
    return [
        rule.badge_id for rule in rules if totals.get(rule.metric, 0) >= rule.threshold
    ]


__all__ = ["evaluate", "evaluate_badges"]
