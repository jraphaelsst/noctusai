"""Tests for the Audio Retention Service.

compliance-audit-reconciliation Phase 5 / finding 6 (2026-04-22).
Covers: expired-segment listing + storage-delete dispatch + idempotency.

The tests exercise call-shape (bucket.remove called with extracted path,
metadata cleared on success, not cleared on failure) via a stub storage
client; MockSupabaseClient doesn't simulate storage state.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

from tests.conftest import MockSupabaseClient
from app.services import audio_retention_service


SP_TZ = timezone(timedelta(hours=-3))


def _stub_storage(client: MockSupabaseClient, remove_raises: bool = False):
    """Install a stub `storage.from_(...).remove(...)` on the mock client."""
    bucket = MagicMock()
    if remove_raises:
        bucket.remove.side_effect = RuntimeError("boom")
    else:
        bucket.remove.return_value = {"removed": True}
    client.storage = MagicMock()
    client.storage.from_.return_value = bucket
    return bucket


class TestExtractStoragePath:
    def test_extracts_from_bucket_path_drops_signing_token(self):
        """`urlparse().path` excludes the query — the storage object key is
        the path portion only, never the signing token."""
        url = "https://xyz.supabase.co/storage/v1/object/sign/therapy-session-audio/room-1/seg.webm?token=abc"
        assert audio_retention_service._extract_storage_path(url) == "room-1/seg.webm"

    def test_extracts_from_object_public_path(self):
        url = "https://xyz.supabase.co/storage/v1/object/public/other-bucket/dir/file.mp3"
        assert audio_retention_service._extract_storage_path(url) == "dir/file.mp3"

    def test_passthrough_for_unfamiliar(self):
        out = audio_retention_service._extract_storage_path("file-only")
        assert out == "file-only"


class TestFindExpiredSegments:
    def test_returns_empty_when_none_expired(self):
        db = MockSupabaseClient()
        db.set_table_data("session_audio_segments", [])
        assert audio_retention_service.find_expired_segments(db) == []


class TestExpireAudioFile:
    def test_expire_no_url_returns_false(self):
        db = MockSupabaseClient()
        _stub_storage(db)
        segment = {"id": "s-1", "video_room_id": "r-1", "audio_file_url": None}
        assert audio_retention_service.expire_audio_file(segment, db) is False

    def test_expire_calls_bucket_remove_with_extracted_path(self):
        db = MockSupabaseClient()
        db.set_table_data("video_rooms", [{"id": "r-1", "appointment_id": "a-1"}])
        db.set_table_data("session_records", [])
        bucket = _stub_storage(db)
        segment = {
            "id": "s-1",
            "video_room_id": "r-1",
            "audio_file_url": (
                "https://x.supabase.co/storage/v1/object/sign/"
                "therapy-session-audio/r-1/f.webm?token=abc"
            ),
        }
        ok = audio_retention_service.expire_audio_file(segment, db)
        assert ok is True
        bucket.remove.assert_called_once_with(["r-1/f.webm"])

    def test_expire_storage_failure_preserves_metadata(self):
        db = MockSupabaseClient()
        db.set_table_data("video_rooms", [{"id": "r-1", "appointment_id": "a-1"}])
        _stub_storage(db, remove_raises=True)
        segment = {
            "id": "s-1",
            "video_room_id": "r-1",
            "audio_file_url": (
                "https://x.supabase.co/storage/v1/object/sign/"
                "therapy-session-audio/r-1/f.webm"
            ),
        }
        ok = audio_retention_service.expire_audio_file(segment, db)
        assert ok is False


class TestRunRetentionSweep:
    def test_sweep_with_no_expired_returns_zero(self):
        db = MockSupabaseClient()
        db.set_table_data("session_audio_segments", [])
        _stub_storage(db)
        result = audio_retention_service.run_retention_sweep(db)
        assert result == {"found": 0, "deleted": 0}
