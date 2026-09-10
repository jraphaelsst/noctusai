"""google.drive.* tools — thin wrappers over the seed Drive libs.

Tools registered:
- google.drive.parse_url     — READ/pure. Extract a file id from a share URL.
- google.drive.get_metadata  — READ. Size / mime / md5 (None ⇒ missing OR inaccessible).
- google.drive.download      — READ. Stream bytes to a local path.
- google.drive.search        — READ. Name + full-text search (DriveReader).
- google.drive.read_file     — READ. Export/stream content + deterministic stats.

Two SIBLING seed surfaces back these tools (verified 2026-05-18 against
`noctusai_lib.integrations.google_drive` on the post-absorption base):

1. The DOWNLOADER surface (`make_drive_downloader` / `FakeDriveDownloader`
   / `parse_drive_url` / `DriveFile`) — `parse_url` / `get_metadata` /
   `download`. Download-to-disk for the upload-pipeline consumer.

2. The READER surface (`make_drive_reader` / `FakeDriveReader` /
   `DriveReader` / `DriveSearchResult` / `DriveFileContent` /
   `compute_content_stats`, added 2026-05-16 by the social-wiring
   absorption Wave 1.E3) — `search` / `read_file`. The chatbot
   "inspect my Drive" consumer. A SECOND Protocol in the same package,
   NOT an overload of the download contract.

`read_file` returns the result of `compute_content_stats(...)` as
`stats` — the LLM-recount-trap defense: the tool description forbids
the model from recounting long structured data and points it at
`stats` (Python-computed ground truth). All read tools are real and
complete against the shipped Fake+Real surfaces.
"""
from __future__ import annotations

import logging
from pathlib import Path

from mcp.server import Server
from mcp.types import Tool

from noctusai_lib.integrations.google_drive import (
    compute_content_stats,
    make_drive_downloader,
    make_drive_reader,
    parse_drive_url,
)

from _kit.errors import typed_error

from settings import get_settings
from schemas import (
    DownloadInput,
    DownloadOutput,
    DriveFileContentModel,
    DriveFileModel,
    DriveSearchHitModel,
    DriveSearchInput,
    DriveSearchOutput,
    GetMetadataInput,
    GetMetadataOutput,
    ParseUrlInput,
    ParseUrlOutput,
    ReadFileInput,
    ReadFileOutput,
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


# Connector-side test seam (dependency injection, NOT monkeypatching):
# `search` / `read_file` resolve their `DriveReader` through this slot so
# a test can inject a seeded `FakeDriveReader` and exercise the REAL
# handler path — search/read shaping + `compute_content_stats` + the
# binary branch — without a network round-trip. Production leaves it
# None ⇒ the api_key/Fake selection below applies. Mirrors
# `youtube.configure_upload_client` + the FastAPI-dep-factory module-slot
# pattern (default None, populated by an explicit configure call).
_reader_override = None


def configure_reader(reader) -> None:
    """Inject the `DriveReader` `search`/`read_file` use (tests only).

    Pass `None` to restore the production api_key/Fake selection.
    """
    global _reader_override
    _reader_override = reader


def _reader_and_kind():
    """Real `DriveReader` when an API key is configured (anyone-with-link
    public files — the quick-start path), else the in-memory Fake. An
    injected reader (tests) wins and reports kind='fake'. Mirrors
    `_downloader_and_kind()` — the reader is a SIBLING seed surface, not
    an overload of the download contract."""
    if _reader_override is not None:
        return _reader_override, "fake"
    s = get_settings()
    if s.api_key:
        return make_drive_reader(api_key=s.api_key), "real"
    return make_drive_reader(use_fake=True), "fake"


def _hit_model(h) -> DriveSearchHitModel:
    return DriveSearchHitModel(
        id=h.id,
        name=h.name,
        mime_type=h.mime_type,
        modified_time=h.modified_time,
        size_bytes=h.size_bytes,
        web_view_link=h.web_view_link,
        capabilities=h.capabilities,
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


async def search(args: dict) -> dict:
    inp = DriveSearchInput(**args)
    reader, kind = _reader_and_kind()
    try:
        res = await reader.search(
            inp.query,
            mime_type=inp.mime_type,
            folder_id=inp.folder_id,
            page_size=inp.page_size,
        )
    except Exception as e:  # noqa: BLE001
        return DriveSearchOutput(
            hits=[], next_page_token=None, adapter=kind
        ).model_dump() | {"error": typed_error(e)}
    return DriveSearchOutput(
        hits=[_hit_model(h) for h in res.hits],
        next_page_token=res.next_page_token,
        adapter=kind,
    ).model_dump()


# rendered_as values that carry decodable UTF-8 text (the rest is
# binary — defer extraction to the media seam, don't decode here).
_TEXT_RENDERS = {"text/csv", "text/plain", "passthrough"}


async def read_file(args: dict) -> dict:
    inp = ReadFileInput(**args)
    reader, kind = _reader_and_kind()
    try:
        content = await reader.read_file(inp.file_id, max_bytes=inp.max_bytes)
    except Exception as e:  # noqa: BLE001
        return ReadFileOutput(content=None, stats={}, adapter=kind).model_dump() | {
            "error": typed_error(e)
        }
    if content is None:
        # Missing OR inaccessible (Drive 404s both, by design). Not an
        # error envelope — a clean null result, mirroring get_metadata.
        return ReadFileOutput(content=None, stats={}, adapter=kind).model_dump()

    if content.rendered_as in _TEXT_RENDERS:
        text = content.data.decode("utf-8", errors="replace")
        stats = compute_content_stats(text, rendered_as=content.rendered_as)
        data_out = text
    else:
        # Binary (PDF/DOCX/image/video) — NOT decoded here. Aggregates
        # don't apply; hand the file to the media seam for extraction.
        stats = {
            "note": (
                "binary content — not decoded here; defer extraction to "
                "the media seam (PyMuPDF / vision)"
            ),
            "byte_length": len(content.data),
        }
        data_out = (
            f"<binary {content.mime_type} ({len(content.data)} bytes) — "
            "not inlined; use the media seam to extract>"
        )
    return ReadFileOutput(
        content=DriveFileContentModel(
            file_id=content.file_id,
            name=content.name,
            mime_type=content.mime_type,
            rendered_as=content.rendered_as,
            data=data_out,
            truncated=content.truncated,
        ),
        stats=stats,
        adapter=kind,
    ).model_dump()


# ─── Registration ───────────────────────────────────────────────────────


HANDLERS = {
    "google.drive.parse_url": parse_url,
    "google.drive.get_metadata": get_metadata,
    "google.drive.download": download,
    "google.drive.search": search,
    "google.drive.read_file": read_file,
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
        Tool(
            name="google.drive.search",
            description=(
                "Name + full-text search across Drive files the "
                "credentials can see (matched against file name AND "
                "content). Optional mime_type / folder_id narrow it. "
                "Each hit carries `capabilities` (canDownload / canEdit) "
                "so you can tell permission-denied from 404. The "
                "`web_view_link` is IMMUTABLE — copy it verbatim; "
                "rewriting the domain or inserting '/u/0/' breaks the "
                "link (Google 400). Read."
            ),
            inputSchema=DriveSearchInput.model_json_schema(),
        ),
        Tool(
            name="google.drive.read_file",
            description=(
                "Read a Drive file's content. Google-native types are "
                "exported (Sheets→CSV, Docs→text/plain); text/CSV/JSON "
                "stream verbatim; binary (PDF/DOCX/image/video) is NOT "
                "decoded (use the media seam). Clipped at max_bytes "
                "(truncated=true ⇒ partial — say so, don't over-claim). "
                "CRITICAL: the `stats` field holds Python-computed "
                "aggregates (total_lines / non_empty_lines / CSV "
                "column+row counts). QUOTE `stats` VERBATIM as ground "
                "truth — NEVER recount from `content.data` (LLMs "
                "miscount long structured data). Read."
            ),
            inputSchema=ReadFileInput.model_json_schema(),
        ),
    ]


__all__ = ["register", "tool_descriptors", "HANDLERS"]
