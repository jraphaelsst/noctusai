"""``noctus.youtube.report`` — N-day analytics report for a YouTube channel.

THE headline tool.  Reads ``social_wiring.youtube_channel_snapshots`` and
``social_wiring.youtube_video_snapshots`` for the last N days and returns:

  1. **Channel growth** — subscriber/view delta between the earliest and
     latest snapshot within the window (first snapshot vs last snapshot).
  2. **Top video movers** — the videos with the largest view delta across
     any two snapshots in the window (requires ≥2 snapshots to compute a delta).
  3. **Totals** — current totals from the most recent channel snapshot.

Growth computation
------------------
For each metric (subscribers, channel views) the delta is::

    delta = last_snapshot.value - first_snapshot.value

where ``first``/``last`` are the snapshots with the minimum/maximum
``snapshot_date`` within ``[today − days, today]``.

A positive delta means the channel grew.  A negative delta is also valid
(e.g. subscriber churn).

Top video movers
----------------
For each video that appears in ``youtube_video_snapshots`` within the window:

  1. Collect all (snapshot_date, view_count) pairs.
  2. Compute delta = max(view_count) − min(view_count) over those pairs
     (treats the earliest-in-window as the baseline).
  3. Return the top-N videos by delta (default N=10, configurable via
     ``top_n``).

If there is only one snapshot per video in the window (i.e. the first
sync was just run) the delta is 0 and the mover list is uninformative —
the tool annotates this with ``"note": "only_one_snapshot_in_window"``
in the return dict.

Parameters
----------
account : str
    Resolve by UUID, label, or empty for auto-select.
days : int
    Window size in days (default 30).  The window is
    ``[today − days, today]`` (inclusive on both ends).
top_n : int
    Number of top video movers to return (default 10, max 50).

Returns
-------
dict  — one of:

    Success::

        {
          "account_id": "<uuid>",
          "account_label": "My Channel",
          "channel_title": "My Channel Title",
          "window_days": 30,
          "window_start": "2026-05-02",
          "window_end":   "2026-06-01",
          "channel_snapshots_in_window": 12,
          "channel_growth": {
            "subscriber_delta": +250,
            "view_delta": +18400,
            "first_snapshot": {
              "date": "2026-05-02",
              "subscriber_count": 10200,
              "view_count": 950000,
            },
            "last_snapshot": {
              "date": "2026-06-01",
              "subscriber_count": 10450,
              "view_count": 968400,
            },
          },
          "current_totals": {
            "subscriber_count": 10450,
            "view_count": 968400,
            "video_count": 95,
          },
          "top_video_movers": [
            {
              "youtube_video_id": "abc123",
              "view_delta": 12300,
              "snapshots_in_window": 5,
            },
            ...
          ],
          "video_snapshots_in_window": 87,
          "note": null,          # or "only_one_snapshot_in_window"
        }

    Not enough data::

        {
          "status": "insufficient_data",
          "account_id": "<uuid>",
          "channel_snapshots_in_window": 0,
          "message": "No channel snapshots in the requested window...",
        }

    Account not found / not configured: structured ``error`` dict.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Any

from ._db import get_yt_client, _not_configured_error
from ._resolve import resolve_account

logger = logging.getLogger(__name__)

_DEFAULT_DAYS = 30
_DEFAULT_TOP_N = 10
_MAX_TOP_N = 50


def report(
    account: str = "",
    days: int = _DEFAULT_DAYS,
    top_n: int = _DEFAULT_TOP_N,
) -> dict:
    """Generate a channel analytics report for the last N days.

    Parameters
    ----------
    account : str
        Account specifier — UUID, label, or empty for auto-select.
    days : int
        Window size in days (default 30).
    top_n : int
        Number of top video movers to include (default 10, max 50).

    Returns
    -------
    dict
        Channel growth (subscriber/view delta first-vs-last snapshot in window),
        current totals, and top video movers by view delta.
        Structured error dicts for missing credentials, unknown account,
        or insufficient data.
    """
    try:
        client = get_yt_client()
    except RuntimeError:
        return _not_configured_error("noctus.youtube.report")

    acc = resolve_account(client, account or None)
    if acc is None or "error" in acc:
        return {
            "error": "account_not_found",
            "account": account,
            "message": "No active YouTube account matched the specifier.",
            "detail": acc,
        }

    account_id = acc["id"]
    channel_info: dict = acc.get("channel_info") or {}
    days = max(1, days)
    top_n = min(max(1, top_n), _MAX_TOP_N)

    today = date.today()
    window_start = today - timedelta(days=days)

    # ── Channel snapshots in window ──────────────────────────────────────────
    ch_resp = (
        client.table("youtube_channel_snapshots")
        .select("snapshot_date, subscriber_count, view_count, video_count, captured_at")
        .eq("account_id", account_id)
        .gte("snapshot_date", window_start.isoformat())
        .lte("snapshot_date", today.isoformat())
        .order("snapshot_date", desc=False)
        .execute()
    )
    ch_snaps: list[dict[str, Any]] = ch_resp.data or []

    if not ch_snaps:
        return {
            "status": "insufficient_data",
            "account_id": account_id,
            "account_label": acc.get("account_label", ""),
            "channel_snapshots_in_window": 0,
            "window_days": days,
            "window_start": window_start.isoformat(),
            "window_end": today.isoformat(),
            "message": (
                f"No channel snapshots found in the {days}-day window "
                f"({window_start} to {today}). "
                "Run noctus.youtube.snapshot_run first."
            ),
        }

    first_snap = ch_snaps[0]
    last_snap = ch_snaps[-1]

    subscriber_delta = last_snap["subscriber_count"] - first_snap["subscriber_count"]
    view_delta = last_snap["view_count"] - first_snap["view_count"]

    # ── Video snapshots in window ────────────────────────────────────────────
    vid_resp = (
        client.table("youtube_video_snapshots")
        .select("youtube_video_id, snapshot_date, view_count, like_count, comment_count, kind")
        .eq("account_id", account_id)
        .gte("snapshot_date", window_start.isoformat())
        .lte("snapshot_date", today.isoformat())
        .order("snapshot_date", desc=False)
        .execute()
    )
    vid_snaps: list[dict[str, Any]] = vid_resp.data or []

    # Group by video_id → compute per-video view delta (max - min view_count)
    vid_groups: dict[str, list[int]] = {}
    for row in vid_snaps:
        vid_id = row["youtube_video_id"]
        vid_groups.setdefault(vid_id, []).append(row["view_count"])

    only_one = all(len(v) == 1 for v in vid_groups.values()) if vid_groups else False

    movers = []
    for vid_id, counts in vid_groups.items():
        delta = max(counts) - min(counts)
        movers.append({
            "youtube_video_id": vid_id,
            "view_delta": delta,
            "snapshots_in_window": len(counts),
        })
    movers.sort(key=lambda x: x["view_delta"], reverse=True)
    top_movers = movers[:top_n]

    note = "only_one_snapshot_in_window" if only_one and vid_groups else None

    return {
        "account_id": account_id,
        "account_label": acc.get("account_label", ""),
        "channel_title": channel_info.get("title", ""),
        "window_days": days,
        "window_start": window_start.isoformat(),
        "window_end": today.isoformat(),
        "channel_snapshots_in_window": len(ch_snaps),
        "channel_growth": {
            "subscriber_delta": subscriber_delta,
            "view_delta": view_delta,
            "first_snapshot": {
                "date": first_snap["snapshot_date"],
                "subscriber_count": first_snap["subscriber_count"],
                "view_count": first_snap["view_count"],
            },
            "last_snapshot": {
                "date": last_snap["snapshot_date"],
                "subscriber_count": last_snap["subscriber_count"],
                "view_count": last_snap["view_count"],
            },
        },
        "current_totals": {
            "subscriber_count": last_snap["subscriber_count"],
            "view_count": last_snap["view_count"],
            "video_count": last_snap["video_count"],
        },
        "top_video_movers": top_movers,
        "video_snapshots_in_window": len(vid_snaps),
        "note": note,
    }


def register(server) -> None:
    """Register ``noctus.youtube.report`` on the MCP server."""

    @server.tool(
        name="noctus.youtube.report",
        description=(
            "Generate an N-day YouTube channel analytics report. "
            "Reads youtube_channel_snapshots + youtube_video_snapshots for "
            "the last ``days`` days (default 30). "
            "Returns: subscriber/view growth (first-vs-last snapshot delta), "
            "current totals, and top video movers by view delta. "
            "Pass ``account`` as UUID, label, or empty for auto-select. "
            "``top_n`` controls how many top movers to include (default 10). "
            "Use for 'give me a 30-day report on channel X'. "
            "Returns structured error if credentials missing, account not found, "
            "or no snapshots in the window (run snapshot_run first)."
        ),
    )
    def _handler(
        account: str = "",
        days: int = _DEFAULT_DAYS,
        top_n: int = _DEFAULT_TOP_N,
    ) -> dict:
        return report(account=account, days=days, top_n=top_n)
