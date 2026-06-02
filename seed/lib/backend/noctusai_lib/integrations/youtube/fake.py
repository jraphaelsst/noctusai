"""In-memory deterministic FakeYoutubeClient for dev + tests.

Mirrors the YouTube Data API v3 quota math so tests can assert exact
unit counts without running through googleapiclient. Page size is
deliberately small (`PAGE_SIZE = 2`) so paging logic exercises in 3-4
videos rather than 50.

Seed-data shape:

```python
FakeYoutubeClient(
    channels={
        "UC123": Channel(
            id="UC123",
            title="Demo",
            description="...",
            uploads_playlist_id="UU123",
        ),
    },
    videos={
        "vid1": Video(id="vid1", channel_id="UC123", ...),
        "vid2": Video(id="vid2", channel_id="UC123", ...),
    },
    playlists={
        "UU123": Playlist(id="UU123", title="Uploads from Demo"),
    },
)
```

Cumulative `quota_units_consumed` is exposed as a public attribute; tests
assert against it after a sequence of calls.
"""

from __future__ import annotations

from noctusai_lib.integrations.youtube.types import (
    TITLE_MAX_LEN,
    UPLOAD_QUOTA_UNITS,
    Channel,
    ChannelInfo,
    ListResult,
    Playlist,
    PrivacyStatus,
    ProcessingStatus,
    Video,
    VideoFull,
    VideoUpload,
)


class FakeYoutubeClient:
    """Deterministic in-memory `YoutubeClient` implementation.

    Deterministically pages a channel's videos in insertion order
    (insertion order = newest-first by convention; tests should add
    videos in the order they expect to see them paginated)."""

    PAGE_SIZE: int = 2

    def __init__(
        self,
        channels: dict[str, Channel] | None = None,
        videos: dict[str, Video] | None = None,
        playlists: dict[str, Playlist] | None = None,
        owned_channel_info: ChannelInfo | None = None,
        owned_videos: list[VideoFull] | None = None,
    ) -> None:
        self.channels: dict[str, Channel] = dict(channels or {})
        self.videos: dict[str, Video] = dict(videos or {})
        self.playlists: dict[str, Playlist] = dict(playlists or {})
        self.quota_units_consumed: int = 0
        self.uploaded: list[VideoUpload] = []
        """Every `upload_video` call appends here, in order — tests
        assert against it without going near googleapiclient."""
        self._upload_seq: int = 0
        self.thumbnails_set: list[dict[str, str]] = []
        """Every `set_thumbnail` call appends a ``{video_id, thumbnail_path,
        mime_type}`` dict here, in order — tests assert against it
        without going near googleapiclient."""
        self.processing_states: dict[str, ProcessingStatus] = {}
        """Seed per-video processing state. When ``video_id`` is absent,
        :meth:`get_processing_status` returns the default
        "uploaded + processing + private" state (matches the YouTube
        behavior immediately after `videos.insert`). Tests pre-populate
        this dict to assert terminal states."""
        self.owned_channel_info: ChannelInfo | None = owned_channel_info
        """Seeded OAuth-authenticated channel metadata for
        :meth:`get_channel_info_mine`. ``None`` mimics the
        "OAuth account has no associated YT channel" branch — the
        method raises :class:`ValueError` to match the Real adapter."""
        self.owned_videos: list[VideoFull] = list(owned_videos or [])
        """Seeded OAuth-owned video corpus for
        :meth:`list_owned_videos`. Paged in insertion order — first
        :attr:`PAGE_SIZE` items are page 1. Tests append in the order
        they expect to see in pagination."""

    # ---- Quota helper ----------------------------------------------------

    def _charge(self, units: int) -> int:
        self.quota_units_consumed += units
        return units

    # ---- Internal paging -------------------------------------------------

    def _page(
        self,
        items: list,
        page_token: str | None,
        page_size: int | None = None,
    ) -> tuple[list, str | None]:
        """Slice `items` into a page of size `page_size` (default
        :attr:`PAGE_SIZE`). `page_token` is the integer offset (as a
        string), `None` for the first page. Returns
        `(page_items, next_page_token)` — `next_page_token` is `None`
        on the last page.

        `page_size` is honoured per-call to support
        :meth:`list_owned_videos` exposing the YT-API `maxResults`
        knob; existing callers omit it and inherit `PAGE_SIZE`."""
        size = page_size if page_size is not None else self.PAGE_SIZE
        offset = int(page_token) if page_token else 0
        end = offset + size
        page_items = items[offset:end]
        next_token = str(end) if end < len(items) else None
        return page_items, next_token

    # ---- YoutubeClient surface ------------------------------------------

    async def get_channel(self, channel_id: str) -> Channel | None:
        """1 quota unit (mirrors `channels.list`)."""
        self._charge(1)
        return self.channels.get(channel_id)

    async def list_channel_videos(
        self,
        channel_id: str,
        page_token: str | None = None,
    ) -> ListResult[Video]:
        """2 quota units (1 for `playlistItems.list` + 1 for `videos.list`).

        The fake's `_charge(2)` happens unconditionally — even when the
        channel doesn't exist — to faithfully mirror the API's
        "you-pay-on-call" semantics (an unknown id still costs 1+1)."""
        cost = self._charge(2)
        channel = self.channels.get(channel_id)
        if channel is None:
            return ListResult(items=[], next_page_token=None, quota_units_consumed=cost)

        # Order videos by their insertion order in self.videos. Filter
        # by channel_id so the same fake can host multi-channel data.
        channel_videos = [v for v in self.videos.values() if v.channel_id == channel_id]
        page_items, next_token = self._page(channel_videos, page_token)

        return ListResult(
            items=page_items,
            next_page_token=next_token,
            quota_units_consumed=cost,
        )

    async def get_video(self, video_id: str) -> Video | None:
        """1 quota unit (mirrors `videos.list`)."""
        self._charge(1)
        return self.videos.get(video_id)

    async def search(
        self,
        query: str,
        page_token: str | None = None,
    ) -> ListResult[Video]:
        """100 quota units (mirrors `search.list`).

        Match is a naive case-insensitive substring on title/description
        — enough for tests; not a stand-in for real-world relevance."""
        cost = self._charge(100)
        q = query.lower()
        matched = [
            v
            for v in self.videos.values()
            if q in v.title.lower() or q in v.description.lower()
        ]
        page_items, next_token = self._page(matched, page_token)
        return ListResult(
            items=page_items,
            next_page_token=next_token,
            quota_units_consumed=cost,
        )

    async def get_video_full(self, video_id: str) -> VideoFull | None:
        """1 quota unit (mirrors `videos.list?part=snippet,statistics,
        status,contentDetails`). Resolves against :attr:`owned_videos`
        by id (the rich projection lives there, not on the lean
        :attr:`videos` dict). Returns ``None`` when not present."""
        self._charge(1)
        for v in self.owned_videos:
            if v.id == video_id:
                return v
        return None

    async def get_channel_info_mine(self) -> ChannelInfo:
        """1 quota unit (mirrors `channels.list?mine=True`).

        Returns the seeded :attr:`owned_channel_info`. Raises
        :class:`ValueError` when none was seeded — mirrors the Real
        adapter's "OAuth account has no associated YT channel"
        branch."""
        self._charge(1)
        if self.owned_channel_info is None:
            raise ValueError(
                "channels.list?mine=True returned no items — the OAuth "
                "account has no associated YouTube channel."
            )
        return self.owned_channel_info

    async def list_owned_videos(
        self,
        *,
        page_token: str | None = None,
        page_size: int = 50,
    ) -> ListResult[VideoFull]:
        """101 quota units / page (mirrors `search.list?forMine` (100)
        + `videos.list` (1)). When the page has no ids, only 100 is
        charged (the `videos.list` step is skipped — matches the Real
        adapter).

        Pages :attr:`owned_videos` in insertion order. ``page_size`` is
        honoured per-call (the test fixture can use a small value to
        exercise pagination without seeding 50 entries)."""
        page_items, next_token = self._page(
            self.owned_videos, page_token, page_size=page_size
        )
        if not page_items:
            cost = self._charge(100)
            return ListResult(
                items=[], next_page_token=next_token, quota_units_consumed=cost
            )
        cost = self._charge(101)
        return ListResult(
            items=list(page_items),
            next_page_token=next_token,
            quota_units_consumed=cost,
        )

    async def list_owned_videos_via_uploads(
        self,
        *,
        page_token: str | None = None,
        page_size: int = 50,
    ) -> ListResult[VideoFull]:
        """~2-3 quota units / page (the cheap uploads-playlist path):
        1 `channels.list?mine` + 1 `playlistItems.list` + 1 `videos.list`
        when the page has ids; 2 when the page is empty (`videos.list`
        skipped). Mirrors :meth:`list_owned_videos` paging over
        :attr:`owned_videos` (which, unlike the real `search.list` path,
        faithfully includes private + unlisted entries).

        Raises :class:`ValueError` when no :attr:`owned_channel_info`
        was seeded — mirrors the Real adapter's
        `channels.list?mine=True returned no items` branch."""
        if self.owned_channel_info is None:
            self._charge(1)
            raise ValueError(
                "channels.list?mine=True returned no items — the OAuth "
                "account has no associated YouTube channel."
            )
        page_items, next_token = self._page(
            self.owned_videos, page_token, page_size=page_size
        )
        if not page_items:
            cost = self._charge(2)
            return ListResult(
                items=[], next_page_token=next_token, quota_units_consumed=cost
            )
        cost = self._charge(3)
        return ListResult(
            items=list(page_items),
            next_page_token=next_token,
            quota_units_consumed=cost,
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
        """1600 quota units (mirrors `videos.insert`).

        Deterministic: video ids are `fake-upload-1`, `fake-upload-2`,
        … in call order. Title is clipped to `TITLE_MAX_LEN` exactly
        like the Real adapter so tests catch over-long titles without
        a network round-trip. The result is also appended to
        `self.uploaded` for post-hoc assertions. `file_path` is not
        read — the fake never touches the filesystem."""
        self._charge(UPLOAD_QUOTA_UNITS)
        self._upload_seq += 1
        video_id = f"fake-upload-{self._upload_seq}"
        result = VideoUpload(
            video_id=video_id,
            title=title[:TITLE_MAX_LEN],
            url=f"https://www.youtube.com/watch?v={video_id}",
            privacy_status=privacy_status,
            quota_units_consumed=UPLOAD_QUOTA_UNITS,
        )
        self.uploaded.append(result)
        # Seed a default "uploaded + processing" state so a follow-up
        # get_processing_status sees the newly-uploaded video by id
        # without the caller having to pre-populate processing_states.
        self.processing_states.setdefault(
            video_id,
            ProcessingStatus(
                video_id=video_id,
                upload_status="uploaded",
                processing_status="processing",
                privacy_status=privacy_status,
            ),
        )
        return result

    async def set_thumbnail(
        self,
        *,
        video_id: str,
        thumbnail_path: str,
        mime_type: str = "image/jpeg",
    ) -> None:
        """50 quota units (mirrors `thumbnails.set`).

        The fake never touches the filesystem — `thumbnail_path` is
        recorded verbatim on `self.thumbnails_set` for post-hoc
        assertions, alongside `video_id` + `mime_type`."""
        self._charge(50)
        self.thumbnails_set.append(
            {
                "video_id": video_id,
                "thumbnail_path": thumbnail_path,
                "mime_type": mime_type,
            }
        )

    async def update_video(
        self,
        video_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        privacy_status: str | None = None,
    ) -> VideoFull:
        """~50 quota units (mirrors ``videos.update``).

        Merges the provided fields onto the matching entry in
        :attr:`owned_videos` (the ``VideoFull`` corpus). If the video is not
        found in ``owned_videos``, raises ``ValueError`` mirroring the Real
        adapter's "video deleted" branch.

        The merge behavior mirrors the Real adapter's GOTCHA handling: when
        only ``description`` is provided, the existing ``title`` and
        ``category_id`` are preserved (no field-erasure). Only the
        non-``None`` arguments replace the existing values.

        Returns a new :class:`VideoFull` with the merged fields. The
        :attr:`owned_videos` list is updated in-place so subsequent calls
        see the new state."""
        self._charge(50)
        for i, v in enumerate(self.owned_videos):
            if v.id == video_id:
                merged = VideoFull(
                    id=v.id,
                    title=(title[:TITLE_MAX_LEN] if title is not None else v.title),
                    description=(description if description is not None else v.description),
                    channel_id=v.channel_id,
                    published_at=v.published_at,
                    duration_seconds=v.duration_seconds,
                    duration_iso=v.duration_iso,
                    thumbnail_url=v.thumbnail_url,
                    privacy_status=(privacy_status if privacy_status is not None else v.privacy_status),
                    view_count=v.view_count,
                    like_count=v.like_count,
                    comment_count=v.comment_count,
                    tags=v.tags,
                    category_id=v.category_id,
                )
                self.owned_videos[i] = merged
                return merged
        raise ValueError(
            f"videos.list returned no items for video_id={video_id!r} — "
            "video not found in FakeYoutubeClient.owned_videos."
        )

    async def get_processing_status(self, video_id: str) -> ProcessingStatus:
        """1 quota unit (mirrors `videos.list?part=status,processingDetails`).

        Returns a pre-populated state from `self.processing_states`
        when one was seeded for ``video_id``; otherwise returns a
        sensible "freshly uploaded" default
        (``upload_status="uploaded"``, ``processing_status="processing"``,
        ``privacy_status="private"``). Raises ``ValueError`` when the
        video id is the explicit sentinel ``"<missing>"`` — used by
        tests asserting the missing-video branch."""
        self._charge(1)
        if video_id == "<missing>":
            raise ValueError(
                f"videos.list returned no items for video_id={video_id!r}"
            )
        state = self.processing_states.get(video_id)
        if state is not None:
            return state
        return ProcessingStatus(
            video_id=video_id,
            upload_status="uploaded",
            processing_status="processing",
            privacy_status="private",
        )


__all__ = ["FakeYoutubeClient"]
