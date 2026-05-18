"""google.youtube.* tools — thin wrappers over the seed YouTube client.

Tools registered:
- google.youtube.get_channel         — READ, 1 quota unit.
- google.youtube.list_channel_videos — READ, ~2 units / 50 videos (the cheap path).
- google.youtube.get_video           — READ, 1 quota unit.
- google.youtube.upload_video        — WRITE, OAuth-only, 1600 quota units.

Read tools compose `make_youtube_client(...)` from
`noctusai_lib.integrations.youtube` — Fake by default (no api_key /
OAuth), Real when credentials are configured.

QUOTA NOTE (surfaced from the lib Protocol docstrings): YouTube's daily
default is 10,000 units. `list_channel_videos` is ~50× cheaper than a
`search.list`-style listing — prefer it for channel-scoped browsing.

upload_video LIB GAP: the seed `YoutubeClient` Protocol / Fake / factory
ship NO upload method (get_channel / list_channel_videos / get_video /
search only — verified against
`noctusai_lib.integrations.youtube.{protocol,fake,factory}.py` 2026-05-17).
The tool is registered with the WRITE contract (confirm gate + audit
log) but returns a typed error pointing at the lib gap rather than
silently faking an upload success — building a real uploader belongs in
a seed-lib follow-up, not in mcp/ (no-connector-logic-in-mcp rule).
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.youtube import Video, make_youtube_client

from _kit.errors import typed_error

from settings import get_settings
from schemas import (
    ChannelModel,
    GetChannelInput,
    GetChannelOutput,
    GetVideoInput,
    GetVideoOutput,
    ListChannelVideosInput,
    ListChannelVideosOutput,
    VideoModel,
)

logger = logging.getLogger(__name__)
_audit = logging.getLogger("google.audit")


def _client_and_kind():
    """Real client when api_key OR OAuth creds present; else Fake."""
    s = get_settings()
    if s.api_key or s.oauth_configured:
        return (
            make_youtube_client(api_key=s.api_key),
            "real",
        )
    return make_youtube_client(use_fake=True), "fake"


def _video_model(v: Video) -> VideoModel:
    return VideoModel(
        id=v.id,
        title=v.title,
        description=v.description,
        channel_id=v.channel_id,
        published_at=v.published_at.isoformat(),
        duration_seconds=v.duration_seconds,
        view_count=v.view_count,
    )


# ─── Handlers ────────────────────────────────────────────────────────────


async def get_channel(args: dict) -> dict:
    inp = GetChannelInput(**args)
    client, kind = _client_and_kind()
    try:
        ch = await client.get_channel(inp.channel_id)
    except Exception as e:  # noqa: BLE001
        return GetChannelOutput(
            channel=None, quota_units_consumed=1, adapter=kind
        ).model_dump() | {"error": typed_error(e)}
    return GetChannelOutput(
        channel=(
            ChannelModel(
                id=ch.id,
                title=ch.title,
                description=ch.description,
                uploads_playlist_id=ch.uploads_playlist_id,
            )
            if ch
            else None
        ),
        quota_units_consumed=1,
        adapter=kind,
    ).model_dump()


async def list_channel_videos(args: dict) -> dict:
    inp = ListChannelVideosInput(**args)
    client, kind = _client_and_kind()
    try:
        result = await client.list_channel_videos(inp.channel_id, inp.page_token)
    except Exception as e:  # noqa: BLE001
        return ListChannelVideosOutput(
            videos=[], next_page_token=None, quota_units_consumed=2, adapter=kind
        ).model_dump() | {"error": typed_error(e)}
    return ListChannelVideosOutput(
        videos=[_video_model(v) for v in result.items],
        next_page_token=result.next_page_token,
        quota_units_consumed=result.quota_units_consumed,
        adapter=kind,
    ).model_dump()


async def get_video(args: dict) -> dict:
    inp = GetVideoInput(**args)
    client, kind = _client_and_kind()
    try:
        v = await client.get_video(inp.video_id)
    except Exception as e:  # noqa: BLE001
        return GetVideoOutput(
            video=None, quota_units_consumed=1, adapter=kind
        ).model_dump() | {"error": typed_error(e)}
    return GetVideoOutput(
        video=_video_model(v) if v else None,
        quota_units_consumed=1,
        adapter=kind,
    ).model_dump()


async def upload_video(args: dict) -> dict:
    """WRITE, OAuth-only, 1600 quota units. Confirm-gated + audited.

    The seed YouTube client ships no upload method (verified lib gap —
    see module docstring). We honor the WRITE contract (gate + audit)
    but return a typed error rather than silently faking success."""
    confirm = bool(args.get("confirm", False))
    s = get_settings()

    if not confirm:
        return {"uploaded": False, "adapter": "unconfirmed"} | {
            "error": typed_error(
                PermissionError(
                    "google.youtube.upload_video is a WRITE — re-call with "
                    "confirm=true to attempt the upload."
                )
            )
        }

    if not s.oauth_configured:
        return {"uploaded": False, "adapter": "real"} | {
            "error": typed_error(
                PermissionError(
                    "google.youtube.upload_video requires the OAuth "
                    "user-delegated trio (GOOGLE_OAUTH_CLIENT_ID / "
                    "GOOGLE_OAUTH_CLIENT_SECRET / GOOGLE_OAUTH_REFRESH_TOKEN); "
                    "an API key cannot authorize uploads."
                )
            )
        }

    _audit.info(
        "AUDIT google.youtube.upload_video adapter=real confirm=true "
        "(LIB GAP — no seed uploader; returning typed error)"
    )
    return {"uploaded": False, "adapter": "real"} | {
        "error": typed_error(
            NotImplementedError(
                "Seed YouTube client ships no upload method "
                "(noctusai_lib.integrations.youtube exposes get_channel / "
                "list_channel_videos / get_video / search only). A real "
                "uploader (resumable MediaFileUpload, 1600-quota) must be "
                "added to the seed lib before this tool can execute — "
                "filed as a Wave-3 seed-lib follow-up. mcp/ holds no "
                "connector logic by rule."
            )
        )
    }


# ─── Registration ───────────────────────────────────────────────────────


HANDLERS = {
    "google.youtube.get_channel": get_channel,
    "google.youtube.list_channel_videos": list_channel_videos,
    "google.youtube.get_video": get_video,
    "google.youtube.upload_video": upload_video,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="google.youtube.get_channel",
            description=(
                "Fetch a YouTube channel by id. QUOTA: 1 unit "
                "(channels.list). Returns the channel's uploads_playlist_id "
                "— feed it to list_channel_videos for cheap listing. Read."
            ),
            inputSchema=GetChannelInput.model_json_schema(),
        ),
        Tool(
            name="google.youtube.list_channel_videos",
            description=(
                "List a channel's uploads, newest first, paginated. "
                "QUOTA: ~2 units / 50 videos (playlistItems.list + "
                "videos.list) — ~50× CHEAPER than a search.list-style "
                "listing (100 units/page). Prefer this for channel-scoped "
                "browsing. Read."
            ),
            inputSchema=ListChannelVideosInput.model_json_schema(),
        ),
        Tool(
            name="google.youtube.get_video",
            description=(
                "Fetch a single video by id. QUOTA: 1 unit (videos.list). "
                "Read."
            ),
            inputSchema=GetVideoInput.model_json_schema(),
        ),
        Tool(
            name="google.youtube.upload_video",
            description=(
                "Upload a video. WRITE side-effect, OAuth-only, QUOTA: "
                "1600 units. You MUST pass confirm=true or the call is "
                "refused. Requires the OAuth trio (an API key cannot "
                "authorize uploads). NOTE: the seed YouTube client ships "
                "no uploader yet — this returns a typed NotImplementedError "
                "(Wave-3 seed-lib follow-up); it never fakes success."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "confirm": {
                        "type": "boolean",
                        "description": "WRITE GATE — must be true.",
                    },
                },
                "required": ["confirm"],
            },
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
