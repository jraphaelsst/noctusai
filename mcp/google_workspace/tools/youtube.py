"""google.youtube.* tools — thin wrappers over the seed YouTube client.

Tools registered:
- google.youtube.get_channel         — READ, 1 quota unit.
- google.youtube.list_channel_videos — READ, ~2 units / 50 videos (the cheap path).
- google.youtube.get_video           — READ, 1 quota unit.
- google.youtube.upload_video        — WRITE, OAuth-only, 1600 quota units.

All tools compose `make_youtube_client(...)` from
`noctusai_lib.integrations.youtube` — Fake by default (no api_key /
OAuth), Real when credentials are configured.

QUOTA NOTE (surfaced from the lib Protocol docstrings): YouTube's daily
default is 10,000 units. `list_channel_videos` is ~50× cheaper than a
`search.list`-style listing — prefer it for channel-scoped browsing.
`upload_video` (`videos.insert`, resumable) costs 1600 units — the
single most expensive call in the API (≈6 uploads exhaust a fresh
daily quota).

upload_video is REAL against the seed `YoutubeClient.upload_video`
contract (verified 2026-05-17 against
`noctusai_lib.integrations.youtube.{protocol,fake,factory,types}.py` on
the post-absorption base — Protocol + `FakeYoutubeClient` (records
`.uploaded`) + `RealYoutubeClient` + factory all ship the method).
The tool keeps the WRITE contract: a required `confirm=true` gate, an
OAuth-trio check (an API key cannot authorize uploads — the Real
adapter raises `ValueError` without OAuth creds), and a `google.audit`
log line. No creds ⇒ a typed error explaining the OAuth requirement
(NEVER a faked success — no-silent-error).
"""
from __future__ import annotations

import logging

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.youtube import (
    Video,
    VideoUpload,
    make_youtube_client,
)

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
    UploadedVideoModel,
    UploadVideoInput,
    UploadVideoOutput,
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


# Connector-side test seam (dependency injection, NOT monkeypatching):
# `upload_video` builds its OAuth-delegated client through this slot so
# a test can inject a `FakeYoutubeClient` (recording `.uploaded`) and
# exercise the REAL handler path — gate + OAuth-check + audit + shaping —
# without a network round-trip. Production leaves it None ⇒ the real
# `google.oauth2.credentials.Credentials`-backed client is built. Mirrors
# the FastAPI-dep-factory module-slot pattern used across the codebase
# (default None, populated by an explicit configure call at request time).
_upload_client_override = None


def configure_upload_client(client) -> None:
    """Inject the `YoutubeClient` `upload_video` uses (tests only).

    Pass `None` to restore the production path (real OAuth client).
    """
    global _upload_client_override
    _upload_client_override = client


def _oauth_youtube_client(s):
    """Build the OAuth-delegated Real `YoutubeClient` from the connector's
    env/.env refresh-token trio.

    Connector-side credential plumbing is the right layer: `_kit` owns
    only generic boilerplate; vendor credential resolution stays
    connector-side (the same boundary the calendar tool's
    `_EnvOAuthResolver` draws). The lib's `RealYoutubeClient` accepts any
    `google.oauth2.credentials.Credentials`-shaped object and refreshes
    the access token on demand from the refresh_token."""
    from google.oauth2.credentials import Credentials

    creds = Credentials(
        token=None,
        refresh_token=s.oauth_refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=s.oauth_client_id,
        client_secret=s.oauth_client_secret,
        scopes=["https://www.googleapis.com/auth/youtube.upload"],
    )
    return make_youtube_client(oauth_credentials=creds)


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

    Real against the seed `YoutubeClient.upload_video` contract. Gate
    order: confirm → OAuth-trio check → build client → upload → shape.
    No OAuth creds ⇒ a typed `PermissionError` (an API key cannot
    authorize uploads) — NEVER a faked success (no-silent-error)."""
    if not bool(args.get("confirm", False)):
        return UploadVideoOutput(
            uploaded=False, video=None, adapter="unconfirmed"
        ).model_dump() | {
            "error": typed_error(
                PermissionError(
                    "google.youtube.upload_video is a WRITE — re-call with "
                    "confirm=true to attempt the upload."
                )
            )
        }

    inp = UploadVideoInput(**args)
    s = get_settings()

    client = _upload_client_override
    if client is None:
        if not s.oauth_configured:
            return UploadVideoOutput(
                uploaded=False, video=None, adapter="real"
            ).model_dump() | {
                "error": typed_error(
                    PermissionError(
                        "google.youtube.upload_video requires the OAuth "
                        "user-delegated trio (GOOGLE_OAUTH_CLIENT_ID / "
                        "GOOGLE_OAUTH_CLIENT_SECRET / "
                        "GOOGLE_OAUTH_REFRESH_TOKEN); an API key cannot "
                        "authorize uploads."
                    )
                )
            }
        client = _oauth_youtube_client(s)

    _audit.info(
        "AUDIT google.youtube.upload_video adapter=real confirm=true "
        "file_path=%s privacy=%s (1600-quota videos.insert attempt)",
        inp.file_path,
        inp.privacy_status,
    )
    try:
        result: VideoUpload = await client.upload_video(
            file_path=inp.file_path,
            title=inp.title,
            description=inp.description,
            tags=inp.tags or None,
            privacy_status=inp.privacy_status,  # type: ignore[arg-type]
            category_id=inp.category_id,
        )
    except Exception as e:  # noqa: BLE001
        _audit.warning(
            "AUDIT google.youtube.upload_video FAILED file_path=%s error=%s",
            inp.file_path,
            type(e).__name__,
        )
        return UploadVideoOutput(
            uploaded=False, video=None, adapter="real"
        ).model_dump() | {"error": typed_error(e)}

    _audit.info(
        "AUDIT google.youtube.upload_video OK video_id=%s quota=%d",
        result.video_id,
        result.quota_units_consumed,
    )
    return UploadVideoOutput(
        uploaded=True,
        video=UploadedVideoModel(
            video_id=result.video_id,
            title=result.title,
            url=result.url,
            privacy_status=result.privacy_status,
            quota_units_consumed=result.quota_units_consumed,
        ),
        adapter="real",
    ).model_dump()


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
                "Upload a local video file to YouTube (resumable "
                "videos.insert). WRITE side-effect, OAuth-only, QUOTA: "
                "1600 units — the single most expensive call in the API "
                "(≈6 uploads exhaust a fresh 10,000/day quota). You MUST "
                "pass confirm=true or the call is refused. Requires the "
                "OAuth trio (an API key cannot authorize uploads). "
                "Defaults privacy_status to 'private' — upload public/"
                "unlisted ONLY if the user explicitly asked. The attempt "
                "and outcome are written to the google.audit log."
            ),
            inputSchema=UploadVideoInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
