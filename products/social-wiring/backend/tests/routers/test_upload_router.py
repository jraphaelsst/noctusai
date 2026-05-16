"""Tests for upload_router — boundary validation + 503-on-config-gap.

Full pipeline tests live in test_upload_service.py; here we just verify
the router wires correctly and rejects bad inputs at the FastAPI layer."""
from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from app.config import settings


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
    def test_non_google_url_rejected_at_schema(self, client, monkeypatch):
        monkeypatch.setattr(settings, "encryption_key", "QrNxsUUWeoIb1OnT5e_n7P9MbESvJ6KkA8b8q3lXiBg=")
        monkeypatch.setattr(settings, "youtube_client_id", "cid")
        monkeypatch.setattr(settings, "youtube_client_secret", "csecret")

        resp = client.post(
            "/api/videos/upload-from-drive",
            json={
                "drive_url": "https://example.com/file.mp4",
                "metadata": json.loads(_valid_metadata()),
            },
        )
        assert resp.status_code == 422
        assert "google host" in resp.text.lower()

    def test_drive_root_url_rejected_at_service(self, client, monkeypatch):
        monkeypatch.setattr(settings, "encryption_key", "QrNxsUUWeoIb1OnT5e_n7P9MbESvJ6KkA8b8q3lXiBg=")
        monkeypatch.setattr(settings, "youtube_client_id", "cid")
        monkeypatch.setattr(settings, "youtube_client_secret", "csecret")

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


class TestUploadConfigGaps:
    """When ENCRYPTION_KEY or YOUTUBE_CLIENT_* are missing, every upload
    endpoint returns 503 — the operator gets a clear "config gap" signal
    rather than a 500 traceback."""

    def test_missing_encryption_key_returns_503(self, client, monkeypatch):
        monkeypatch.setattr(settings, "encryption_key", "")
        monkeypatch.setattr(settings, "youtube_client_id", "cid")
        monkeypatch.setattr(settings, "youtube_client_secret", "csecret")

        resp = client.get("/api/videos/upload/00000000-0000-0000-0000-000000000000/status")
        assert resp.status_code == 503
        assert "encryption_key" in resp.text.lower()

    def test_missing_youtube_creds_returns_503(self, client, monkeypatch):
        monkeypatch.setattr(settings, "encryption_key", "QrNxsUUWeoIb1OnT5e_n7P9MbESvJ6KkA8b8q3lXiBg=")
        monkeypatch.setattr(settings, "youtube_client_id", "")
        monkeypatch.setattr(settings, "youtube_client_secret", "")

        resp = client.get("/api/videos/upload/00000000-0000-0000-0000-000000000000/status")
        assert resp.status_code == 503
        assert "youtube_client" in resp.text.lower()


class TestHistoryLimitValidation:
    def test_limit_above_100_rejected(self, client, monkeypatch):
        monkeypatch.setattr(settings, "encryption_key", "QrNxsUUWeoIb1OnT5e_n7P9MbESvJ6KkA8b8q3lXiBg=")
        monkeypatch.setattr(settings, "youtube_client_id", "cid")
        monkeypatch.setattr(settings, "youtube_client_secret", "csecret")

        resp = client.get("/api/videos/upload/history?limit=500")
        assert resp.status_code == 400
        assert "limit" in resp.text.lower()

    def test_limit_zero_rejected(self, client, monkeypatch):
        monkeypatch.setattr(settings, "encryption_key", "QrNxsUUWeoIb1OnT5e_n7P9MbESvJ6KkA8b8q3lXiBg=")
        monkeypatch.setattr(settings, "youtube_client_id", "cid")
        monkeypatch.setattr(settings, "youtube_client_secret", "csecret")

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

    def _setup_creds(self, monkeypatch):
        monkeypatch.setattr(
            settings,
            "encryption_key",
            "QrNxsUUWeoIb1OnT5e_n7P9MbESvJ6KkA8b8q3lXiBg=",
        )
        monkeypatch.setattr(settings, "youtube_client_id", "cid")
        monkeypatch.setattr(settings, "youtube_client_secret", "csecret")

    def test_retry_requires_auth(self, client):
        resp = client.raw().post(
            "/api/videos/upload/00000000-0000-0000-0000-000000000000/retry"
        )
        assert resp.status_code in (401, 403)

    def test_retry_returns_404_for_missing_job(self, client, monkeypatch):
        self._setup_creds(monkeypatch)
        with patch(
            "app.services.upload_service.UploadService.retry_failed_job",
            side_effect=__import__(
                "app.services.upload_service", fromlist=["UploadServiceError"]
            ).UploadServiceError("job xyz not found"),
        ):
            resp = client.post(
                "/api/videos/upload/00000000-0000-0000-0000-000000000000/retry"
            )
        assert resp.status_code == 404
        assert "not found" in resp.text.lower()

    def test_retry_returns_409_for_non_failed_job(self, client, monkeypatch):
        self._setup_creds(monkeypatch)
        with patch(
            "app.services.upload_service.UploadService.retry_failed_job",
            side_effect=__import__(
                "app.services.upload_service", fromlist=["UploadServiceError"]
            ).UploadServiceError(
                "job xyz is in status='uploading'; retry only works on failed jobs."
            ),
        ):
            resp = client.post(
                "/api/videos/upload/00000000-0000-0000-0000-000000000000/retry"
            )
        assert resp.status_code == 409
        assert "failed" in resp.text.lower()
