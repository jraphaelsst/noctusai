"""In-memory Drive adapter for tests + the no-credentials fallback.

Mirrors the read-side of Drive v3: search/list/get against an
internal dict of DriveFile rows. Tests can seed it via
``adapter.seed(files=[...])``.
"""
from __future__ import annotations

from typing import Iterable

from app.services.drive_api.mappers import FOLDER_MIME
from app.services.drive_api.types import DriveFile, DriveFileContent, DriveSearchResult


class FakeDriveAdapter:
    """Read-only in-memory Drive adapter."""

    def __init__(self) -> None:
        self._files: dict[str, DriveFile] = {}

    def seed(self, files: Iterable[DriveFile]) -> None:
        for f in files:
            self._files[f.file_id] = f

    def search(
        self,
        *,
        query: str | None = None,
        mime_type: str | None = None,
        folder_id: str | None = None,
        page_size: int = 20,
        order_by: str = "modifiedTime desc",  # noqa: ARG002
    ) -> DriveSearchResult:
        results: list[DriveFile] = []
        needle = (query or "").lower()
        for f in self._files.values():
            if mime_type and f.mime_type != mime_type:
                continue
            if folder_id and folder_id not in f.parents:
                continue
            if needle and needle not in f.name.lower():
                continue
            results.append(f)
            if len(results) >= page_size:
                break
        return DriveSearchResult(files=results, query_used=query)

    def get_file(self, file_id: str) -> DriveFile | None:
        return self._files.get(file_id)

    def list_recent(self, *, page_size: int = 10) -> DriveSearchResult:
        files = list(self._files.values())[:page_size]
        return DriveSearchResult(files=files)

    def read_content(
        self,
        file_id: str,
        *,
        max_bytes: int = 200_000,  # noqa: ARG002
    ) -> DriveFileContent | None:
        f = self._files.get(file_id)
        if f is None:
            return None
        # Fake content for tests — callers seed the dict if they need
        # specific text. Default empty.
        return DriveFileContent(
            file_id=file_id,
            name=f.name,
            mime_type=f.mime_type,
            rendered_as="text",
            text=f.raw.get("fake_text", "") if isinstance(f.raw, dict) else "",
            bytes_read=0,
            is_truncated=False,
        )
