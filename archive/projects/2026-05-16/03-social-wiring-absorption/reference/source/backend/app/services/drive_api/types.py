"""Drive API adapter contract.

Same shape as the Calendar adapters: a Protocol the chatbot tools
call into, dataclasses for the wire shape every adapter returns.

We sit OUTSIDE the existing ``gdrive_service`` module on purpose —
that module is the download-URL parser used by the YouTube upload
pipeline. This package is the active Drive API client (search, list,
metadata) for the chatbot's "what's in my Drive?" tools. Two
different problems, two different surfaces.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True)
class DriveFile:
    """One row from the Drive API.

    Field set chosen to match what the chatbot most commonly needs to
    report back to the user: name, type, size, when modified, owner,
    a viewable link, and a parents/path hint for folder context.
    """

    file_id: str
    name: str
    mime_type: str
    size_bytes: int | None
    modified_at: datetime | None
    web_view_link: str | None
    icon_link: str | None = None
    parents: list[str] = field(default_factory=list)
    owners: list[str] = field(default_factory=list)
    is_folder: bool = False
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DriveSearchResult:
    files: list[DriveFile]
    next_page_token: str | None = None
    query_used: str | None = None


@dataclass(frozen=True)
class DriveFileContent:
    """A file's content rendered as text + metadata about how it
    was extracted. Used by the chatbot to count rows, summarize,
    answer questions about specific values.
    """

    file_id: str
    name: str
    mime_type: str
    rendered_as: str           # "csv" | "text" | "pdf-text" | "binary"
    text: str                   # may be truncated; check is_truncated
    bytes_read: int
    is_truncated: bool
    raw_mime: str | None = None  # e.g. "video/x-matroska" for binaries we can't render


class DriveAdapter(Protocol):
    """Read-only Drive surface the chatbot uses.

    Write surfaces (create folder, upload file) are out of scope for
    v1 — those happen via the existing upload pipeline, not via the
    agent. When/if the agent needs to write back, add to this Protocol.
    """

    def search(
        self,
        *,
        query: str | None = None,
        mime_type: str | None = None,
        folder_id: str | None = None,
        page_size: int = 20,
        order_by: str = "modifiedTime desc",
    ) -> DriveSearchResult: ...

    def get_file(self, file_id: str) -> DriveFile | None: ...

    def list_recent(self, *, page_size: int = 10) -> DriveSearchResult: ...

    def read_content(
        self,
        file_id: str,
        *,
        max_bytes: int = 200_000,
    ) -> DriveFileContent | None: ...
