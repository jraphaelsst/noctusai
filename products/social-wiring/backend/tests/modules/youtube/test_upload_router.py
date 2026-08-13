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

import asyncio
import json
from uuid import uuid4

import pytest

from noctusai_lib.domain.real_estate import Imovel

from app.services.imoveis_service import _imovel_to_row

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


class TestUploadFromCodeValidation:
    """POST /api/videos/upload/from-code — the simplified "file + code only"
    browser upload. Server resolves metadata from `social_wiring.imoveis`
    (local mirror, never a live Vista call — roadmap
    `social-wiring-imoveis-vista-2026-08`, P2.5), so the boundary cases are:
    bad code format (422) + no property in the local catalog (404). Both
    fail BEFORE the file is staged, so no service/pipeline mock is needed."""

    _FILE = {"file": ("v.mp4", b"data", "video/mp4")}

    def test_requires_auth(self, client):
        resp = client.raw().post(
            "/api/videos/upload/from-code",
            files=self._FILE,
            data={"product_code": "ONE0000"},
        )
        assert resp.status_code in (401, 403)

    def test_invalid_code_returns_422(self, client, override_settings):
        override_settings(**_COMPLETE_CREDS)
        resp = client.post(
            "/api/videos/upload/from-code",
            files=self._FILE,
            data={"product_code": "BADCODE"},
        )
        assert resp.status_code == 422
        assert "product_code" in resp.text.lower()

    def test_code_not_in_local_catalog_returns_404_actionable(self, client, override_settings):
        """A miss fails loudly with an actionable message — the code + 'local
        catalog' in the body — never a generic 500 and never a silent retry
        against Vista. No seeding needed: the mock admin client starts with
        an empty `imoveis` table, which is exactly a clean miss."""
        override_settings(**_COMPLETE_CREDS)
        resp = client.post(
            "/api/videos/upload/from-code",
            files=self._FILE,
            data={"product_code": "ONE0000"},
        )
        assert resp.status_code == 404
        assert "ONE0000" in resp.text
        assert "local catalog" in resp.text.lower()

    def test_non_one_prefixed_code_also_returns_404_when_absent(self, client, override_settings):
        """`CA0190`-shaped codes (non-ONE prefix, 285/1919 of the live
        catalog) must validate + resolve through the same path as an ONE
        code — asserting this against the *widened* `validate_product_code`
        regex, not a narrower ONE-only pattern."""
        override_settings(**_COMPLETE_CREDS)
        resp = client.post(
            "/api/videos/upload/from-code",
            files=self._FILE,
            data={"product_code": "CA0190"},
        )
        # Not 422 — the code format is valid; 404 because the local mock
        # catalog is empty in this test (a real hit is covered at the
        # `_resolve_metadata_from_product_code` unit level below).
        assert resp.status_code == 404
        assert "CA0190" in resp.text


class _FakeReadTable:
    def __init__(self, rows: list[dict]):
        self._rows = rows
        self._filters: dict = {}

    def select(self, *_a, **_kw):
        return self

    def eq(self, col, value):
        self._filters[col] = value
        return self

    def limit(self, *_a, **_kw):
        return self

    def execute(self):
        matched = [
            r for r in self._rows
            if all(r.get(k) == v for k, v in self._filters.items())
        ]

        class _Resp:
            data = matched

        return _Resp()


class _FakeReadClient:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def schema(self, _name):
        return self

    def table(self, _name):
        return _FakeReadTable(self._rows)


class TestResolveMetadataFromProductCode:
    """Unit-level coverage of `_resolve_metadata_from_product_code` — the
    youtube-dashboard product-code resolver both `/upload/from-code` and
    `/drive-folder` share. Bypasses HTTP/DI plumbing (staging, credential
    vault, YouTube service) that the full pipeline needs but this resolver
    doesn't touch."""

    ORG = uuid4()

    @staticmethod
    def _row(codigo: str, **kw) -> dict:
        imovel = Imovel(codigo=codigo, **kw)
        return _imovel_to_row(imovel, TestResolveMetadataFromProductCode.ORG, "2026-08-03T23:50:31Z")

    def test_hit_builds_metadata_from_the_local_row(self, monkeypatch):
        from app.modules.youtube.routers import upload as upload_mod

        row = self._row("ONE10640", titulo="Apartamento 3 quartos — Moema")
        monkeypatch.setattr(
            upload_mod, "get_admin_client", lambda: _FakeReadClient([row])
        )

        metadata = asyncio.run(
            upload_mod._resolve_metadata_from_product_code(
                product_code="one10640",
                privacy_status="private",
                org_id=self.ORG,
            )
        )

        assert metadata.product_code == "ONE10640"
        assert "ONE10640" in metadata.title
        assert "Apartamento 3 quartos — Moema" in metadata.title

    def test_hit_on_a_non_one_prefixed_code(self, monkeypatch):
        """`CA0190` — a real live code outside the ONE prefix."""
        from app.modules.youtube.routers import upload as upload_mod

        row = self._row("CA0190", titulo="Casa com piscina")
        monkeypatch.setattr(
            upload_mod, "get_admin_client", lambda: _FakeReadClient([row])
        )

        metadata = asyncio.run(
            upload_mod._resolve_metadata_from_product_code(
                product_code="CA0190",
                privacy_status="private",
                org_id=self.ORG,
            )
        )

        assert metadata.product_code == "CA0190"
        assert "CA0190" in metadata.title

    def test_miss_raises_404_with_actionable_detail(self, monkeypatch):
        from fastapi import HTTPException

        from app.modules.youtube.routers import upload as upload_mod

        monkeypatch.setattr(
            upload_mod, "get_admin_client", lambda: _FakeReadClient([])
        )

        with pytest.raises(HTTPException) as exc_info:
            asyncio.run(
                upload_mod._resolve_metadata_from_product_code(
                    product_code="ONE99999",
                    privacy_status="private",
                    org_id=self.ORG,
                )
            )

        assert exc_info.value.status_code == 404
        assert "ONE99999" in exc_info.value.detail
        assert "local catalog" in exc_info.value.detail.lower()
