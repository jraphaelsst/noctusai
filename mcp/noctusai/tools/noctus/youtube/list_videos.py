"""``noctus.youtube.list_videos`` — catalog of YouTube videos for an account.

Reads ``social_wiring.youtube_videos``, returning the most-recently-published
rows first.  Bounded by ``limit`` (default 50, max 200) — never dumps the
whole table.

Parameters
----------
account : str
    Resolve by UUID, label, or empty for auto-select.
limit : int
    Maximum rows to return (default 50, capped at 200).

Returns
-------
dict  — one of:

    Success::

        {
          "account_id": "<uuid>",
          "account_label": "My Channel",
          "total_returned": 42,
          "videos": [
            {
              "youtube_video_id": "dQw4w9WgXcQ",
              "title": "Never Gonna Give You Up",
              "published_at": "2009-10-25T06:57:33+00:00",
              "view_count": 1400000000,
              "like_count": 15000000,
              "comment_count": 2000000,
              "privacy_status": "public",
              "duration_seconds": 213,
            },
            ...
          ],
        }

    No data / account error: structured ``error`` or ``status: no_data`` dict.
"""
from __future__ import annotations

import logging
from typing import Any

from ._db import get_yt_client, _not_configured_error
from ._resolve import resolve_account

logger = logging.getLogger(__name__)

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


def list_videos(account: str = "", limit: int = _DEFAULT_LIMIT) -> dict:
    """Return a bounded catalog of YouTube videos for an account.

    Parameters
    ----------
    account : str
        Account specifier — UUID, label, or empty for auto-select.
    limit : int
        Max rows (default 50, capped at 200).  Ordered by published_at DESC.

    Returns
    -------
    dict
        ``account_id``, ``account_label``, ``total_returned``, ``videos`` list.
        Each video row includes: youtube_video_id, title, published_at,
        view_count, like_count, comment_count, privacy_status, duration_seconds.
    """
    try:
        client = get_yt_client()
    except RuntimeError:
        return _not_configured_error("noctus.youtube.list_videos")

    acc = resolve_account(client, account or None)
    if acc is None or "error" in acc:
        return {
            "error": "account_not_found",
            "account": account,
            "message": "No active YouTube account matched the specifier.",
            "detail": acc,
        }

    account_id = acc["id"]
    limit = min(max(1, limit), _MAX_LIMIT)

    resp = (
        client.table("youtube_videos")
        .select(
            "youtube_video_id, title, published_at, view_count, like_count, "
            "comment_count, privacy_status, duration_seconds"
        )
        .eq("account_id", account_id)
        .order("published_at", desc=True)
        .limit(limit)
        .execute()
    )
    rows: list[dict[str, Any]] = resp.data or []

    if not rows:
        return {
            "status": "no_data",
            "account_id": account_id,
            "account_label": acc.get("account_label", ""),
            "message": "No videos found — run noctus.youtube.snapshot_run first.",
        }

    return {
        "account_id": account_id,
        "account_label": acc.get("account_label", ""),
        "total_returned": len(rows),
        "videos": rows,
    }


def register(server) -> None:
    """Register ``noctus.youtube.list_videos`` on the MCP server."""

    @server.tool(
        name="noctus.youtube.list_videos",
        description=(
            "Return a bounded catalog of YouTube videos for an account. "
            "Reads social_wiring.youtube_videos, ordered by published_at DESC. "
            "Pass ``account`` as a UUID, label substring, or leave empty to auto-select. "
            "``limit`` caps rows returned (default 50, max 200). "
            "Returns youtube_video_id, title, published_at, view_count, like_count, "
            "comment_count, privacy_status, duration_seconds per video."
        ),
    )
    def _handler(account: str = "", limit: int = _DEFAULT_LIMIT) -> dict:
        return list_videos(account=account, limit=limit)
