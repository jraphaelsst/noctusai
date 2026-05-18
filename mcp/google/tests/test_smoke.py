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
    from tools import calendar, drive, gmail, maps, youtube  # noqa: F401
    from noctusai_lib.integrations import (  # noqa: F401
        gmail as gmail_seed,
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
        "google.drive.search",
        "google.drive.read_file",
        "google.gmail.send_message",
        "google.gmail.list_messages",
        "google.gmail.get_message",
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


# ─── Gmail ───────────────────────────────────────────────────────────────


def test_gmail_send_blocked_without_confirm():
    """WRITE GATE: confirm omitted ⇒ typed error, nothing sent."""
    h = all_handlers()
    out = _run(
        h["google.gmail.send_message"](
            {"to": "x@y.com", "subject": "hi", "body_text": "hello"}
        )
    )
    assert out["sent"] is None
    assert out["adapter"] == "unconfirmed"
    assert out["error"]["error_class"] == "PermissionError"


def test_gmail_send_with_confirm_uses_fake():
    h = all_handlers()
    out = _run(
        h["google.gmail.send_message"](
            {
                "to": "x@y.com",
                "subject": "hi",
                "body_text": "hello",
                "confirm": True,
            }
        )
    )
    assert out["adapter"] == "fake"
    assert out["sent"] is not None
    assert out["sent"]["message_id"]
    assert out["sent"]["thread_id"]
    assert "error" not in out


def test_gmail_list_messages_no_confirm_gate():
    h = all_handlers()
    out = _run(h["google.gmail.list_messages"]({}))
    assert out["adapter"] == "fake"
    assert isinstance(out["messages"], list)
    assert "error" not in out


def test_gmail_get_message_missing_returns_null():
    h = all_handlers()
    out = _run(h["google.gmail.get_message"]({"message_id": "does-not-exist"}))
    assert out["adapter"] == "fake"
    assert out["message"] is None
    assert "error" not in out


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
    """confirm passed but NO OAuth trio ⇒ typed PermissionError; an API
    key cannot authorize uploads. NEVER a faked success."""
    h = all_handlers()
    out = _run(
        h["google.youtube.upload_video"](
            {"confirm": True, "file_path": "/tmp/v.mp4", "title": "T"}
        )
    )
    assert out["uploaded"] is False
    assert out["video"] is None
    assert out["adapter"] == "real"
    assert out["error"]["error_class"] == "PermissionError"
    assert "OAuth" in out["error"]["message"]


def test_youtube_upload_real_path_against_fake_records_uploaded():
    """The REAL handler path — confirm gate + client + audit + shaping —
    exercised against an injected FakeYoutubeClient (records `.uploaded`)
    via the connector's dependency-injection test seam (NOT a
    monkeypatch of our own guard)."""
    from noctusai_lib.integrations.youtube import FakeYoutubeClient
    from tools import youtube as yt_tool

    fake = FakeYoutubeClient()
    yt_tool.configure_upload_client(fake)
    try:
        h = all_handlers()
        out = _run(
            h["google.youtube.upload_video"](
                {
                    "confirm": True,
                    "file_path": "/tmp/clip.mp4",
                    "title": "x" * 130,  # adapter clips to 100
                    "description": "demo",
                    "tags": ["a", "b"],
                    "privacy_status": "unlisted",
                }
            )
        )
    finally:
        yt_tool.configure_upload_client(None)

    assert out["uploaded"] is True
    assert out["adapter"] == "real"
    assert "error" not in out
    assert out["video"]["video_id"] == "fake-upload-1"
    assert out["video"]["privacy_status"] == "unlisted"
    assert len(out["video"]["title"]) == 100  # TITLE_MAX_LEN clip
    assert out["video"]["quota_units_consumed"] == 1600
    # Recorded on the fake — the real handler path actually called it.
    assert len(fake.uploaded) == 1
    assert fake.uploaded[0].video_id == "fake-upload-1"


def test_youtube_upload_blocked_without_confirm_skips_client():
    """confirm gate fires BEFORE any client is built/injected — an
    injected client must NOT be called when confirm is omitted."""
    from noctusai_lib.integrations.youtube import FakeYoutubeClient
    from tools import youtube as yt_tool

    fake = FakeYoutubeClient()
    yt_tool.configure_upload_client(fake)
    try:
        h = all_handlers()
        out = _run(
            h["google.youtube.upload_video"](
                {"file_path": "/tmp/v.mp4", "title": "T"}
            )
        )
    finally:
        yt_tool.configure_upload_client(None)
    assert out["uploaded"] is False
    assert out["adapter"] == "unconfirmed"
    assert out["error"]["error_class"] == "PermissionError"
    assert fake.uploaded == []  # gate short-circuited before the client


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


# ─── Drive reader (search / read_file) ───────────────────────────────────


def test_drive_search_fake_empty_no_creds():
    """No creds ⇒ FakeDriveReader; no seeded files ⇒ empty hits, no
    error envelope, adapter='fake'."""
    h = all_handlers()
    out = _run(h["google.drive.search"]({"query": "anything"}))
    assert out["adapter"] == "fake"
    assert out["hits"] == []
    assert out["next_page_token"] is None
    assert "error" not in out


def test_drive_read_file_fake_missing_is_none_not_error():
    """Missing/inaccessible ⇒ clean null result (Drive 404s both), NOT
    an error envelope — mirrors get_metadata."""
    h = all_handlers()
    out = _run(h["google.drive.read_file"]({"file_id": "absent"}))
    assert out["adapter"] == "fake"
    assert out["content"] is None
    assert out["stats"] == {}
    assert "error" not in out


def test_drive_read_file_csv_stats_defends_the_recount_trap():
    """read_file returns Python-computed `stats` for CSV content — the
    LLM-recount-trap defense. Exercised against an injected
    FakeDriveReader via the connector's DI test seam."""
    from noctusai_lib.integrations.google_drive import FakeDriveReader
    from tools import drive as drive_tool

    fake = FakeDriveReader()
    csv = "Data,Ref\n1,ONE5597\n2,ONE5598\n3,ONE5599\n"
    fake.add_file(
        "sheet1", "Cronograma", csv.encode(),
        mime_type="text/csv", rendered_as="text/csv",
    )
    drive_tool.configure_reader(fake)
    try:
        h = all_handlers()
        sres = _run(h["google.drive.search"]({"query": "cronograma"}))
        out = _run(h["google.drive.read_file"]({"file_id": "sheet1"}))
    finally:
        drive_tool.configure_reader(None)

    assert sres["hits"][0]["id"] == "sheet1"
    assert sres["hits"][0]["capabilities"] == {"canDownload": True}
    assert out["content"]["rendered_as"] == "text/csv"
    # stats is ground truth — 3 data rows under the header.
    assert out["stats"]["csv_data_rows"] == 3
    assert out["stats"]["csv_column_count"] == 2
    assert out["stats"]["csv_header"] == "Data,Ref"
    assert out["stats"]["total_lines"] == 4
    assert "error" not in out


def test_drive_read_file_binary_not_decoded():
    """Binary content is NOT decoded — placeholder data + byte_length
    note; extraction deferred to the media seam."""
    from noctusai_lib.integrations.google_drive import FakeDriveReader
    from tools import drive as drive_tool

    fake = FakeDriveReader()
    fake.add_file(
        "pdf1", "report.pdf", b"%PDF-1.7\x00\x01binary",
        mime_type="application/pdf", rendered_as="binary",
    )
    drive_tool.configure_reader(fake)
    try:
        h = all_handlers()
        out = _run(h["google.drive.read_file"]({"file_id": "pdf1"}))
    finally:
        drive_tool.configure_reader(None)

    assert out["content"]["rendered_as"] == "binary"
    assert "not inlined" in out["content"]["data"]
    assert out["stats"]["byte_length"] == len(b"%PDF-1.7\x00\x01binary")
    assert "media seam" in out["stats"]["note"]
    assert "error" not in out


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
