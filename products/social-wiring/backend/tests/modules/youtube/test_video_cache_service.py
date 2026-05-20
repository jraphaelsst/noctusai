"""Tests for video_cache_service — sync pipeline + read-side projection.

Mirrors test_upload_service.py's lean-stub pattern (`_MockSupabase`)
because the lib's `MockSupabaseClient` is heavier than the service-layer
needs here."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.modules.youtube.services.video_cache import (
    SyncOutcome,
    VideoCacheError,
    VideoCacheService,
)
from app.modules.youtube.services.youtube import VideoSummary, YouTubeServiceError


# ─── Lean Supabase stub ────────────────────────────────────────────────
class _MockSupabase:
    """Tracks insert/upsert payloads + returns canned select responses
    in the order they're queued. ``set_select`` populates the next
    select.execute() return; ``upserted_payloads`` collects every upsert
    payload list."""

    def __init__(self):
        self.upserted_payloads: list = []
        self._select_queue: list = []
        self._last_filters: list = []
        self._mode: str = "select"

    def set_select(self, data, count=None):
        """Queue the next select.execute() response."""
        self._select_queue.append((data, count))

    # Builder protocol
    def schema(self, _name):
        return self

    def table(self, _name):
        return self

    def select(self, *_args, **_kwargs):
        self._mode = "select"
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def eq(self, key, value):
        self._last_filters.append(("eq", key, value))
        return self

    def in_(self, key, values):
        self._last_filters.append(("in", key, list(values)))
        return self

    def lt(self, *_a, **_k):
        return self

    def or_(self, *_a, **_k):
        return self

    def upsert(self, payload, **_kwargs):
        self._mode = "upsert"
        self.upserted_payloads.append(list(payload) if isinstance(payload, list) else [payload])
        return self

    def execute(self):
        if self._mode == "upsert":
            return MagicMock(data=[])
        if self._select_queue:
            data, count = self._select_queue.pop(0)
            return MagicMock(data=data, count=count)
        return MagicMock(data=[], count=0)


def _summary(video_id: str, *, published="2026-05-01T00:00:00Z", views=100) -> VideoSummary:
    return VideoSummary(
        video_id=video_id,
        title=f"Video {video_id}",
        description="d",
        thumbnail_url="https://t.example/x.jpg",
        published_at=datetime.fromisoformat(published.replace("Z", "+00:00")),
        duration="PT1M",
        privacy_status="public",
        view_count=views,
        like_count=10,
        comment_count=2,
        tags=["t"],
        category_id="22",
    )


@pytest.fixture
def yt_mock():
    yt = MagicMock()
    return yt


# ─── Sync — single page ────────────────────────────────────────────────
class TestSyncSinglePage:
    def test_inserts_when_cache_empty(self, yt_mock):
        org_id = uuid4()
        yt_mock.list_all_videos.return_value = ([_summary("a"), _summary("b")], None)

        admin = _MockSupabase()
        # First select: app_uploaded_ids (no app uploads yet) → empty.
        admin.set_select(data=[])
        # Second select: existing_ids check → empty.
        admin.set_select(data=[])

        svc = VideoCacheService(
            user_supabase=_MockSupabase(),
            admin_supabase=admin,
            youtube_service=yt_mock,
        )

        outcome = svc.sync(org_id=org_id)

        assert outcome.fetched == 2
        assert outcome.inserted == 2
        assert outcome.updated == 0
        assert outcome.pages == 1
        assert outcome.quota_units_estimated == 2
        assert outcome.last_synced_at is not None
        assert len(admin.upserted_payloads) == 1
        assert len(admin.upserted_payloads[0]) == 2

    def test_updates_when_cache_has_rows(self, yt_mock):
        org_id = uuid4()
        yt_mock.list_all_videos.return_value = ([_summary("a"), _summary("b")], None)

        admin = _MockSupabase()
        admin.set_select(data=[])  # app_uploaded_ids
        admin.set_select(data=[{"youtube_video_id": "a"}])  # existing
        svc = VideoCacheService(
            user_supabase=_MockSupabase(),
            admin_supabase=admin,
            youtube_service=yt_mock,
        )

        outcome = svc.sync(org_id=org_id)

        assert outcome.inserted == 1
        assert outcome.updated == 1


# ─── Sync — multi-page ─────────────────────────────────────────────────
class TestSyncMultiPage:
    def test_walks_until_next_page_token_is_none(self, yt_mock):
        org_id = uuid4()
        yt_mock.list_all_videos.side_effect = [
            ([_summary("a")], "page-2"),
            ([_summary("b")], "page-3"),
            ([_summary("c")], None),
        ]

        admin = _MockSupabase()
        admin.set_select(data=[])  # app_uploaded_ids
        for _ in range(3):
            admin.set_select(data=[])  # existing checks per page
        svc = VideoCacheService(
            user_supabase=_MockSupabase(),
            admin_supabase=admin,
            youtube_service=yt_mock,
        )

        outcome = svc.sync(org_id=org_id)

        assert outcome.pages == 3
        assert outcome.fetched == 3
        assert outcome.inserted == 3
        assert outcome.quota_units_estimated == 6
        assert yt_mock.list_all_videos.call_count == 3

    def test_youtube_error_is_re_raised(self, yt_mock):
        org_id = uuid4()
        yt_mock.list_all_videos.side_effect = YouTubeServiceError("boom")

        admin = _MockSupabase()
        admin.set_select(data=[])  # app_uploaded_ids
        svc = VideoCacheService(
            user_supabase=_MockSupabase(),
            admin_supabase=admin,
            youtube_service=yt_mock,
        )

        with pytest.raises(YouTubeServiceError):
            svc.sync(org_id=org_id)


# ─── Sync — uploaded_via_app projection ────────────────────────────────
class TestUploadedViaApp:
    def test_flag_set_when_id_in_app_uploads(self, yt_mock):
        org_id = uuid4()
        yt_mock.list_all_videos.return_value = (
            [_summary("from-app"), _summary("from-elsewhere")],
            None,
        )

        admin = _MockSupabase()
        admin.set_select(data=[{"youtube_video_id": "from-app"}])  # app_uploaded
        admin.set_select(data=[])                                    # existing
        svc = VideoCacheService(
            user_supabase=_MockSupabase(),
            admin_supabase=admin,
            youtube_service=yt_mock,
        )

        svc.sync(org_id=org_id)

        # Inspect the upserted payload — first row is "from-app" (in the
        # app set), second is not.
        rows = admin.upserted_payloads[0]
        by_id = {r["youtube_video_id"]: r for r in rows}
        assert by_id["from-app"]["uploaded_via_app"] is True
        assert by_id["from-elsewhere"]["uploaded_via_app"] is False


# ─── Sync — empty channel ──────────────────────────────────────────────
class TestEmptyChannel:
    def test_no_videos_returns_zero_counts(self, yt_mock):
        org_id = uuid4()
        yt_mock.list_all_videos.return_value = ([], None)

        admin = _MockSupabase()
        admin.set_select(data=[])  # app_uploaded_ids
        svc = VideoCacheService(
            user_supabase=_MockSupabase(),
            admin_supabase=admin,
            youtube_service=yt_mock,
        )

        outcome = svc.sync(org_id=org_id)

        assert outcome.fetched == 0
        assert outcome.inserted == 0
        assert outcome.pages == 1
        assert admin.upserted_payloads == []  # no upsert called when empty


# ─── Read path ─────────────────────────────────────────────────────────
class TestList:
    def test_returns_items_no_next_cursor_when_under_limit(self, yt_mock):
        org_id = uuid4()
        user_sb = _MockSupabase()
        rows = [
            {
                "id": str(uuid4()),
                "youtube_video_id": "a",
                "published_at": "2026-05-01T00:00:00+00:00",
                "synced_at": "2026-05-06T00:00:00+00:00",
            },
        ]
        user_sb.set_select(data=rows, count=1)
        svc = VideoCacheService(
            user_supabase=user_sb,
            admin_supabase=_MockSupabase(),
            youtube_service=yt_mock,
        )

        items, cursor, total = svc.list(org_id=org_id, limit=10)
        assert len(items) == 1
        assert cursor is None
        assert total == 1

    def test_emits_next_cursor_when_over_limit(self, yt_mock):
        org_id = uuid4()
        user_sb = _MockSupabase()
        rows = [
            {
                "id": f"id-{i}",
                "youtube_video_id": f"v-{i}",
                "published_at": f"2026-05-{i:02d}T00:00:00+00:00",
                "synced_at": "2026-05-06T00:00:00+00:00",
            }
            for i in range(1, 4)
        ]
        # Asked for limit=2, builder fetches 3 → has_next=True
        user_sb.set_select(data=rows, count=3)
        svc = VideoCacheService(
            user_supabase=user_sb,
            admin_supabase=_MockSupabase(),
            youtube_service=yt_mock,
        )

        items, cursor, total = svc.list(org_id=org_id, limit=2)
        assert len(items) == 2
        assert cursor is not None
        assert "|" in cursor                # ts|id format

    def test_uploaded_via_app_filter_passes_through(self, yt_mock):
        org_id = uuid4()
        user_sb = _MockSupabase()
        user_sb.set_select(data=[], count=0)
        svc = VideoCacheService(
            user_supabase=user_sb,
            admin_supabase=_MockSupabase(),
            youtube_service=yt_mock,
        )

        svc.list(org_id=org_id, uploaded_via_app=True)
        # The filter list captured the eq("uploaded_via_app", True) call.
        assert any(
            f == ("eq", "uploaded_via_app", True)
            for f in user_sb._last_filters
        )


class TestGet:
    def test_returns_row_when_present(self, yt_mock):
        org_id = uuid4()
        user_sb = _MockSupabase()
        user_sb.set_select(data=[{"id": "abc", "youtube_video_id": "v1"}])
        svc = VideoCacheService(
            user_supabase=user_sb,
            admin_supabase=_MockSupabase(),
            youtube_service=yt_mock,
        )
        row = svc.get(org_id=org_id, youtube_video_id="v1")
        assert row is not None
        assert row["youtube_video_id"] == "v1"

    def test_returns_none_when_absent(self, yt_mock):
        user_sb = _MockSupabase()
        user_sb.set_select(data=[])
        svc = VideoCacheService(
            user_supabase=user_sb,
            admin_supabase=_MockSupabase(),
            youtube_service=yt_mock,
        )
        row = svc.get(org_id=uuid4(), youtube_video_id="ghost")
        assert row is None
