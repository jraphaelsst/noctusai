"""In-memory deterministic `FakeDriveReader` for dev + tests.

Mirrors the Drive v3 read surface so chatbot Drive-tool consumers can
swap real/fake transparently. Seed fixtures with `add_file(...)`:

```python
fake = FakeDriveReader()
fake.add_file("xyz", "Cronograma One", b"Data,Ref\\n1,ONE5597\\n",
              mime_type="text/csv")
res = await fake.search("cronograma")
content = await fake.read_file("xyz")
```

Enriched (2026-05-19, `social-wiring-google-seed-consume` Phase
6a-drive): `add_file(...)` accepts the new optional projection fields
(`parents`, `owners`, `icon_link`, `raw`) and the Fake mirrors the
Real adapter's `DriveFileContent.raw_mime` emission so tests can
inspect every field surfaced by the enriched seed Protocol.
"""

from __future__ import annotations

from typing import Any

from noctusai_lib.integrations.google_drive.reader_types import (
    DriveFileContent,
    DriveSearchHit,
    DriveSearchResult,
)


class FakeDriveReader:
    """Deterministic in-memory `DriveReader`."""

    def __init__(self) -> None:
        # file_id -> (DriveSearchHit, content_bytes, rendered_as, raw_mime)
        self._files: dict[
            str, tuple[DriveSearchHit, bytes, str, str | None]
        ] = {}

    def add_file(
        self,
        file_id: str,
        name: str,
        content: bytes,
        *,
        mime_type: str = "text/plain",
        rendered_as: str = "passthrough",
        modified_time: str | None = None,
        web_view_link: str | None = None,
        capabilities: dict | None = None,
        parents: list[str] | None = None,
        owners: list[str] | None = None,
        icon_link: str | None = None,
        raw: dict[str, Any] | None = None,
        raw_mime: str | None = None,
    ) -> DriveSearchHit:
        hit = DriveSearchHit(
            id=file_id,
            name=name,
            mime_type=mime_type,
            modified_time=modified_time,
            size_bytes=len(content),
            web_view_link=web_view_link
            or f"https://drive.google.com/file/d/{file_id}/view",
            capabilities=capabilities or {"canDownload": True},
            parents=list(parents or []),
            owners=list(owners or []),
            icon_link=icon_link,
            raw=dict(raw or {}),
        )
        self._files[file_id] = (hit, content, rendered_as, raw_mime)
        return hit

    async def search(
        self,
        query: str,
        *,
        mime_type: str | None = None,
        folder_id: str | None = None,
        page_size: int = 20,
    ) -> DriveSearchResult:
        q = query.lower().strip()
        hits = [
            hit
            for hit, _content, _r, _rm in self._files.values()
            if (not q or q in hit.name.lower())
            and (mime_type is None or hit.mime_type == mime_type)
            and (folder_id is None or folder_id in hit.parents)
        ]
        return DriveSearchResult(hits=hits[:page_size])

    async def list_recent(self, *, page_size: int = 20) -> DriveSearchResult:
        hits = [hit for hit, _c, _r, _rm in self._files.values()]
        hits.sort(key=lambda h: h.modified_time or "", reverse=True)
        return DriveSearchResult(hits=hits[:page_size])

    async def get_file(self, file_id: str) -> DriveSearchHit | None:
        entry = self._files.get(file_id)
        return entry[0] if entry else None

    async def read_file(
        self, file_id: str, *, max_bytes: int = 200_000
    ) -> DriveFileContent | None:
        entry = self._files.get(file_id)
        if entry is None:
            return None
        hit, content, rendered_as, raw_mime = entry
        truncated = len(content) > max_bytes
        return DriveFileContent(
            file_id=file_id,
            name=hit.name,
            mime_type=hit.mime_type,
            rendered_as=rendered_as,
            data=content[:max_bytes],
            truncated=truncated,
            raw_mime=raw_mime if raw_mime is not None else hit.mime_type,
        )


__all__ = ["FakeDriveReader"]
