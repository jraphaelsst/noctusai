"""Tests for SnapshotService — Phase 3 daily snapshot pipeline.

Coverage:
  - claim-row guard: same-day re-run skipped (idempotency)
  - force=True overrides the skip
  - classify_short routing: video vs short table
  - channel snapshot upsert
  - video snapshot upsert
  - backfill_from_video_cache seeds catalog when empty
  - error path: status='error' set, exception re-raised

DI pattern: SnapshotService accepts optional ``yt_service_builder`` and
``ia_service_builder`` constructor params (KB § PATTERNS/backend/di-test-seam.md
Class-B). Tests inject fakes directly without patching our own symbols.
"""
from __future__ import annotations

import asyncio
from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from noctusai_lib.integrations.youtube.types import ChannelInfo, VideoFull, ListResult
from noctusai_lib.integrations.youtube.classification import ShortClassification

from app.modules.youtube.services.snapshot_service import (
    SnapshotOutcome,
    SnapshotService,
    SnapshotServiceError,
)


# ─── Stubs ────────────────────────────────────────────────────────────────

class _StubSupabase:
    """Minimal Supabase stub that records upserts + returns canned selects."""

    def __init__(self):
        self.upserts: list[dict] = []    # (table, payload) pairs
        self.updates: list[dict] = []
        self._select_queue: list = []
        self._mode = "select"
        self._table_name = ""

    def set_select(self, data, count=None):
        self._select_queue.append((data, count))

    def schema(self, _name):
        return self

    def table(self, name):
        self._table_name = name
        return self

    def select(self, *_a, **_k):
        self._mode = "select"
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def gte(self, *_a, **_k):
        return self

    def upsert(self, payload, **_k):
        self._mode = "upsert"
        self.upserts.append({"table": self._table_name, "payload": payload})
        return self

    def update(self, payload):
        self._mode = "update"
        self.updates.append({"table": self._table_name, "payload": payload})
        return self

    def execute(self):
        if self._mode in ("upsert", "update"):
            return MagicMock(data=[{}])
        if self._select_queue:
            data, count = self._select_queue.pop(0)
            return MagicMock(data=data, count=count)
        return MagicMock(data=[], count=0)


def _make_video_full(
    vid_id: str,
    *,
    duration_seconds: int = 200,
    description: str = "",
    tags: tuple = (),
) -> VideoFull:
    return VideoFull(
        id=vid_id,
        title=f"Video {vid_id}",
        description=description,
        channel_id="UC123",
        published_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        duration_seconds=duration_seconds,
        duration_iso=f"PT{duration_seconds}S",
        thumbnail_url="https://t.example/x.jpg",
        privacy_status="public",
        view_count=100,
        like_count=10,
        comment_count=2,
        tags=tags,
        category_id="22",
    )


def _make_short_full(vid_id: str) -> VideoFull:
    """A video that classify_short will route to youtube_shorts (≤60s)."""
    return _make_video_full(vid_id, duration_seconds=45)


def _stub_cfg():
    cfg = MagicMock()
    cfg.encryption_key = "test-key"
    cfg.youtube_client_id = "cid"
    cfg.youtube_client_secret = "csec"
    cfg.youtube_redirect_uri = "http://localhost/cb"
    return cfg


# ─── claim-row guard ──────────────────────────────────────────────────────

class TestClaimRowGuard:
    def test_skips_when_done_row_exists(self):
        """Same-day re-run returns skipped=True without calling YouTube API."""
        admin = _StubSupabase()
        # Claim check: 'done' row exists
        admin.set_select(data=[{"status": "done"}])

        svc = SnapshotService(admin_supabase=admin, cfg=_stub_cfg())
        outcome = svc.run_for_account(
            org_id=uuid4(),
            account_id=uuid4(),
            snapshot_date=date(2026, 6, 1),
        )

        assert outcome.skipped is True
        assert outcome.videos_upserted == 0
        assert outcome.shorts_upserted == 0

    def test_force_overrides_done_row(self):
        """force=True runs even when a done row exists (writes snapshot_runs again).

        Uses DI seam: yt_service_builder / ia_service_builder injected at
        construction so no patching of our own module symbols is needed.
        Per KB § PATTERNS/backend/di-test-seam.md (Class-B).
        """
        admin = _StubSupabase()
        # Claim check: 'done' row
        admin.set_select(data=[{"status": "done"}])

        channel_info = ChannelInfo(
            channel_id="UC1",
            title="Test",
            subscriber_count=500,
            video_count=10,
            view_count=1000,
        )
        vf_regular = _make_video_full("vid1")

        mock_yt = MagicMock()
        mock_yt.get_channel_info.return_value = channel_info
        mock_yt.list_all_videos_full.return_value = ([vf_regular], None)

        mock_ia_svc = MagicMock()
        mock_ia_svc.update_channel_info.return_value = MagicMock()

        svc = SnapshotService(
            admin_supabase=admin,
            cfg=_stub_cfg(),
            yt_service_builder=lambda *a, **kw: mock_yt,
            ia_service_builder=lambda *a, **kw: mock_ia_svc,
        )

        # Catalog is empty (no existing rows)
        admin.set_select(data=[])   # catalog_is_empty youtube_videos
        admin.set_select(data=[])   # catalog_is_empty youtube_shorts
        # backfill: video_cache is empty
        admin.set_select(data=[])
        # app_uploaded_ids
        admin.set_select(data=[])

        outcome = svc.run_for_account(
            org_id=uuid4(),
            account_id=uuid4(),
            snapshot_date=date(2026, 6, 1),
            force=True,
        )

        assert outcome.skipped is False
        assert outcome.videos_upserted == 1


# ─── classify routing ─────────────────────────────────────────────────────

class TestClassifyRouting:
    def _run_with_videos(self, videos: list[VideoFull]) -> tuple[_StubSupabase, SnapshotOutcome]:
        """Run SnapshotService with a pre-seeded video list.

        Uses DI seam: yt_service_builder / ia_service_builder injected so no
        patching of our own module symbols is needed.
        Per KB § PATTERNS/backend/di-test-seam.md (Class-B).
        """
        admin = _StubSupabase()
        # Claim check: no existing row → proceed
        admin.set_select(data=[])
        # Catalog is empty
        admin.set_select(data=[])
        admin.set_select(data=[])
        # backfill: video_cache empty
        admin.set_select(data=[])
        # app_uploaded_ids
        admin.set_select(data=[])

        channel_info = ChannelInfo(
            channel_id="UC1", title="T", subscriber_count=0, video_count=0, view_count=0
        )
        org_id = uuid4()
        account_id = uuid4()

        mock_yt = MagicMock()
        mock_yt.get_channel_info.return_value = channel_info
        # Simulate pagination: single page returning 'videos', then done
        pages = iter([(videos, None)])
        def _list_full(**_kwargs):
            return next(pages)
        mock_yt.list_all_videos_full.side_effect = _list_full

        mock_ia_svc = MagicMock()
        mock_ia_svc.update_channel_info.return_value = MagicMock()

        svc = SnapshotService(
            admin_supabase=admin,
            cfg=_stub_cfg(),
            yt_service_builder=lambda *a, **kw: mock_yt,
            ia_service_builder=lambda *a, **kw: mock_ia_svc,
        )

        outcome = svc.run_for_account(
            org_id=org_id,
            account_id=account_id,
            snapshot_date=date(2026, 6, 1),
        )

        return admin, outcome

    def test_long_video_routes_to_youtube_videos(self):
        """Duration > 180s → youtube_videos table."""
        admin, outcome = self._run_with_videos([_make_video_full("v1", duration_seconds=300)])
        upserted_tables = [u["table"] for u in admin.upserts]
        assert "youtube_videos" in upserted_tables
        assert "youtube_shorts" not in upserted_tables
        assert outcome.videos_upserted == 1
        assert outcome.shorts_upserted == 0

    def test_short_video_routes_to_youtube_shorts(self):
        """Duration ≤ 60s → youtube_shorts table."""
        admin, outcome = self._run_with_videos([_make_short_full("s1")])
        upserted_tables = [u["table"] for u in admin.upserts]
        assert "youtube_shorts" in upserted_tables
        assert "youtube_videos" not in upserted_tables
        assert outcome.shorts_upserted == 1
        assert outcome.videos_upserted == 0

    def test_hashtag_short_routes_to_youtube_shorts(self):
        """#Shorts hashtag in description → youtube_shorts."""
        vf = _make_video_full("h1", duration_seconds=200, description="My #shorts upload")
        admin, outcome = self._run_with_videos([vf])
        upserted_tables = [u["table"] for u in admin.upserts]
        assert "youtube_shorts" in upserted_tables
        assert outcome.shorts_upserted == 1

    def test_video_snapshot_upserted_for_each_video(self):
        """youtube_video_snapshots upserted for every video processed."""
        admin, outcome = self._run_with_videos([
            _make_video_full("v1"), _make_short_full("s1")
        ])
        snap_upserts = [u for u in admin.upserts if u["table"] == "youtube_video_snapshots"]
        assert len(snap_upserts) == 2
        assert outcome.video_snapshots_upserted == 2

    def test_channel_snapshot_upserted(self):
        """youtube_channel_snapshots upserted once per run."""
        admin, outcome = self._run_with_videos([_make_video_full("v1")])
        chan_upserts = [u for u in admin.upserts if u["table"] == "youtube_channel_snapshots"]
        assert len(chan_upserts) == 1

    def test_needs_probe_count_for_ambiguous(self):
        """Duration 61-180s → needs_probe, not classified as short."""
        vf = _make_video_full("a1", duration_seconds=90)
        admin, outcome = self._run_with_videos([vf])
        assert outcome.needs_probe_count == 1
        # Default: not a short for ambiguous band
        upserted_tables = [u["table"] for u in admin.upserts]
        assert "youtube_videos" in upserted_tables


# ─── error path ──────────────────────────────────────────────────────────

class TestErrorPath:
    def test_marks_error_and_reraises(self):
        """When the YouTube call fails, snapshot_runs is marked 'error' + exception re-raised.

        Uses DI seam: yt_service_builder injected so no patching of our own
        module symbols is needed. Per KB § PATTERNS/backend/di-test-seam.md (Class-B).
        """
        admin = _StubSupabase()
        admin.set_select(data=[])  # claim: no existing row

        mock_yt = MagicMock()
        mock_yt.get_channel_info.side_effect = Exception("YouTube boom")

        svc = SnapshotService(
            admin_supabase=admin,
            cfg=_stub_cfg(),
            yt_service_builder=lambda *a, **kw: mock_yt,
        )

        with pytest.raises(SnapshotServiceError):
            svc.run_for_account(
                org_id=uuid4(),
                account_id=uuid4(),
                snapshot_date=date(2026, 6, 1),
            )

        # snapshot_runs should have a status='error' update
        error_updates = [
            u for u in admin.updates
            if u["table"] == "snapshot_runs" and u["payload"].get("status") == "error"
        ]
        assert error_updates, "Expected snapshot_runs status='error' update"


# ─── backfill ────────────────────────────────────────────────────────────

class TestBackfill:
    def test_backfill_routes_cache_rows(self):
        """backfill_from_video_cache classifies legacy rows and seeds catalog tables."""
        admin = _StubSupabase()
        org_id = uuid4()
        account_id = uuid4()

        cache_rows = [
            {
                "youtube_video_id": "vc1",
                "title": "Long video",
                "description": "",
                "thumbnail_url": "",
                "published_at": "2026-01-01T00:00:00+00:00",
                "duration": "PT5M",        # 300s → regular
                "privacy_status": "public",
                "view_count": 500,
                "like_count": 20,
                "comment_count": 5,
                "favorite_count": 0,
                "tags": [],
                "category_id": "22",
                "uploaded_via_app": False,
                "synced_at": "2026-01-01T00:00:00+00:00",
            },
            {
                "youtube_video_id": "vc2",
                "title": "Short vid",
                "description": "#shorts",
                "thumbnail_url": "",
                "published_at": "2026-01-02T00:00:00+00:00",
                "duration": "PT30S",       # 30s + #shorts → short
                "privacy_status": "public",
                "view_count": 1000,
                "like_count": 50,
                "comment_count": 10,
                "favorite_count": 0,
                "tags": [],
                "category_id": "22",
                "uploaded_via_app": False,
                "synced_at": "2026-01-02T00:00:00+00:00",
            },
        ]
        admin.set_select(data=cache_rows)

        svc = SnapshotService(admin_supabase=admin, cfg=_stub_cfg())
        count = svc.backfill_from_video_cache(org_id=org_id, account_id=account_id)

        assert count == 2
        upserted_tables = [u["table"] for u in admin.upserts]
        assert "youtube_videos" in upserted_tables
        assert "youtube_shorts" in upserted_tables
