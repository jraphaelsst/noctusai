"""`evaluate` — the pure scoring function. Idempotency + caps are the two
correctness-critical behaviors (double-counting an engagement point, or
letting a cap silently overflow, is exactly the class of bug a hardcoded
per-product `gamificacao_service.py` would have shipped uncaught)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from noctusai_lib.domain.engagement import (
    BadgeRule,
    DuplicateEvent,
    EngagementEvent,
    PointAward,
    PointRule,
    RuleSet,
    evaluate,
    evaluate_badges,
)


def _event(
    *,
    member_id: str = "m1",
    source: str = "platform",
    action: str = "post",
    occurred_at: datetime,
    idempotency_key: str,
) -> EngagementEvent:
    return EngagementEvent(
        member_id=member_id,
        source=source,
        action=action,
        occurred_at=occurred_at,
        idempotency_key=idempotency_key,
    )


def _award(
    *,
    member_id: str = "m1",
    source: str = "platform",
    action: str = "post",
    points: int,
    occurred_at: datetime,
    idempotency_key: str,
) -> PointAward:
    return PointAward(
        member_id=member_id,
        source=source,
        action=action,
        points=points,
        occurred_at=occurred_at,
        idempotency_key=idempotency_key,
    )


def test_no_configured_rule_awards_nothing_not_an_error() -> None:
    rules = RuleSet.from_rules([PointRule(source="platform", action="post", points=10)])
    event = _event(
        action="login",  # no rule for (platform, login)
        occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc),
        idempotency_key="k1",
    )
    assert evaluate(event, rules, history=[]) == []


def test_first_delivery_is_awarded_full_points() -> None:
    rules = RuleSet.from_rules([PointRule(source="platform", action="post", points=10)])
    event = _event(
        occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc), idempotency_key="k1"
    )
    result = evaluate(event, rules, history=[])
    assert result == [
        PointAward(
            member_id="m1",
            source="platform",
            action="post",
            points=10,
            occurred_at=event.occurred_at,
            idempotency_key="k1",
        )
    ]


def test_duplicate_idempotency_key_returns_duplicate_event_not_award() -> None:
    """THE idempotency test: a replayed event (same idempotency_key
    already in history) must be a proven no-op result, never a second
    award and never a silently-swallowed empty list indistinguishable
    from 'no rule matched'."""
    rules = RuleSet.from_rules([PointRule(source="platform", action="post", points=10)])
    occurred_at = datetime(2026, 9, 16, tzinfo=timezone.utc)
    event = _event(occurred_at=occurred_at, idempotency_key="dup-1")
    history = [_award(points=10, occurred_at=occurred_at, idempotency_key="dup-1")]

    result = evaluate(event, rules, history)

    assert isinstance(result, DuplicateEvent)
    assert result.member_id == "m1"
    assert result.idempotency_key == "dup-1"


def test_duplicate_check_does_not_raise() -> None:
    rules = RuleSet.from_rules([PointRule(source="platform", action="post", points=10)])
    occurred_at = datetime(2026, 9, 16, tzinfo=timezone.utc)
    event = _event(occurred_at=occurred_at, idempotency_key="dup-2")
    history = [_award(points=10, occurred_at=occurred_at, idempotency_key="dup-2")]
    try:
        evaluate(event, rules, history)
    except Exception as exc:  # noqa: BLE001 - explicitly proving no raise
        raise AssertionError(
            f"duplicate evaluate() raised {exc!r} instead of returning DuplicateEvent"
        ) from exc


def test_daily_cap_clips_award_when_partially_exhausted() -> None:
    rules = RuleSet.from_rules(
        [PointRule(source="platform", action="post", points=10, daily_cap=15)]
    )
    day = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)
    history = [_award(points=10, occurred_at=day, idempotency_key="k1")]
    event = _event(
        occurred_at=datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc),
        idempotency_key="k2",
    )
    result = evaluate(event, rules, history)
    assert result == [
        PointAward(
            member_id="m1",
            source="platform",
            action="post",
            points=5,  # 15 - 10 already awarded today
            occurred_at=event.occurred_at,
            idempotency_key="k2",
        )
    ]


def test_daily_cap_fully_exhausted_awards_nothing() -> None:
    rules = RuleSet.from_rules(
        [PointRule(source="platform", action="post", points=10, daily_cap=10)]
    )
    day = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)
    history = [_award(points=10, occurred_at=day, idempotency_key="k1")]
    event = _event(
        occurred_at=datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc),
        idempotency_key="k2",
    )
    assert evaluate(event, rules, history) == []


def test_daily_cap_groups_by_utc_date_not_the_events_local_date() -> None:
    # 23:30 at -03:00 (Brazil) on the 15th is 02:30 UTC on the 16th, the same
    # UTC day as the existing award, so the cap is already exhausted.
    rules = RuleSet.from_rules(
        [PointRule(source="platform", action="post", points=10, daily_cap=10)]
    )
    history = [
        _award(
            points=10,
            occurred_at=datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc),
            idempotency_key="k1",
        )
    ]
    brt = timezone(timedelta(hours=-3))
    event = _event(
        occurred_at=datetime(2026, 9, 15, 23, 30, tzinfo=brt),
        idempotency_key="k2",
    )
    assert evaluate(event, rules, history) == []


def test_daily_cap_resets_on_a_different_utc_date() -> None:
    rules = RuleSet.from_rules(
        [PointRule(source="platform", action="post", points=10, daily_cap=10)]
    )
    history = [
        _award(
            points=10,
            occurred_at=datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc),
            idempotency_key="k1",
        )
    ]
    event = _event(
        occurred_at=datetime(2026, 9, 17, 8, 0, tzinfo=timezone.utc),  # next day
        idempotency_key="k2",
    )
    result = evaluate(event, rules, history)
    assert result == [
        PointAward(
            member_id="m1",
            source="platform",
            action="post",
            points=10,
            occurred_at=event.occurred_at,
            idempotency_key="k2",
        )
    ]


def test_period_cap_clips_across_full_history_window() -> None:
    """`period_cap` applies to the entirety of `history` the caller
    passes — the caller pre-scopes `history` to whatever window (week,
    fortnight, month) represents "the period" for their product."""
    rules = RuleSet.from_rules(
        [PointRule(source="platform", action="post", points=10, period_cap=25)]
    )
    history = [
        _award(
            points=10,
            occurred_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
            idempotency_key="k1",
        ),
        _award(
            points=10,
            occurred_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
            idempotency_key="k2",
        ),
    ]
    event = _event(
        occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc), idempotency_key="k3"
    )
    result = evaluate(event, rules, history)
    assert result == [
        PointAward(
            member_id="m1",
            source="platform",
            action="post",
            points=5,  # 25 - 20 already awarded this period
            occurred_at=event.occurred_at,
            idempotency_key="k3",
        )
    ]


def test_period_cap_does_not_leak_across_other_members_or_actions() -> None:
    rules = RuleSet.from_rules(
        [PointRule(source="platform", action="post", points=10, period_cap=10)]
    )
    history = [
        _award(
            member_id="other-member",
            points=10,
            occurred_at=datetime(2026, 9, 10, tzinfo=timezone.utc),
            idempotency_key="k1",
        ),
        _award(
            member_id="m1",
            action="comment",  # different action, must not count against "post"
            points=10,
            occurred_at=datetime(2026, 9, 12, tzinfo=timezone.utc),
            idempotency_key="k2",
        ),
    ]
    event = _event(
        occurred_at=datetime(2026, 9, 16, tzinfo=timezone.utc), idempotency_key="k3"
    )
    result = evaluate(event, rules, history)
    assert result == [
        PointAward(
            member_id="m1",
            source="platform",
            action="post",
            points=10,
            occurred_at=event.occurred_at,
            idempotency_key="k3",
        )
    ]


def test_tightest_cap_wins_when_both_configured() -> None:
    rules = RuleSet.from_rules(
        [
            PointRule(
                source="platform", action="post", points=10, daily_cap=10, period_cap=12
            )
        ]
    )
    day = datetime(2026, 9, 16, 8, 0, tzinfo=timezone.utc)
    history = [_award(points=8, occurred_at=day, idempotency_key="k1")]
    event = _event(
        occurred_at=datetime(2026, 9, 16, 20, 0, tzinfo=timezone.utc),
        idempotency_key="k2",
    )
    # daily remaining = 10-8=2, period remaining = 12-8=4 -> tightest = 2
    result = evaluate(event, rules, history)
    assert result[0].points == 2


# --- evaluate_badges -------------------------------------------------------


def test_evaluate_badges_returns_ids_meeting_threshold() -> None:
    rules = [
        BadgeRule(badge_id="bronze", metric="total_pontos", threshold=100),
        BadgeRule(badge_id="prata", metric="total_pontos", threshold=500),
        BadgeRule(badge_id="fechador", metric="total_vendas", threshold=5),
    ]
    totals = {"total_pontos": 120, "total_vendas": 5}
    assert evaluate_badges(totals, rules) == ["bronze", "fechador"]


def test_evaluate_badges_missing_metric_reads_as_zero() -> None:
    rules = [BadgeRule(badge_id="bronze", metric="total_pontos", threshold=1)]
    assert evaluate_badges({}, rules) == []


def test_evaluate_badges_threshold_is_inclusive() -> None:
    rules = [BadgeRule(badge_id="bronze", metric="total_pontos", threshold=100)]
    assert evaluate_badges({"total_pontos": 100}, rules) == ["bronze"]
