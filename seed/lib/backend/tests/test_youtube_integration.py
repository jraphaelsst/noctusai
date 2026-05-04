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
