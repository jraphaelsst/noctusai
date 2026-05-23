"""DriveV3Downloader — folder traversal, native-file skipping, pagination.

Network is faked via an injected `service` + `byte_fetcher` (DI for the external
boundary — never monkeypatching our own code).
"""
import re
from pathlib import Path

import pytest

from app.integrations.google_drive.drive_v3_adapter import (
    DriveV3Downloader,
    _to_drive_file,
)

FOLDER = "application/vnd.google-apps.folder"
DOC = "application/vnd.google-apps.document"


class _Exec:
    def __init__(self, val):
        self._val = val

    def execute(self):
        return self._val


class _FakeFiles:
    def __init__(self, pages: dict, metas: dict):
        self._pages = pages   # folder_id -> [page_dict, ...]
        self._metas = metas   # file_id   -> metadata dict

    def list(self, **kw):
        folder_id = re.search(r"'([^']+)' in parents", kw["q"]).group(1)
        pages = self._pages.get(folder_id, [{"files": []}])
        idx = int(kw["pageToken"]) if kw.get("pageToken") else 0
        page = dict(pages[idx])
        if idx + 1 < len(pages):
            page["nextPageToken"] = str(idx + 1)
        else:
            page.pop("nextPageToken", None)
        return _Exec(page)

    def get(self, **kw):
        return _Exec(self._metas[kw["fileId"]])


class _FakeService:
    def __init__(self, files):
        self._files = files

    def files(self):
        return self._files


def _downloader(pages: dict, metas: dict) -> DriveV3Downloader:
    service = _FakeService(_FakeFiles(pages, metas))
    return DriveV3Downloader(
        service=service,
        byte_fetcher=lambda file_id: f"bytes-{file_id}".encode(),
    )


@pytest.mark.asyncio
async def test_download_folder_recurses_and_skips_native(tmp_path: Path):
    pages = {
        "ROOTfolder1": [
            {"files": [
                {"id": "v1", "name": "aula-01.mp4", "mimeType": "video/mp4", "size": "10"},
                {"id": "SUBfolder12", "name": "modulo-2", "mimeType": FOLDER},
                {"id": "d1", "name": "notas", "mimeType": DOC},
            ]},
        ],
        "SUBfolder12": [
            {"files": [
                {"id": "v2", "name": "aula-02.mp4", "mimeType": "video/mp4", "size": "20"},
            ]},
        ],
    }
    d = _downloader(pages, {})
    out = await d.download_folder(
        "https://drive.google.com/drive/folders/ROOTfolder1", tmp_path
    )

    assert sorted(o.path.name for o in out) == ["aula-01.mp4", "aula-02.mp4"]
    assert (tmp_path / "aula-01.mp4").read_bytes() == b"bytes-v1"
    # subfolder structure preserved
    assert (tmp_path / "modulo-2" / "aula-02.mp4").read_bytes() == b"bytes-v2"
    # google-native doc skipped (can't get_media)
    assert not (tmp_path / "notas").exists()


@pytest.mark.asyncio
async def test_download_folder_paginates(tmp_path: Path):
    pages = {
        "ROOTfolder1": [
            {"files": [{"id": "v1", "name": "a1.mp4", "mimeType": "video/mp4", "size": "1"}]},
            {"files": [{"id": "v2", "name": "a2.mp4", "mimeType": "video/mp4", "size": "2"}]},
        ],
    }
    d = _downloader(pages, {})
    out = await d.download_folder(
        "https://drive.google.com/drive/folders/ROOTfolder1", tmp_path
    )
    assert sorted(o.path.name for o in out) == ["a1.mp4", "a2.mp4"]


@pytest.mark.asyncio
async def test_download_single_file(tmp_path: Path):
    metas = {
        "v1": {
            "id": "v1", "name": "x.mp4", "mimeType": "video/mp4",
            "size": "123", "md5Checksum": "abc",
        }
    }
    d = _downloader({}, metas)
    dest = tmp_path / "x.mp4"
    meta = await d.download("v1", dest)

    assert dest.read_bytes() == b"bytes-v1"
    assert meta.name == "x.mp4"
    assert meta.size_bytes == 123
    assert meta.md5_checksum == "abc"


@pytest.mark.asyncio
async def test_list_folder_recurses_without_downloading(tmp_path: Path):
    pages = {
        "ROOTfolder1": [
            {"files": [
                {"id": "v1", "name": "aula-01.mp4", "mimeType": "video/mp4", "size": "10"},
                {"id": "SUBfolder12", "name": "modulo-2", "mimeType": FOLDER},
            ]},
        ],
        "SUBfolder12": [
            {"files": [
                {"id": "v2", "name": "aula-02.mp4", "mimeType": "video/mp4", "size": "20"},
            ]},
        ],
    }
    d = _downloader(pages, {})
    files = await d.list_folder("https://drive.google.com/drive/folders/ROOTfolder1")

    assert sorted(f.name for f in files) == ["aula-01.mp4", "aula-02.mp4"]
    assert list(tmp_path.iterdir()) == []  # nothing downloaded


def test_to_drive_file_handles_missing_size():
    df = _to_drive_file({"id": "a", "name": "n", "mimeType": "video/mp4"})
    assert df.size_bytes is None
    assert df.mime_type == "video/mp4"
