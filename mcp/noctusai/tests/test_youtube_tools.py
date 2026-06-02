"""Tests for ``noctus.youtube.*`` MCP tools.

All DB/HTTP interactions are mocked — no real Supabase credentials required.
Covers:
  - account resolution (UUID / label / auto-select / ambiguous / not-found)
  - channel_stats (success, no-data, not-configured)
  - list_videos / list_shorts (success, no-data)
  - report: growth delta + top-movers aggregation math (the key invariant)
  - snapshot_run: stub return when api_token absent
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

MCP_ROOT = Path(__file__).resolve().parents[1]
if str(MCP_ROOT) not in sys.path:
    sys.path.insert(0, str(MCP_ROOT))

from tools.noctus.youtube._resolve import resolve_account  # noqa: E402
from tools.noctus.youtube.channel_stats import channel_stats  # noqa: E402
from tools.noctus.youtube.list_videos import list_videos  # noqa: E402
from tools.noctus.youtube.list_shorts import list_shorts  # noqa: E402
from tools.noctus.youtube.report import report  # noqa: E402
from tools.noctus.youtube.snapshot_run import snapshot_run  # noqa: E402


# ─── helpers ─────────────────────────────────────────────────────────────────


def _fake_account(
    account_id: str = "aaaaaaaa-0000-0000-0000-000000000001",
    label: str = "my-channel",
    channel_info: dict | None = None,
) -> dict:
    return {
        "id": account_id,
        "account_label": label,
        "channel_info": channel_info or {"title": "My Channel", "channelId": "UCtest"},
        "status": "active",
        "org_id": "bbbbbbbb-0000-0000-0000-000000000001",
        "created_at": "2026-01-01T00:00:00+00:00",
    }


def _supabase_resp(data: list) -> MagicMock:
    """Return a mock Supabase response object."""
    m = MagicMock()
    m.data = data
    return m


def _make_client(accounts=None, snapshots=None, videos=None, shorts=None, vid_snaps=None):
    """Build a fake Supabase client whose .table(...).select(...).eq(...).execute() returns
    the appropriate fixture data.

    Works by matching the table name on .table() and returning a fluent mock
    that chains any number of .select/.eq/.order/.limit/.gte/.lte/.ilike calls
    before .execute().
    """
    data_map = {
        "integration_accounts": accounts or [],
        "youtube_channel_snapshots": snapshots or [],
        "youtube_videos": videos or [],
        "youtube_shorts": shorts or [],
        "youtube_video_snapshots": vid_snaps or [],
    }

    def _table(name):
        resp_data = data_map.get(name, [])
        chain = MagicMock()
        # Every chained method returns the same chain object
        chain.select.return_value = chain
        chain.eq.return_value = chain
        chain.order.return_value = chain
        chain.limit.return_value = chain
        chain.gte.return_value = chain
        chain.lte.return_value = chain
        chain.ilike.return_value = chain
        chain.execute.return_value = _supabase_resp(resp_data)
        return chain

    client = MagicMock()
    client.table.side_effect = _table
    return client


# ─── _resolve ────────────────────────────────────────────────────────────────


def test_resolve_account_by_uuid():
    acc = _fake_account()
    client = _make_client(accounts=[acc])
    result = resolve_account(client, acc["id"])
    assert result is not None
    assert result["id"] == acc["id"]


def test_resolve_account_by_label():
    acc = _fake_account(label="my-channel")
    client = _make_client(accounts=[acc])
    result = resolve_account(client, "my-channel")
    assert result["account_label"] == "my-channel"


def test_resolve_account_auto_select_single():
    acc = _fake_account()
    client = _make_client(accounts=[acc])
    result = resolve_account(client, None)
    assert result["id"] == acc["id"]


def test_resolve_account_auto_select_ambiguous():
    a1 = _fake_account(account_id="aaaaaaaa-0000-0000-0000-000000000001", label="ch1")
    a2 = _fake_account(account_id="aaaaaaaa-0000-0000-0000-000000000002", label="ch2")
    client = _make_client(accounts=[a1, a2])
    result = resolve_account(client, None)
    assert result is not None
    assert result.get("error") == "ambiguous"
    assert result["count"] == 2


def test_resolve_account_not_found():
    client = _make_client(accounts=[])
    result = resolve_account(client, "nonexistent")
    assert result is None


def test_resolve_account_multiple_label_matches_exact_wins():
    a1 = _fake_account(account_id="aaaaaaaa-0000-0000-0000-000000000001", label="channel")
    a2 = _fake_account(account_id="aaaaaaaa-0000-0000-0000-000000000002", label="channel-2")
    client = _make_client(accounts=[a1, a2])
    result = resolve_account(client, "channel")
    # exact match wins over partial
    assert result["id"] == a1["id"]


# ─── channel_stats ───────────────────────────────────────────────────────────


def test_channel_stats_success():
    acc = _fake_account()
    snaps = [
        {
            "snapshot_date": "2026-06-01",
            "subscriber_count": 10500,
            "view_count": 1_000_000,
            "video_count": 100,
            "captured_at": "2026-06-01T12:00:00+00:00",
        }
    ]
    client = _make_client(accounts=[acc], snapshots=snaps)

    with patch("tools.noctus.youtube.channel_stats.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.channel_stats.resolve_account", return_value=acc):
        result = channel_stats(account=acc["id"])

    assert result["subscriber_count"] == 10500
    assert result["channel_title"] == "My Channel"
    assert result["snapshot_date"] == "2026-06-01"
    assert result["account_id"] == acc["id"]


def test_channel_stats_no_data():
    acc = _fake_account()
    client = _make_client(accounts=[acc], snapshots=[])

    with patch("tools.noctus.youtube.channel_stats.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.channel_stats.resolve_account", return_value=acc):
        result = channel_stats()

    assert result.get("status") == "no_data"
    assert "snapshot_run" in result["message"]


def test_channel_stats_account_not_found():
    client = _make_client(accounts=[])

    with patch("tools.noctus.youtube.channel_stats.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.channel_stats.resolve_account", return_value=None):
        result = channel_stats(account="unknown")

    assert result.get("error") == "account_not_found"


def test_channel_stats_not_configured():
    with patch("tools.noctus.youtube.channel_stats.get_yt_client",
               side_effect=RuntimeError("missing creds")):
        result = channel_stats()

    assert result.get("error") == "not_configured"


# ─── list_videos ─────────────────────────────────────────────────────────────


def test_list_videos_success():
    acc = _fake_account()
    videos = [
        {
            "youtube_video_id": "vid001",
            "title": "Hello World",
            "published_at": "2026-05-01T10:00:00+00:00",
            "view_count": 5000,
            "like_count": 300,
            "comment_count": 50,
            "privacy_status": "public",
            "duration_seconds": 600,
        }
    ]
    client = _make_client(accounts=[acc], videos=videos)

    with patch("tools.noctus.youtube.list_videos.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.list_videos.resolve_account", return_value=acc):
        result = list_videos(account=acc["id"])

    assert result["total_returned"] == 1
    assert result["videos"][0]["youtube_video_id"] == "vid001"


def test_list_videos_respects_limit():
    acc = _fake_account()
    # The limit is enforced client-side (the mock returns whatever data we give,
    # but we test that the clamping logic doesn't allow >200 and >0)
    client = _make_client(accounts=[acc], videos=[])

    with patch("tools.noctus.youtube.list_videos.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.list_videos.resolve_account", return_value=acc):
        result = list_videos(account=acc["id"], limit=300)
    # limit was clamped → no crash
    assert result.get("status") == "no_data"


def test_list_videos_no_data():
    acc = _fake_account()
    client = _make_client(accounts=[acc], videos=[])

    with patch("tools.noctus.youtube.list_videos.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.list_videos.resolve_account", return_value=acc):
        result = list_videos()

    assert result.get("status") == "no_data"


# ─── list_shorts ─────────────────────────────────────────────────────────────


def test_list_shorts_success():
    acc = _fake_account()
    shorts = [
        {
            "youtube_video_id": "sht001",
            "title": "Quick Short",
            "published_at": "2026-05-10T08:00:00+00:00",
            "view_count": 55_000,
            "like_count": 3_000,
            "comment_count": 120,
            "privacy_status": "public",
            "duration_seconds": 58,
            "detected_via": "duration",
            "is_short_confidence": "high",
        }
    ]
    client = _make_client(accounts=[acc], shorts=shorts)

    with patch("tools.noctus.youtube.list_shorts.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.list_shorts.resolve_account", return_value=acc):
        result = list_shorts(account=acc["id"])

    assert result["total_returned"] == 1
    assert result["shorts"][0]["detected_via"] == "duration"
    assert result["shorts"][0]["is_short_confidence"] == "high"


def test_list_shorts_no_data():
    acc = _fake_account()
    client = _make_client(accounts=[acc], shorts=[])

    with patch("tools.noctus.youtube.list_shorts.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.list_shorts.resolve_account", return_value=acc):
        result = list_shorts()

    assert result.get("status") == "no_data"


# ─── report — growth delta + top movers (the critical math) ──────────────────


def _ch_snap(date_str: str, subs: int, views: int, vids: int = 50) -> dict:
    return {
        "snapshot_date": date_str,
        "subscriber_count": subs,
        "view_count": views,
        "video_count": vids,
        "captured_at": f"{date_str}T12:00:00+00:00",
    }


def _vid_snap(vid_id: str, date_str: str, views: int) -> dict:
    return {
        "youtube_video_id": vid_id,
        "snapshot_date": date_str,
        "view_count": views,
        "like_count": 0,
        "comment_count": 0,
        "kind": "video",
    }


def test_report_growth_delta_correct():
    """Core invariant: growth delta = last_snap - first_snap (for the window)."""
    acc = _fake_account()
    today = date.today()
    d0 = (today - timedelta(days=7)).isoformat()
    d1 = today.isoformat()

    ch_snaps = [
        _ch_snap(d0, subs=10_000, views=900_000),
        _ch_snap(d1, subs=10_300, views=918_400),
    ]
    vid_snaps = [
        _vid_snap("v1", d0, 1_000),
        _vid_snap("v1", d1, 4_500),
        _vid_snap("v2", d0, 500),
        _vid_snap("v2", d1, 700),
    ]

    client = _make_client(accounts=[acc], snapshots=ch_snaps, vid_snaps=vid_snaps)

    with patch("tools.noctus.youtube.report.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.report.resolve_account", return_value=acc):
        result = report(account=acc["id"], days=30)

    growth = result["channel_growth"]
    assert growth["subscriber_delta"] == 300     # 10300 - 10000
    assert growth["view_delta"] == 18_400        # 918400 - 900000

    # Top movers: v1 has delta 3500, v2 has delta 200
    movers = result["top_video_movers"]
    assert movers[0]["youtube_video_id"] == "v1"
    assert movers[0]["view_delta"] == 3_500
    assert movers[1]["youtube_video_id"] == "v2"
    assert movers[1]["view_delta"] == 200

    assert result["note"] is None  # 2 snapshots per video → not "only_one"


def test_report_top_n_capped():
    """top_n > _MAX_TOP_N gets clamped; result length ≤ top_n."""
    acc = _fake_account()
    today = date.today()
    d0 = (today - timedelta(days=3)).isoformat()
    d1 = today.isoformat()

    ch_snaps = [_ch_snap(d0, 1000, 10000), _ch_snap(d1, 1010, 10100)]
    # 5 videos, each with 2 snaps
    vid_snaps = []
    for i in range(5):
        vid_snaps.append(_vid_snap(f"v{i}", d0, i * 100))
        vid_snaps.append(_vid_snap(f"v{i}", d1, i * 100 + 50))

    client = _make_client(accounts=[acc], snapshots=ch_snaps, vid_snaps=vid_snaps)

    with patch("tools.noctus.youtube.report.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.report.resolve_account", return_value=acc):
        result = report(account=acc["id"], days=10, top_n=3)

    # Clamped to top_n=3
    assert len(result["top_video_movers"]) == 3


def test_report_only_one_snapshot_note():
    """When each video has exactly one snapshot in the window, note is set."""
    acc = _fake_account()
    today = date.today()
    d0 = today.isoformat()

    ch_snaps = [_ch_snap(d0, 1000, 10000)]
    vid_snaps = [
        _vid_snap("v1", d0, 500),
        _vid_snap("v2", d0, 200),
    ]

    client = _make_client(accounts=[acc], snapshots=ch_snaps, vid_snaps=vid_snaps)

    with patch("tools.noctus.youtube.report.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.report.resolve_account", return_value=acc):
        result = report(account=acc["id"], days=30)

    assert result["note"] == "only_one_snapshot_in_window"
    # Deltas are all 0 when only one snapshot
    for m in result["top_video_movers"]:
        assert m["view_delta"] == 0


def test_report_insufficient_data():
    """No channel snapshots in window → status: insufficient_data."""
    acc = _fake_account()
    client = _make_client(accounts=[acc], snapshots=[])

    with patch("tools.noctus.youtube.report.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.report.resolve_account", return_value=acc):
        result = report()

    assert result.get("status") == "insufficient_data"
    assert result["channel_snapshots_in_window"] == 0


def test_report_not_configured():
    with patch("tools.noctus.youtube.report.get_yt_client",
               side_effect=RuntimeError("creds")):
        result = report()
    assert result.get("error") == "not_configured"


def test_report_current_totals_from_last_snap():
    """current_totals must reflect the LAST (most recent) snapshot in the window."""
    acc = _fake_account()
    today = date.today()
    snaps = [
        _ch_snap((today - timedelta(days=5)).isoformat(), subs=9_900, views=980_000),
        _ch_snap((today - timedelta(days=2)).isoformat(), subs=10_000, views=990_000),
        _ch_snap(today.isoformat(), subs=10_200, views=1_000_000, vids=105),
    ]
    client = _make_client(accounts=[acc], snapshots=snaps)

    with patch("tools.noctus.youtube.report.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.report.resolve_account", return_value=acc):
        result = report(account=acc["id"], days=30)

    totals = result["current_totals"]
    assert totals["subscriber_count"] == 10_200
    assert totals["view_count"] == 1_000_000
    assert totals["video_count"] == 105


# ─── snapshot_run / sync ─────────────────────────────────────────────────────


def test_snapshot_run_returns_stub_without_token():
    acc = _fake_account()
    client = _make_client(accounts=[acc])

    with patch("tools.noctus.youtube.snapshot_run.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.snapshot_run.resolve_account", return_value=acc):
        result = snapshot_run(account=acc["id"])

    assert result.get("status") == "stub"
    assert "manual_trigger" in result
    assert "NOC-REMEDIATE[yt-mcp-sync-auth]" in result.get("remediation", "")
    assert acc["id"] in result["manual_trigger"]["url"]


def test_snapshot_run_not_configured_still_returns_stub():
    """If Supabase creds are missing but account+token are provided,
    the tool should still attempt to resolve — if it fails, it returns a stub
    with account_id=None rather than crashing."""
    with patch("tools.noctus.youtube.snapshot_run.get_yt_client",
               side_effect=RuntimeError("creds")):
        result = snapshot_run(account="some-label", api_token="", base_url="")

    # stub is returned even when account resolution fails
    assert result.get("status") == "stub"
    assert result.get("account_id") is None


def test_snapshot_run_with_full_auth_calls_http(monkeypatch):
    """When api_token + base_url are provided, the tool calls the product API."""
    acc = _fake_account()
    client = _make_client(accounts=[acc])

    # Mock httpx inside the module
    import types
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.headers = {"content-type": "application/json"}
    fake_response.json.return_value = {"ok": True}

    fake_httpx = types.SimpleNamespace(
        Client=MagicMock(return_value=MagicMock(
            __enter__=MagicMock(return_value=MagicMock(
                post=MagicMock(return_value=fake_response)
            )),
            __exit__=MagicMock(return_value=False),
        ))
    )

    with patch("tools.noctus.youtube.snapshot_run.get_yt_client", return_value=client), \
         patch("tools.noctus.youtube.snapshot_run.resolve_account", return_value=acc), \
         patch.dict("sys.modules", {"httpx": fake_httpx}):
        result = snapshot_run(
            account=acc["id"],
            api_token="tok_test",
            base_url="https://social-wiring.example.com",
        )

    assert result.get("status") == "triggered"
    assert result["account_id"] == acc["id"]


# ─── registration smoke ───────────────────────────────────────────────────────


def test_register_all_smoke():
    """register_all() should register 6 tools without raising."""
    from tools.noctus.youtube import register_all

    names: list[str] = []

    class FakeServer:
        def tool(self, *, name: str, description: str = ""):
            def decorator(fn):
                names.append(name)
                return fn
            return decorator

    register_all(FakeServer())

    assert "noctus.youtube.channel_stats" in names
    assert "noctus.youtube.list_videos" in names
    assert "noctus.youtube.list_shorts" in names
    assert "noctus.youtube.report" in names
    assert "noctus.youtube.snapshot_run" in names
    assert "noctus.youtube.sync" in names
    assert len(names) == 6
