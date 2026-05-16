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
    ListResult,
    Playlist,
    PrivacyStatus,
    Video,
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
    ) -> None:
        self.channels: dict[str, Channel] = dict(channels or {})
        self.videos: dict[str, Video] = dict(videos or {})
        self.playlists: dict[str, Playlist] = dict(playlists or {})
        self.quota_units_consumed: int = 0
        self.uploaded: list[VideoUpload] = []
        """Every `upload_video` call appends here, in order — tests
        assert against it without going near googleapiclient."""
        self._upload_seq: int = 0

    # ---- Quota helper ----------------------------------------------------

    def _charge(self, units: int) -> int:
        self.quota_units_consumed += units
        return units

    # ---- Internal paging -------------------------------------------------

    def _page(
        self,
        items: list[Video],
        page_token: str | None,
    ) -> tuple[list[Video], str | None]:
        """Slice `items` into a page of size `PAGE_SIZE`. `page_token`
        is the integer offset (as a string), `None` for the first page.
        Returns `(page_items, next_page_token)` — `next_page_token`
        is `None` on the last page."""
        offset = int(page_token) if page_token else 0
        end = offset + self.PAGE_SIZE
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
        return result


__all__ = ["FakeYoutubeClient"]
