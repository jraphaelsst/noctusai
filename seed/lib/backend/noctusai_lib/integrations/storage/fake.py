"""In-memory deterministic FakeStorageBackend for dev + tests.

Dict-of-(bucket, key) → (bytes + metadata). No I/O, no filesystem,
no network — fully hermetic. Use it as the default in tests; the
factory's `kind="fake"` returns this class.

Determinism: `created_at` is taken from `now_fn` (defaults to
`datetime.now(UTC)`) so tests can pin time by injecting a fake clock
if needed. `signed_url` returns a stable sentinel format so URL
assertions in tests stay readable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from noctusai_lib.integrations.storage.types import BlobMetadata, StoredBlob


class FakeStorageBackend:
    """Deterministic in-memory `StorageBackend` implementation.

    State lives in `self._blobs: dict[str, dict[str, _BlobRecord]]`,
    keyed first by bucket then by key. Buckets are created lazily on
    first `put` — no separate `create_bucket` API (matches the
    public-bucket Supabase pattern most consumers use).
    """

    def __init__(
        self,
        *,
        now_fn: Callable[[], datetime] | None = None,
    ) -> None:
        self._blobs: dict[str, dict[str, tuple[BlobMetadata, bytes]]] = {}
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    async def put(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
    ) -> BlobMetadata:
        meta = BlobMetadata(
            bucket=bucket,
            key=key,
            size=len(data),
            content_type=content_type,
            created_at=self._now_fn(),
            custom_metadata=dict(metadata or {}),
        )
        self._blobs.setdefault(bucket, {})[key] = (meta, bytes(data))
        return meta

    async def get(self, *, bucket: str, key: str) -> StoredBlob | None:
        record = self._blobs.get(bucket, {}).get(key)
        if record is None:
            return None
        meta, data = record
        return StoredBlob(metadata=meta, data=data)

    async def delete(self, *, bucket: str, key: str) -> bool:
        bucket_blobs = self._blobs.get(bucket)
        if bucket_blobs is None or key not in bucket_blobs:
            return False
        del bucket_blobs[key]
        return True

    async def list_keys(
        self,
        *,
        bucket: str,
        prefix: str = "",
        limit: int = 100,
    ) -> list[str]:
        bucket_blobs = self._blobs.get(bucket, {})
        matched = sorted(k for k in bucket_blobs.keys() if k.startswith(prefix))
        return matched[:limit]

    async def signed_url(
        self,
        *,
        bucket: str,
        key: str,
        expires_in_seconds: int = 3600,
    ) -> str:
        # Stable sentinel so tests can assert on URL shape without
        # depending on wall-clock time. We DO embed expires_in so the
        # consumer can verify the requested TTL round-trips.
        expires_at_ts = int(self._now_fn().timestamp()) + expires_in_seconds
        return f"fake://storage/{bucket}/{key}?expires={expires_at_ts}"

    async def exists(self, *, bucket: str, key: str) -> bool:
        return key in self._blobs.get(bucket, {})


__all__ = ["FakeStorageBackend"]
