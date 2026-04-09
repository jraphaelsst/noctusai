"""
Unit tests for storage_service — file validation, upload, delete, signed URLs,
bucket management, dry-run mode.
"""
import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

class TestConstants:

    def test_buckets_defined(self):
        from app.services.storage_service import BUCKETS
        assert "certidoes" in BUCKETS
        assert "geral" in BUCKETS

    def test_allowed_types_defined(self):
        from app.services.storage_service import ALLOWED_TYPES
        assert "application/pdf" in ALLOWED_TYPES["certidoes"]
        assert "image/jpeg" in ALLOWED_TYPES["geral"]

    def test_max_file_size(self):
        from app.services.storage_service import MAX_FILE_SIZE
        assert MAX_FILE_SIZE == 10 * 1024 * 1024


# ---------------------------------------------------------------------------
# validate_file
# ---------------------------------------------------------------------------

class TestValidateFile:

    def _make_svc(self):
        mock_client = MagicMock()
        mock_client.storage.list_buckets.side_effect = Exception("not available")
        from app.services.storage_service import StorageService
        return StorageService(mock_client, "org-1")

    def test_valid_image(self):
        svc = self._make_svc()
        err = svc.validate_file("foto.jpg", "image/jpeg", 1024, "geral")
        assert err is None

    def test_invalid_content_type(self):
        svc = self._make_svc()
        err = svc.validate_file("script.sh", "application/x-sh", 100, "geral")
        assert err is not None
        assert "não permitido" in err

    def test_file_too_large(self):
        svc = self._make_svc()
        err = svc.validate_file("big.jpg", "image/jpeg", 20 * 1024 * 1024, "geral")
        assert err is not None
        assert "muito grande" in err

    def test_valid_pdf_for_certidoes(self):
        svc = self._make_svc()
        err = svc.validate_file("doc.pdf", "application/pdf", 5000, "certidoes")
        assert err is None

    def test_invalid_exe_for_certidoes(self):
        svc = self._make_svc()
        err = svc.validate_file("malware.exe", "application/x-msdownload", 5000, "certidoes")
        assert err is not None

    def test_unknown_categoria_uses_geral(self):
        svc = self._make_svc()
        # PDF is allowed in geral
        err = svc.validate_file("doc.pdf", "application/pdf", 5000, "unknown_cat")
        assert err is None


# ---------------------------------------------------------------------------
# _get_bucket / _generate_path
# ---------------------------------------------------------------------------

class TestBucketAndPath:

    def _make_svc(self):
        mock_client = MagicMock()
        mock_client.storage.list_buckets.side_effect = Exception("not available")
        from app.services.storage_service import StorageService
        return StorageService(mock_client, "org-test")

    def test_known_bucket(self):
        svc = self._make_svc()
        assert svc._get_bucket("certidoes") == "erp-certidoes"
        assert svc._get_bucket("geral") == "erp-geral"

    def test_unknown_bucket_fallback(self):
        svc = self._make_svc()
        assert svc._get_bucket("xpto") == "erp-geral"

    def test_generate_path_format(self):
        svc = self._make_svc()
        path = svc._generate_path("geral", "photo.jpg")
        # Should be org_id/uuid.ext
        assert path.startswith("org-test/")
        assert path.endswith(".jpg")

    def test_generate_path_no_extension(self):
        svc = self._make_svc()
        path = svc._generate_path("geral", "noext")
        assert path.endswith(".bin")


# ---------------------------------------------------------------------------
# upload — dry-run mode
# ---------------------------------------------------------------------------

class TestUploadDryRun:

    @pytest.mark.asyncio
    async def test_dry_run_upload(self):
        mock_client = MagicMock()
        mock_client.storage.list_buckets.side_effect = Exception("not available")

        from app.services.storage_service import StorageService
        svc = StorageService(mock_client, "org-1")

        result = await svc.upload(b"fake-content", "photo.jpg", "image/jpeg", "geral")

        assert result["dry_run"] is True
        assert "mock.noctus.app" in result["url"]
        assert result["bucket"] == "erp-geral"
        assert result["size"] == len(b"fake-content")
        assert result["content_type"] == "image/jpeg"

    @pytest.mark.asyncio
    async def test_dry_run_upload_multiple(self):
        mock_client = MagicMock()
        mock_client.storage.list_buckets.side_effect = Exception("not available")

        from app.services.storage_service import StorageService
        svc = StorageService(mock_client, "org-1")

        files = [
            (b"img1", "a.jpg", "image/jpeg"),
            (b"img2", "b.png", "image/png"),
        ]
        results = await svc.upload_multiple(files, "geral")

        assert len(results) == 2
        assert all(r["dry_run"] for r in results)


# ---------------------------------------------------------------------------
# upload — real storage
# ---------------------------------------------------------------------------

class TestUploadReal:

    @pytest.mark.asyncio
    async def test_real_upload_returns_url(self):
        mock_client = MagicMock()
        mock_client.storage.list_buckets.return_value = []  # storage available
        mock_bucket = MagicMock()
        mock_bucket.upload.return_value = None
        mock_bucket.get_public_url.return_value = "https://storage.real/org-1/photo.jpg"
        mock_client.storage.from_.return_value = mock_bucket

        from app.services.storage_service import StorageService
        svc = StorageService(mock_client, "org-1")

        result = await svc.upload(b"data", "photo.jpg", "image/jpeg", "geral")

        assert result["dry_run"] is False
        assert result["url"] == "https://storage.real/org-1/photo.jpg"
        mock_bucket.upload.assert_called_once()

    @pytest.mark.asyncio
    async def test_upload_exception_propagates(self):
        mock_client = MagicMock()
        mock_client.storage.list_buckets.return_value = []
        mock_bucket = MagicMock()
        mock_bucket.upload.side_effect = RuntimeError("upload failed")
        mock_client.storage.from_.return_value = mock_bucket

        from app.services.storage_service import StorageService
        svc = StorageService(mock_client, "org-1")

        with pytest.raises(RuntimeError, match="upload failed"):
            await svc.upload(b"data", "photo.jpg", "image/jpeg", "geral")


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------

class TestDelete:

    @pytest.mark.asyncio
    async def test_dry_run_delete(self):
        mock_client = MagicMock()
        mock_client.storage.list_buckets.side_effect = Exception("not available")

        from app.services.storage_service import StorageService
        svc = StorageService(mock_client, "org-1")

        result = await svc.delete("org-1/imoveis/abc.jpg", "geral")
        assert result is True

    @pytest.mark.asyncio
    async def test_real_delete(self):
        mock_client = MagicMock()
        mock_client.storage.list_buckets.return_value = []
        mock_bucket = MagicMock()
        mock_bucket.remove.return_value = None
        mock_client.storage.from_.return_value = mock_bucket

        from app.services.storage_service import StorageService
        svc = StorageService(mock_client, "org-1")

        result = await svc.delete("org-1/imoveis/abc.jpg", "geral")
        assert result is True
        mock_bucket.remove.assert_called_once_with(["org-1/imoveis/abc.jpg"])

    @pytest.mark.asyncio
    async def test_delete_failure_returns_false(self):
        mock_client = MagicMock()
        mock_client.storage.list_buckets.return_value = []
        mock_bucket = MagicMock()
        mock_bucket.remove.side_effect = RuntimeError("delete error")
        mock_client.storage.from_.return_value = mock_bucket

        from app.services.storage_service import StorageService
        svc = StorageService(mock_client, "org-1")

        result = await svc.delete("org-1/imoveis/abc.jpg", "geral")
        assert result is False


# ---------------------------------------------------------------------------
# get_signed_url
# ---------------------------------------------------------------------------

class TestGetSignedUrl:

    def test_dry_run_signed_url(self):
        mock_client = MagicMock()
        mock_client.storage.list_buckets.side_effect = Exception("not available")

        from app.services.storage_service import StorageService
        svc = StorageService(mock_client, "org-1")

        url = svc.get_signed_url("org-1/docs/file.pdf", "certidoes")
        assert url is not None
        assert "mock.noctus.app" in url
        assert "mock-signed" in url

    def test_real_signed_url(self):
        mock_client = MagicMock()
        mock_client.storage.list_buckets.return_value = []
        mock_bucket = MagicMock()
        mock_bucket.create_signed_url.return_value = {
            "signedURL": "https://storage.real/signed/abc?token=xyz"
        }
        mock_client.storage.from_.return_value = mock_bucket

        from app.services.storage_service import StorageService
        svc = StorageService(mock_client, "org-1")

        url = svc.get_signed_url("org-1/docs/file.pdf", "certidoes", expires_in=7200)
        assert url == "https://storage.real/signed/abc?token=xyz"
        mock_bucket.create_signed_url.assert_called_once_with("org-1/docs/file.pdf", 7200)

    def test_signed_url_exception_returns_none(self):
        mock_client = MagicMock()
        mock_client.storage.list_buckets.return_value = []
        mock_bucket = MagicMock()
        mock_bucket.create_signed_url.side_effect = RuntimeError("fail")
        mock_client.storage.from_.return_value = mock_bucket

        from app.services.storage_service import StorageService
        svc = StorageService(mock_client, "org-1")

        url = svc.get_signed_url("org-1/docs/file.pdf", "certidoes")
        assert url is None
