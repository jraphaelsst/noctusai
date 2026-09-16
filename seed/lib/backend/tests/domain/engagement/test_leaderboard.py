"""`leaderboard` — pure ranking. Standard competition ranking (ties share
a rank; the next distinct score skips ahead) + reuses `metas.Period`."""
from __future__ import annotations

from datetime import date

from noctusai_lib.domain.engagement import LeaderboardEntry, LeaderboardResult, leaderboard
from noctusai_lib.domain.metas import Period, PeriodKind


def _period() -> Period:
    return Period(kind=PeriodKind.WEEKLY, start=date(2026, 9, 14), end=date(2026, 9, 20))


def test_ranks_descending_by_points() -> None:
    totals = {"m1": 50, "m2": 100, "m3": 10}
    result = leaderboard(totals, _period())
    assert result.entries == (
        LeaderboardEntry(member_id="m2", points=100, rank=1),
        LeaderboardEntry(member_id="m1", points=50, rank=2),
        LeaderboardEntry(member_id="m3", points=10, rank=3),
    )


def test_ties_share_rank_and_next_rank_skips() -> None:
    """1, 1, 3 — never 1, 1, 2 — because two members tied for first
    means the third-place member is genuinely in third position."""
    totals = {"m1": 100, "m2": 100, "m3": 50}
    result = leaderboard(totals, _period())
    ranks = [entry.rank for entry in result.entries]
    assert ranks == [1, 1, 3]


def test_result_carries_the_period_through_unmodified() -> None:
    period = _period()
    result = leaderboard({"m1": 10}, period)
    assert result.period is period


def test_empty_totals_yields_empty_leaderboard() -> None:
    result = leaderboard({}, _period())
    assert result == LeaderboardResult(period=_period(), entries=())


def test_tied_members_ordered_by_member_id_for_determinism() -> None:
    totals = {"zzz": 100, "aaa": 100}
    result = leaderboard(totals, _period())
    assert [entry.member_id for entry in result.entries] == ["aaa", "zzz"]
