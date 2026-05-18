"""Smoke + behavior tests for the Google connector MCP.

Deterministic, no network — every tool is exercised against the seed
libs' Fakes (`FakeCalendarAdapter`, `StaticRoutingAdapter`,
`FakeYoutubeClient`, `FakeDriveDownloader`), reached through the public
factories with no creds configured. Mirrors `mcp/vista/tests/`.

Path setup mirrors mcp/noctusai's self-dir strategy: `mcp/` for `_kit`,
`mcp/google/` for the flat connector modules (the package name `google`
collides with the PyPI `google.*` namespace, so we never import it as a
`google.` package).
"""
from __future__ import annotations

import asyncio

import pytest

# sys.path wiring (mcp/ for _kit, mcp/google/ for the flat connector
# modules) is owned by ../conftest.py — it runs before collection so the
# `from tools import ...` below resolves. See conftest.py for why the
# package isn't imported as a `google.` package.

from tools import all_descriptors, all_handlers
import settings as gsettings


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    """get_settings is process-cached; clear before each test so env
    isolation holds (no test configures creds — all run Fake paths)."""
    gsettings.get_settings.cache_clear()
    yield
    gsettings.get_settings.cache_clear()


# ─── Composition / registry ──────────────────────────────────────────────


def test_package_imports():
    import schemas  # noqa: F401
    from tools import calendar, drive, maps, youtube  # noqa: F401
    from noctusai_lib.integrations import (  # noqa: F401
        google_calendar,
        google_drive,
        google_maps,
        youtube as yt_seed,
    )


def test_all_handlers_aggregates_every_leaf():
    descriptors = all_descriptors()
    handlers = all_handlers()
    descriptor_names = {d.name for d in descriptors}
    handler_names = set(handlers.keys())
    assert descriptor_names == handler_names, (
        f"mismatch — descriptors only: {descriptor_names - handler_names}; "
        f"handlers only: {handler_names - descriptor_names}"
    )


def test_exact_tool_name_set():
    """Pin the registered tool set (regression guard)."""
    assert set(all_handlers().keys()) == {
        "google.calendar.create_event",
        "google.calendar.list_events",
        "google.maps.travel_estimate",
        "google.youtube.get_channel",
        "google.youtube.list_channel_videos",
        "google.youtube.get_video",
        "google.youtube.upload_video",
        "google.drive.parse_url",
        "google.drive.get_metadata",
        "google.drive.download",
    }


def test_dotted_naming_convention():
    for name in all_handlers():
        parts = name.split(".")
        assert len(parts) == 3, f"tool {name!r} not 3-segment dotted"
        assert parts[0] == "google", f"tool {name!r} not under google.* umbrella"


def test_settings_lenient_no_config():
    """Deferred-config: construction must not raise with nothing set."""
    s = gsettings.GoogleConnectorSettings()
    assert s.configured is False
    assert s.oauth_configured is False


def test_settings_oauth_requires_full_trio():
    partial = gsettings.GoogleConnectorSettings(
        oauth_client_id="cid", oauth_client_secret="sec"
    )
    assert partial.oauth_configured is False
    full = gsettings.GoogleConnectorSettings(
        oauth_client_id="cid",
        oauth_client_secret="sec",
        oauth_refresh_token="rt",
    )
    assert full.oauth_configured is True


# ─── Calendar ────────────────────────────────────────────────────────────


def test_calendar_create_event_blocked_without_confirm():
    """WRITE GATE: confirm omitted ⇒ typed error, NO mutation."""
    h = all_handlers()
    out = _run(
        h["google.calendar.create_event"](
            {
                "calendar_id": "primary",
                "summary": "Standup",
                "start_at": "2026-05-20T14:00:00",
                "end_at": "2026-05-20T14:30:00",
                "timezone": "America/Sao_Paulo",
            }
        )
    )
    assert out["created"] is None
    assert out["adapter"] == "unconfirmed"
    assert out["error"]["error_class"] == "PermissionError"


def test_calendar_create_event_with_confirm_uses_fake():
    h = all_handlers()
    out = _run(
        h["google.calendar.create_event"](
            {
                "calendar_id": "primary",
                "summary": "Standup",
                "start_at": "2026-05-20T14:00:00",
                "end_at": "2026-05-20T14:30:00",
                "timezone": "America/Sao_Paulo",
                "confirm": True,
            }
        )
    )
    assert out["adapter"] == "fake"
    assert out["created"] is not None
    assert out["created"]["event_id"]
    assert "error" not in out


def test_calendar_list_events_no_confirm_gate():
    h = all_handlers()
    out = _run(
        h["google.calendar.list_events"](
            {
                "calendar_id": "primary",
                "time_min": "2026-05-01T00:00:00",
                "time_max": "2026-05-31T23:59:59",
            }
        )
    )
    assert out["adapter"] == "fake"
    assert out["events"] == []
    assert "error" not in out


# ─── Maps ────────────────────────────────────────────────────────────────


def test_maps_travel_estimate_static_fallback():
    h = all_handlers()
    out = _run(
        h["google.maps.travel_estimate"](
            {
                "origin": {"latitude": -23.5, "longitude": -46.6},
                "destination": {"latitude": -23.6, "longitude": -46.7},
            }
        )
    )
    assert out["adapter"] == "static"
    assert out["minutes"] == 20  # StaticRoutingAdapter default
    assert "error" not in out


def test_maps_travel_estimate_identical_coords_is_zero():
    h = all_handlers()
    out = _run(
        h["google.maps.travel_estimate"](
            {
                "origin": {"latitude": -23.5, "longitude": -46.6},
                "destination": {"latitude": -23.5, "longitude": -46.6},
            }
        )
    )
    assert out["minutes"] == 0


# ─── YouTube ─────────────────────────────────────────────────────────────


def test_youtube_get_channel_fake_unknown_id():
    h = all_handlers()
    out = _run(h["google.youtube.get_channel"]({"channel_id": "UCnope"}))
    assert out["adapter"] == "fake"
    assert out["channel"] is None
    assert out["quota_units_consumed"] == 1


def test_youtube_list_channel_videos_fake_empty():
    h = all_handlers()
    out = _run(
        h["google.youtube.list_channel_videos"]({"channel_id": "UCnope"})
    )
    assert out["adapter"] == "fake"
    assert out["videos"] == []
    # Fake charges 2 units even for an unknown channel (you-pay-on-call).
    assert out["quota_units_consumed"] == 2


def test_youtube_get_video_fake_unknown_id():
    h = all_handlers()
    out = _run(h["google.youtube.get_video"]({"video_id": "nope"}))
    assert out["adapter"] == "fake"
    assert out["video"] is None
    assert out["quota_units_consumed"] == 1


def test_youtube_upload_blocked_without_confirm():
    """WRITE GATE."""
    h = all_handlers()
    out = _run(h["google.youtube.upload_video"]({}))
    assert out["uploaded"] is False
    assert out["adapter"] == "unconfirmed"
    assert out["error"]["error_class"] == "PermissionError"


def test_youtube_upload_confirm_but_no_oauth_returns_oauth_error():
    h = all_handlers()
    out = _run(h["google.youtube.upload_video"]({"confirm": True}))
    assert out["uploaded"] is False
    assert out["error"]["error_class"] == "PermissionError"
    assert "OAuth" in out["error"]["message"]


def test_youtube_upload_lib_gap_is_not_silently_faked(monkeypatch):
    """With confirm+OAuth configured, the LIB GAP surfaces as a typed
    NotImplementedError — NEVER a fake success (no-silent-error)."""
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "cid")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "sec")
    monkeypatch.setenv("GOOGLE_OAUTH_REFRESH_TOKEN", "rt")
    gsettings.get_settings.cache_clear()
    h = all_handlers()
    out = _run(h["google.youtube.upload_video"]({"confirm": True}))
    assert out["uploaded"] is False
    assert out["error"]["error_class"] == "NotImplementedError"
    assert "no upload method" in out["error"]["message"]


# ─── Drive ───────────────────────────────────────────────────────────────


# Drive ids are URL-safe base64, ≥20 chars (the lib mapper's contract).
_FAKE_DRIVE_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz0123456"


def test_drive_parse_url_extracts_id():
    h = all_handlers()
    out = _run(
        h["google.drive.parse_url"](
            {
                "url_or_id": (
                    f"https://drive.google.com/file/d/{_FAKE_DRIVE_ID}/view?usp=sharing"
                )
            }
        )
    )
    assert out["file_id"] == _FAKE_DRIVE_ID


def test_drive_parse_url_passthrough_bare_id():
    h = all_handlers()
    out = _run(h["google.drive.parse_url"]({"url_or_id": _FAKE_DRIVE_ID}))
    assert out["file_id"] == _FAKE_DRIVE_ID


def test_drive_parse_url_bad_input_returns_typed_error():
    """Too-short / non-Drive input ⇒ lib raises ValueError ⇒ tool
    surfaces a typed error (no crash, no silent empty success)."""
    h = all_handlers()
    out = _run(h["google.drive.parse_url"]({"url_or_id": "nope"}))
    assert out["file_id"] == ""
    assert out["error"]["error_class"] == "ValueError"


def test_drive_get_metadata_fake_missing_is_none():
    h = all_handlers()
    out = _run(h["google.drive.get_metadata"]({"file_id": "absent"}))
    assert out["adapter"] == "fake"
    # Fake has no seeded files ⇒ None (mirrors Drive's 404-for-both).
    assert out["file"] is None
    assert "error" not in out


def test_drive_download_fake_missing_returns_typed_error(tmp_path):
    """FakeDriveDownloader raises FileNotFoundError for an unseeded id;
    the tool must surface it as a typed error, not crash."""
    h = all_handlers()
    out = _run(
        h["google.drive.download"](
            {"file_id": "absent", "dest_path": str(tmp_path / "x.bin")}
        )
    )
    assert out["adapter"] == "fake"
    assert out["file"] is None
    assert out["error"]["error_class"] == "FileNotFoundError"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
