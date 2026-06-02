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
import time
from datetime import datetime, timezone
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

from noctusai_lib.integrations.youtube.types import (
    TITLE_MAX_LEN,
    UPLOAD_QUOTA_UNITS,
    Channel,
    ChannelInfo,
    ListResult,
    PrivacyStatus,
    ProcessingStatus,
    Video,
    VideoFull,
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


def _pick_thumbnail_url(thumbnails: dict[str, Any]) -> str:
    """Highest-resolution → fallback walk: `maxres` → `high` → `medium`
    → `default`. Returns ``""`` when no thumbnail block is present
    (matches the `VideoFull.thumbnail_url` contract)."""
    for key in ("maxres", "high", "medium", "default"):
        block = thumbnails.get(key) or {}
        url = block.get("url")
        if url:
            return url
    return ""


def _video_full_from_api(item: dict[str, Any]) -> VideoFull:
    """Map a `videos.list?part=snippet,statistics,status,contentDetails`
    item to a :class:`VideoFull`. Mirrors `_video_from_api` for the
    base fields + adds the wider projection. Missing-field defaults
    match the seed convention (0 for ints, ``""`` for strings, ``()``
    for tags, ``"unknown"`` for privacy_status — never None)."""
    snippet = item.get("snippet", {}) or {}
    content_details = item.get("contentDetails", {}) or {}
    statistics = item.get("statistics", {}) or {}
    status = item.get("status", {}) or {}
    duration_iso = content_details.get("duration", "") or ""
    raw_tags = snippet.get("tags") or []
    return VideoFull(
        id=item["id"],
        title=snippet.get("title", ""),
        description=snippet.get("description", ""),
        channel_id=snippet.get("channelId", ""),
        published_at=_parse_published_at(snippet.get("publishedAt", "")),
        duration_seconds=_parse_iso8601_duration(duration_iso),
        duration_iso=duration_iso,
        thumbnail_url=_pick_thumbnail_url(snippet.get("thumbnails", {}) or {}),
        privacy_status=status.get("privacyStatus") or "unknown",
        view_count=int(statistics.get("viewCount", 0) or 0),
        like_count=int(statistics.get("likeCount", 0) or 0),
        comment_count=int(statistics.get("commentCount", 0) or 0),
        tags=tuple(raw_tags),
        category_id=snippet.get("categoryId", "") or "",
    )


def _channel_info_from_api(item: dict[str, Any]) -> ChannelInfo:
    """Map a `channels.list?mine=True&part=snippet,statistics` item to
    a :class:`ChannelInfo`. Numeric fields default to 0 when omitted."""
    snippet = item.get("snippet", {}) or {}
    statistics = item.get("statistics", {}) or {}
    return ChannelInfo(
        channel_id=item["id"],
        title=snippet.get("title", ""),
        subscriber_count=int(statistics.get("subscriberCount", 0) or 0),
        video_count=int(statistics.get("videoCount", 0) or 0),
        view_count=int(statistics.get("viewCount", 0) or 0),
    )
CHUNK_RETRY_MAX_ATTEMPTS = 3
"""Max retries per chunk (4 total attempts: 1 initial + 3 retries). Resets
to 0 on each successful chunk."""

CHUNK_RETRY_BASE_DELAY_S = 1.0
"""Exponential-backoff base — 1s, 2s, 4s for attempts 1/2/3."""

CHUNK_RETRY_MAX_DELAY_S = 4.0
"""Cap the per-attempt sleep so a long backoff doesn't stall the operator."""


def _is_quota_exceeded(exc: HttpError) -> bool:
    """Detect the `quotaExceeded` sub-error in an `HttpError` body.

    Google returns 403 with `reason="quotaExceeded"` (or
    `"dailyLimitExceeded"`) when the daily quota is hit. The status code
    alone (403) can't distinguish quota-exhaustion from
    permission-denied — we have to inspect the JSON body.

    Returns `False` on any decode error (no silent swallow — the WARN
    log lives at the call site)."""
    try:
        content = (
            exc.content.decode("utf-8")
            if isinstance(exc.content, bytes)
            else str(exc.content or "")
        )
    except (UnicodeDecodeError, AttributeError):
        return False
    lowered = content.lower()
    return (
        "quotaexceeded" in lowered
        or "dailylimitexceeded" in lowered
        or ("ratelimitexceeded" in lowered and getattr(exc.resp, "status", 0) == 403)
    )


def _is_transient_http_error(exc: HttpError) -> bool:
    """`5xx` server errors + `429` rate-limit are transient; everything
    else is permanent. `quotaExceeded` is special-cased UP at the call
    site (raised immediately, never retried)."""
    status = getattr(exc.resp, "status", 0)
    return status == 429 or 500 <= status < 600


def _is_transient_network_error(exc: BaseException) -> bool:
    """Transport-layer transients that the resumable upload loop can
    retry from. Kept separate from `_is_transient_http_error` because
    these don't carry an HTTP status code at all."""
    import socket
    import ssl

    return isinstance(exc, (ConnectionError, TimeoutError, socket.error, ssl.SSLError))


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

    async def get_video_full(self, video_id: str) -> VideoFull | None:
        """**1 quota unit** (`videos.list?part=snippet,statistics,
        status,contentDetails&id=<video_id>`). Same cost as
        :meth:`get_video` (the `part=` selection does not change the
        per-call cost)."""
        try:
            response = (
                self._service()
                .videos()
                .list(
                    part="snippet,statistics,status,contentDetails",
                    id=video_id,
                )
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "youtube.get_video_full_http_error video_id=%s status=%s",
                video_id,
                getattr(exc.resp, "status", "?"),
            )
            raise

        items = response.get("items", [])
        if not items:
            return None
        return _video_full_from_api(items[0])

    async def get_channel_info_mine(self) -> ChannelInfo:
        """**1 quota unit** (`channels.list?mine=True&part=snippet,
        statistics`). OAuth-only — the `mine=True` flag resolves the
        channel from the credentials, so an API-key-only client cannot
        call this. Raises `ValueError` at call time when no OAuth
        credentials were supplied (fail loud, per the no-silent-errors
        rule)."""
        if self._oauth_credentials is None:
            raise ValueError(
                "RealYoutubeClient.get_channel_info_mine requires "
                "oauth_credentials (channels.list?mine=True needs an "
                "authenticated context — an API key cannot resolve "
                "'the current user')"
            )
        try:
            response = (
                self._service()
                .channels()
                .list(part="snippet,statistics", mine=True)
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "youtube.get_channel_info_mine_http_error status=%s",
                getattr(exc.resp, "status", "?"),
            )
            raise

        items = response.get("items") or []
        if not items:
            raise ValueError(
                "channels.list?mine=True returned no items — the OAuth "
                "account has no associated YouTube channel."
            )
        return _channel_info_from_api(items[0])

    async def list_owned_videos(
        self,
        *,
        page_token: str | None = None,
        page_size: int = 50,
    ) -> ListResult[VideoFull]:
        """**101 quota units / page** — `search.list?forMine=True` (100)
        + `videos.list?part=snippet,statistics,status,contentDetails`
        (1). OAuth-only — `forMine=True` resolves the channel from the
        credentials. Raises `ValueError` at call time when no OAuth
        credentials were supplied."""
        if self._oauth_credentials is None:
            raise ValueError(
                "RealYoutubeClient.list_owned_videos requires "
                "oauth_credentials (search.list?forMine=True needs an "
                "authenticated context — an API key cannot resolve "
                "'the current user')"
            )

        try:
            search_response = (
                self._service()
                .search()
                .list(
                    part="id",
                    forMine=True,
                    type="video",
                    maxResults=page_size,
                    pageToken=page_token,
                )
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "youtube.list_owned_videos_search_http_error status=%s",
                getattr(exc.resp, "status", "?"),
            )
            raise

        video_ids = [
            item["id"]["videoId"]
            for item in search_response.get("items", [])
            if item.get("id", {}).get("videoId")
        ]
        next_page_token = search_response.get("nextPageToken")
        if not video_ids:
            # Only spent 100 (search.list); videos.list skipped.
            return ListResult(
                items=[], next_page_token=next_page_token, quota_units_consumed=100
            )

        try:
            videos_response = (
                self._service()
                .videos()
                .list(
                    part="snippet,statistics,status,contentDetails",
                    id=",".join(video_ids),
                )
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "youtube.list_owned_videos_videos_http_error status=%s",
                getattr(exc.resp, "status", "?"),
            )
            raise

        videos = [_video_full_from_api(item) for item in videos_response.get("items", [])]
        return ListResult(
            items=videos,
            next_page_token=next_page_token,
            # 100 (search.list?forMine) + 1 (videos.list) = 101.
            quota_units_consumed=101,
        )

    async def list_owned_videos_via_uploads(
        self,
        *,
        page_token: str | None = None,
        page_size: int = 50,
    ) -> ListResult[VideoFull]:
        """~2-3 quota units / page — the cheap, reliable "all my uploads
        (incl. private + unlisted)" path. See the Protocol docstring for
        the corrected uploads-playlist-returns-private contract.

        1. `channels.list?mine=True&part=contentDetails` → uploads
           playlist id (1 unit).
        2. `playlistItems.list?playlistId=<uploads>` → up to `page_size`
           video ids for the page (1 unit).
        3. `videos.list?part=snippet,statistics,status,contentDetails`
           → VideoFull batch (1 unit; skipped when the page is empty)."""
        if self._oauth_credentials is None:
            raise ValueError(
                "RealYoutubeClient.list_owned_videos_via_uploads requires "
                "oauth_credentials (channels.list?mine=True needs an "
                "authenticated context — an API key cannot resolve "
                "'the current user')"
            )

        # Step 1: resolve the uploads playlist id from the owner's channel.
        try:
            channel_response = (
                self._service()
                .channels()
                .list(part="contentDetails", mine=True)
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "youtube.list_owned_videos_via_uploads_channel_http_error status=%s",
                getattr(exc.resp, "status", "?"),
            )
            raise

        channel_items = channel_response.get("items") or []
        if not channel_items:
            raise ValueError(
                "channels.list?mine=True returned no items — the OAuth "
                "account has no associated YouTube channel."
            )
        uploads_playlist_id = _channel_from_api(channel_items[0]).uploads_playlist_id
        if not uploads_playlist_id:
            # Channel exists but exposes no uploads playlist — only the
            # 1-unit channels.list was spent.
            return ListResult(items=[], next_page_token=None, quota_units_consumed=1)

        # Step 2: page the uploads playlist for video ids (1 unit).
        try:
            playlist_response = (
                self._service()
                .playlistItems()
                .list(
                    part="contentDetails",
                    playlistId=uploads_playlist_id,
                    maxResults=page_size,
                    pageToken=page_token,
                )
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "youtube.list_owned_videos_via_uploads_playlist_http_error status=%s",
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
            # 1 (channels.list) + 1 (playlistItems.list); videos.list skipped.
            return ListResult(
                items=[], next_page_token=next_page_token, quota_units_consumed=2
            )

        # Step 3: hydrate the batch to the full projection (1 unit).
        try:
            videos_response = (
                self._service()
                .videos()
                .list(
                    part="snippet,statistics,status,contentDetails",
                    id=",".join(video_ids),
                )
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "youtube.list_owned_videos_via_uploads_videos_http_error status=%s",
                getattr(exc.resp, "status", "?"),
            )
            raise

        videos = [
            _video_full_from_api(item) for item in videos_response.get("items", [])
        ]
        return ListResult(
            items=videos,
            next_page_token=next_page_token,
            # 1 (channels.list) + 1 (playlistItems.list) + 1 (videos.list) = 3.
            quota_units_consumed=3,
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
        memory.

        **Per-chunk retry on transient failures.** Transient HTTP errors
        (5xx, 429) and transport-level network errors (ConnectionError,
        TimeoutError, SSLError) trigger a bounded retry of the SAME
        chunk (the resumable upload URI is preserved on the `request`
        object, so `next_chunk()` resumes from the last successful byte
        offset — no restart-from-zero).

        - Up to `CHUNK_RETRY_MAX_ATTEMPTS` (3) retries per chunk.
        - Retry budget **resets on every successful chunk** so a 50-
          chunk upload over a flaky network produces many short retries
          rather than exhausting a global budget at chunk 4.
        - Exponential backoff: 1s, 2s, 4s (capped at
          `CHUNK_RETRY_MAX_DELAY_S`).
        - `quotaExceeded` / `dailyLimitExceeded` (403 with the matching
          sub-error) is **NEVER retried** — propagates immediately as
          `HttpError` so the consumer's quota-handling layer can
          translate it to a "tomorrow / retry-in-6h" message."""
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
        request = (
            self._service()
            .videos()
            .insert(part="snippet,status", body=body, media_body=media)
        )

        response = self._drive_resumable_upload(
            request, log_label=f"upload_video title={clipped_title!r}"
        )

        video_id = response.get("id", "")
        return VideoUpload(
            video_id=video_id,
            title=clipped_title,
            url=f"https://www.youtube.com/watch?v={video_id}",
            privacy_status=privacy_status,
            quota_units_consumed=UPLOAD_QUOTA_UNITS,
        )

    async def set_thumbnail(
        self,
        *,
        video_id: str,
        thumbnail_path: str,
        mime_type: str = "image/jpeg",
    ) -> None:
        """**50 quota units** (`thumbnails.set`).

        Requires OAuth credentials — `thumbnails.set` is a write call;
        an API-key-only client cannot upload thumbnails. Raises
        `ValueError` at call time when no OAuth credentials were
        supplied (fail loud, per the no-silent-errors rule).

        The local file is streamed via a `MediaFileUpload` matching the
        `upload_video` shape so memory pressure stays bounded for the
        2MB ceiling YouTube enforces server-side."""
        if self._oauth_credentials is None:
            raise ValueError(
                "RealYoutubeClient.set_thumbnail requires oauth_credentials "
                "(thumbnails.set is a write; an API key cannot upload)"
            )

        media = MediaFileUpload(thumbnail_path, mimetype=mime_type, resumable=False)
        try:
            self._service().thumbnails().set(
                videoId=video_id, media_body=media
            ).execute()
        except HttpError as exc:
            logger.warning(
                "youtube.set_thumbnail_http_error video_id=%s status=%s",
                video_id,
                getattr(exc.resp, "status", "?"),
            )
            raise

    async def update_video(
        self,
        video_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        privacy_status: str | None = None,
    ) -> VideoFull:
        """Update mutable metadata via ``videos.update``.

        **Quota cost: ~50 units/update** — ``videos.update`` costs 50 units
        per call. Only the parts that actually change are included in the
        request (``snippet`` when ``title``/``description`` is non-None;
        ``status`` when ``privacy_status`` is non-None).

        **GOTCHA — ``snippet`` part requires ``title`` AND ``categoryId``:**
        YouTube rejects ``videos.update?part=snippet`` when ``snippet.title``
        or ``snippet.categoryId`` is missing. This adapter fetches the
        existing video full-projection first (1 unit), merges the caller's
        values on top, and then writes only what changed (≤49 more units for
        the update). Callers can pass only the fields they want to change.

        **Requires OAuth** — ``videos.update`` is a write. Raises
        ``ValueError`` at call time when no OAuth credentials were supplied.

        Returns the re-fetched :class:`VideoFull` after the write so the
        returned state is YouTube's authoritative record.

        Raises:
            ValueError: when no OAuth credentials supplied OR ``get_video_full``
                returns ``None`` (video deleted between fetch and update).
            HttpError: on YouTube API errors (quota, permission, etc.)."""
        if self._oauth_credentials is None:
            raise ValueError(
                "RealYoutubeClient.update_video requires oauth_credentials "
                "(videos.update is a write; an API key cannot update metadata)"
            )

        parts: list[str] = []
        body: dict[str, Any] = {"id": video_id}

        if title is not None or description is not None:
            # Fetch existing snippet to supply the required title + categoryId
            # fields when only description is changing (YouTube rejects the
            # update if either is absent).
            existing = await self.get_video_full(video_id)
            if existing is None:
                raise ValueError(
                    f"videos.list returned no items for video_id={video_id!r} — "
                    "may have been deleted or is not accessible."
                )
            body["snippet"] = {
                "title": (title if title is not None else existing.title)[:TITLE_MAX_LEN],
                "description": (description if description is not None else existing.description),
                "categoryId": existing.category_id or "22",
                "tags": list(existing.tags) if existing.tags else [],
            }
            parts.append("snippet")

        if privacy_status is not None:
            body["status"] = {"privacyStatus": privacy_status}
            parts.append("status")

        if not parts:
            # No-op: nothing to update — re-fetch and return current state.
            existing = await self.get_video_full(video_id)
            if existing is None:
                raise ValueError(
                    f"videos.list returned no items for video_id={video_id!r}"
                )
            return existing

        try:
            self._service().videos().update(
                part=",".join(parts),
                body=body,
            ).execute()
        except HttpError as exc:
            logger.warning(
                "youtube.update_video_http_error video_id=%s status=%s",
                video_id,
                getattr(exc.resp, "status", "?"),
            )
            raise

        # Re-fetch the updated state as the authoritative record.
        updated = await self.get_video_full(video_id)
        if updated is None:
            raise ValueError(
                f"videos.list returned no items for video_id={video_id!r} after update"
            )
        return updated

    async def get_processing_status(self, video_id: str) -> ProcessingStatus:
        """**1 quota unit** (`videos.list?part=status,processingDetails&id=<vid>`).

        Returns a :class:`ProcessingStatus` echoing the queried
        ``video_id``. Unknown / API-omitted field values are surfaced
        as the explicit ``"unknown"`` literal. Raises ``ValueError``
        when ``videos.list`` returns no items (deleted / never finished
        uploading) so the caller branches on a real exception, not a
        sentinel."""
        try:
            response = (
                self._service()
                .videos()
                .list(part="status,processingDetails", id=video_id)
                .execute()
            )
        except HttpError as exc:
            logger.warning(
                "youtube.get_processing_status_http_error video_id=%s status=%s",
                video_id,
                getattr(exc.resp, "status", "?"),
            )
            raise

        items = response.get("items") or []
        if not items:
            raise ValueError(
                f"videos.list returned no items for video_id={video_id!r} — "
                "may have been deleted or never finished uploading."
            )
        item = items[0]
        status_block = item.get("status", {}) or {}
        proc_block = item.get("processingDetails", {}) or {}
        return ProcessingStatus(
            video_id=video_id,
            upload_status=status_block.get("uploadStatus") or "unknown",
            processing_status=proc_block.get("processingStatus") or "unknown",
            privacy_status=status_block.get("privacyStatus") or "unknown",
        )

    def _drive_resumable_upload(
        self, request: Any, *, log_label: str
    ) -> dict[str, Any]:
        """Drive a googleapiclient resumable upload to completion with
        per-chunk retry on transient failures.

        Algorithm (lifted from product `_resumable_upload_with_chunk_retry`,
        Phase 4 fix-on-contact — see module docstring above):

        - Keep the same `request` object across retries so its
          `resumable_uri` (encoding the upload-session URI + byte offset
          on YT's side) stays valid and `next_chunk()` resumes from the
          last successful byte rather than restarting from zero.
        - Per-chunk retry budget (`CHUNK_RETRY_MAX_ATTEMPTS`) **resets on
          every successful chunk** so a long upload with multiple flaky
          moments doesn't exhaust the budget on the first hiccup.
        - `quotaExceeded` / `dailyLimitExceeded` (403) → NO retry,
          propagate immediately as `HttpError` (consumer's quota layer
          translates it to a user-facing message).
        - Other transient HTTP errors (5xx, 429) and transport-level
          errors (ConnectionError, TimeoutError, SSLError) → exponential
          backoff (1s, 2s, 4s) then re-attempt the same chunk.
        - Non-transient errors propagate immediately."""
        response: dict[str, Any] | None = None
        attempts_this_chunk = 0
        while response is None:
            try:
                _status, response = request.next_chunk()
                attempts_this_chunk = 0  # reset on chunk success
            except HttpError as exc:
                if _is_quota_exceeded(exc):
                    logger.warning(
                        "youtube.%s.quota_exceeded status=%s",
                        log_label,
                        getattr(exc.resp, "status", "?"),
                    )
                    raise
                if not _is_transient_http_error(exc):
                    logger.warning(
                        "youtube.%s.non_transient_http_error status=%s",
                        log_label,
                        getattr(exc.resp, "status", "?"),
                    )
                    raise
                attempts_this_chunk += 1
                if attempts_this_chunk > CHUNK_RETRY_MAX_ATTEMPTS:
                    logger.warning(
                        "youtube.%s.chunk_retries_exhausted attempts=%d",
                        log_label,
                        CHUNK_RETRY_MAX_ATTEMPTS,
                    )
                    raise
                delay = min(
                    CHUNK_RETRY_BASE_DELAY_S * (2 ** (attempts_this_chunk - 1)),
                    CHUNK_RETRY_MAX_DELAY_S,
                )
                logger.warning(
                    "youtube.%s.transient_http_retry attempt=%d/%d delay=%.1fs status=%s",
                    log_label,
                    attempts_this_chunk,
                    CHUNK_RETRY_MAX_ATTEMPTS,
                    delay,
                    getattr(exc.resp, "status", "?"),
                )
                time.sleep(delay)
            except Exception as exc:
                if not _is_transient_network_error(exc):
                    raise
                attempts_this_chunk += 1
                if attempts_this_chunk > CHUNK_RETRY_MAX_ATTEMPTS:
                    logger.warning(
                        "youtube.%s.chunk_network_retries_exhausted attempts=%d",
                        log_label,
                        CHUNK_RETRY_MAX_ATTEMPTS,
                    )
                    raise
                delay = min(
                    CHUNK_RETRY_BASE_DELAY_S * (2 ** (attempts_this_chunk - 1)),
                    CHUNK_RETRY_MAX_DELAY_S,
                )
                logger.warning(
                    "youtube.%s.transient_network_retry attempt=%d/%d delay=%.1fs err=%s",
                    log_label,
                    attempts_this_chunk,
                    CHUNK_RETRY_MAX_ATTEMPTS,
                    delay,
                    exc,
                )
                time.sleep(delay)
        return response


__all__ = ["RealYoutubeClient"]
