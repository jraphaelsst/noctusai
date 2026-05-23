"""Drive write surface + docx publish orchestration.

The DriveV3Downloader write glue is exercised via an injected fake `service` +
`media_factory` (DI for the network/SDK boundary). The publish orchestration is
exercised via the in-memory FakeDriveDownloader — no network, no credentials.
"""
from pathlib import Path

import pytest

from app.integrations.google_drive.drive_v3_adapter import FOLDER_MIME, DriveV3Downloader
from app.integrations.google_drive.fake import FakeDriveDownloader
from app.services.drive_publish import (
    DOCX_MIME,
    ensure_child_folder,
    publish_docx_tree,
)


class _Exec:
    def __init__(self, val):
        self._val = val

    def execute(self):
        return self._val


class _RecordingFiles:
    """Minimal Drive `files()` double that records create() calls."""

    def __init__(self):
        self.created: list[dict] = []
        self.listed: list[str] = []

    def create(self, **kw):
        self.created.append(kw)
        body = kw["body"]
        return _Exec({"id": f"new-{len(self.created)}", "name": body["name"],
                      "mimeType": body.get("mimeType")})

    def list(self, **kw):
        self.listed.append(kw["q"])
        return _Exec({"files": [
            {"id": "kid", "name": "existing.docx", "mimeType": DOCX_MIME},
        ]})


class _RecordingService:
    def __init__(self, files):
        self._files = files

    def files(self):
        return self._files


@pytest.mark.asyncio
async def test_create_folder_calls_drive_create():
    files = _RecordingFiles()
    d = DriveV3Downloader(service=_RecordingService(files))

    df = await d.create_folder("docx", "PARENT")

    assert df.name == "docx"
    body = files.created[0]["body"]
    assert body["mimeType"] == FOLDER_MIME
    assert body["parents"] == ["PARENT"]
    assert files.created[0]["supportsAllDrives"] is True


@pytest.mark.asyncio
async def test_upload_file_uses_media_factory(tmp_path: Path):
    files = _RecordingFiles()
    seen = {}

    def fake_media(path: Path, mime: str | None):
        seen["path"], seen["mime"] = path, mime
        return "MEDIA"

    d = DriveV3Downloader(service=_RecordingService(files), media_factory=fake_media)
    doc = tmp_path / "x.docx"
    doc.write_bytes(b"PK\x03\x04")

    df = await d.upload_file(doc, "FOLDER", name="x.docx", mime_type=DOCX_MIME)

    assert df.name == "x.docx"
    assert seen == {"path": doc, "mime": DOCX_MIME}
    assert files.created[0]["media_body"] == "MEDIA"
    assert files.created[0]["body"]["parents"] == ["FOLDER"]


@pytest.mark.asyncio
async def test_list_children_returns_direct_children():
    files = _RecordingFiles()
    d = DriveV3Downloader(service=_RecordingService(files))

    kids = await d.list_children("PARENTfolder1")

    assert [k.name for k in kids] == ["existing.docx"]
    assert "'PARENTfolder1' in parents" in files.listed[0]


@pytest.mark.asyncio
async def test_ensure_child_folder_reuses_existing():
    fake = FakeDriveDownloader()
    existing = fake.add_folder("sum-id", "summaries", "ROOT")

    got = await ensure_child_folder(fake, "summaries", "ROOT")

    assert got.id == existing.id  # reused, not recreated


@pytest.mark.asyncio
async def test_ensure_child_folder_creates_when_missing():
    fake = FakeDriveDownloader()
    got = await ensure_child_folder(fake, "summaries", "ROOT")
    assert got.name == "summaries"
    assert [c.name for c in await fake.list_children("ROOT")] == ["summaries"]


@pytest.mark.asyncio
async def test_publish_docx_tree_uploads_and_is_idempotent(tmp_path: Path):
    # local: summaries/<module>/docx/*.docx
    root = tmp_path / "summaries"
    for module in ("1 Mod A", "2 Mod B"):
        d = root / module / "docx"
        d.mkdir(parents=True)
        (d / "aula 1.docx").write_bytes(b"PK\x03\x04")

    fake = FakeDriveDownloader()
    # Drive already has module "1 Mod A" (no docx yet); "2 Mod B" must be created.
    fake.add_folder("modA-id", "1 Mod A", "PARENT")

    first = await publish_docx_tree(fake, parent_id="PARENT", local_root=root)

    assert sorted((r.module, r.name) for r in first) == [
        ("1 Mod A", "aula 1.docx"),
        ("2 Mod B", "aula 1.docx"),
    ]
    assert all(not r.skipped for r in first)
    assert len(fake.uploads) == 2

    # second run: same files already present → all skipped, no new uploads.
    second = await publish_docx_tree(fake, parent_id="PARENT", local_root=root)
    assert all(r.skipped for r in second)
    assert len(fake.uploads) == 2  # unchanged


@pytest.mark.asyncio
async def test_publish_docx_tree_overwrite_reuploads(tmp_path: Path):
    root = tmp_path / "transcripts"
    d = root / "1 Mod A" / "docx"
    d.mkdir(parents=True)
    (d / "aula 1.docx").write_bytes(b"PK\x03\x04")

    fake = FakeDriveDownloader()
    await publish_docx_tree(fake, parent_id="PARENT", local_root=root)
    again = await publish_docx_tree(
        fake, parent_id="PARENT", local_root=root, overwrite=True
    )

    assert all(not r.skipped for r in again)
    assert len(fake.uploads) == 2  # uploaded twice
