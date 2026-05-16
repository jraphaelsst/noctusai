"""YouTube Data API v3 client — canonical Protocol+Fake+Real+factory.

Lifted 2026-05-04 by `projects/seed-hardening-from-youtube-crawler/` Phase 1.3
to encode correct quota math at the seed level so `youtube-crawler` (and
any future YouTube-touching product) inherits the cheap
channel→uploads-playlist→playlistItems strategy without re-derivation.

**What ships:**
- `Channel`, `Video`, `Playlist`, `ListResult[T]` value objects.
- `YoutubeClient` Protocol with quota-cost-documented async methods:
  - `get_channel(channel_id)` — 1 unit (`channels.list`).
  - `list_channel_videos(channel_id, page_token=None)` — ~2 units / 50 videos
    (`playlistItems.list` + `videos.list` over the channel's auto uploads playlist).
  - `get_video(video_id)` — 1 unit (`videos.list`).
  - `search(query, page_token=None)` — **100 units / page** (`search.list`).
  - `upload_video(file_path=, title=, description="", tags=None,
    privacy_status="private", category_id="22")` — **1600 units**
    (`videos.insert`, resumable). OAuth-only; returns `VideoUpload`.
- `FakeYoutubeClient` — deterministic in-memory; tracks cumulative
  `quota_units_consumed`; `PAGE_SIZE = 2` for testable paging;
  records uploads on `.uploaded`.
- `RealYoutubeClient(api_key=, oauth_credentials=)` — wraps
  `googleapiclient.discovery.build("youtube", "v3", ...)`. Logs HTTP
  errors at WARN+ before re-raising; never swallows silently.
- `make_youtube_client(use_fake=False, api_key=, oauth_credentials=,
  fake_seed_data=None)` — factory.

**Quota math is the whole point of lifting this.** The default
`search.list` strategy burns 100 units / page (1% of daily quota).
The `list_channel_videos` strategy is ~50× cheaper. The Protocol
docstrings document this; consumers reading the surface pick the
cheap path by default.
"""

from noctusai_lib.integrations.youtube.factory import make_youtube_client
from noctusai_lib.integrations.youtube.fake import FakeYoutubeClient
from noctusai_lib.integrations.youtube.protocol import YoutubeClient
from noctusai_lib.integrations.youtube.real import RealYoutubeClient
from noctusai_lib.integrations.youtube.types import (
    DESCRIPTION_MAX_LEN,
    TITLE_MAX_LEN,
    UPLOAD_QUOTA_UNITS,
    Channel,
    ListResult,
    Playlist,
    PrivacyStatus,
    Video,
    VideoUpload,
)

__all__ = [
    "DESCRIPTION_MAX_LEN",
    "TITLE_MAX_LEN",
    "UPLOAD_QUOTA_UNITS",
    "Channel",
    "FakeYoutubeClient",
    "ListResult",
    "Playlist",
    "PrivacyStatus",
    "RealYoutubeClient",
    "Video",
    "VideoUpload",
    "YoutubeClient",
    "make_youtube_client",
]
