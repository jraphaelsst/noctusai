"""Local filesystem `StorageBackend` for dev convenience.

Buckets are sub-directories of `root_dir`. Keys are written verbatim
under `root_dir/<bucket>/<key>` — including any path separators in
the key (e.g. `org-42/photos/scan.pdf` becomes a nested directory).

`signed_url` returns a `file://` URL clearly marked as dev-only; it
does NOT enforce expiry (consumers should NEVER expose Local URLs to
end users). Use this backend for local development, integration tests
that need real bytes-on-disk semantics, and CI.

User metadata is persisted via a sidecar JSON file at
`<root>/<bucket>/<key>.meta.json` — keeps round-trip semantics
identical to Fake / Supabase.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from noctusai_lib.integrations.storage.types import BlobMetadata, StoredBlob

logger = logging.getLogger(__name__)

_META_SUFFIX = ".meta.json"


class LocalFilesystemStorageBackend:
    """Filesystem-backed `StorageBackend`.

    `root_dir` is created on first use if missing. Buckets are
    sub-directories created on first `put`. The class is process-local
    (no inter-process locking); consumers wanting cross-process safety
    must add their own coordination.
    """

    def __init__(self, root_dir: Path | str) -> None:
        self._root_dir = Path(root_dir)
        self._root_dir.mkdir(parents=True, exist_ok=True)

    # ---- Internal path helpers ---------------------------------------

    def _bucket_dir(self, bucket: str) -> Path:
        return self._root_dir / bucket

    def _blob_path(self, bucket: str, key: str) -> Path:
        return self._bucket_dir(bucket) / key

    def _meta_path(self, bucket: str, key: str) -> Path:
        return self._bucket_dir(bucket) / (key + _META_SUFFIX)

    # ---- StorageBackend surface --------------------------------------

    async def put(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
    ) -> BlobMetadata:
        blob_path = self._blob_path(bucket, key)
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(data)

        custom_metadata = dict(metadata or {})
        created_at = datetime.now(timezone.utc)
        meta = BlobMetadata(
            bucket=bucket,
            key=key,
            size=len(data),
            content_type=content_type,
            created_at=created_at,
            custom_metadata=custom_metadata,
        )
        # Persist sidecar so subsequent `get` returns identical metadata.
        sidecar = {
            "content_type": content_type,
            "created_at": created_at.isoformat(),
            "custom_metadata": custom_metadata,
        }
        self._meta_path(bucket, key).write_text(json.dumps(sidecar))
        return meta

    async def get(self, *, bucket: str, key: str) -> StoredBlob | None:
        blob_path = self._blob_path(bucket, key)
        if not blob_path.is_file():
            return None
        data = blob_path.read_bytes()
        meta = self._read_metadata(bucket, key, size=len(data))
        return StoredBlob(metadata=meta, data=data)

    async def delete(self, *, bucket: str, key: str) -> bool:
        blob_path = self._blob_path(bucket, key)
        if not blob_path.is_file():
            return False
        blob_path.unlink()
        meta_path = self._meta_path(bucket, key)
        if meta_path.is_file():
            meta_path.unlink()
        return True

    async def list_keys(
        self,
        *,
        bucket: str,
        prefix: str = "",
        limit: int = 100,
    ) -> list[str]:
        bucket_dir = self._bucket_dir(bucket)
        if not bucket_dir.is_dir():
            return []
        keys: list[str] = []
        for path in bucket_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.name.endswith(_META_SUFFIX):
                continue
            relative = path.relative_to(bucket_dir).as_posix()
            if relative.startswith(prefix):
                keys.append(relative)
        keys.sort()
        return keys[:limit]

    async def signed_url(
        self,
        *,
        bucket: str,
        key: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        # `file://` URLs are dev-only. `expires_in_seconds` is encoded as
        # a query param so callers + tests can verify it round-trips, but
        # the local backend does NOT enforce expiry.
        blob_path = self._blob_path(bucket, key).resolve()
        expires_at_ts = int(datetime.now(timezone.utc).timestamp()) + expires_in_seconds
        # quote() escapes spaces / unicode so the URL stays well-formed.
        return f"file://{quote(str(blob_path))}?expires={expires_at_ts}"

    async def exists(self, *, bucket: str, key: str) -> bool:
        return self._blob_path(bucket, key).is_file()

    # ---- Metadata sidecar parsing ------------------------------------

    def _read_metadata(self, bucket: str, key: str, *, size: int) -> BlobMetadata:
        meta_path = self._meta_path(bucket, key)
        content_type = "application/octet-stream"
        created_at = datetime.now(timezone.utc)
        custom_metadata: dict[str, Any] = {}
        if meta_path.is_file():
            try:
                payload = json.loads(meta_path.read_text())
                content_type = payload.get("content_type", content_type)
                if "created_at" in payload:
                    created_at = datetime.fromisoformat(payload["created_at"])
                custom_metadata = payload.get("custom_metadata", {}) or {}
            except (json.JSONDecodeError, ValueError) as exc:
                # Sidecar exists but is corrupt — surface, don't swallow.
                logger.warning(
                    "storage.local.sidecar_parse_failed bucket=%s key=%s err=%s",
                    bucket,
                    key,
                    exc,
                )
        return BlobMetadata(
            bucket=bucket,
            key=key,
            size=size,
            content_type=content_type,
            created_at=created_at,
            custom_metadata=custom_metadata,
        )


__all__ = ["LocalFilesystemStorageBackend"]
