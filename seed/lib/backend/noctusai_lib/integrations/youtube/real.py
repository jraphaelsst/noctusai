"""Real YouTube Data API v3 client.

Wraps `googleapiclient.discovery.build("youtube", "v3", ...)`.
Authenticates either with an API key (the typical case for read-only
public data) OR OAuth credentials (when private playlists / signed-in
context is needed).

The client encodes the cheap channel→uploads-playlist→playlistItems
trick correctly so consumers don't re-derive it. Quota costs are
documented in `protocol.py` and round-tripped via
`ListResult.quota_units_consumed` so consumers can budget.

API errors are logged at WARN level before re-raising — never silently
swallowed (per the no-silent-errors rule).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from noctusai_lib.integrations.youtube.types import (
    TITLE_MAX_LEN,
    UPLOAD_QUOTA_UNITS,
    Channel,
    ListResult,
    PrivacyStatus,
    Video,
    VideoUpload,
)

logger = logging.getLogger(__name__)


# ---- ISO-8601 duration parser ----------------------------------------------


def _parse_iso8601_duration(duration: str) -> int:
    """Parse YouTube's `contentDetails.duration` (ISO-8601, e.g.
    `PT1H5M30S`, `PT5M30S`, `PT45S`) into integer seconds.

    Handles only the H/M/S subset YouTube emits. Days/weeks/months
    don't appear in video durations. Returns 0 on parse failure
    (logged at WARN) — never raises so a malformed entry doesn't
    poison a whole list."""
    if not duration or not duration.startswith("PT"):
        if duration:
            logger.warning(
                "youtube.duration_parse_unexpected_prefix duration=%r", duration
            )
        return 0

    body = duration[2:]
    hours = minutes = seconds = 0
    buf = ""
    try:
        for ch in body:
            if ch.isdigit():
                buf += ch
            elif ch == "H":
                hours = int(buf)
                buf = ""
            elif ch == "M":
                minutes = int(buf)
                buf = ""
            elif ch == "S":
                seconds = int(buf)
                buf = ""
    except ValueError:
        logger.warning("youtube.duration_parse_failed duration=%r", duration)
        return 0
    return hours * 3600 + minutes * 60 + seconds


def _parse_published_at(value: str) -> datetime:
    """Parse YouTube's `snippet.publishedAt` (RFC 3339, always UTC).

    Falls back to `datetime.min` (UTC) on parse failure — logged at WARN."""
    try:
        # YouTube emits `2026-05-04T12:00:00Z`. Python <3.11 chokes on
        # the `Z`; replace it for compatibility.
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        logger.warning("youtube.published_at_parse_failed value=%r", value)
        return datetime.min.replace(tzinfo=timezone.utc)


# ---- Mappers ---------------------------------------------------------------


def _channel_from_api(item: dict[str, Any]) -> Channel:
    snippet = item.get("snippet", {})
    content_details = item.get("contentDetails", {})
    related = content_details.get("relatedPlaylists", {})
    return Channel(
        id=item["id"],
        title=snippet.get("title", ""),
        description=snippet.get("description", ""),
        uploads_playlist_id=related.get("uploads", ""),
    )


def _video_from_api(item: dict[str, Any]) -> Video:
    snippet = item.get("snippet", {})
    content_details = item.get("contentDetails", {})
    statistics = item.get("statistics", {})
    return Video(
        id=item["id"],
        title=snippet.get("title", ""),
        description=snippet.get("description", ""),
        channel_id=snippet.get("channelId", ""),
        published_at=_parse_published_at(snippet.get("publishedAt", "")),
        duration_seconds=_parse_iso8601_duration(content_details.get("duration", "")),
        view_count=int(statistics.get("viewCount", 0) or 0),
    )


# ---- RealYoutubeClient -----------------------------------------------------


class RealYoutubeClient:
    """Real YouTube Data API v3 client.

    Pass either `api_key` (read-only public data — the common case) OR
    `oauth_credentials` (any `google.oauth2.credentials.Credentials`-shaped
    object — when private context is needed). At least one must be
    supplied; both being None raises `ValueError` at construction.

    Logs every API error at WARN+ before re-raising or returning None
    (per the no-silent-errors rule)."""

    def __init__(
        self,
        api_key: str | None = None,
        oauth_credentials: Any = None,
    ) -> None:
        if not api_key and oauth_credentials is None:
            raise ValueError(
                "RealYoutubeClient requires api_key or oauth_credentials"
            )
        self._api_key = api_key
        self._oauth_credentials = oauth_credentials

    def _service(self) -> Any:
        if self._oauth_credentials is not None:
            return build(
                "youtube",
                "v3",
                credentials=self._oauth_credentials,
                cache_discovery=False,
            )
        return build(
            "youtube",
            "v3",
            developerKey=self._api_key,
            cache_discovery=False,
        )

    # ---- YoutubeClient surface ----------------------------------------

    async def get_channel(self, channel_id: str) -> Channel | None:
        """1 quota unit (`channels.list?part=snippet,contentDetails`)."""
        try:
            response = (
                self._service()
                .channels()
                .list(part="snippet,contentDetails", id=channel_id)
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "youtube.get_channel_http_error channel_id=%s status=%s",
                channel_id,
                getattr(exc.resp, "status", "?"),
            )
            raise

        items = response.get("items", [])
        if not items:
            return None
        return _channel_from_api(items[0])

    async def list_channel_videos(
        self,
        channel_id: str,
        page_token: str | None = None,
    ) -> ListResult[Video]:
        """~2 quota units per page of 50 videos.

        Resolves the uploads playlist on every call (1 unit). To save
        that unit on subsequent pages, callers should cache the
        `Channel.uploads_playlist_id` value from the first call;
        a future enhancement may add an in-client cache."""
        # Step 1: resolve uploads playlist id (1 unit).
        channel = await self.get_channel(channel_id)
        if channel is None or not channel.uploads_playlist_id:
            return ListResult(items=[], next_page_token=None, quota_units_consumed=1)

        # Step 2: fetch a page of playlist items (1 unit).
        try:
            playlist_response = (
                self._service()
                .playlistItems()
                .list(
                    part="contentDetails",
                    playlistId=channel.uploads_playlist_id,
                    maxResults=50,
                    pageToken=page_token,
                )
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "youtube.list_channel_videos_http_error channel_id=%s status=%s",
                channel_id,
                getattr(exc.resp, "status", "?"),
            )
            raise

        playlist_items = playlist_response.get("items", [])
        next_page_token = playlist_response.get("nextPageToken")
        video_ids = [
            item["contentDetails"]["videoId"]
            for item in playlist_items
            if item.get("contentDetails", {}).get("videoId")
        ]

        if not video_ids:
            # No videos — only spent 1 (channels.list) + 1 (playlistItems.list).
            return ListResult(
                items=[], next_page_token=next_page_token, quota_units_consumed=2
            )

        # Step 3: fetch full video details for the batch (1 unit, regardless
        # of how many ids — up to 50 — the batch carries).
        try:
            videos_response = (
                self._service()
                .videos()
                .list(
                    part="snippet,contentDetails,statistics",
                    id=",".join(video_ids),
                )
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "youtube.list_channel_videos_videos_http_error channel_id=%s status=%s",
                channel_id,
                getattr(exc.resp, "status", "?"),
            )
            raise

        videos = [_video_from_api(item) for item in videos_response.get("items", [])]
        return ListResult(
            items=videos,
            next_page_token=next_page_token,
            # 1 (channels.list) + 1 (playlistItems.list) + 1 (videos.list) = 3.
            # Note: the "~2 units / page" figure in the Protocol assumes the
            # caller has already cached uploads_playlist_id; the first call
            # pays the extra unit for channels.list.
            quota_units_consumed=3,
        )

    async def get_video(self, video_id: str) -> Video | None:
        """1 quota unit (`videos.list?id=<video_id>`)."""
        try:
            response = (
                self._service()
                .videos()
                .list(part="snippet,contentDetails,statistics", id=video_id)
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "youtube.get_video_http_error video_id=%s status=%s",
                video_id,
                getattr(exc.resp, "status", "?"),
            )
            raise

        items = response.get("items", [])
        if not items:
            return None
        return _video_from_api(items[0])

    async def search(
        self,
        query: str,
        page_token: str | None = None,
    ) -> ListResult[Video]:
        """**100 quota units per page**. Prefer `list_channel_videos`
        for channel-scoped listings (~50× cheaper)."""
        try:
            response = (
                self._service()
                .search()
                .list(
                    part="snippet",
                    q=query,
                    type="video",
                    maxResults=50,
                    pageToken=page_token,
                )
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "youtube.search_http_error query=%r status=%s",
                query,
                getattr(exc.resp, "status", "?"),
            )
            raise

        items = response.get("items", [])
        # search.list snippet items don't include duration/statistics —
        # only id + snippet. We surface the snippet fields and leave
        # numeric fields at 0; consumers that need full details can
        # follow up with get_video(id).
        videos: list[Video] = []
        for item in items:
            video_id = item.get("id", {}).get("videoId")
            if not video_id:
                continue
            snippet = item.get("snippet", {})
            videos.append(
                Video(
                    id=video_id,
                    title=snippet.get("title", ""),
                    description=snippet.get("description", ""),
                    channel_id=snippet.get("channelId", ""),
                    published_at=_parse_published_at(snippet.get("publishedAt", "")),
                    duration_seconds=0,
                    view_count=0,
                )
            )

        return ListResult(
            items=videos,
            next_page_token=response.get("nextPageToken"),
            quota_units_consumed=100,
        )

    async def upload_video(
        self,
        *,
        file_path: str,
        title: str,
        description: str = "",
        tags: list[str] | None = None,
        privacy_status: PrivacyStatus = "private",
        category_id: str = "22",
    ) -> VideoUpload:
        """**1600 quota units** (`videos.insert`, resumable).

        Requires OAuth credentials — `videos.insert` is a write call;
        an API-key-only client cannot upload. Raises `ValueError` at
        call time when no OAuth credentials were supplied (fail loud,
        per the no-silent-errors rule). The local file is streamed via
        a resumable `MediaFileUpload` so large videos don't buffer in
        memory."""
        if self._oauth_credentials is None:
            raise ValueError(
                "RealYoutubeClient.upload_video requires oauth_credentials "
                "(videos.insert is a write; an API key cannot upload)"
            )

        clipped_title = title[:TITLE_MAX_LEN]
        body: dict[str, Any] = {
            "snippet": {
                "title": clipped_title,
                "description": description,
                "categoryId": category_id,
            },
            "status": {"privacyStatus": privacy_status},
        }
        if tags:
            body["snippet"]["tags"] = tags

        media = MediaFileUpload(file_path, resumable=True)
        try:
            request = (
                self._service()
                .videos()
                .insert(part="snippet,status", body=body, media_body=media)
            )
            response: dict[str, Any] | None = None
            while response is None:
                # Resumable upload: drive the chunked transfer to
                # completion. next_chunk() returns (status, response);
                # response stays None until the final chunk lands.
                _status, response = request.next_chunk()
        except HttpError as exc:
            logger.warning(
                "youtube.upload_video_http_error title=%r status=%s",
                clipped_title,
                getattr(exc.resp, "status", "?"),
            )
            raise

        video_id = response.get("id", "")
        return VideoUpload(
            video_id=video_id,
            title=clipped_title,
            url=f"https://www.youtube.com/watch?v={video_id}",
            privacy_status=privacy_status,
            quota_units_consumed=UPLOAD_QUOTA_UNITS,
        )


__all__ = ["RealYoutubeClient"]
