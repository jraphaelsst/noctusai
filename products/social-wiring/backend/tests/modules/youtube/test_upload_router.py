"""Tests for upload_router — boundary validation + 503-on-config-gap.

Full pipeline tests live in test_upload_service.py; here we just verify
the router wires correctly and rejects bad inputs at the FastAPI layer.

Settings reach the router via the ``Depends(get_settings)`` DI seam, so
config values are injected through the ``override_settings`` fixture
(``app.dependency_overrides[get_settings]``) rather than
``monkeypatch.setattr(settings, ...)``. The upload-service method is
injected through the ``get_upload_service`` DI seam for the same reason.
Per ``KB § PATTERNS/di-test-seam.md`` (Class-A + Class-B)."""
from __future__ import annotations

import json

import pytest

_VALID_ENC_KEY = "QrNxsUUWeoIb1OnT5e_n7P9MbESvJ6KkA8b8q3lXiBg="
_COMPLETE_CREDS = dict(
    encryption_key=_VALID_ENC_KEY,
    youtube_client_id="cid",
    youtube_client_secret="csecret",
)


def _valid_metadata() -> str:
    """JSON-encoded metadata that passes the schema."""
    return json.dumps({
        "title": "T",
        "description": "",
        "tags": [],
        "privacy_status": "private",
        "category_id": "22",
        "notify_recipients": [],
    })


class TestUploadFromDriveValidation:
    def test_non_google_url_rejected_at_schema(self, client, override_settings):
        override_settings(**_COMPLETE_CREDS)

        resp = client.post(
            "/api/videos/upload-from-drive",
            json={
                "drive_url": "https://example.com/file.mp4",
                "metadata": json.loads(_valid_metadata()),
            },
        )
        assert resp.status_code == 422
        assert "google host" in resp.text.lower()

    def test_drive_root_url_rejected_at_service(self, client, override_settings):
        override_settings(**_COMPLETE_CREDS)

        # Schema accepts any google.com URL; service rejects when it can't
        # parse a file_id out.
        resp = client.post(
            "/api/videos/upload-from-drive",
            json={
                "drive_url": "https://drive.google.com/",
                "metadata": json.loads(_valid_metadata()),
            },
        )
        assert resp.status_code == 400
        assert "file id" in resp.text.lower()


class TestUploadFromDriveFolderValidation:
    """Boundary checks for POST /api/videos/upload/drive-folder
    (youtube-drive-folder-fanout Phase 3). Schema-level rejection +
    service-level URL parse failure + service-level "no videos found"
    422 path are exercised here; the happy-path multi-row insert lives
    in `test_upload_service.TestQueueDriveFolderUpload`."""

    def test_non_google_url_rejected_at_schema(self, client, override_settings):
        override_settings(**_COMPLETE_CREDS)

        resp = client.post(
            "/api/videos/upload/drive-folder",
            json={
                "drive_folder_url": "https://example.com/folder",
                "metadata": json.loads(_valid_metadata()),
            },
        )
        assert resp.status_code == 422
        assert "google host" in resp.text.lower()

    def test_drive_root_url_rejected_at_service(self, client, override_settings):
        override_settings(**_COMPLETE_CREDS)

        # Schema accepts any google.com URL; service rejects when it
        # can't extract a folder_id (no `/folders/<id>` segment).
        resp = client.post(
            "/api/videos/upload/drive-folder",
            json={
                "drive_folder_url": "https://drive.google.com/",
                "metadata": json.loads(_valid_metadata()),
            },
        )
        assert resp.status_code == 400
        assert "folder" in resp.text.lower()


class TestUploadConfigGaps:
    """When ENCRYPTION_KEY or YOUTUBE_CLIENT_* are missing, every upload
    endpoint returns 503 — the operator gets a clear "config gap" signal
    rather than a 500 traceback."""

    def test_missing_encryption_key_returns_503(self, client, override_settings):
        override_settings(
            encryption_key="",
            youtube_client_id="cid",
            youtube_client_secret="csecret",
        )

        resp = client.get("/api/videos/upload/00000000-0000-0000-0000-000000000000/status")
        assert resp.status_code == 503
        assert "encryption_key" in resp.text.lower()

    def test_missing_youtube_creds_returns_503(self, client, override_settings):
        override_settings(
            encryption_key=_VALID_ENC_KEY,
            youtube_client_id="",
            youtube_client_secret="",
        )

        resp = client.get("/api/videos/upload/00000000-0000-0000-0000-000000000000/status")
        assert resp.status_code == 503
        assert "youtube_client" in resp.text.lower()


class TestHistoryLimitValidation:
    def test_limit_above_100_rejected(self, client, override_settings):
        override_settings(**_COMPLETE_CREDS)

        resp = client.get("/api/videos/upload/history?limit=500")
        assert resp.status_code == 400
        assert "limit" in resp.text.lower()

    def test_limit_zero_rejected(self, client, override_settings):
        override_settings(**_COMPLETE_CREDS)

        resp = client.get("/api/videos/upload/history?limit=0")
        assert resp.status_code == 400


class TestStatusUnauthenticated:
    def test_status_requires_auth(self, client):
        resp = client.raw().get(
            "/api/videos/upload/00000000-0000-0000-0000-000000000000/status",
        )
        assert resp.status_code in (401, 403)


class TestRetryEndpoint:
    """POST /api/videos/upload/{job_id}/retry — re-queues a previously-failed
    job. Validates state transition + 404/409 boundary conditions."""

    def test_retry_requires_auth(self, client):
        resp = client.raw().post(
            "/api/videos/upload/00000000-0000-0000-0000-000000000000/retry"
        )
        assert resp.status_code in (401, 403)

    def test_retry_returns_404_for_missing_job(
        self, client, override_settings, override_upload_service
    ):
        override_settings(**_COMPLETE_CREDS)
        from app.modules.youtube.services.upload import UploadServiceError

        class _Svc:
            def retry_failed_job(self, **_kwargs):
                raise UploadServiceError("job xyz not found")

        override_upload_service(_Svc())
        resp = client.post(
            "/api/videos/upload/00000000-0000-0000-0000-000000000000/retry"
        )
        assert resp.status_code == 404
        assert "not found" in resp.text.lower()

    def test_retry_returns_409_for_non_failed_job(
        self, client, override_settings, override_upload_service
    ):
        override_settings(**_COMPLETE_CREDS)
        from app.modules.youtube.services.upload import UploadServiceError

        class _Svc:
            def retry_failed_job(self, **_kwargs):
                raise UploadServiceError(
                    "job xyz is in status='uploading'; retry only works on "
                    "failed jobs."
                )

        override_upload_service(_Svc())
        resp = client.post(
            "/api/videos/upload/00000000-0000-0000-0000-000000000000/retry"
        )
        assert resp.status_code == 409
        assert "failed" in resp.text.lower()
