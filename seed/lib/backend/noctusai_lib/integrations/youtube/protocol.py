"""YouTube Data API v3 client Protocol.

The seed encodes correct quota math at the contract level so consumers
never re-derive it. YouTube's daily quota defaults to 10,000 units;
the wrong listing strategy (`search.list` at 100 units/page) burns the
budget in 100 calls. The right strategy
(`channels.list` → uploads-playlist → `playlistItems.list` →
`videos.list`) costs ~2 units per page of 50 videos.

The Protocol's docstrings document the per-method quota cost so any
consumer reading the surface picks the cheap path by default.
"""

from __future__ import annotations

from typing import Protocol

from noctusai_lib.integrations.youtube.types import (
    Channel,
    ChannelInfo,
    ListResult,
    PrivacyStatus,
    ProcessingStatus,
    Video,
    VideoFull,
    VideoUpload,
)


class YoutubeClient(Protocol):
    """YouTube Data API v3 client contract.

    Two concrete implementations ship in the seed:
    - `FakeYoutubeClient` — deterministic in-memory dev/test default.
      Tracks cumulative `quota_units_consumed` for assertions.
    - `RealYoutubeClient` — wraps `googleapiclient.discovery.build`.
      Logs API errors at WARN level before re-raising.

    Build via `make_youtube_client(...)`. The factory routes based on
    `use_fake` flag — see `factory.py`.

    **Quota math (YouTube daily default = 10,000 units):**

    | Method | Cost | Notes |
    |---|---|---|
    | `get_channel` | 1 | `channels.list` is 1 unit per call. |
    | `list_channel_videos` | ~2 / page of 50 | Two API calls: `playlistItems.list` (1 unit) returns up to 50 video IDs, then `videos.list` (1 unit) fetches details for the batch. The cheap path. |
    | `get_video` | 1 | `videos.list` with one ID is 1 unit. |
    | `search` | **100** | `search.list` is 100 units per page (1% of daily quota per call). PREFER `list_channel_videos` for channel-scoped listings. |
    | `upload_video` | **1600** | `videos.insert` (resumable) — the single most expensive call in the API; ≈6 uploads exhaust a fresh 10,000/day quota. Requires OAuth (an API key cannot write). |
    | `set_thumbnail` | **50** | `thumbnails.set` (resumable). Custom-thumbnail permission required (most channels have it; brand-new channels need verification). Requires OAuth (write). |
    | `get_processing_status` | 1 | `videos.list?part=status,processingDetails&id=<vid>` — same cost as `get_video`; the `part` selection doesn't change the cost. |

    The `ListResult.quota_units_consumed` field carries the per-call
    cost so consumers can budget against the daily quota."""

    async def get_channel(self, channel_id: str) -> Channel | None:
        """Fetch a channel by id.

        **Quota cost: 1 unit** (`channels.list?part=snippet,contentDetails`).

        Returns `None` when the channel doesn't exist."""
        ...

    async def list_channel_videos(
        self,
        channel_id: str,
        page_token: str | None = None,
    ) -> ListResult[Video]:
        """List a channel's uploaded videos, newest first.

        **Quota cost: ~2 units per page of 50 videos.** Implementation:
        1. Fetch the channel's `uploads_playlist_id` (cached after first call
           OR resolved per-call by `channels.list` — 1 unit).
        2. `playlistItems.list?playlistId=<uploads>` returns 50 video IDs (1 unit).
        3. `videos.list?id=<id1,id2,...,id50>` fetches details for the batch (1 unit).

        This is the cheap path. NEVER use `search.list?channelId=...` for the
        same purpose — `search.list` costs 100 units per page (50× more)."""
        ...

    async def get_video(self, video_id: str) -> Video | None:
        """Fetch a single video by id.

        **Quota cost: 1 unit** (`videos.list?id=<video_id>`).

        Returns `None` when the video doesn't exist or has been removed."""
        ...

    async def search(
        self,
        query: str,
        page_token: str | None = None,
    ) -> ListResult[Video]:
        """Free-text video search.

        **Quota cost: 100 units per page** (`search.list` is the most
        expensive endpoint in the API). Calling this 100×/day burns the
        full default quota — measure carefully before exposing it
        in any user-facing surface.

        For channel-scoped listings (newest videos from one channel),
        use `list_channel_videos(channel_id)` instead — same data, ~50×
        cheaper."""
        ...

    async def get_channel_info_mine(self) -> ChannelInfo:
        """Fetch the OAuth-authenticated channel's metadata + engagement
        counters.

        **Quota cost: 1 unit** (`channels.list?mine=True&part=snippet,
        statistics`). The OAuth-authenticated variant of
        :meth:`get_channel` — the `mine=True` flag tells YT to resolve
        the channel from the credentials instead of from a `channel_id`,
        so this method only makes sense on an OAuth-backed client.

        Distinct from :meth:`get_channel` because (a) it doesn't take an
        id (resolves via OAuth context), (b) the response includes
        `statistics` (subscriber / video / view counts) rather than
        `contentDetails` (uploads playlist id), and (c) the return type
        is :class:`ChannelInfo` (engagement-counters projection) rather
        than :class:`Channel` (uploads-playlist projection).

        Raises:
            ValueError: when `channels.list?mine=True` returns no items
                (the OAuth account has no associated YT channel —
                the operator surface should redirect the user back to
                consent with a different Google account). Surfaced as
                an explicit exception rather than a sentinel so the
                caller branches on a real signal."""
        ...

    async def get_video_full(self, video_id: str) -> VideoFull | None:
        """Fetch a single video with the rich projection.

        **Quota cost: 1 unit** (`videos.list?part=snippet,statistics,
        status,contentDetails&id=<video_id>`). Same cost as
        :meth:`get_video` because YouTube charges per call regardless
        of which `part=` pieces are requested.

        Distinct from :meth:`get_video` only in the return type — use
        this when the wider field set (`thumbnail_url`, `tags`,
        `like_count`, `comment_count`, `privacy_status`, etc.) is
        needed. When only id/title/view_count/duration matter, prefer
        :meth:`get_video` — the lean projection makes consumer code
        loud about which fields it depends on.

        Returns `None` when the video doesn't exist or has been
        removed (mirrors :meth:`get_video`)."""
        ...

    async def list_owned_videos(
        self,
        *,
        page_token: str | None = None,
        page_size: int = 50,
    ) -> ListResult[VideoFull]:
        """List the OAuth-authenticated channel's videos with the full
        projection via the **expensive `search.list?forMine=True`** path.

        ⚠️ **PREFER :meth:`list_owned_videos_via_uploads`.** This method
        is retained for back-compat, but `search.list?forMine=True` is
        both **50× more expensive** (101 units/page vs ~2-3) AND
        **unreliable for private/unlisted uploads** — `search.list` is
        index-backed and lags / omits non-public videos, so a channel
        whose uploads are all private can return ZERO results here even
        though the videos exist (observed in production, 2026-06).

        **Quota cost: 101 units / page** — `search.list?forMine=True`
        (100 units) + `videos.list?part=snippet,statistics,status,
        contentDetails&id=...` (1 unit) for the page batch.

        Args:
            page_token: opaque YT pagination token; `None` for the
                first page.
            page_size: `maxResults` (1-50). YT caps at 50; the seed
                forwards the value verbatim.

        Returns:
            `ListResult[VideoFull]` — `quota_units_consumed` is 101 for
            the standard 2-call path; 100 when the search page returns
            no ids and `videos.list` is skipped."""
        ...

    async def list_owned_videos_via_uploads(
        self,
        *,
        page_token: str | None = None,
        page_size: int = 50,
    ) -> ListResult[VideoFull]:
        """List EVERY upload of the OAuth-authenticated channel —
        **including private + unlisted** — via the cheap, reliable
        uploads-playlist path. This is the canonical "see all my videos"
        method; prefer it over :meth:`list_owned_videos`.

        **Quota cost: ~3 units / page of 50** (1 `channels.list?mine=
        True&part=contentDetails` to resolve the uploads playlist + 1
        `playlistItems.list` for the page of ids + 1 `videos.list` for
        the batch hydration). Drops to 2 when the page has no ids
        (`videos.list` skipped).

        **Why this returns private/unlisted (the corrected contract):**
        a channel's auto-managed `uploads` playlist (`relatedPlaylists.
        uploads`, id `UU…`) contains **all** of the owner's uploads in
        reverse-chronological order. When `playlistItems.list` is called
        with the **owner's OAuth credentials**, it returns the owner's
        private + unlisted items too — the "uploads playlist is
        public-only" belief is true only for an API-key / third-party
        context, NOT for the authenticated owner. The expensive
        `search.list?forMine=True` path was historically used under that
        mistaken belief; this method is the cheap, complete replacement.

        OAuth-only: `channels.list?mine=True` needs an authenticated
        context. The Real adapter raises `ValueError` when no OAuth
        credentials were supplied (fail loud, per no-silent-errors).

        Args:
            page_token: opaque YT pagination token (the
                `playlistItems.list` token); `None` for the first page.
            page_size: `maxResults` (1-50). YT caps at 50.

        Returns:
            `ListResult[VideoFull]` — `next_page_token` is `None` on the
            last page. `quota_units_consumed` reflects the ~2-3 unit
            per-call cost. To classify each item as a Short, pass it to
            `noctusai_lib.integrations.youtube.classify_short`."""
        ...

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
        """Upload a local video file to YouTube (resumable `videos.insert`).

        **Quota cost: 1600 units** — the most expensive call in the
        API. Budget against the daily 10,000-unit quota via the
        returned `VideoUpload.quota_units_consumed`.

        **Requires OAuth** — `videos.insert` is a write; an API-key-only
        client cannot upload. The Real adapter raises `ValueError` at
        call time if no OAuth credentials were supplied.

        Args:
            file_path: Absolute path to the local video file. The Real
                adapter streams it via a resumable `MediaFileUpload`
                (no full in-memory buffering).
            title: `snippet.title`. **Truncated to
                `TITLE_MAX_LEN` (100) chars** by the adapter — YouTube
                rejects longer titles outright.
            description: `snippet.description` (≤5000 chars; default "").
            tags: `snippet.tags`. `None` → no tags.
            privacy_status: `status.privacyStatus` —
                `"private"` (default; nothing goes public implicitly) /
                `"unlisted"` / `"public"`.
            category_id: `snippet.categoryId`. Default `"22"`
                (People & Blogs) — a safe always-available category.

        Returns a `VideoUpload` with the new `video_id`, canonical
        watch `url`, and `quota_units_consumed=1600`."""
        ...

    async def set_thumbnail(
        self,
        *,
        video_id: str,
        thumbnail_path: str,
        mime_type: str = "image/jpeg",
    ) -> None:
        """Upload a custom thumbnail for ``video_id`` via
        ``thumbnails.set``.

        **Quota cost: 50 units.** Custom-thumbnail permission is
        required on the channel (most channels carry it; brand-new
        channels require Google verification first). Image format must
        be JPEG/PNG/BMP; YouTube enforces a 2MB ceiling server-side.

        **Requires OAuth** — ``thumbnails.set`` is a write; an
        API-key-only client cannot upload thumbnails. The Real adapter
        raises ``ValueError`` at call time if no OAuth credentials were
        supplied (fail loud, per the no-silent-errors rule).

        Args:
            video_id: YouTube video id whose thumbnail is being set.
            thumbnail_path: Absolute path to the local thumbnail image
                file. The Real adapter streams it via
                ``MediaFileUpload`` (matches the upload_video shape).
            mime_type: Image MIME type. Default ``"image/jpeg"``;
                ``"image/png"`` / ``"image/bmp"`` also accepted by
                YouTube. The adapter passes it through to the
                ``MediaFileUpload`` mimetype kwarg so YT routes the
                upload correctly.

        Returns ``None``; success is the absence of an exception.
        ``HttpError`` is logged at WARN+ and re-raised."""
        ...

    async def get_processing_status(self, video_id: str) -> ProcessingStatus:
        """Probe YouTube's processing-pipeline state for ``video_id``.

        **Quota cost: 1 unit** (``videos.list?part=status,processingDetails``).

        Used by upload pipelines that need to wait until a freshly
        inserted video is actually playable before surfacing the URL
        to the operator. ``videos.insert`` returns once YT has received
        the bytes, but transcoding then runs asynchronously — the
        video is not shareable until ``upload_status == "processed"``
        AND ``processing_status == "succeeded"``.

        Returns:
            A :class:`ProcessingStatus` with ``video_id`` echoed back +
            the three pipeline-state fields. Unknown / API-omitted
            values are surfaced as the explicit ``"unknown"`` literal
            so consumers branch on the value rather than truthy-check
            (no silent-errors).

        Raises:
            ValueError: when ``videos.list`` returns no items
                (deleted / never finished uploading); the seed surfaces
                this explicitly rather than returning a sentinel."""
        ...

    async def update_video(
        self,
        video_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        privacy_status: str | None = None,
    ) -> VideoFull:
        """Update mutable metadata for an existing YouTube video.

        **Quota cost: ~50 units/update** — ``videos.update`` costs 50 units
        per call regardless of which ``part=`` slices are written. Only the
        parts that actually change are sent (``snippet`` when ``title`` or
        ``description`` is non-None; ``status`` when ``privacy_status`` is
        non-None) so a privacy-only update avoids a ``snippet`` write and vice
        versa.

        **GOTCHA — ``snippet`` part requires ``title`` AND ``categoryId``:**
        YouTube's ``videos.update?part=snippet`` rejects the call if
        ``snippet.title`` or ``snippet.categoryId`` is absent, even when only
        the description is being changed. The Real adapter fetches the existing
        video's snippet first (``get_video_full``) and merges the caller's
        values on top so the required fields are always present. Callers do NOT
        need to pass the current title just to change the description.

        **Requires OAuth** — ``videos.update`` is a write; an API-key-only
        client cannot update metadata. The Real adapter raises ``ValueError``
        at call time if no OAuth credentials were supplied.

        Args:
            video_id: YouTube video id to update.
            title: New ``snippet.title``. ``None`` = keep existing.
            description: New ``snippet.description``. ``None`` = keep existing.
            privacy_status: New ``status.privacyStatus`` (``"public"`` /
                ``"unlisted"`` / ``"private"``). ``None`` = keep existing.

        Returns:
            The updated video as a :class:`VideoFull` (re-fetched after the
            write so the returned state matches YouTube's authoritative
            record, not the caller's input).

        Raises:
            ValueError: when no OAuth credentials were supplied, or when
                ``videos.list`` returns no items for ``video_id`` (the video
                was deleted between the fetch and the update — treat as a
                404 at the call site).
            HttpError: on YouTube API errors (quota, permission, etc.)."""
        ...


__all__ = ["YoutubeClient"]
