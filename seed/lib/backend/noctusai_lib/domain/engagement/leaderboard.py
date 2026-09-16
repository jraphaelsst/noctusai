"""Engagement domain — leaderboard ranking.

Pure, reuses `noctusai_lib.domain.metas.Period` (see
`value_objects.LeaderboardResult` docstring for why) rather than
inventing a second period vocabulary alongside metas'.
"""
from __future__ import annotations

from collections.abc import Mapping

from noctusai_lib.domain.engagement.value_objects import (
    LeaderboardEntry,
    LeaderboardResult,
)
from noctusai_lib.domain.metas import Period


def leaderboard(totals: Mapping[str, int], period: Period) -> LeaderboardResult:
    """Rank `totals` (member_id -> points) descending by points.

    Standard competition ranking: equal points share the same rank and
    the next distinct score skips ahead (1, 1, 3 — never 1, 1, 2, which
    would understate how many members are tied for the top spot).
    Ties are ordered by `member_id` ascending purely for a deterministic
    row order in the returned tuple; the shared `rank` value is what
    matters for display, not the row order.
    """
    ordered = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))

    entries: list[LeaderboardEntry] = []
    prev_points: int | None = None
    prev_rank = 0
    for position, (member_id, points) in enumerate(ordered, start=1):
        if points != prev_points:
            prev_rank = position
        entries.append(LeaderboardEntry(member_id=member_id, points=points, rank=prev_rank))
        prev_points = points

    return LeaderboardResult(period=period, entries=tuple(entries))


__all__ = ["leaderboard"]
