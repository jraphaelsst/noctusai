"""YouTube Data API v3 client tests — Fake + Real (mocked transport).

Covers:
- **Contract** — round-trips on Fake; same shape on Real-with-mocked-transport.
- **Quota math** — Fake tracks cumulative units that match documented costs.
- **Real client transport** — `googleapiclient.discovery.build` patched at the
  boundary (external-service carve-out per the no-monkeypatching rule);
  asserts the right API methods + parameters get called.
- **Factory** — routes Fake / Real correctly.

Network-free: no real googleapiclient calls; the Real adapter's transport
is mocked at the boundary.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from noctusai_lib.integrations.youtube import (
    Channel,
    FakeYoutubeClient,
    ListResult,
    Playlist,
    ProcessingStatus,
    RealYoutubeClient,
    Video,
    YoutubeClient,
    make_youtube_client,
)
from noctusai_lib.integrations.youtube.real import (
    _parse_iso8601_duration,
    _parse_published_at,
)


# ============================================================================
# Fixtures
# ============================================================================


def _channel(
    channel_id: str = "UC123",
    uploads_playlist_id: str = "UU123",
) -> Channel:
    return Channel(
        id=channel_id,
        title="Demo channel",
        description="Demo description",
        uploads_playlist_id=uploads_playlist_id,
    )


def _video(video_id: str, channel_id: str = "UC123", **overrides: Any) -> Video:
    return Video(
        id=video_id,
        title=overrides.get("title", f"Video {video_id}"),
        description=overrides.get("description", "Some description"),
        channel_id=channel_id,
        published_at=overrides.get(
            "published_at", datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)
        ),
        duration_seconds=overrides.get("duration_seconds", 330),
        view_count=overrides.get("view_count", 1000),
    )


def _seeded_fake() -> FakeYoutubeClient:
    """50 videos in one channel for quota-math assertions
    (one full page of `playlistItems.list` per the API)."""
    channel = _channel()
    videos = {f"vid{i:02d}": _video(f"vid{i:02d}") for i in range(50)}
    playlists = {channel.uploads_playlist_id: Playlist(
        id=channel.uploads_playlist_id, title="Uploads from Demo channel"
    )}
    return FakeYoutubeClient(
        channels={channel.id: channel},
        videos=videos,
        playlists=playlists,
    )


# ============================================================================
# Contract tests — Fake
# ============================================================================


@pytest.mark.asyncio
async def test_fake_get_channel_round_trip() -> None:
    fake = _seeded_fake()

    channel = await fake.get_channel("UC123")

    assert channel is not None
    assert channel.id == "UC123"
    assert channel.uploads_playlist_id == "UU123"


@pytest.mark.asyncio
async def test_fake_get_channel_returns_none_for_unknown_id() -> None:
    fake = _seeded_fake()
    assert await fake.get_channel("missing-channel") is None


@pytest.mark.asyncio
async def test_fake_list_channel_videos_pages_correctly() -> None:
    """Walk all pages; sum should equal seed video count."""
    fake = _seeded_fake()
    seen_ids: list[str] = []
    page_token: str | None = None
    page_count = 0

    while True:
        result = await fake.list_channel_videos("UC123", page_token=page_token)
        seen_ids.extend(v.id for v in result.items)
        page_count += 1
        if result.next_page_token is None:
            break
        page_token = result.next_page_token

    # 50 videos / PAGE_SIZE=2 → 25 pages, all 50 ids seen.
    assert len(seen_ids) == 50
    assert page_count == 25
    # Each page returned exactly PAGE_SIZE items (last page included since 50 % 2 == 0).
    assert all(seen_ids.count(vid) == 1 for vid in seen_ids)


@pytest.mark.asyncio
async def test_fake_list_channel_videos_unknown_channel_returns_empty() -> None:
    fake = _seeded_fake()
    result = await fake.list_channel_videos("UC-missing")
    assert result.items == []
    assert result.next_page_token is None


@pytest.mark.asyncio
async def test_fake_get_video_hit_and_miss() -> None:
    fake = _seeded_fake()
    hit = await fake.get_video("vid00")
    miss = await fake.get_video("vid99-doesnt-exist")
    assert hit is not None and hit.id == "vid00"
    assert miss is None


@pytest.mark.asyncio
async def test_fake_search_returns_matching_videos() -> None:
    fake = FakeYoutubeClient(
        channels={"UC123": _channel()},
        videos={
            "vid1": _video("vid1", title="Python tutorial"),
            "vid2": _video("vid2", title="Rust deep dive"),
            "vid3": _video("vid3", description="A python beginner guide"),
        },
    )
    result = await fake.search("python")
    matched_ids = {v.id for v in result.items}
    assert "vid1" in matched_ids
    assert "vid3" in matched_ids
    assert "vid2" not in matched_ids


# ============================================================================
# Quota math — Fake
# ============================================================================


@pytest.mark.asyncio
async def test_fake_get_channel_costs_one_unit() -> None:
    fake = _seeded_fake()
    await fake.get_channel("UC123")
    assert fake.quota_units_consumed == 1


@pytest.mark.asyncio
async def test_fake_list_channel_videos_one_page_costs_two_units() -> None:
    """`playlistItems.list` (1) + `videos.list` (1) = 2 per page."""
    fake = _seeded_fake()
    result = await fake.list_channel_videos("UC123")
    assert result.quota_units_consumed == 2
    assert fake.quota_units_consumed == 2


@pytest.mark.asyncio
async def test_fake_list_channel_videos_full_walk_50_videos_costs_proportional() -> None:
    """Walking all 25 pages of 50 videos: 25 × 2 = 50 units total.

    NOTE: in the seed's documented quota math, '~2 units per 50 videos'
    refers to the REAL-API page size of 50. The Fake's PAGE_SIZE=2 is
    a testability knob; the cost-per-page (2 units) is what matters and
    matches the API contract."""
    fake = _seeded_fake()
    page_token: str | None = None
    while True:
        result = await fake.list_channel_videos("UC123", page_token=page_token)
        if result.next_page_token is None:
            break
        page_token = result.next_page_token
    # 25 pages × 2 units = 50 units cumulative.
    assert fake.quota_units_consumed == 50


@pytest.mark.asyncio
async def test_fake_search_costs_100_units_per_page() -> None:
    fake = _seeded_fake()
    await fake.search("video")
    assert fake.quota_units_consumed == 100


@pytest.mark.asyncio
async def test_fake_get_video_costs_one_unit() -> None:
    fake = _seeded_fake()
    await fake.get_video("vid00")
    assert fake.quota_units_consumed == 1


@pytest.mark.asyncio
async def test_fake_quota_units_accumulate_across_calls() -> None:
    fake = _seeded_fake()
    await fake.get_channel("UC123")  # 1
    await fake.list_channel_videos("UC123")  # 2
    await fake.get_video("vid00")  # 1
    await fake.search("Demo")  # 100
    assert fake.quota_units_consumed == 104


# ============================================================================
# Real client — mocked googleapiclient.discovery.build
# ============================================================================


def _mock_service_with_responses(
    *,
    channels_response: dict[str, Any] | None = None,
    playlist_items_response: dict[str, Any] | None = None,
    videos_response: dict[str, Any] | None = None,
    search_response: dict[str, Any] | None = None,
) -> MagicMock:
    """Wires a MagicMock that mirrors googleapiclient's chained-builder
    shape: `service.<resource>().list(**kwargs).execute()`."""
    service = MagicMock()
    if channels_response is not None:
        service.channels.return_value.list.return_value.execute.return_value = (
            channels_response
        )
    if playlist_items_response is not None:
        service.playlistItems.return_value.list.return_value.execute.return_value = (
            playlist_items_response
        )
    if videos_response is not None:
        service.videos.return_value.list.return_value.execute.return_value = (
            videos_response
        )
    if search_response is not None:
        service.search.return_value.list.return_value.execute.return_value = (
            search_response
        )
    return service


@pytest.mark.asyncio
async def test_real_get_channel_calls_channels_list_with_correct_part() -> None:
    service = _mock_service_with_responses(
        channels_response={
            "items": [
                {
                    "id": "UC123",
                    "snippet": {"title": "Demo", "description": "..."},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
                }
            ]
        },
    )
    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ) as build_mock:
        client = RealYoutubeClient(api_key="fake-key")
        channel = await client.get_channel("UC123")

    assert channel is not None
    assert channel.id == "UC123"
    assert channel.uploads_playlist_id == "UU123"
    build_mock.assert_called_with(
        "youtube", "v3", developerKey="fake-key", cache_discovery=False
    )
    list_kwargs = service.channels.return_value.list.call_args.kwargs
    assert list_kwargs["id"] == "UC123"
    assert "snippet" in list_kwargs["part"]
    assert "contentDetails" in list_kwargs["part"]


@pytest.mark.asyncio
async def test_real_get_channel_returns_none_when_no_items() -> None:
    service = _mock_service_with_responses(channels_response={"items": []})
    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        channel = await client.get_channel("UC-missing")
    assert channel is None


@pytest.mark.asyncio
async def test_real_list_channel_videos_uses_uploads_playlist_path() -> None:
    """Round-trip the channel → uploads-playlist → videos chain. Asserts
    that the cheap sequence runs (NOT search.list)."""
    service = _mock_service_with_responses(
        channels_response={
            "items": [
                {
                    "id": "UC123",
                    "snippet": {"title": "Demo", "description": "..."},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
                }
            ]
        },
        playlist_items_response={
            "items": [
                {"contentDetails": {"videoId": "vid1"}},
                {"contentDetails": {"videoId": "vid2"}},
            ],
            "nextPageToken": "next-tok",
        },
        videos_response={
            "items": [
                {
                    "id": "vid1",
                    "snippet": {
                        "title": "First",
                        "description": "...",
                        "channelId": "UC123",
                        "publishedAt": "2026-05-04T12:00:00Z",
                    },
                    "contentDetails": {"duration": "PT5M30S"},
                    "statistics": {"viewCount": "1000"},
                },
                {
                    "id": "vid2",
                    "snippet": {
                        "title": "Second",
                        "description": "...",
                        "channelId": "UC123",
                        "publishedAt": "2026-05-03T12:00:00Z",
                    },
                    "contentDetails": {"duration": "PT3M"},
                    "statistics": {"viewCount": "500"},
                },
            ]
        },
    )
    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        result = await client.list_channel_videos("UC123")

    # Used the cheap path — search() must NOT have been touched.
    assert not service.search.called

    # playlistItems.list got the uploads playlist id.
    pli_kwargs = service.playlistItems.return_value.list.call_args.kwargs
    assert pli_kwargs["playlistId"] == "UU123"
    assert pli_kwargs["maxResults"] == 50

    # videos.list got the comma-joined video ids.
    videos_kwargs = service.videos.return_value.list.call_args.kwargs
    assert videos_kwargs["id"] == "vid1,vid2"

    assert [v.id for v in result.items] == ["vid1", "vid2"]
    assert result.next_page_token == "next-tok"
    assert result.items[0].duration_seconds == 5 * 60 + 30
    assert result.items[0].view_count == 1000
    # 1 (channels.list) + 1 (playlistItems.list) + 1 (videos.list) = 3.
    assert result.quota_units_consumed == 3


@pytest.mark.asyncio
async def test_real_list_channel_videos_passes_page_token() -> None:
    service = _mock_service_with_responses(
        channels_response={
            "items": [
                {
                    "id": "UC123",
                    "snippet": {"title": "Demo", "description": "..."},
                    "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
                }
            ]
        },
        playlist_items_response={"items": [], "nextPageToken": None},
    )
    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        await client.list_channel_videos("UC123", page_token="page-2")

    pli_kwargs = service.playlistItems.return_value.list.call_args.kwargs
    assert pli_kwargs["pageToken"] == "page-2"


@pytest.mark.asyncio
async def test_real_list_channel_videos_returns_empty_when_channel_missing() -> None:
    service = _mock_service_with_responses(channels_response={"items": []})
    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        result = await client.list_channel_videos("UC-missing")
    assert result.items == []
    assert result.next_page_token is None


@pytest.mark.asyncio
async def test_real_get_video_returns_none_when_missing() -> None:
    service = _mock_service_with_responses(videos_response={"items": []})
    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        video = await client.get_video("missing")
    assert video is None


@pytest.mark.asyncio
async def test_real_get_video_returns_video_when_present() -> None:
    service = _mock_service_with_responses(
        videos_response={
            "items": [
                {
                    "id": "vidX",
                    "snippet": {
                        "title": "X",
                        "description": "...",
                        "channelId": "UC123",
                        "publishedAt": "2026-05-04T12:00:00Z",
                    },
                    "contentDetails": {"duration": "PT45S"},
                    "statistics": {"viewCount": "42"},
                }
            ]
        }
    )
    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        video = await client.get_video("vidX")
    assert video is not None
    assert video.id == "vidX"
    assert video.duration_seconds == 45
    assert video.view_count == 42


@pytest.mark.asyncio
async def test_real_search_calls_search_list_with_query_and_quota_100() -> None:
    service = _mock_service_with_responses(
        search_response={
            "items": [
                {
                    "id": {"videoId": "vid1", "kind": "youtube#video"},
                    "snippet": {
                        "title": "Match",
                        "description": "...",
                        "channelId": "UC123",
                        "publishedAt": "2026-05-04T12:00:00Z",
                    },
                }
            ],
            "nextPageToken": "next",
        }
    )
    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        result = await client.search("python")

    assert result.quota_units_consumed == 100
    assert result.next_page_token == "next"
    assert [v.id for v in result.items] == ["vid1"]
    search_kwargs = service.search.return_value.list.call_args.kwargs
    assert search_kwargs["q"] == "python"
    assert search_kwargs["type"] == "video"


def test_real_uses_oauth_credentials_when_supplied() -> None:
    creds = MagicMock()
    with patch(
        "noctusai_lib.integrations.youtube.real.build"
    ) as build_mock:
        client = RealYoutubeClient(oauth_credentials=creds)
        client._service()
    build_mock.assert_called_with(
        "youtube", "v3", credentials=creds, cache_discovery=False
    )


def test_real_requires_credentials_at_construction() -> None:
    with pytest.raises(ValueError, match="api_key or oauth_credentials"):
        RealYoutubeClient()


@pytest.mark.asyncio
async def test_real_get_channel_logs_and_raises_on_http_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """No silent errors: HttpError is logged at WARN+ and re-raised."""
    from googleapiclient.errors import HttpError

    fake_resp = MagicMock()
    fake_resp.status = 403
    err = HttpError(resp=fake_resp, content=b"forbidden")

    service = MagicMock()
    service.channels.return_value.list.return_value.execute.side_effect = err

    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        with caplog.at_level("WARNING"):
            with pytest.raises(HttpError):
                await client.get_channel("UC123")

    assert any(
        "youtube.get_channel_http_error" in record.message for record in caplog.records
    )


# ============================================================================
# Mappers / parsers
# ============================================================================


def test_parse_iso8601_duration_handles_h_m_s() -> None:
    assert _parse_iso8601_duration("PT1H5M30S") == 3600 + 5 * 60 + 30
    assert _parse_iso8601_duration("PT5M30S") == 5 * 60 + 30
    assert _parse_iso8601_duration("PT45S") == 45
    assert _parse_iso8601_duration("PT0S") == 0


def test_parse_iso8601_duration_returns_zero_on_garbage() -> None:
    assert _parse_iso8601_duration("garbage") == 0
    assert _parse_iso8601_duration("") == 0


def test_parse_published_at_handles_z_suffix() -> None:
    parsed = _parse_published_at("2026-05-04T12:00:00Z")
    assert parsed == datetime(2026, 5, 4, 12, 0, tzinfo=timezone.utc)


def test_parse_published_at_returns_min_on_garbage() -> None:
    parsed = _parse_published_at("not a date")
    assert parsed.tzinfo is timezone.utc
    assert parsed.year == 1


# ============================================================================
# Factory
# ============================================================================


def test_factory_returns_fake_when_use_fake_true() -> None:
    client = make_youtube_client(use_fake=True)
    assert isinstance(client, FakeYoutubeClient)


def test_factory_returns_real_when_use_fake_false() -> None:
    client = make_youtube_client(use_fake=False, api_key="real-key")
    assert isinstance(client, RealYoutubeClient)


def test_factory_pre_populates_fake_with_seed_data() -> None:
    channel = _channel()
    seed = {
        "channels": {channel.id: channel},
        "videos": {"vid1": _video("vid1")},
        "playlists": {"UU123": Playlist(id="UU123", title="Uploads")},
    }
    client = make_youtube_client(use_fake=True, fake_seed_data=seed)
    assert isinstance(client, FakeYoutubeClient)
    assert client.channels == seed["channels"]
    assert client.videos == seed["videos"]
    assert client.playlists == seed["playlists"]


def test_factory_real_requires_credentials() -> None:
    with pytest.raises(ValueError, match="api_key or oauth_credentials"):
        make_youtube_client(use_fake=False)


def test_fake_satisfies_youtube_client_protocol() -> None:
    """Structural typing: FakeYoutubeClient instances are usable wherever
    YoutubeClient is annotated."""
    fake: YoutubeClient = FakeYoutubeClient()
    # Method existence proves Protocol satisfaction at runtime.
    assert hasattr(fake, "get_channel")
    assert hasattr(fake, "list_channel_videos")
    assert hasattr(fake, "get_video")
    assert hasattr(fake, "search")


def test_real_satisfies_youtube_client_protocol() -> None:
    real: YoutubeClient = RealYoutubeClient(api_key="x")
    assert hasattr(real, "get_channel")
    assert hasattr(real, "list_channel_videos")
    assert hasattr(real, "get_video")
    assert hasattr(real, "search")


def test_list_result_default_empty() -> None:
    """Round-trip the value object's defaults."""
    result: ListResult[Video] = ListResult()
    assert result.items == []
    assert result.next_page_token is None
    assert result.quota_units_consumed == 0


# ============================================================================
# Upload surface — Fake
# ============================================================================


@pytest.mark.asyncio
async def test_fake_upload_video_deterministic_id_and_quota() -> None:
    from noctusai_lib.integrations.youtube import UPLOAD_QUOTA_UNITS, VideoUpload

    fake = FakeYoutubeClient()
    result = await fake.upload_video(
        file_path="/tmp/x.mp4", title="My video", description="d"
    )
    assert isinstance(result, VideoUpload)
    assert result.video_id == "fake-upload-1"
    assert result.url == "https://www.youtube.com/watch?v=fake-upload-1"
    assert result.privacy_status == "private"
    assert result.quota_units_consumed == UPLOAD_QUOTA_UNITS == 1600
    assert fake.quota_units_consumed == 1600
    assert fake.uploaded == [result]

    second = await fake.upload_video(file_path="/tmp/y.mp4", title="Two")
    assert second.video_id == "fake-upload-2"
    assert fake.quota_units_consumed == 3200
    assert fake.uploaded == [result, second]


@pytest.mark.asyncio
async def test_fake_upload_video_clips_title_to_100() -> None:
    fake = FakeYoutubeClient()
    long_title = "A" * 250
    result = await fake.upload_video(file_path="/tmp/x.mp4", title=long_title)
    assert len(result.title) == 100


@pytest.mark.asyncio
async def test_fake_upload_video_respects_privacy_status() -> None:
    fake = FakeYoutubeClient()
    result = await fake.upload_video(
        file_path="/tmp/x.mp4", title="t", privacy_status="unlisted"
    )
    assert result.privacy_status == "unlisted"


# ============================================================================
# Upload surface — Real (mocked transport)
# ============================================================================


@pytest.mark.asyncio
async def test_real_upload_video_requires_oauth() -> None:
    client = RealYoutubeClient(api_key="key-only")
    with pytest.raises(ValueError, match="requires oauth_credentials"):
        await client.upload_video(file_path="/tmp/x.mp4", title="t")


@pytest.mark.asyncio
async def test_real_upload_video_calls_insert_resumable() -> None:
    creds = MagicMock()
    service = MagicMock()
    insert_request = MagicMock()
    # Resumable loop: first next_chunk → (status, None), then final chunk.
    insert_request.next_chunk.side_effect = [
        (MagicMock(), None),
        (MagicMock(), {"id": "newvid42"}),
    ]
    service.videos.return_value.insert.return_value = insert_request

    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ), patch(
        "noctusai_lib.integrations.youtube.real.MediaFileUpload"
    ) as media_mock:
        client = RealYoutubeClient(oauth_credentials=creds)
        result = await client.upload_video(
            file_path="/tmp/v.mp4",
            title="X" * 250,
            description="desc",
            tags=["a", "b"],
            privacy_status="public",
            category_id="22",
        )

    media_mock.assert_called_once_with("/tmp/v.mp4", resumable=True)
    insert_kwargs = service.videos.return_value.insert.call_args.kwargs
    assert insert_kwargs["part"] == "snippet,status"
    body = insert_kwargs["body"]
    assert len(body["snippet"]["title"]) == 100  # clipped
    assert body["snippet"]["tags"] == ["a", "b"]
    assert body["status"]["privacyStatus"] == "public"
    assert result.video_id == "newvid42"
    assert result.url == "https://www.youtube.com/watch?v=newvid42"
    assert result.quota_units_consumed == 1600


def test_fake_and_real_satisfy_upload_surface() -> None:
    fake: YoutubeClient = FakeYoutubeClient()
    real: YoutubeClient = RealYoutubeClient(api_key="x")
    assert hasattr(fake, "upload_video")
    assert hasattr(real, "upload_video")


# ============================================================================
# set_thumbnail — Fake
# ============================================================================


@pytest.mark.asyncio
async def test_fake_set_thumbnail_records_call_and_quota() -> None:
    fake = FakeYoutubeClient()
    await fake.set_thumbnail(
        video_id="vid1",
        thumbnail_path="/tmp/cover.jpg",
        mime_type="image/jpeg",
    )
    assert fake.quota_units_consumed == 50
    assert fake.thumbnails_set == [
        {
            "video_id": "vid1",
            "thumbnail_path": "/tmp/cover.jpg",
            "mime_type": "image/jpeg",
        }
    ]


@pytest.mark.asyncio
async def test_fake_set_thumbnail_accumulates_per_call() -> None:
    """Three thumbnails → three records + 150 cumulative units."""
    fake = FakeYoutubeClient()
    for i in range(3):
        await fake.set_thumbnail(
            video_id=f"vid{i}", thumbnail_path=f"/tmp/t{i}.png", mime_type="image/png"
        )
    assert len(fake.thumbnails_set) == 3
    assert fake.quota_units_consumed == 150
    assert fake.thumbnails_set[2]["mime_type"] == "image/png"


# ============================================================================
# set_thumbnail — Real (mocked transport)
# ============================================================================


@pytest.mark.asyncio
async def test_real_set_thumbnail_requires_oauth() -> None:
    client = RealYoutubeClient(api_key="key-only")
    with pytest.raises(ValueError, match="requires oauth_credentials"):
        await client.set_thumbnail(video_id="v", thumbnail_path="/tmp/x.jpg")


@pytest.mark.asyncio
async def test_real_set_thumbnail_calls_thumbnails_set_with_media() -> None:
    creds = MagicMock()
    service = MagicMock()
    service.thumbnails.return_value.set.return_value.execute.return_value = {"kind": "ok"}

    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ), patch(
        "noctusai_lib.integrations.youtube.real.MediaFileUpload"
    ) as media_mock:
        client = RealYoutubeClient(oauth_credentials=creds)
        await client.set_thumbnail(
            video_id="vidX",
            thumbnail_path="/tmp/cover.jpg",
            mime_type="image/jpeg",
        )

    media_mock.assert_called_once_with(
        "/tmp/cover.jpg", mimetype="image/jpeg", resumable=False
    )
    set_kwargs = service.thumbnails.return_value.set.call_args.kwargs
    assert set_kwargs["videoId"] == "vidX"
    # media_body is the return value of MediaFileUpload
    assert set_kwargs["media_body"] is media_mock.return_value


@pytest.mark.asyncio
async def test_real_set_thumbnail_logs_and_raises_on_http_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from googleapiclient.errors import HttpError

    fake_resp = MagicMock()
    fake_resp.status = 403
    err = HttpError(resp=fake_resp, content=b"forbidden")

    service = MagicMock()
    service.thumbnails.return_value.set.return_value.execute.side_effect = err

    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ), patch(
        "noctusai_lib.integrations.youtube.real.MediaFileUpload"
    ):
        client = RealYoutubeClient(oauth_credentials=MagicMock())
        with caplog.at_level("WARNING"):
            with pytest.raises(HttpError):
                await client.set_thumbnail(video_id="vidX", thumbnail_path="/tmp/x.jpg")

    assert any(
        "youtube.set_thumbnail_http_error" in record.message for record in caplog.records
    )


# ============================================================================
# get_processing_status — Fake
# ============================================================================


@pytest.mark.asyncio
async def test_fake_get_processing_status_default_for_unknown_video() -> None:
    """Default state when video not in `processing_states`: uploaded + processing."""
    fake = FakeYoutubeClient()
    state = await fake.get_processing_status("brand-new-vid")
    assert state.video_id == "brand-new-vid"
    assert state.upload_status == "uploaded"
    assert state.processing_status == "processing"
    assert state.privacy_status == "private"
    assert state.quota_units_consumed == 1
    assert fake.quota_units_consumed == 1


@pytest.mark.asyncio
async def test_fake_get_processing_status_returns_seeded_terminal_state() -> None:
    fake = FakeYoutubeClient()
    fake.processing_states["vidX"] = ProcessingStatus(
        video_id="vidX",
        upload_status="processed",
        processing_status="succeeded",
        privacy_status="public",
    )
    state = await fake.get_processing_status("vidX")
    assert state.upload_status == "processed"
    assert state.processing_status == "succeeded"
    assert state.privacy_status == "public"


@pytest.mark.asyncio
async def test_fake_get_processing_status_failed_state() -> None:
    fake = FakeYoutubeClient()
    fake.processing_states["vidF"] = ProcessingStatus(
        video_id="vidF",
        upload_status="failed",
        processing_status="failed",
        privacy_status="private",
    )
    state = await fake.get_processing_status("vidF")
    assert state.upload_status == "failed"
    assert state.processing_status == "failed"


@pytest.mark.asyncio
async def test_fake_get_processing_status_raises_for_missing_sentinel() -> None:
    fake = FakeYoutubeClient()
    with pytest.raises(ValueError, match="no items"):
        await fake.get_processing_status("<missing>")


@pytest.mark.asyncio
async def test_fake_upload_video_seeds_processing_state() -> None:
    """`upload_video` seeds a default state for the new id so the
    upload-then-poll-status flow round-trips through the same fake."""
    fake = FakeYoutubeClient()
    result = await fake.upload_video(
        file_path="/tmp/v.mp4", title="t", privacy_status="unlisted"
    )
    state = await fake.get_processing_status(result.video_id)
    assert state.video_id == result.video_id
    assert state.upload_status == "uploaded"
    assert state.processing_status == "processing"
    assert state.privacy_status == "unlisted"  # Echoes the upload's privacy_status.


# ============================================================================
# get_processing_status — Real (mocked transport)
# ============================================================================


@pytest.mark.asyncio
async def test_real_get_processing_status_returns_terminal_state() -> None:
    service = _mock_service_with_responses(
        videos_response={
            "items": [
                {
                    "id": "vidX",
                    "status": {
                        "uploadStatus": "processed",
                        "privacyStatus": "public",
                    },
                    "processingDetails": {"processingStatus": "succeeded"},
                }
            ]
        }
    )
    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        state = await client.get_processing_status("vidX")

    assert state.video_id == "vidX"
    assert state.upload_status == "processed"
    assert state.processing_status == "succeeded"
    assert state.privacy_status == "public"
    assert state.quota_units_consumed == 1
    list_kwargs = service.videos.return_value.list.call_args.kwargs
    assert list_kwargs["id"] == "vidX"
    assert "status" in list_kwargs["part"]
    assert "processingDetails" in list_kwargs["part"]


@pytest.mark.asyncio
async def test_real_get_processing_status_processing_state() -> None:
    service = _mock_service_with_responses(
        videos_response={
            "items": [
                {
                    "id": "vidY",
                    "status": {
                        "uploadStatus": "uploaded",
                        "privacyStatus": "private",
                    },
                    "processingDetails": {"processingStatus": "processing"},
                }
            ]
        }
    )
    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        state = await client.get_processing_status("vidY")

    assert state.upload_status == "uploaded"
    assert state.processing_status == "processing"


@pytest.mark.asyncio
async def test_real_get_processing_status_failed_state() -> None:
    service = _mock_service_with_responses(
        videos_response={
            "items": [
                {
                    "id": "vidZ",
                    "status": {
                        "uploadStatus": "failed",
                        "privacyStatus": "private",
                    },
                    "processingDetails": {"processingStatus": "failed"},
                }
            ]
        }
    )
    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        state = await client.get_processing_status("vidZ")

    assert state.upload_status == "failed"
    assert state.processing_status == "failed"


@pytest.mark.asyncio
async def test_real_get_processing_status_raises_when_missing() -> None:
    service = _mock_service_with_responses(videos_response={"items": []})
    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        with pytest.raises(ValueError, match="no items"):
            await client.get_processing_status("missing")


@pytest.mark.asyncio
async def test_real_get_processing_status_unknown_defaults() -> None:
    """API omitted the status fields → seed surfaces "unknown" literals."""
    service = _mock_service_with_responses(
        videos_response={"items": [{"id": "vidQ", "status": {}, "processingDetails": {}}]}
    )
    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        state = await client.get_processing_status("vidQ")
    assert state.upload_status == "unknown"
    assert state.processing_status == "unknown"
    assert state.privacy_status == "unknown"


@pytest.mark.asyncio
async def test_real_get_processing_status_logs_and_raises_on_http_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from googleapiclient.errors import HttpError

    fake_resp = MagicMock()
    fake_resp.status = 403
    err = HttpError(resp=fake_resp, content=b"forbidden")

    service = MagicMock()
    service.videos.return_value.list.return_value.execute.side_effect = err

    with patch(
        "noctusai_lib.integrations.youtube.real.build", return_value=service
    ):
        client = RealYoutubeClient(api_key="fake-key")
        with caplog.at_level("WARNING"):
            with pytest.raises(HttpError):
                await client.get_processing_status("vidX")

    assert any(
        "youtube.get_processing_status_http_error" in record.message
        for record in caplog.records
    )


# ============================================================================
# Protocol satisfaction — new surface
# ============================================================================


def test_fake_and_real_satisfy_thumbnail_and_processing_surface() -> None:
    fake: YoutubeClient = FakeYoutubeClient()
    real: YoutubeClient = RealYoutubeClient(api_key="x")
    assert hasattr(fake, "set_thumbnail")
    assert hasattr(real, "set_thumbnail")
    assert hasattr(fake, "get_processing_status")
    assert hasattr(real, "get_processing_status")
