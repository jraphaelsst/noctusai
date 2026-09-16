"""Construction-time validation for engagement value objects. Owner-tunable
config (KB § 07-GAMIFICATION.md § 8) must fail fast on a malformed rule —
never silently accept a nonsensical points/cap value."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from noctusai_lib.domain.engagement import (
    EngagementEvent,
    EngagementRuleError,
    PointRule,
    RuleSet,
)


def test_point_rule_rejects_non_positive_points() -> None:
    with pytest.raises(EngagementRuleError):
        PointRule(source="platform", action="login", points=0)


def test_point_rule_rejects_non_positive_daily_cap() -> None:
    with pytest.raises(EngagementRuleError):
        PointRule(source="platform", action="post", points=10, daily_cap=0)


def test_point_rule_rejects_daily_cap_exceeding_period_cap() -> None:
    with pytest.raises(EngagementRuleError):
        PointRule(
            source="platform",
            action="post",
            points=10,
            daily_cap=100,
            period_cap=50,
        )


def test_point_rule_rejects_empty_source_or_action() -> None:
    with pytest.raises(EngagementRuleError):
        PointRule(source="", action="post", points=10)
    with pytest.raises(EngagementRuleError):
        PointRule(source="platform", action="", points=10)


def test_ruleset_rejects_duplicate_source_action_pair() -> None:
    dup = PointRule(source="platform", action="post", points=10)
    dup2 = PointRule(source="platform", action="post", points=20)
    with pytest.raises(EngagementRuleError):
        RuleSet.from_rules([dup, dup2])


def test_ruleset_for_action_returns_none_when_unconfigured() -> None:
    rules = RuleSet.from_rules([PointRule(source="platform", action="post", points=10)])
    assert rules.for_action("platform", "login") is None


def test_ruleset_for_action_finds_matching_rule() -> None:
    rule = PointRule(source="whatsapp", action="reply", points=5)
    rules = RuleSet.from_rules([rule])
    assert rules.for_action("whatsapp", "reply") is rule


def test_engagement_event_rejects_naive_datetime() -> None:
    with pytest.raises(EngagementRuleError):
        EngagementEvent(
            member_id="m1",
            source="platform",
            action="post",
            occurred_at=datetime(2026, 9, 16),  # naive, no tzinfo
            idempotency_key="k1",
        )


def test_engagement_event_rejects_empty_member_id() -> None:
    with pytest.raises(EngagementRuleError):
        EngagementEvent(
            member_id="",
            source="platform",
            action="post",
            occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
            idempotency_key="k1",
        )


def test_engagement_event_rejects_empty_idempotency_key() -> None:
    with pytest.raises(EngagementRuleError):
        EngagementEvent(
            member_id="m1",
            source="platform",
            action="post",
            occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
            idempotency_key="",
        )


def test_engagement_event_accepts_valid_construction() -> None:
    event = EngagementEvent(
        member_id="m1",
        source="whatsapp",
        action="reply",
        occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        idempotency_key="k1",
    )
    assert event.member_id == "m1"
    assert event.source == "whatsapp"
