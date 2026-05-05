"""Blob storage value objects.

Two frozen dataclasses make up the public type surface:

- `BlobMetadata` — describes a blob without holding its contents.
  Returned by `put`, `list_keys` (when extended later), and embedded in
  `StoredBlob`. `created_at` is timezone-aware UTC.
- `StoredBlob` — `BlobMetadata` + raw `bytes`. Returned by `get`.

Types are deliberately shallow (no nested vendor blobs) so callers get
a stable contract that survives a hypothetical Supabase / storage3
version bump. Real (Supabase), Local (filesystem), and Fake adapters
all produce identical instances.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


@dataclass(frozen=True)
class BlobMetadata:
    """Description of a stored blob, without its bytes.

    `custom_metadata` is a free-form dict the consumer attaches at
    `put` time — small, string-shaped key/value pairs (e.g.
    `{"uploader": "user-42", "original_filename": "scan.pdf"}`).
    Adapters that lack first-class user-metadata (Local filesystem)
    persist it via a sidecar `.meta.json` so round-trip semantics
    match Fake / Supabase.
    """

    bucket: str
    key: str
    size: int
    content_type: str
    created_at: datetime
    custom_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StoredBlob:
    """A retrieved blob — metadata plus raw bytes.

    Returned by `StorageBackend.get(...)`; `None` is returned for a
    missing key (never raises). Consumers wanting only the bytes can
    do `blob.data` directly; metadata is on `blob.metadata`.
    """

    metadata: BlobMetadata
    data: bytes


__all__ = ["BlobMetadata", "StoredBlob"]
