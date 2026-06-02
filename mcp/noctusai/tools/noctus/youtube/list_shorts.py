"""``noctus.youtube.list_shorts`` — catalog of YouTube Shorts for an account.

Reads ``social_wiring.youtube_shorts``, which classifies short-form content
separately from long-form videos.  Each row has the same engagement columns as
``youtube_videos`` plus short-specific classification metadata
(``detected_via``, ``is_short_confidence``).

Parameters
----------
account : str
    Resolve by UUID, label, or empty for auto-select.
limit : int
    Maximum rows to return (default 50, max 200).

Returns
-------
dict  — one of:

    Success::

        {
          "account_id": "<uuid>",
          "account_label": "My Channel",
          "total_returned": 15,
          "shorts": [
            {
              "youtube_video_id": "abc123",
              "title": "My Short",
              "published_at": "2026-05-01T10:00:00+00:00",
              "view_count": 55000,
              "like_count": 3000,
              "comment_count": 120,
              "privacy_status": "public",
              "duration_seconds": 58,
              "detected_via": "duration",
              "is_short_confidence": "high",
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


def list_shorts(account: str = "", limit: int = _DEFAULT_LIMIT) -> dict:
    """Return a bounded catalog of YouTube Shorts for an account.

    Parameters
    ----------
    account : str
        Account specifier — UUID, label, or empty for auto-select.
    limit : int
        Max rows (default 50, capped at 200).  Ordered by published_at DESC.

    Returns
    -------
    dict
        ``account_id``, ``account_label``, ``total_returned``, ``shorts`` list.
        Each short row includes: youtube_video_id, title, published_at,
        view_count, like_count, comment_count, privacy_status, duration_seconds,
        detected_via, is_short_confidence.
    """
    try:
        client = get_yt_client()
    except RuntimeError:
        return _not_configured_error("noctus.youtube.list_shorts")

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
        client.table("youtube_shorts")
        .select(
            "youtube_video_id, title, published_at, view_count, like_count, "
            "comment_count, privacy_status, duration_seconds, "
            "detected_via, is_short_confidence"
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
            "message": "No shorts found — run noctus.youtube.snapshot_run first.",
        }

    return {
        "account_id": account_id,
        "account_label": acc.get("account_label", ""),
        "total_returned": len(rows),
        "shorts": rows,
    }


def register(server) -> None:
    """Register ``noctus.youtube.list_shorts`` on the MCP server."""

    @server.tool(
        name="noctus.youtube.list_shorts",
        description=(
            "Return a bounded catalog of YouTube Shorts for an account. "
            "Reads social_wiring.youtube_shorts (short-form videos ≤60 s), "
            "ordered by published_at DESC. "
            "Pass ``account`` as UUID, label substring, or empty for auto-select. "
            "``limit`` caps rows returned (default 50, max 200). "
            "Returns youtube_video_id, title, published_at, view_count, like_count, "
            "comment_count, privacy_status, duration_seconds, "
            "detected_via, is_short_confidence per short."
        ),
    )
    def _handler(account: str = "", limit: int = _DEFAULT_LIMIT) -> dict:
        return list_shorts(account=account, limit=limit)
