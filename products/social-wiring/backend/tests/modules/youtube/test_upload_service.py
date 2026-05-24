"""Tests for upload_service — pipeline orchestration with mocked YouTube."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from app.modules.youtube.schemas.upload import UploadMetadata
from app.modules.youtube.services.upload import (
    UploadService,
    UploadServiceError,
    rename_for_job,
    stage_browser_upload,
)
from app.modules.youtube.services.youtube import YouTubeNotConnected, YouTubeServiceError


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


class _CountingMockSupabase(_MockSupabase):
    """Mock that returns a fresh job id per insert (needed for batch
    fan-out tests where N inserts must yield N distinct UUIDs)."""

    def execute(self):
        if self.inserted_payloads and not self._select_response:
            # Return a fresh id per insert call. We track how many
            # inserts have happened via len(inserted_payloads); the
            # response always corresponds to the LATEST insert.
            return MagicMock(data=[{"id": str(uuid4())}])
        return MagicMock(data=self._select_response)


def _install_fake_gdown(
    monkeypatch,
    files_to_create: list[tuple[str, bytes]] | None = None,
    *,
    raises: Exception | None = None,
):
    """Install a fake ``gdown`` module that materialises files under
    ``output/drive-folder-root/...``. Mirrors the pattern in
    test_gdrive_service.TestIterDriveFolderVideos so the upload service
    can be exercised end-to-end against the real
    ``iter_drive_folder_videos`` integration."""
    import sys
    import types

    materialise = files_to_create or []

    def fake_download_folder(*, id, output, quiet, **_kwargs):
        if raises is not None:
            raise raises
        output_dir = Path(output)
        root = output_dir / "drive-folder-root"
        root.mkdir(parents=True, exist_ok=True)
        written: list[str] = []
        for relpath, content in materialise:
            target = root / relpath
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            written.append(str(target))
        return written

    fake_module = types.SimpleNamespace(download_folder=fake_download_folder)
    monkeypatch.setitem(sys.modules, "gdown", fake_module)


class TestQueueDriveFolderUpload:
    """Phase 3 of youtube-drive-folder-fanout: one Drive folder URL →
    N upload_jobs rows sharing one batch_id, each with the file already
    on disk in the canonical `<job_id>__<file_name>` browser-source
    location ready for the worker."""

    _FOLDER_URL = "https://drive.google.com/drive/folders/1abc23DEF456ghi789JKL012mno345PQ"

    def _make_service(self, upload_dir, yt_mock):
        sb = _CountingMockSupabase()
        admin = _MockSupabase()
        svc = UploadService(
            user_supabase=sb,
            admin_supabase=admin,
            upload_dir=upload_dir,
            youtube_service=yt_mock,
        )
        return svc, sb, admin

    def test_flat_folder_two_videos_creates_two_rows(
        self, upload_dir, yt_mock, monkeypatch
    ):
        """2 videos in folder → 2 rows, shared batch_id, both files staged."""
        _install_fake_gdown(monkeypatch, [
            ("horizontal.mp4", b"x" * 100),
            ("vertical.mp4", b"y" * 200),
        ])

        svc, sb, _admin = self._make_service(upload_dir, yt_mock)

        result = svc.queue_drive_folder_upload(
            org_id=uuid4(),
            created_by=None,
            metadata=_make_metadata(),
            drive_folder_url=self._FOLDER_URL,
        )

        assert len(result.children) == 2
        # Same batch_id across siblings (the dashboard grouping key).
        batch_ids_inserted = {p["batch_id"] for p in sb.inserted_payloads}
        assert batch_ids_inserted == {str(result.batch_id)}
        # Both child files are now at the canonical browser-source path.
        for child in result.children:
            canonical = upload_dir / f"{child.job_id}__{child.file_name}"
            assert canonical.exists(), (
                f"expected staged file at {canonical} after fan-out rename"
            )

    def test_payload_carries_browser_source_type_and_folder_audit_url(
        self, upload_dir, yt_mock, monkeypatch
    ):
        """The DB row uses source_type='browser' (file already on disk)
        but records the originating folder URL in source_url for audit."""
        _install_fake_gdown(monkeypatch, [("clip.mp4", b"x" * 10)])

        svc, sb, _ = self._make_service(upload_dir, yt_mock)

        svc.queue_drive_folder_upload(
            org_id=uuid4(),
            created_by=None,
            metadata=_make_metadata(),
            drive_folder_url=self._FOLDER_URL,
        )

        assert len(sb.inserted_payloads) == 1
        payload = sb.inserted_payloads[0]
        assert payload["source_type"] == "browser"
        assert payload["source_url"] == self._FOLDER_URL
        # Worker stamps target_format later; queue-time row has no value
        # for it (omitted from payload so DB default NULL applies).
        assert "target_format" not in payload
        # file_size known at queue time for folder fan-out (unlike the
        # single-file Drive path which leaves it NULL until download).
        assert payload["file_size_bytes"] == 10

    def test_subfolder_parent_label_propagated(
        self, upload_dir, yt_mock, monkeypatch
    ):
        """A subfolder-nested video carries its subfolder name on the ref."""
        _install_fake_gdown(monkeypatch, [
            ("Episode 3/cut.mp4", b"x" * 10),
            ("master.mp4", b"y" * 10),
        ])

        svc, _, _ = self._make_service(upload_dir, yt_mock)

        result = svc.queue_drive_folder_upload(
            org_id=uuid4(),
            created_by=None,
            metadata=_make_metadata(),
            drive_folder_url=self._FOLDER_URL,
        )

        by_name = {c.file_name: c for c in result.children}
        assert by_name["cut.mp4"].parent_subfolder == "Episode 3"
        assert by_name["master.mp4"].parent_subfolder is None

    def test_invalid_folder_url_raises_before_download(
        self, upload_dir, yt_mock
    ):
        """Bad URL → UploadServiceError BEFORE any Drive download."""
        svc, _, _ = self._make_service(upload_dir, yt_mock)

        with pytest.raises(UploadServiceError):
            svc.queue_drive_folder_upload(
                org_id=uuid4(),
                created_by=None,
                metadata=_make_metadata(),
                drive_folder_url="https://drive.google.com/",
            )

    def test_empty_folder_raises(self, upload_dir, yt_mock, monkeypatch):
        """gdown returning [] → UploadServiceError (wraps GoogleDriveError)."""
        _install_fake_gdown(monkeypatch, [])

        svc, _, _ = self._make_service(upload_dir, yt_mock)

        with pytest.raises(UploadServiceError, match="fanout failed"):
            svc.queue_drive_folder_upload(
                org_id=uuid4(),
                created_by=None,
                metadata=_make_metadata(),
                drive_folder_url=self._FOLDER_URL,
            )

    def test_folder_with_only_non_videos_raises(
        self, upload_dir, yt_mock, monkeypatch
    ):
        """Folder existed but had nothing to upload → UploadServiceError."""
        _install_fake_gdown(monkeypatch, [
            ("README.txt", b"hi"),
        ])

        svc, _, _ = self._make_service(upload_dir, yt_mock)

        with pytest.raises(UploadServiceError, match="fanout failed"):
            svc.queue_drive_folder_upload(
                org_id=uuid4(),
                created_by=None,
                metadata=_make_metadata(),
                drive_folder_url=self._FOLDER_URL,
            )


class TestGetBatchStatus:
    """Phase 5 — aggregate status read for a fan-out batch."""

    def _make_service(self, upload_dir, yt_mock, rows):
        sb = _MockSupabase(select_response=rows)
        admin = _MockSupabase()
        svc = UploadService(
            user_supabase=sb,
            admin_supabase=admin,
            upload_dir=upload_dir,
            youtube_service=yt_mock,
        )
        return svc

    def test_returns_none_when_batch_unknown(self, upload_dir, yt_mock):
        svc = self._make_service(upload_dir, yt_mock, rows=[])
        out = svc.get_batch_status(org_id=uuid4(), batch_id=uuid4())
        assert out is None

    def test_counts_aggregate_across_statuses(self, upload_dir, yt_mock):
        batch_id = uuid4()
        rows = [
            {"id": str(uuid4()), "status": "published", "batch_id": str(batch_id)},
            {"id": str(uuid4()), "status": "published", "batch_id": str(batch_id)},
            {"id": str(uuid4()), "status": "uploading", "batch_id": str(batch_id)},
            {"id": str(uuid4()), "status": "failed",    "batch_id": str(batch_id)},
            {"id": str(uuid4()), "status": "queued",    "batch_id": str(batch_id)},
        ]
        svc = self._make_service(upload_dir, yt_mock, rows=rows)
        out = svc.get_batch_status(org_id=uuid4(), batch_id=batch_id)
        assert out is not None
        assert out["total"] == 5
        assert out["counts"]["published"] == 2
        assert out["counts"]["uploading"] == 1
        assert out["counts"]["failed"] == 1
        assert out["counts"]["queued"] == 1
        # Untouched buckets stay zero.
        assert out["counts"]["downloading"] == 0
        assert out["counts"]["notified"] == 0

    def test_unknown_status_does_not_break_counts(self, upload_dir, yt_mock):
        """A row with an unexpected status (forward-compat) is counted
        in `total` but doesn't blow up the per-status buckets."""
        batch_id = uuid4()
        rows = [
            {"id": str(uuid4()), "status": "exotic-new-state", "batch_id": str(batch_id)},
            {"id": str(uuid4()), "status": "published",        "batch_id": str(batch_id)},
        ]
        svc = self._make_service(upload_dir, yt_mock, rows=rows)
        out = svc.get_batch_status(org_id=uuid4(), batch_id=batch_id)
        assert out is not None
        assert out["total"] == 2
        assert out["counts"]["published"] == 1
        # Unknown statuses simply not bucketed → all other counts are 0.
        assert sum(out["counts"].values()) == 1


class TestShortsAwareDescription:
    """Phase 4 helper — pure function, no IO."""

    def test_horizontal_passthrough(self):
        out = UploadService._shorts_aware_description(
            description="my long-form video", target_format="youtube"
        )
        assert out == "my long-form video"

    def test_unknown_passthrough(self):
        out = UploadService._shorts_aware_description(
            description="ambiguous video", target_format="unknown"
        )
        assert out == "ambiguous video"

    def test_none_target_format_passthrough(self):
        out = UploadService._shorts_aware_description(
            description="legacy row no classification", target_format=None
        )
        assert out == "legacy row no classification"

    def test_shorts_appends_tag(self):
        out = UploadService._shorts_aware_description(
            description="my vertical video", target_format="shorts"
        )
        assert out == "my vertical video\n\n#Shorts"

    def test_shorts_idempotent_when_tag_already_present(self):
        out = UploadService._shorts_aware_description(
            description="already tagged #Shorts here", target_format="shorts"
        )
        assert out == "already tagged #Shorts here"

    def test_shorts_idempotent_lowercase_tag(self):
        out = UploadService._shorts_aware_description(
            description="lowercase #shorts also counts", target_format="shorts"
        )
        assert out == "lowercase #shorts also counts"

    def test_shorts_empty_description_becomes_just_tag(self):
        out = UploadService._shorts_aware_description(
            description="", target_format="shorts"
        )
        assert out == "#Shorts"


class TestClassifyAndStampTargetFormat:
    """Phase 4 worker classification: after the file is on disk, the
    pipeline stamps `target_format` so the upload step + the dashboard
    know what the row is. Best-effort: a classify failure stamps
    'unknown' rather than failing the upload."""

    def _make_service(self, upload_dir, yt_mock, classifier=None):
        # `classifier` is the Class-B DI seam: inject a stub video classifier
        # through the constructor instead of patching
        # `gdrive_service.classify_video_format` (our own module fn). Per
        # KB § PATTERNS/di-test-seam.md.
        sb = _MockSupabase()
        admin = _MockSupabase()
        svc = UploadService(
            user_supabase=sb,
            admin_supabase=admin,
            upload_dir=upload_dir,
            youtube_service=yt_mock,
            classifier=classifier,
        )
        return svc, admin

    def test_existing_value_is_idempotent(self, upload_dir, yt_mock):
        """Re-running on a row that already has target_format does NOT
        re-classify or re-write — retries stay clean."""
        svc, admin = self._make_service(upload_dir, yt_mock)
        local = upload_dir / "video.mp4"
        local.write_bytes(b"\x00" * 10)

        out = svc._classify_and_stamp_target_format(
            job_id=uuid4(), local_path=local, existing="youtube"
        )
        assert out == "youtube"
        assert admin.updated_payloads == [], (
            "idempotent path must NOT write to the DB"
        )

    def test_classify_reels_is_mapped_to_shorts(self, upload_dir, yt_mock):
        """classify_video_format returns 'reels' → DB column gets 'shorts'."""
        svc, admin = self._make_service(
            upload_dir, yt_mock, classifier=lambda p: "reels"
        )
        local = upload_dir / "vertical.mp4"
        local.write_bytes(b"\x00" * 10)

        out = svc._classify_and_stamp_target_format(
            job_id=uuid4(), local_path=local, existing=None
        )
        assert out == "shorts"
        assert admin.updated_payloads
        assert admin.updated_payloads[0]["target_format"] == "shorts"

    def test_classify_youtube_stamped_directly(self, upload_dir, yt_mock):
        svc, admin = self._make_service(
            upload_dir, yt_mock, classifier=lambda p: "youtube"
        )
        local = upload_dir / "horizontal.mp4"
        local.write_bytes(b"\x00" * 10)

        out = svc._classify_and_stamp_target_format(
            job_id=uuid4(), local_path=local, existing=None
        )
        assert out == "youtube"
        assert admin.updated_payloads[0]["target_format"] == "youtube"

    def test_classify_failure_stamps_unknown(self, upload_dir, yt_mock):
        """A raise from classify_video_format → stamp 'unknown', no abort."""
        def boom(_p):
            raise RuntimeError("ffprobe gone wild")

        svc, admin = self._make_service(upload_dir, yt_mock, classifier=boom)
        local = upload_dir / "video.mp4"
        local.write_bytes(b"\x00" * 10)

        out = svc._classify_and_stamp_target_format(
            job_id=uuid4(), local_path=local, existing=None
        )
        assert out == "unknown"
        assert admin.updated_payloads[0]["target_format"] == "unknown"

    def test_unexpected_classify_value_defensive_unknown(self, upload_dir, yt_mock):
        """If classify_video_format ever returns a NEW value we don't
        recognise, the stamp falls back to 'unknown' so the DB CHECK
        constraint is never violated."""
        svc, admin = self._make_service(
            upload_dir, yt_mock, classifier=lambda p: "experimental"
        )
        local = upload_dir / "weird.mp4"
        local.write_bytes(b"\x00" * 10)

        out = svc._classify_and_stamp_target_format(
            job_id=uuid4(), local_path=local, existing=None
        )
        assert out == "unknown"
        assert admin.updated_payloads[0]["target_format"] == "unknown"


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
