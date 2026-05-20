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


# ─── iter_drive_folder_videos — Phase 1 of youtube-drive-folder-fanout ──

class TestIterDriveFolderVideos:
    """Tests for the multi-video Drive-folder enumerator.

    Strategy: monkeypatch ``gdown.download_folder`` to simulate disk
    layouts (gdown is an external library — patching it is allowed per
    ``KB § PATTERNS/testing.md § external-boundary-only patches``). The
    fake materialises the requested files on disk inside ``tmp_path`` so
    the function's downstream walk + classify + size logic sees a real
    filesystem, exactly as it would in production.
    """

    _FOLDER_URL = "https://drive.google.com/drive/folders/1abc23DEF456ghi789JKL012mno345PQ"

    @staticmethod
    def _install_fake_gdown(
        monkeypatch,
        files_to_create: list[tuple[str, bytes]] | None = None,
        *,
        raises: Exception | None = None,
    ):
        """Install a fake ``gdown`` module in ``sys.modules`` so the
        production code's lazy ``import gdown`` picks it up. Materialises
        ``files_to_create`` under ``output/drive-folder-root/...`` (the
        same shape ``gdown.download_folder`` produces in production) and
        returns the resulting paths. ``raises`` short-circuits with an
        error to exercise the ``GoogleDriveError`` wrapping branch.

        Allowed-shape monkeypatch: ``gdown`` is an external library, not
        our own code (per ``KB § PATTERNS/testing.md`` external-boundary
        rule)."""
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

    def test_flat_folder_two_videos(self, monkeypatch, tmp_path):
        """Folder w/ two top-level videos → two refs, parent_subfolder=None."""
        self._install_fake_gdown(monkeypatch, [
            ("horizontal.mp4", b"x" * 100),
            ("vertical.mp4", b"y" * 200),
        ])

        refs = gdrive_service.iter_drive_folder_videos(
            folder_url=self._FOLDER_URL,
            target_dir=tmp_path,
        )

        assert len(refs) == 2
        names = sorted(r.file_name for r in refs)
        assert names == ["horizontal.mp4", "vertical.mp4"]
        for r in refs:
            assert r.parent_subfolder is None
            assert r.local_path.exists()
            assert r.file_size_bytes > 0

    def test_subfolder_one_level(self, monkeypatch, tmp_path):
        """One subfolder → ref's parent_subfolder is the subfolder name."""
        self._install_fake_gdown(monkeypatch, [
            ("Episode 3/clip.mp4", b"x" * 50),
        ])

        refs = gdrive_service.iter_drive_folder_videos(
            folder_url=self._FOLDER_URL,
            target_dir=tmp_path,
        )

        assert len(refs) == 1
        assert refs[0].file_name == "clip.mp4"
        assert refs[0].parent_subfolder == "Episode 3"

    def test_mixed_root_and_subfolder(self, monkeypatch, tmp_path):
        """Root file + subfolder file both surface; parent labels differ."""
        self._install_fake_gdown(monkeypatch, [
            ("master.mp4", b"x" * 10),
            ("Shorts/cut.mp4", b"y" * 10),
        ])

        refs = gdrive_service.iter_drive_folder_videos(
            folder_url=self._FOLDER_URL,
            target_dir=tmp_path,
        )

        assert len(refs) == 2
        by_name = {r.file_name: r for r in refs}
        assert by_name["master.mp4"].parent_subfolder is None
        assert by_name["cut.mp4"].parent_subfolder == "Shorts"

    def test_non_video_files_silently_skipped(self, monkeypatch, tmp_path):
        """README/thumbnail bystanders are ignored, videos kept."""
        self._install_fake_gdown(monkeypatch, [
            ("video.mp4", b"x" * 10),
            ("README.txt", b"hi"),
            ("thumb.png", b"\x89PNG"),
        ])

        refs = gdrive_service.iter_drive_folder_videos(
            folder_url=self._FOLDER_URL,
            target_dir=tmp_path,
        )

        assert [r.file_name for r in refs] == ["video.mp4"]

    def test_empty_folder_raises(self, monkeypatch, tmp_path):
        """gdown returning [] → GoogleDriveError (permission hint)."""
        self._install_fake_gdown(monkeypatch, [])  # no files

        with pytest.raises(gdrive_service.GoogleDriveError, match="no files"):
            gdrive_service.iter_drive_folder_videos(
                folder_url=self._FOLDER_URL,
                target_dir=tmp_path,
            )

    def test_folder_with_only_non_videos_raises(self, monkeypatch, tmp_path):
        """Folder downloaded but no accepted videos → GoogleDriveError."""
        self._install_fake_gdown(monkeypatch, [
            ("README.txt", b"hi"),
            ("notes.docx", b"\x00"),
        ])

        with pytest.raises(gdrive_service.GoogleDriveError, match="No accepted video"):
            gdrive_service.iter_drive_folder_videos(
                folder_url=self._FOLDER_URL,
                target_dir=tmp_path,
            )

    def test_depth_two_subfolder_is_pruned(self, monkeypatch, tmp_path):
        """File two subfolders deep is dropped + cleaned up per the
        one-level recursion contract."""
        self._install_fake_gdown(monkeypatch, [
            ("root.mp4", b"x" * 10),
            ("Sub1/Sub2/deep.mp4", b"x" * 10),
        ])

        refs = gdrive_service.iter_drive_folder_videos(
            folder_url=self._FOLDER_URL,
            target_dir=tmp_path,
        )

        names = sorted(r.file_name for r in refs)
        assert names == ["root.mp4"]
        # And the pruned file was actually deleted (not just skipped).
        deep = tmp_path / "drive-folder-root" / "Sub1" / "Sub2" / "deep.mp4"
        assert not deep.exists()

    def test_oversized_file_dropped(self, monkeypatch, tmp_path):
        """A video exceeding max_bytes is dropped + cleaned up; others kept."""
        self._install_fake_gdown(monkeypatch, [
            ("small.mp4", b"x" * 10),
            ("huge.mp4", b"x" * 5000),
        ])

        refs = gdrive_service.iter_drive_folder_videos(
            folder_url=self._FOLDER_URL,
            target_dir=tmp_path,
            max_bytes=100,
        )

        assert [r.file_name for r in refs] == ["small.mp4"]
        huge = tmp_path / "drive-folder-root" / "huge.mp4"
        assert not huge.exists()

    def test_invalid_folder_url_raises(self, tmp_path):
        """Bad URL → InvalidDriveURL BEFORE gdown is touched."""
        with pytest.raises(gdrive_service.InvalidDriveURL):
            gdrive_service.iter_drive_folder_videos(
                folder_url="https://drive.google.com/",
                target_dir=tmp_path,
            )

    def test_gdown_failure_wrapped(self, monkeypatch, tmp_path):
        """gdown raising any error → GoogleDriveError with folder_id."""
        self._install_fake_gdown(
            monkeypatch, raises=RuntimeError("network unreachable")
        )

        with pytest.raises(gdrive_service.GoogleDriveError, match="folder download failed"):
            gdrive_service.iter_drive_folder_videos(
                folder_url=self._FOLDER_URL,
                target_dir=tmp_path,
            )
