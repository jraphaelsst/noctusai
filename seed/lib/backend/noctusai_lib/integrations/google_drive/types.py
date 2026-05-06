"""Google Drive v3 value objects.

`DriveFile` is a flattened projection of `files.get` (`fields=id,name,
size,mimeType,md5Checksum`) — deliberately shallow so callers don't bind
to googleapiclient response shape. Real / Fake adapters both produce
identical instances.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DriveFile:
    """A Google Drive file's metadata projection."""

    id: str
    name: str
    size_bytes: int
    """`files.size` parsed to int. Drive returns this as a string in the
    JSON; the adapter parses it. Folders (`application/vnd.google-apps.folder`)
    have no size and surface as 0 — callers should reject folders by
    `mime_type` rather than relying on size."""
    mime_type: str
    """E.g. `video/mp4`, `application/pdf`. Folders are
    `application/vnd.google-apps.folder` — reject before download."""
    md5_checksum: str | None = None
    """Drive emits md5 for binary uploads but NOT for native Google Docs
    types (Docs / Sheets / Slides) since those have no canonical bytes.
    `None` is expected for native-Docs files; consumers needing checksum
    integrity should reject `None` for binary download paths."""


__all__ = ["DriveFile"]
