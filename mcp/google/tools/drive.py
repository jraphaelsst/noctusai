"""google.drive.* tools — thin wrappers over the seed Drive downloader.

Tools registered:
- google.drive.parse_url     — READ/pure. Extract a file id from a share URL.
- google.drive.get_metadata  — READ. Size / mime / md5 (None ⇒ missing OR inaccessible).
- google.drive.download      — READ. Stream bytes to a local path.

LIB GAP — drive READER surface absent. The brief specified
`google.drive.search` + `google.drive.read_file` via `make_drive_reader`
(+ `compute_content_stats` to defend the LLM-recount trap) and
`FakeDriveReader`. Verified 2026-05-17 against
`noctusai_lib.integrations.google_drive` (`__init__`, every module): the
package ships ONLY the *downloader* surface — `make_drive_downloader`,
`FakeDriveDownloader`, `parse_drive_url`, `DriveFile`, and the
`DriveDownloader` Protocol whose own docstring says list/read are
"explicitly out of scope until the second consumer arrives". There is
no `make_drive_reader` / `FakeDriveReader` / `DriveReader` /
`compute_content_stats` / `read_file` / `search` anywhere in the lib.

Per verify-the-seed-ships-it + no-connector-logic-in-mcp: search /
read_file are NOT registered here (registering them would force a
connector-side reader fork — wrong layer). The gap is surfaced loudly in
findings + README as a Wave-3 seed-lib follow-up. The three downloader
tools below are real and complete against the shipped Fake+Real surface.
"""
from __future__ import annotations

import logging
from pathlib import Path

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.google_drive import (
    make_drive_downloader,
    parse_drive_url,
)

from _kit.errors import typed_error

from settings import get_settings
from schemas import (
    DownloadInput,
    DownloadOutput,
    DriveFileModel,
    GetMetadataInput,
    GetMetadataOutput,
    ParseUrlInput,
    ParseUrlOutput,
)

logger = logging.getLogger(__name__)


def _downloader_and_kind():
    """Real downloader when an API key is configured (works for
    anyone-with-link public files), else the in-memory Fake."""
    s = get_settings()
    if s.api_key:
        return make_drive_downloader(api_key=s.api_key), "real"
    return make_drive_downloader(use_fake=True), "fake"


def _file_model(f) -> DriveFileModel:
    return DriveFileModel(
        id=f.id,
        name=f.name,
        size_bytes=f.size_bytes,
        mime_type=f.mime_type,
        md5_checksum=f.md5_checksum,
    )


# ─── Handlers ────────────────────────────────────────────────────────────


async def parse_url(args: dict) -> dict:
    inp = ParseUrlInput(**args)
    try:
        file_id = parse_drive_url(inp.url_or_id)
    except Exception as e:  # noqa: BLE001
        return {"file_id": ""} | {"error": typed_error(e)}
    return ParseUrlOutput(file_id=file_id).model_dump()


async def get_metadata(args: dict) -> dict:
    inp = GetMetadataInput(**args)
    dl, kind = _downloader_and_kind()
    try:
        meta = await dl.get_metadata(inp.file_id)
    except Exception as e:  # noqa: BLE001
        return GetMetadataOutput(file=None, adapter=kind).model_dump() | {
            "error": typed_error(e)
        }
    return GetMetadataOutput(
        file=_file_model(meta) if meta else None,
        adapter=kind,
    ).model_dump()


async def download(args: dict) -> dict:
    inp = DownloadInput(**args)
    dl, kind = _downloader_and_kind()
    try:
        meta = await dl.download(inp.file_id, Path(inp.dest_path))
    except Exception as e:  # noqa: BLE001
        return DownloadOutput(
            file=None, written_to=None, adapter=kind
        ).model_dump() | {"error": typed_error(e)}
    return DownloadOutput(
        file=_file_model(meta),
        written_to=inp.dest_path,
        adapter=kind,
    ).model_dump()


# ─── Registration ───────────────────────────────────────────────────────


HANDLERS = {
    "google.drive.parse_url": parse_url,
    "google.drive.get_metadata": get_metadata,
    "google.drive.download": download,
}


def register(server: Server) -> dict:
    return HANDLERS


def tool_descriptors() -> list[Tool]:
    return [
        Tool(
            name="google.drive.parse_url",
            description=(
                "Extract a Drive file id from a share URL "
                "(file/d/{id}/..., open?id=, uc?id=, uc?export=download&id=) "
                "or pass through a bare id. Pure — no network, no auth. "
                "Use this BEFORE get_metadata / download."
            ),
            inputSchema=ParseUrlInput.model_json_schema(),
        ),
        Tool(
            name="google.drive.get_metadata",
            description=(
                "Fetch a Drive file's metadata (name / size_bytes / "
                "mime_type / md5_checksum). Returns null file when the id "
                "is missing OR inaccessible (Drive returns 404 for both — "
                "by design). Read. Real adapter needs GOOGLE_API_KEY "
                "(public files) or OAuth (private)."
            ),
            inputSchema=GetMetadataInput.model_json_schema(),
        ),
        Tool(
            name="google.drive.download",
            description=(
                "Stream a Drive file's bytes to an absolute local path "
                "(creates parent dirs, overwrites). Returns the file "
                "metadata so you can verify size/md5. Read."
            ),
            inputSchema=DownloadInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
