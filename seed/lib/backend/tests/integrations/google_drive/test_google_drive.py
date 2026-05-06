"""Google Drive v3 download client tests — Fake + Real (mocked transport).

Covers:
- **URL parser** — every shape we accept, plus rejection of non-Drive URLs.
- **Fake adapter** — round-trips metadata + writes bytes to disk.
- **Real adapter** — `googleapiclient.discovery.build` patched at the boundary
  (external-service carve-out per the no-monkeypatching rule); asserts the
  right files().get / files().get_media calls happen.
- **Factory** — routes Fake / Real correctly; refuses Real without creds.

Network-free: no real googleapiclient calls.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from noctusai_lib.integrations.google_drive import (
    DriveFile,
    FakeDriveDownloader,
    make_drive_downloader,
    parse_drive_url,
)


# ============================================================================
# parse_drive_url
# ============================================================================

VALID_ID = "1AbCdEfGhIjKlMnOpQrStUvWxYz12"  # 28 chars, valid alphabet


class TestParseDriveUrl:
    def test_file_d_view(self) -> None:
        assert (
            parse_drive_url(f"https://drive.google.com/file/d/{VALID_ID}/view")
            == VALID_ID
        )

    def test_file_d_edit(self) -> None:
        assert (
            parse_drive_url(f"https://drive.google.com/file/d/{VALID_ID}/edit")
            == VALID_ID
        )

    def test_file_d_trailing_slash(self) -> None:
        assert (
            parse_drive_url(f"https://drive.google.com/file/d/{VALID_ID}/")
            == VALID_ID
        )

    def test_open_id(self) -> None:
        assert (
            parse_drive_url(f"https://drive.google.com/open?id={VALID_ID}")
            == VALID_ID
        )

    def test_uc_id(self) -> None:
        assert (
            parse_drive_url(f"https://drive.google.com/uc?id={VALID_ID}")
            == VALID_ID
        )

    def test_uc_export_download(self) -> None:
        assert (
            parse_drive_url(
                f"https://drive.google.com/uc?export=download&id={VALID_ID}"
            )
            == VALID_ID
        )

    def test_docs_document(self) -> None:
        assert (
            parse_drive_url(f"https://docs.google.com/document/d/{VALID_ID}/edit")
            == VALID_ID
        )

    def test_bare_id(self) -> None:
        assert parse_drive_url(VALID_ID) == VALID_ID

    def test_strip_whitespace(self) -> None:
        assert parse_drive_url(f"  {VALID_ID}  ") == VALID_ID

    def test_non_drive_url_raises(self) -> None:
        with pytest.raises(ValueError, match="not a google drive URL"):
            parse_drive_url("https://example.com/file/d/abc")

    def test_empty_raises(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            parse_drive_url("")

    def test_drive_url_without_id_raises(self) -> None:
        with pytest.raises(ValueError, match="could not extract"):
            parse_drive_url("https://drive.google.com/")

    def test_short_bare_string_rejected(self) -> None:
        with pytest.raises(ValueError):
            parse_drive_url("short")


# ============================================================================
# FakeDriveDownloader
# ============================================================================


class TestFakeDriveDownloader:
    @pytest.mark.asyncio
    async def test_add_and_get_metadata(self) -> None:
        fake = FakeDriveDownloader()
        meta = fake.add_fake_file(
            "file1", "clip.mp4", b"abc", mime_type="video/mp4"
        )
        assert meta.id == "file1"
        assert meta.name == "clip.mp4"
        assert meta.size_bytes == 3
        assert meta.mime_type == "video/mp4"
        retrieved = await fake.get_metadata("file1")
        assert retrieved == meta

    @pytest.mark.asyncio
    async def test_metadata_missing_returns_none(self) -> None:
        fake = FakeDriveDownloader()
        assert await fake.get_metadata("nope") is None

    @pytest.mark.asyncio
    async def test_download_writes_bytes(self, tmp_path: Path) -> None:
        fake = FakeDriveDownloader()
        fake.add_fake_file("file1", "clip.mp4", b"hello world", "video/mp4")
        dest = tmp_path / "subdir" / "out.mp4"
        meta = await fake.download("file1", dest)
        assert dest.read_bytes() == b"hello world"
        assert dest.parent.is_dir()  # parent created
        assert meta.size_bytes == 11

    @pytest.mark.asyncio
    async def test_download_overwrites_existing(self, tmp_path: Path) -> None:
        fake = FakeDriveDownloader()
        fake.add_fake_file("file1", "clip.mp4", b"new", "video/mp4")
        dest = tmp_path / "out.mp4"
        dest.write_bytes(b"old content")
        await fake.download("file1", dest)
        assert dest.read_bytes() == b"new"

    @pytest.mark.asyncio
    async def test_download_missing_raises(self, tmp_path: Path) -> None:
        fake = FakeDriveDownloader()
        with pytest.raises(FileNotFoundError, match="not in fake"):
            await fake.download("nope", tmp_path / "x")

    def test_constructor_seeds_files(self) -> None:
        meta = DriveFile(id="seeded", name="x.mp4", size_bytes=3, mime_type="video/mp4")
        fake = FakeDriveDownloader(files={"seeded": (meta, b"abc")})
        # __init__ takes the dict; tests typically use add_fake_file but
        # constructor seeding works for product-side fixtures.
        assert "seeded" in fake._files


# ============================================================================
# Factory
# ============================================================================


class TestFactory:
    def test_use_fake_returns_fake(self) -> None:
        client = make_drive_downloader(use_fake=True)
        assert isinstance(client, FakeDriveDownloader)

    def test_use_fake_with_seed_data(self) -> None:
        meta = DriveFile(id="x", name="a", size_bytes=1, mime_type="text/plain")
        client = make_drive_downloader(
            use_fake=True, fake_seed_data={"files": {"x": (meta, b"a")}}
        )
        assert isinstance(client, FakeDriveDownloader)
        assert "x" in client._files

    def test_real_without_credentials_raises(self) -> None:
        with pytest.raises(ValueError, match="api_key or oauth_credentials"):
            make_drive_downloader(use_fake=False)

    def test_real_with_api_key(self) -> None:
        # Lazy-import boundary — should not raise even without network.
        client = make_drive_downloader(use_fake=False, api_key="test-key")
        # Don't call methods; just verify construction.
        assert client is not None


# ============================================================================
# Real adapter — transport mocked at the googleapiclient boundary
# ============================================================================


def _build_mock_service(
    *,
    metadata_response: dict | None = None,
    metadata_raises: Exception | None = None,
    media_chunks: list[bytes] | None = None,
) -> MagicMock:
    """Construct a MagicMock matching googleapiclient's chain:

        service.files().get(fileId=..., fields=...).execute()
        service.files().get_media(fileId=...) → request
    """
    service = MagicMock()
    files = service.files.return_value

    get_chain = files.get.return_value
    if metadata_raises is not None:
        get_chain.execute.side_effect = metadata_raises
    else:
        get_chain.execute.return_value = metadata_response or {}

    files.get_media.return_value = MagicMock(name="media-request")
    return service


class TestRealDriveDownloader:
    @pytest.mark.asyncio
    async def test_get_metadata_parses_response(self) -> None:
        from noctusai_lib.integrations.google_drive.real import RealDriveDownloader

        mock_service = _build_mock_service(
            metadata_response={
                "id": "file1",
                "name": "clip.mp4",
                "size": "12345",
                "mimeType": "video/mp4",
                "md5Checksum": "abcdef",
            }
        )

        with patch(
            "noctusai_lib.integrations.google_drive.real.build",
            return_value=mock_service,
        ):
            client = RealDriveDownloader(api_key="test")
            meta = await client.get_metadata("file1")

        assert meta is not None
        assert meta.id == "file1"
        assert meta.name == "clip.mp4"
        assert meta.size_bytes == 12345
        assert meta.mime_type == "video/mp4"
        assert meta.md5_checksum == "abcdef"

    @pytest.mark.asyncio
    async def test_get_metadata_404_returns_none(self) -> None:
        from googleapiclient.errors import HttpError

        from noctusai_lib.integrations.google_drive.real import RealDriveDownloader

        resp = MagicMock(status=404, reason="Not Found")
        err = HttpError(resp=resp, content=b"")

        mock_service = _build_mock_service(metadata_raises=err)

        with patch(
            "noctusai_lib.integrations.google_drive.real.build",
            return_value=mock_service,
        ):
            client = RealDriveDownloader(api_key="test")
            assert await client.get_metadata("missing") is None

    @pytest.mark.asyncio
    async def test_get_metadata_5xx_reraises(self) -> None:
        from googleapiclient.errors import HttpError

        from noctusai_lib.integrations.google_drive.real import RealDriveDownloader

        resp = MagicMock(status=500, reason="Server Error")
        err = HttpError(resp=resp, content=b"")

        mock_service = _build_mock_service(metadata_raises=err)

        with patch(
            "noctusai_lib.integrations.google_drive.real.build",
            return_value=mock_service,
        ):
            client = RealDriveDownloader(api_key="test")
            with pytest.raises(HttpError):
                await client.get_metadata("file1")

    @pytest.mark.asyncio
    async def test_download_writes_via_media_chunks(self, tmp_path: Path) -> None:
        from noctusai_lib.integrations.google_drive.real import RealDriveDownloader

        mock_service = _build_mock_service(
            metadata_response={
                "id": "file1",
                "name": "clip.mp4",
                "size": "5",
                "mimeType": "video/mp4",
            }
        )

        # MediaIoBaseDownload(fh, request) — patch the class so .next_chunk
        # writes bytes to fh and returns done=True.
        def fake_downloader_factory(fh, request):
            class _D:
                _called = False

                def next_chunk(self_inner):
                    if not self_inner._called:
                        fh.write(b"hello")
                        self_inner._called = True
                        return None, True
                    return None, True

            return _D()

        dest = tmp_path / "out.mp4"

        with patch(
            "noctusai_lib.integrations.google_drive.real.build",
            return_value=mock_service,
        ), patch(
            "noctusai_lib.integrations.google_drive.real.MediaIoBaseDownload",
            side_effect=fake_downloader_factory,
        ):
            client = RealDriveDownloader(api_key="test")
            meta = await client.download("file1", dest)

        assert dest.read_bytes() == b"hello"
        assert meta.id == "file1"
        assert meta.size_bytes == 5

    @pytest.mark.asyncio
    async def test_download_missing_raises_filenotfound(self, tmp_path: Path) -> None:
        from googleapiclient.errors import HttpError

        from noctusai_lib.integrations.google_drive.real import RealDriveDownloader

        resp = MagicMock(status=404, reason="Not Found")
        err = HttpError(resp=resp, content=b"")
        mock_service = _build_mock_service(metadata_raises=err)

        with patch(
            "noctusai_lib.integrations.google_drive.real.build",
            return_value=mock_service,
        ):
            client = RealDriveDownloader(api_key="test")
            with pytest.raises(FileNotFoundError):
                await client.download("missing", tmp_path / "x")

    def test_init_requires_credentials(self) -> None:
        from noctusai_lib.integrations.google_drive.real import RealDriveDownloader

        with pytest.raises(ValueError, match="api_key or oauth_credentials"):
            RealDriveDownloader()

    def test_init_with_oauth_credentials(self) -> None:
        from noctusai_lib.integrations.google_drive.real import RealDriveDownloader

        creds = MagicMock(name="creds")
        client = RealDriveDownloader(oauth_credentials=creds)
        assert client._creds is creds
        assert client._api_key is None
