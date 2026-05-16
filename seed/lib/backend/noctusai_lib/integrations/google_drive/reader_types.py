"""Google Drive v3 *read/inspection* value objects + Protocol.

Reconciled 2026-05-16 by `projects/social-wiring-absorption/` Wave 1.E3
from the live-validated workspace package
`youtube-crawler/app/services/drive_api/`
(`reference/.promotions/drive-api-client.md`,
`SESSION-NOTES_drive-api-2026-05-13.md`).

WHY a sibling surface (not a change to `DriveDownloader`)
---------------------------------------------------------
The existing `DriveDownloader` Protocol (download-to-disk for the
youtube-crawler upload pipeline) is a different operation from the
chatbot's *inspect-my-Drive* surface (search / list / metadata /
read-content-for-the-LLM). They have different return shapes and
different consumers. Per `protocol.py`'s own note ("Drive supports
many more endpoints … out of scope until the second consumer
arrives — add to the Protocol then"), the second consumer has now
arrived (social-wiring chatbot Drive tools). We add a SECOND
Protocol (`DriveReader`) in the SAME package rather than overloading
the download contract — both ship Fake+Real+factory.

`read_file` returns raw exported bytes + a `rendered_as` hint, NOT
extracted PDF/Docx text. PDF→text / video-keyframe extraction is
owned by the multimodal `media` seam (Wave 1.E5) — keeping this
module dependency-light (no PyMuPDF/pdfminer import) and the
boundary clean. Sheets→CSV and Docs→text/plain ARE done here
because they are Drive `files.export` MIME selections, not content
parsing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path  # noqa: F401 — re-export convenience for consumers
from typing import Any, Protocol


@dataclass(frozen=True)
class DriveSearchHit:
    """One result row from a Drive search / list call.

    `capabilities` surfaces the Drive `capabilities` sub-object
    (`canDownload`, `canEdit`, ...) so a consumer can distinguish
    "permission denied" from "no tool" from "404" — the gotcha from
    the drive-api session note (a shared spreadsheet looked
    inaccessible but actually had `canDownload: true`; the real issue
    was the bot lacked a read tool)."""

    id: str
    name: str
    mime_type: str
    modified_time: str | None = None
    size_bytes: int | None = None
    web_view_link: str | None = None
    """The Drive UI URL. Treated as IMMUTABLE — see the LLM-URL-rewrite
    gotcha (`SESSION-NOTES_google-integrations-2026-05-12.md` §3): an
    LLM that inserts `/u/0/` or rewrites the domain breaks the link
    (Google returns 400). Consumers surfacing this to an LLM MUST
    instruct it to copy the value verbatim."""
    capabilities: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DriveSearchResult:
    hits: list[DriveSearchHit]
    next_page_token: str | None = None


@dataclass(frozen=True)
class DriveFileContent:
    """The content of a Drive file as exported/streamed bytes.

    `rendered_as` tells the consumer how `data` was produced so it can
    decide how to decode / extract:
    - `"text/csv"`      — Google Sheets exported to CSV (UTF-8 text)
    - `"text/plain"`    — Google Docs exported to plain text (UTF-8)
    - `"passthrough"`   — TXT / CSV / JSON streamed verbatim
    - `"binary"`        — PDF / DOCX / image / video etc. — NOT decoded
                          here; hand `data` to the `media` seam
                          (PyMuPDF / vision) for extraction.
    """

    file_id: str
    name: str
    mime_type: str
    rendered_as: str
    data: bytes
    truncated: bool = False
    """True when `max_bytes` clipped the payload (large sheets/docs).
    Consumers should tell the LLM the data is partial so it doesn't
    over-claim completeness."""


class DriveReader(Protocol):
    """Drive v3 read/inspection contract.

    Concrete impls in this package: `FakeDriveReader` (deterministic
    in-memory dev/test default) + `RealDriveReader` (googleapiclient,
    service-account OR OAuth creds). Build via `make_drive_reader(...)`.

    Auth-agnostic like `DriveDownloader`: the Real adapter takes
    either an `api_key` (anyone-with-link) OR `oauth_credentials`
    (private files). The recommended quick-start for new products is
    the *share-the-folder-with-the-service-account email* path — no
    GCP redirect-URI registration, the SA sees whatever is shared
    recursively (drive-api session note §2)."""

    async def search(
        self,
        query: str,
        *,
        mime_type: str | None = None,
        folder_id: str | None = None,
        page_size: int = 20,
    ) -> DriveSearchResult:
        """Name + full-text search. `query` is matched against file
        name AND content; `mime_type` / `folder_id` narrow it."""
        ...

    async def list_recent(self, *, page_size: int = 20) -> DriveSearchResult:
        """Most-recently-modified files the credentials can see."""
        ...

    async def get_file(self, file_id: str) -> DriveSearchHit | None:
        """Metadata-only lookup (incl. `capabilities`). `None` when the
        file doesn't exist OR the creds can't see it (Drive returns 404
        for both, by design — don't leak existence)."""
        ...

    async def read_file(
        self, file_id: str, *, max_bytes: int = 200_000
    ) -> DriveFileContent | None:
        """Fetch a file's content. Google-native types are exported
        (Sheets→CSV, Docs→text/plain); other types stream verbatim and
        carry `rendered_as="passthrough"` (text) or `"binary"` (defer
        extraction to the `media` seam). Clips at `max_bytes`. `None`
        when the file is missing/inaccessible."""
        ...


__all__ = [
    "DriveSearchHit",
    "DriveSearchResult",
    "DriveFileContent",
    "DriveReader",
]
