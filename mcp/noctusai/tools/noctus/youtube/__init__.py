"""``noctus.youtube.*`` tool umbrella — YouTube channel analytics + action tools.

Dual-use: product code (direct import) AND day-to-day agent use via MCP.

Sub-tools
---------
Read tools (query snapshot/catalog tables — no live API call, no deploy dependency):

  ``noctus.youtube.channel_stats``
      Latest channel snapshot + channel_info for an account.
      Returns subscriber/view/video counts, channel title, last_synced_at.

  ``noctus.youtube.list_videos``
      Rows from ``youtube_videos`` (title, views, likes, comments,
      published_at, privacy_status).  Bounded by ``limit``.

  ``noctus.youtube.list_shorts``
      Rows from ``youtube_shorts`` — same engagement columns plus
      ``detected_via`` + ``is_short_confidence``.

  ``noctus.youtube.report``
      THE headline tool.  Reads ``youtube_channel_snapshots`` +
      ``youtube_video_snapshots`` for the last N days and returns:
      subscriber/view growth (first-vs-last snapshot delta), top video
      movers (by view delta), current totals.
      Use for "give me a 30-day report on channel X".

Action tools (trigger a live pull):

  ``noctus.youtube.snapshot_run`` / ``noctus.youtube.sync``
      Trigger a fresh snapshot via ``POST /api/youtube/snapshot/run``.
      Requires ``api_token`` + ``base_url`` explicitly (MCP toolkit does
      not auto-resolve product credentials).  Returns a stub with manual
      instructions until ``NOC-REMEDIATE[yt-mcp-sync-auth]`` is resolved.

Data-access path
----------------
All read tools query Supabase directly via ``noctusai_lib.integrations.database.
make_supabase_client`` (service-role, ``social_wiring`` schema).  Credentials
come from ``BaseAppSettings.supabase_url`` + ``supabase_service_role_key``
(environment variables ``SUPABASE_URL`` + ``SUPABASE_SERVICE_ROLE_KEY``).

Account resolution
------------------
Every tool accepts an ``account`` parameter resolved by ``_resolve.resolve_account``:
  - UUID string  → matches ``integration_accounts.id``
  - label string → case-insensitive ilike on ``integration_accounts.account_label``
  - empty / None → auto-selects the org's single active YouTube account
    (returns ``error: ambiguous`` if there are multiple)
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every ``noctus.youtube.*`` tool on the given FastMCP server."""
    from . import channel_stats
    from . import list_videos
    from . import list_shorts
    from . import report
    from . import snapshot_run

    channel_stats.register(server)
    list_videos.register(server)
    list_shorts.register(server)
    report.register(server)
    snapshot_run.register(server)


__all__ = ["register_all"]
