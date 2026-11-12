"""The pure decision engine: every strategy, keep-last, capacity, out-of-office, fairness across teams, the hook seam."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from noctusai_lib.domain.assignment import (
    AssignContext,
    HookPickError,
    MemberState,
    NoPick,
    Pick,
    Rule,
    Settings,
    Snapshot,
    TeamState,
    decide,
)

NOW = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
CTX = AssignContext(subject_kind="card", subject_id="s1")


def m(user: str, team: str, pos: int = 0, **kw) -> MemberState:
    return MemberState(user_id=user, team_id=team, position=pos, **kw)


def team(tid: str, *members: MemberState, auto=True, cursor=None, moved=None, unit=None, created="a") -> TeamState:
    return TeamState(
        id=tid, name=tid, auto=auto, members=tuple(members), cursor_user_id=cursor, cursor_moved_at=moved,
        org_unit_id=unit, created_at=created,
    )


def snap(teams, *, strategy="round_robin", default=None, keep_last=True, rules=()) -> Snapshot:
    return Snapshot(settings=Settings(strategy, default, keep_last), teams=tuple(teams), rules=tuple(rules), now=NOW)


def test_round_robin_serves_the_member_after_the_cursor_and_wraps():
    t = team("t", m("a", "t", 0), m("b", "t", 1), m("c", "t", 2), cursor="b")
    assert decide(snap([t]), CTX) == Pick("c", "t", "round_robin", advance_cursor=True)
    t2 = team("t", m("a", "t", 0), m("b", "t", 1), m("c", "t", 2), cursor="c")
    assert decide(snap([t2]), CTX).user_id == "a"


def test_round_robin_starts_at_the_first_member_when_there_is_no_cursor():
    assert decide(snap([team("t", m("b", "t", 1), m("a", "t", 0))]), CTX).user_id == "a"


def test_a_cursor_on_someone_now_unavailable_still_advances_past_them():
    t = team("t", m("a", "t", 0), m("b", "t", 1, active=False), m("c", "t", 2), cursor="a")
    assert decide(snap([t]), CTX).user_id == "c"  # b is skipped, not served


def test_inactive_out_of_office_and_at_capacity_members_are_skipped():
    away = m("away", "t", 1, ooo_from=NOW - timedelta(hours=1), ooo_until=NOW + timedelta(hours=1))
    full = m("full", "t", 2, capacity=2, open_count=2)
    t = team("t", m("off", "t", 0, active=False), away, full, m("ok", "t", 3, capacity=2, open_count=1))
    assert decide(snap([t]), CTX).user_id == "ok"


def test_an_out_of_office_window_that_has_ended_or_not_begun_does_not_block():
    past = m("past", "t", 0, ooo_from=NOW - timedelta(days=3), ooo_until=NOW - timedelta(days=1))
    future = m("future", "t", 1, ooo_from=NOW + timedelta(days=1), ooo_until=NOW + timedelta(days=2))
    assert decide(snap([team("t", past, future)]), CTX).user_id == "past"
    assert past.unavailable_reason(NOW) is None and future.unavailable_reason(NOW) is None


def test_an_open_start_out_of_office_blocks_until_it_ends():
    assert m("a", "t", ooo_until=NOW + timedelta(days=9)).unavailable_reason(NOW) == "out_of_office"
    assert m("a", "t", ooo_from=NOW - timedelta(hours=1), ooo_until=NOW + timedelta(days=9)).unavailable_reason(NOW) == "out_of_office"


def test_nobody_available_is_a_named_outcome_not_an_error():
    t = team("t", m("a", "t", 0, active=False))
    assert decide(snap([t]), CTX) == NoPick("no_available_member")
    assert decide(snap([]), CTX) == NoPick("no_team")


def test_across_teams_the_team_whose_cursor_moved_least_recently_goes_next():
    recent = team("recent", m("r", "recent"), moved=NOW - timedelta(minutes=1), created="a")
    stale = team("stale", m("s", "stale"), moved=NOW - timedelta(days=2), created="b")
    never = team("never", m("n", "never"), moved=None, created="c")
    assert decide(snap([recent, stale, never]), CTX).user_id == "n"
    assert decide(snap([recent, stale]), CTX).user_id == "s"


def test_only_auto_teams_take_part_in_org_wide_round_robin():
    assert decide(snap([team("manual", m("a", "manual"), auto=False)]), CTX) == NoPick("no_team")


def test_manual_strategy_never_picks():
    assert decide(snap([team("t", m("a", "t"))], strategy="manual"), CTX) == NoPick("manual")


def test_keep_last_returns_a_subject_to_its_current_owner_while_eligible():
    t = team("t", m("a", "t", 0), m("b", "t", 1), cursor="a")
    ctx = AssignContext("card", "s1", current_user_id="a")
    assert decide(snap([t]), ctx) == Pick("a", "t", "keep_last", advance_cursor=False)
    assert decide(snap([t], keep_last=False), ctx).user_id == "b"  # rotation proper


def test_keep_last_does_not_keep_an_owner_who_is_no_longer_eligible():
    t = team("t", m("a", "t", 0, active=False), m("b", "t", 1))
    assert decide(snap([t]), AssignContext("card", "s1", current_user_id="a")).user_id == "b"


def test_by_team_uses_the_named_team_then_the_default():
    a, b = team("a", m("ua", "a")), team("b", m("ub", "b"))
    s = snap([a, b], strategy="by_team", default="b")
    assert decide(s, AssignContext("card", "s1", team_id="a")) == Pick("ua", "a", "by_team", advance_cursor=True)
    assert decide(s, CTX).user_id == "ub"
    assert decide(snap([a, b], strategy="by_team"), CTX) == NoPick("no_team")


def test_by_source_routes_through_the_rule_and_falls_back_to_the_default_team():
    a, b = team("a", m("ua", "a")), team("b", m("ub", "b"))
    s = snap([a, b], strategy="by_source", default="b", rules=[Rule("source", "meta_ads", "a")])
    assert decide(s, AssignContext("card", "s1", source="meta_ads")).user_id == "ua"
    assert decide(s, AssignContext("card", "s1", source="portal")).user_id == "ub"
    assert decide(s, CTX).user_id == "ub"


def test_by_unit_prefers_a_unit_rule_then_a_team_stamped_with_the_unit():
    a, b = team("a", m("ua", "a")), team("b", m("ub", "b"), unit="unit-9")
    ctx = AssignContext("card", "s1", org_unit_id="unit-9")
    assert decide(snap([a, b], strategy="by_unit", rules=[Rule("unit", "unit-9", "a")]), ctx).user_id == "ua"
    assert decide(snap([a, b], strategy="by_unit"), ctx).user_id == "ub"
    assert decide(snap([a, b], strategy="by_unit"), AssignContext("card", "s1", org_unit_id="other")) == NoPick("no_team")


def test_a_custom_strategy_hook_decides_and_is_labelled_custom():
    t = team("t", m("a", "t", 0), m("b", "t", 1))
    out = decide(snap([t], strategy="by_plantao"), CTX, {"by_plantao": lambda s, c: Pick("b", "t", "ignored-by-engine")})
    assert out == Pick("b", "t", "custom:by_plantao", advance_cursor=False)
    assert decide(snap([t], strategy="by_plantao"), CTX, {"by_plantao": lambda s, c: None}) == NoPick("hook_declined")


def test_a_hook_cannot_assign_to_a_stranger_or_an_ineligible_member():
    t = team("t", m("a", "t", 0, active=False))
    for bad in (Pick("ghost", "t", "x"), Pick("a", "t", "x"), Pick("a", "nope", "x")):
        with pytest.raises(HookPickError):
            decide(snap([t], strategy="h"), CTX, {"h": lambda s, c, bad=bad: bad})


def test_an_unregistered_strategy_name_fails_loudly():
    with pytest.raises(ValueError, match="unknown strategy"):
        decide(snap([team("t", m("a", "t"))], strategy="nope"), CTX)
