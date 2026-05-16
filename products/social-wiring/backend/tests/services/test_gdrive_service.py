"""Tests for gdrive_service — pure-logic helpers + httpx-mocked download."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from app.services import gdrive_service
from app.services.gdrive_service import (
    DriveFileTooLarge,
    InvalidDriveURL,
    UnsupportedVideoFormat,
    download_from_drive,
    parse_file_id,
    validate_video_filename,
)


class TestParseFileId:
    def test_share_link_with_file_d_path(self):
        url = "https://drive.google.com/file/d/1aBcDeFgHiJkLmNoPqRsTu/view?usp=sharing"
        assert parse_file_id(url) == "1aBcDeFgHiJkLmNoPqRsTu"

    def test_open_url_with_id_query(self):
        url = "https://drive.google.com/open?id=1aBcDeFgHiJkLmNoPqRsTu"
        assert parse_file_id(url) == "1aBcDeFgHiJkLmNoPqRsTu"

    def test_uc_download_url(self):
        url = "https://drive.google.com/uc?export=download&id=1aBcDeFgHiJkLmNoPqRsTu"
        assert parse_file_id(url) == "1aBcDeFgHiJkLmNoPqRsTu"

    def test_path_overrides_query_when_both_present(self):
        # /file/d/{X} + ?id={Y} → path wins (more specific shape).
        url = "https://drive.google.com/file/d/PATHID1234567890ABCD/view?id=QUERYID9876543210WXYZ"
        assert parse_file_id(url) == "PATHID1234567890ABCD"

    def test_empty_url_raises(self):
        with pytest.raises(InvalidDriveURL):
            parse_file_id("")

    def test_unrecognised_url_raises(self):
        with pytest.raises(InvalidDriveURL):
            parse_file_id("https://drive.google.com/")

    def test_short_id_rejected(self):
        # Drive IDs are always ≥20 chars; anything shorter is suspicious.
        url = "https://drive.google.com/open?id=short"
        with pytest.raises(InvalidDriveURL):
            parse_file_id(url)


class TestValidateVideoFilename:
    @pytest.mark.parametrize("ext", [".mp4", ".mov", ".avi", ".mkv", ".webm"])
    def test_accepted_extensions_pass(self, ext):
        validate_video_filename(f"video{ext}")

    def test_uppercase_extension_normalised(self):
        validate_video_filename("VIDEO.MP4")  # should not raise

    def test_no_extension_rejected(self):
        with pytest.raises(UnsupportedVideoFormat):
            validate_video_filename("video")

    def test_unsupported_extension_rejected(self):
        with pytest.raises(UnsupportedVideoFormat):
            validate_video_filename("doc.pdf")


class TestDownloadFromDrive:
    """Exercises the httpx path with a mock transport — no real network."""

    def test_happy_path_writes_file(self, tmp_path):
        body = b"\x00\x01\x02" * 1024  # 3 KB of binary data

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={
                    "content-type": "video/mp4",
                    "content-length": str(len(body)),
                    "content-disposition": 'attachment; filename="my-video.mp4"',
                },
                content=body,
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))

        result = download_from_drive(
            drive_url="https://drive.google.com/file/d/1aBcDeFgHiJkLmNoPqRsTu/view",
            target_dir=tmp_path,
            httpx_client=client,
        )

        assert result.file_name == "my-video.mp4"
        assert result.file_size_bytes == len(body)
        assert result.local_path.exists()
        assert result.local_path.read_bytes() == body

    def test_oversize_rejected_via_content_length(self, tmp_path):
        max_bytes = 100

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={
                    "content-type": "video/mp4",
                    "content-length": str(max_bytes + 1),
                    "content-disposition": 'attachment; filename="huge.mp4"',
                },
                content=b"x" * (max_bytes + 1),
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))

        with pytest.raises(DriveFileTooLarge):
            download_from_drive(
                drive_url="https://drive.google.com/file/d/1aBcDeFgHiJkLmNoPqRsTu/view",
                target_dir=tmp_path,
                max_bytes=max_bytes,
                httpx_client=client,
            )

    def test_oversize_rejected_mid_stream_when_no_content_length(self, tmp_path):
        max_bytes = 50
        # Stream chunks to exceed cap without advertising via content-length.

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={
                    "content-type": "video/mp4",
                    "content-disposition": 'attachment; filename="sneaky.mp4"',
                },
                content=b"x" * (max_bytes + 50),
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))

        with pytest.raises(DriveFileTooLarge):
            download_from_drive(
                drive_url="https://drive.google.com/file/d/1aBcDeFgHiJkLmNoPqRsTu/view",
                target_dir=tmp_path,
                max_bytes=max_bytes,
                httpx_client=client,
            )
        # Partial file should be cleaned up.
        assert list(tmp_path.glob("sneaky*")) == []

    def test_invalid_url_rejected_before_http(self, tmp_path):
        client = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(500)))
        with pytest.raises(InvalidDriveURL):
            download_from_drive(
                drive_url="https://drive.google.com/",
                target_dir=tmp_path,
                httpx_client=client,
            )

    def test_unsupported_extension_rejected_before_write(self, tmp_path):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={
                    "content-type": "application/pdf",
                    "content-length": "10",
                    "content-disposition": 'attachment; filename="not-video.pdf"',
                },
                content=b"x" * 10,
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))

        with pytest.raises(UnsupportedVideoFormat):
            download_from_drive(
                drive_url="https://drive.google.com/file/d/1aBcDeFgHiJkLmNoPqRsTu/view",
                target_dir=tmp_path,
                httpx_client=client,
            )


class TestCleanup:
    def test_unlinks_existing_file(self, tmp_path: Path):
        target = tmp_path / "tmp.mp4"
        target.write_bytes(b"x")
        gdrive_service.cleanup(target)
        assert not target.exists()

    def test_silent_when_file_missing(self, tmp_path: Path):
        # Should not raise — best-effort.
        gdrive_service.cleanup(tmp_path / "ghost.mp4")
