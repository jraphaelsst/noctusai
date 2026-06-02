"""``noctus.youtube.channel_stats`` — latest channel snapshot for an account.

Reads ``social_wiring.youtube_channel_snapshots`` (the most recent row) and
enriches the result with ``channel_info`` JSONB from
``social_wiring.integration_accounts``.

Parameters
----------
account : str
    Resolve by UUID, account_label substring, or leave empty to auto-select
    the org's single active YouTube account.  Passed to ``resolve_account``.

Returns
-------
dict  — one of:

    Success::

        {
          "account_id": "<uuid>",
          "account_label": "My Channel",
          "channel_title": "My Channel Title",
          "channel_id": "UCxxxx",
          "subscriber_count": 12345,
          "view_count": 9876543,
          "video_count": 210,
          "snapshot_date": "2026-06-01",
          "last_synced_at": "2026-06-01T12:00:00+00:00",
        }

    No data yet (account exists but no snapshots)::

        {
          "status": "no_data",
          "account_id": "<uuid>",
          "message": "No channel snapshots found — run noctus.youtube.snapshot_run first.",
        }

    Account not found::

        {
          "error": "account_not_found",
          "account": "<specifier>",
          "message": "...",
        }

    Not configured (missing env creds)::

        {
          "error": "not_configured",
          ...
        }
"""
from __future__ import annotations

import logging

from ._db import get_yt_client, _not_configured_error
from ._resolve import resolve_account

logger = logging.getLogger(__name__)


def channel_stats(account: str = "") -> dict:
    """Return the latest channel snapshot + channel_info for a YouTube account.

    Parameters
    ----------
    account : str
        Account specifier — UUID, label, or empty for auto-select.

    Returns
    -------
    dict
        Subscriber/view/video counts, channel title, last snapshot date.
        Returns a structured ``error`` dict if the account is not found,
        credentials are missing, or no snapshots have been collected yet.
    """
    try:
        client = get_yt_client()
    except RuntimeError:
        return _not_configured_error("noctus.youtube.channel_stats")

    acc = resolve_account(client, account or None)
    if acc is None:
        return {
            "error": "account_not_found",
            "account": account,
            "message": (
                "No active YouTube account found matching the specifier. "
                "Check integration_accounts or run a sync first."
            ),
        }
    if "error" in acc:
        return {
            "error": "account_not_found",
            "account": account,
            "message": acc.get("error"),
            "detail": acc,
        }

    account_id = acc["id"]
    channel_info: dict = acc.get("channel_info") or {}

    # Latest snapshot (one row — sorted by snapshot_date DESC, limit 1)
    snap_resp = (
        client.table("youtube_channel_snapshots")
        .select("snapshot_date, subscriber_count, view_count, video_count, captured_at")
        .eq("account_id", account_id)
        .order("snapshot_date", desc=True)
        .limit(1)
        .execute()
    )
    snaps = snap_resp.data or []

    if not snaps:
        return {
            "status": "no_data",
            "account_id": account_id,
            "account_label": acc.get("account_label", ""),
            "message": "No channel snapshots found — run noctus.youtube.snapshot_run first.",
        }

    snap = snaps[0]
    return {
        "account_id": account_id,
        "account_label": acc.get("account_label", ""),
        "channel_title": channel_info.get("title", ""),
        "channel_id": channel_info.get("channelId", ""),
        "subscriber_count": snap["subscriber_count"],
        "view_count": snap["view_count"],
        "video_count": snap["video_count"],
        "snapshot_date": snap["snapshot_date"],
        "last_synced_at": snap["captured_at"],
    }


def register(server) -> None:
    """Register ``noctus.youtube.channel_stats`` on the MCP server."""

    @server.tool(
        name="noctus.youtube.channel_stats",
        description=(
            "Return the latest channel snapshot + channel_info for a YouTube account. "
            "Reads social_wiring.youtube_channel_snapshots (most recent row) plus "
            "channel_info JSONB from integration_accounts. "
            "Pass ``account`` as a UUID, label substring, or leave empty to auto-select "
            "the org's single active YouTube account. "
            "Returns subscriber_count, view_count, video_count, channel_title, snapshot_date. "
            "Returns a structured error if credentials are missing, account is not found, "
            "or no snapshots exist yet (run noctus.youtube.snapshot_run first)."
        ),
    )
    def _handler(account: str = "") -> dict:
        return channel_stats(account=account)
