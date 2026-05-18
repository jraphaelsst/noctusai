"""Tests for upload_service — pipeline orchestration with mocked YouTube."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.schemas.upload import UploadMetadata
from app.services import gdrive_service
from app.services.upload_service import (
    UploadService,
    UploadServiceError,
    rename_for_job,
    stage_browser_upload,
)
from app.services.youtube_service import YouTubeNotConnected, YouTubeServiceError


def _make_metadata(**overrides) -> UploadMetadata:
    base = {
        "title": "My Video",
        "description": "Test desc",
        "tags": ["a", "b"],
        "privacy_status": "private",
        "category_id": "22",
        "notify_recipients": [],
    }
    base.update(overrides)
    return UploadMetadata(**base)


class _MockSupabase:
    """Tiny stub for the supabase client surface UploadService uses."""

    def __init__(self, *, insert_response=None, select_response=None):
        self._insert_response = insert_response or [{"id": str(uuid4())}]
        self._select_response = select_response or []
        self.inserted_payloads: list = []
        self.updated_payloads: list = []

    def schema(self, _name):
        return self

    def table(self, _name):
        return self

    def insert(self, payload):
        self.inserted_payloads.append(payload)
        return self

    def update(self, payload):
        self.updated_payloads.append(payload)
        return self

    def select(self, *_a, **_k):
        return self

    def order(self, *_a, **_k):
        return self

    def limit(self, *_a, **_k):
        return self

    def eq(self, *_a, **_k):
        return self

    def execute(self):
        # Differentiate insert vs select by whether we just appended an
        # insert payload — good enough for these tests.
        if self.inserted_payloads and not self._select_response:
            return MagicMock(data=self._insert_response)
        return MagicMock(data=self._select_response)


@pytest.fixture
def upload_dir(tmp_path):
    d = tmp_path / "uploads"
    d.mkdir()
    return d


@pytest.fixture
def yt_mock():
    yt = MagicMock()
    yt.upload_video.return_value = "yt_video_abc"
    yt.get_processing_status.return_value = {"upload_status": "processed", "processing_status": "succeeded"}
    return yt


class TestQueueBrowserUpload:
    def test_inserts_job_row_with_browser_source(self, tmp_path, upload_dir, yt_mock):
        local = upload_dir / "video.mp4"
        local.write_bytes(b"\x00" * 1024)

        sb = _MockSupabase(insert_response=[{"id": str(uuid4())}])
        admin = _MockSupabase()
        svc = UploadService(
            user_supabase=sb,
            admin_supabase=admin,
            upload_dir=upload_dir,
            youtube_service=yt_mock,
        )
        org_id = uuid4()
        user_id = uuid4()

        result = svc.queue_browser_upload(
            org_id=org_id,
            created_by=user_id,
            metadata=_make_metadata(),
            file_name="video.mp4",
            file_size_bytes=1024,
            local_path=local,
        )

        assert result.job_id is not None
        assert len(sb.inserted_payloads) == 1
        payload = sb.inserted_payloads[0]
        assert payload["source_type"] == "browser"
        assert payload["title"] == "My Video"
        assert payload["org_id"] == str(org_id)
        assert payload["created_by"] == str(user_id)
        assert payload["file_size_bytes"] == 1024
        assert payload["notify_recipients"] == []

    def test_missing_local_file_raises(self, upload_dir, yt_mock):
        sb = _MockSupabase()
        admin = _MockSupabase()
        svc = UploadService(
            user_supabase=sb,
            admin_supabase=admin,
            upload_dir=upload_dir,
            youtube_service=yt_mock,
        )
        with pytest.raises(UploadServiceError):
            svc.queue_browser_upload(
                org_id=uuid4(),
                created_by=None,
                metadata=_make_metadata(),
                file_name="ghost.mp4",
                file_size_bytes=0,
                local_path=upload_dir / "ghost.mp4",
            )


class TestQueueDriveUpload:
    def test_valid_drive_url_inserts(self, upload_dir, yt_mock):
        sb = _MockSupabase(insert_response=[{"id": str(uuid4())}])
        admin = _MockSupabase()
        svc = UploadService(
            user_supabase=sb,
            admin_supabase=admin,
            upload_dir=upload_dir,
            youtube_service=yt_mock,
        )

        result = svc.queue_drive_upload(
            org_id=uuid4(),
            created_by=None,
            metadata=_make_metadata(),
            drive_url="https://drive.google.com/file/d/1aBcDeFgHiJkLmNoPqRsTu/view",
        )

        assert result.job_id is not None
        payload = sb.inserted_payloads[0]
        assert payload["source_type"] == "gdrive"
        assert payload["source_url"].startswith("https://drive.google.com/")
        assert payload["file_size_bytes"] is None  # unknown until download

    def test_invalid_drive_url_raises(self, upload_dir, yt_mock):
        sb = _MockSupabase()
        admin = _MockSupabase()
        svc = UploadService(
            user_supabase=sb,
            admin_supabase=admin,
            upload_dir=upload_dir,
            youtube_service=yt_mock,
        )
        with pytest.raises(UploadServiceError):
            svc.queue_drive_upload(
                org_id=uuid4(),
                created_by=None,
                metadata=_make_metadata(),
                drive_url="https://drive.google.com/",
            )


class TestRunUploadJob:
    """End-to-end pipeline with mocked youtube service + admin Supabase."""

    def _make_service(self, *, upload_dir, yt_mock, job_row):
        admin = _MockSupabase(select_response=[job_row])
        sb = _MockSupabase()
        svc = UploadService(
            user_supabase=sb,
            admin_supabase=admin,
            upload_dir=upload_dir,
            youtube_service=yt_mock,
        )
        return svc, admin

    def test_browser_job_full_pipeline(self, upload_dir, yt_mock):
        job_id = uuid4()
        org_id = uuid4()
        # Stage the file the worker expects to find.
        local = upload_dir / f"{job_id}__video.mp4"
        local.write_bytes(b"\x00" * 1024)

        job_row = {
            "id": str(job_id),
            "org_id": str(org_id),
            "title": "Browser Vid",
            "description": "",
            "tags": [],
            "privacy_status": "private",
            "category_id": "22",
            "source_type": "browser",
            "source_url": None,
            "file_name": "video.mp4",
        }
        svc, admin = self._make_service(
            upload_dir=upload_dir, yt_mock=yt_mock, job_row=job_row,
        )

        svc.run_upload_job(job_id=job_id)

        yt_mock.upload_video.assert_called_once()
        kwargs = yt_mock.upload_video.call_args.kwargs
        assert kwargs["title"] == "Browser Vid"
        assert kwargs["org_id"] == org_id

        # Status should have transitioned: uploading → published.
        statuses = [p.get("status") for p in admin.updated_payloads]
        assert "uploading" in statuses
        assert "published" in statuses
        # Final update should also carry the youtube_video_id.
        published_update = [p for p in admin.updated_payloads if p.get("status") == "published"][0]
        assert published_update["youtube_video_id"] == "yt_video_abc"

    def test_browser_job_missing_file_marks_failed(self, upload_dir, yt_mock):
        job_id = uuid4()
        # Don't stage the file — pipeline should fail gracefully.
        job_row = {
            "id": str(job_id),
            "org_id": str(uuid4()),
            "title": "Missing",
            "source_type": "browser",
            "source_url": None,
            "file_name": "ghost.mp4",
        }
        svc, admin = self._make_service(
            upload_dir=upload_dir, yt_mock=yt_mock, job_row=job_row,
        )

        svc.run_upload_job(job_id=job_id)

        yt_mock.upload_video.assert_not_called()
        assert any(p.get("status") == "failed" for p in admin.updated_payloads)

    def test_youtube_not_connected_marks_failed(self, upload_dir, yt_mock):
        job_id = uuid4()
        local = upload_dir / f"{job_id}__video.mp4"
        local.write_bytes(b"\x00" * 1024)
        yt_mock.upload_video.side_effect = YouTubeNotConnected("not connected")

        job_row = {
            "id": str(job_id),
            "org_id": str(uuid4()),
            "title": "T", "description": "", "tags": [],
            "privacy_status": "private", "category_id": "22",
            "source_type": "browser", "source_url": None,
            "file_name": "video.mp4",
        }
        svc, admin = self._make_service(
            upload_dir=upload_dir, yt_mock=yt_mock, job_row=job_row,
        )

        svc.run_upload_job(job_id=job_id)

        failed = [p for p in admin.updated_payloads if p.get("status") == "failed"]
        assert len(failed) == 1
        assert "not connected" in failed[0]["error_message"].lower()

    def test_youtube_service_error_marks_failed(self, upload_dir, yt_mock):
        job_id = uuid4()
        local = upload_dir / f"{job_id}__video.mp4"
        local.write_bytes(b"\x00" * 1024)
        yt_mock.upload_video.side_effect = YouTubeServiceError("quota exceeded")

        job_row = {
            "id": str(job_id),
            "org_id": str(uuid4()),
            "title": "T", "description": "", "tags": [],
            "privacy_status": "private", "category_id": "22",
            "source_type": "browser", "source_url": None,
            "file_name": "video.mp4",
        }
        svc, admin = self._make_service(
            upload_dir=upload_dir, yt_mock=yt_mock, job_row=job_row,
        )

        svc.run_upload_job(job_id=job_id)

        failed = [p for p in admin.updated_payloads if p.get("status") == "failed"]
        assert len(failed) == 1
        assert "quota" in failed[0]["error_message"].lower()


class TestStagingHelpers:
    def test_stage_writes_file_then_yields_path(self, tmp_path):
        import io
        with stage_browser_upload(
            upload_dir=tmp_path,
            file_name="x.mp4",
            upload_stream=io.BytesIO(b"data"),
        ) as staged:
            assert staged.exists()
            assert staged.read_bytes() == b"data"
            assert staged.name.endswith("__x.mp4")

    def test_stage_cleans_up_on_inner_exception(self, tmp_path):
        import io
        with pytest.raises(RuntimeError):
            with stage_browser_upload(
                upload_dir=tmp_path,
                file_name="x.mp4",
                upload_stream=io.BytesIO(b"data"),
            ) as staged:
                # Verify file existed inside the block, then blow up.
                assert staged.exists()
                raise RuntimeError("boom")
        # Staged file should have been cleaned up.
        assert list(tmp_path.glob("staging-*")) == []

    def test_rename_for_job_moves_to_job_id_path(self, tmp_path):
        import io
        with stage_browser_upload(
            upload_dir=tmp_path,
            file_name="vid.mp4",
            upload_stream=io.BytesIO(b"d"),
        ) as staged:
            job_id = uuid4()
            final = rename_for_job(staged, job_id, "vid.mp4")
            assert final.exists()
            assert final.name == f"{job_id}__vid.mp4"
            assert not staged.exists()


# ─── Phase 4: notification dispatch hook ───────────────────────────────
class TestNotificationHook:
    """Tail-of-publishing dispatch. The upload-service must:
    1. Skip dispatch when notification_service is None (Phase 2/3 backward-compat).
    2. Skip dispatch when notify_recipients[] is empty (opt-out path).
    3. Transition to status='notified' when dispatcher reports succeeded > 0.
    4. Stay at status='published' when dispatcher fails or all sends fail.
    5. Never let a notification failure undo the publish."""

    def _make_browser_job(self, job_id, *, notify_recipients=None):
        return {
            "id": str(job_id),
            "org_id": str(uuid4()),
            "title": "T", "description": "", "tags": [],
            "privacy_status": "private", "category_id": "22",
            "source_type": "browser", "source_url": None,
            "file_name": "video.mp4",
            "notify_recipients": notify_recipients or [],
        }

    def _stage_browser_file(self, upload_dir, job_id):
        local = upload_dir / f"{job_id}__video.mp4"
        local.write_bytes(b"\x00" * 1024)
        return local

    def test_notification_skipped_when_service_is_none(self, upload_dir, yt_mock):
        """Phase 2/3 backward-compat: no notification_service, no fan-out."""
        job_id = uuid4()
        self._stage_browser_file(upload_dir, job_id)
        admin = _MockSupabase(select_response=[
            self._make_browser_job(job_id, notify_recipients=[str(uuid4())]),
        ])
        svc = UploadService(
            user_supabase=_MockSupabase(),
            admin_supabase=admin,
            upload_dir=upload_dir,
            youtube_service=yt_mock,
            # notification_service= omitted ← Phase 2/3 default
        )
        svc.run_upload_job(job_id=job_id)
        statuses = [p.get("status") for p in admin.updated_payloads]
        assert "published" in statuses
        assert "notified" not in statuses

    def test_notification_skipped_when_recipients_empty(self, upload_dir, yt_mock):
        """Empty notify_recipients[] → no dispatch attempt."""
        job_id = uuid4()
        self._stage_browser_file(upload_dir, job_id)
        admin = _MockSupabase(select_response=[
            self._make_browser_job(job_id, notify_recipients=[]),
        ])
        notif = MagicMock()
        notif.notify_upload = MagicMock()       # would explode if called sync
        svc = UploadService(
            user_supabase=_MockSupabase(),
            admin_supabase=admin,
            upload_dir=upload_dir,
            youtube_service=yt_mock,
            notification_service=notif,
        )
        svc.run_upload_job(job_id=job_id)
        notif.notify_upload.assert_not_called()
        statuses = [p.get("status") for p in admin.updated_payloads]
        assert "notified" not in statuses

    def test_status_transitions_to_notified_on_success(self, upload_dir, yt_mock):
        """At least one recipient succeeded → flip to 'notified'."""
        from unittest.mock import AsyncMock
        from app.services.notification_service import DispatchOutcome

        job_id = uuid4()
        self._stage_browser_file(upload_dir, job_id)
        admin = _MockSupabase(select_response=[
            self._make_browser_job(job_id, notify_recipients=[str(uuid4())]),
        ])
        notif = MagicMock()
        notif.notify_upload = AsyncMock(return_value=DispatchOutcome(
            attempted=1, succeeded=1, failed=0, recipients=1,
        ))
        svc = UploadService(
            user_supabase=_MockSupabase(),
            admin_supabase=admin,
            upload_dir=upload_dir,
            youtube_service=yt_mock,
            notification_service=notif,
        )
        svc.run_upload_job(job_id=job_id)

        statuses = [p.get("status") for p in admin.updated_payloads]
        assert "published" in statuses
        assert "notified" in statuses
        # 'notified' must come AFTER 'published'.
        assert statuses.index("published") < statuses.index("notified")

    def test_stays_at_published_when_all_sends_fail(self, upload_dir, yt_mock):
        """All recipients failed → stay at 'published' (never undo upload)."""
        from unittest.mock import AsyncMock
        from app.services.notification_service import DispatchOutcome

        job_id = uuid4()
        self._stage_browser_file(upload_dir, job_id)
        admin = _MockSupabase(select_response=[
            self._make_browser_job(job_id, notify_recipients=[str(uuid4())]),
        ])
        notif = MagicMock()
        notif.notify_upload = AsyncMock(return_value=DispatchOutcome(
            attempted=1, succeeded=0, failed=1, recipients=1,
        ))
        svc = UploadService(
            user_supabase=_MockSupabase(),
            admin_supabase=admin,
            upload_dir=upload_dir,
            youtube_service=yt_mock,
            notification_service=notif,
        )
        svc.run_upload_job(job_id=job_id)

        statuses = [p.get("status") for p in admin.updated_payloads]
        assert "published" in statuses
        assert "notified" not in statuses

    def test_dispatch_exception_does_not_undo_publish(self, upload_dir, yt_mock):
        """Notification dispatcher raising → publish remains; we just don't
        flip to 'notified'. The upload itself is sacred."""
        from unittest.mock import AsyncMock

        job_id = uuid4()
        self._stage_browser_file(upload_dir, job_id)
        admin = _MockSupabase(select_response=[
            self._make_browser_job(job_id, notify_recipients=[str(uuid4())]),
        ])
        notif = MagicMock()
        notif.notify_upload = AsyncMock(side_effect=RuntimeError("boom"))
        svc = UploadService(
            user_supabase=_MockSupabase(),
            admin_supabase=admin,
            upload_dir=upload_dir,
            youtube_service=yt_mock,
            notification_service=notif,
        )
        # Must NOT raise — exception is captured, logged, and absorbed.
        svc.run_upload_job(job_id=job_id)

        statuses = [p.get("status") for p in admin.updated_payloads]
        assert "published" in statuses
        assert "notified" not in statuses
        assert "failed" not in statuses
