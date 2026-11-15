"""Blob storage Protocol.

Three concrete implementations ship in the seed:

- `FakeStorageBackend` — deterministic in-memory dev/test default.
- `LocalFilesystemStorageBackend` — buckets are sub-dirs of a root
  directory; `signed_url` returns `file://...` (clearly dev-only).
- `SupabaseStorageBackend` — wraps `supabase.storage.from_(bucket)...`.

Build via `make_storage_backend(kind=..., **config)`. The factory
routes based on the `kind` literal — see `factory.py`.

**Contract notes:**

- All methods are `async` so consumers can fan out concurrently
  (Fake / Local don't actually do I/O off-thread; the async surface
  is for uniformity across backends).
- `get` returns `None` on missing key (never raises 404).
- `delete` returns `bool` — `True` if the key existed, `False` if it
  was already gone (never raises 404).
- `signed_url` returns a `str`. The semantics of "signed" differ by
  backend (Fake/Local emit dev-only sentinels); callers should treat
  the URL as opaque and only rely on it being a valid URL string for
  the backend's runtime context.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol

from noctusai_lib.integrations.storage.types import BlobMetadata, StoredBlob

#: Security standard S1 (private by default, short-lived signed URLs).
DEFAULT_SIGNED_URL_TTL_SECONDS = 600
MAX_SIGNED_URL_TTL_SECONDS = 3600


def validate_signed_url_ttl(
    expires_in_seconds: int, ttl_reason: Optional[str] = None
) -> int:
    """The ONE TTL rule every `StorageBackend.signed_url` applies.

    - `1 <= ttl <= 600`: always allowed.
    - `600 < ttl <= 3600`: allowed only with a non-empty `ttl_reason`
      (why a link must outlive 10 minutes).
    - anything else: `ValueError` (never a silent clamp).
    """
    if isinstance(expires_in_seconds, bool) or not isinstance(expires_in_seconds, int):
        raise ValueError(f"signed_url expires_in_seconds must be an int, got {expires_in_seconds!r}")
    if expires_in_seconds < 1:
        raise ValueError(f"signed_url expires_in_seconds must be >= 1, got {expires_in_seconds}")
    if expires_in_seconds > MAX_SIGNED_URL_TTL_SECONDS:
        raise ValueError(
            f"signed_url expires_in_seconds={expires_in_seconds} exceeds the hard max "
            f"{MAX_SIGNED_URL_TTL_SECONDS}s"
        )
    if expires_in_seconds > DEFAULT_SIGNED_URL_TTL_SECONDS and not (ttl_reason or "").strip():
        raise ValueError(
            f"signed_url expires_in_seconds={expires_in_seconds} > {DEFAULT_SIGNED_URL_TTL_SECONDS}s "
            "requires an explicit ttl_reason"
        )
    return expires_in_seconds


class StorageBackend(Protocol):
    """Blob storage contract — Supabase Storage shape, abstracted.

    All implementations must be safe to call concurrently (Fake uses
    a plain dict; Local writes are not coordinated across processes;
    Supabase Storage is server-side concurrent). Callers wanting
    strict cross-process atomicity must add their own locking.
    """

    async def put(
        self,
        *,
        bucket: str,
        key: str,
        data: bytes,
        content_type: str = "application/octet-stream",
        metadata: dict[str, Any] | None = None,
    ) -> BlobMetadata:
        """Upload `data` to `bucket/key`.

        Overwrites any existing blob at `key`. `metadata` is the
        free-form `custom_metadata` payload attached to the blob;
        adapters that don't natively support user-metadata persist
        it via a sidecar (Local) or vendor metadata (Supabase). The
        returned `BlobMetadata` is immediately consistent with the
        upload (i.e. a follow-up `get` returns the same metadata).
        """
        ...

    async def get(self, *, bucket: str, key: str) -> StoredBlob | None:
        """Retrieve the blob at `bucket/key`.

        Returns `None` when the key doesn't exist — does NOT raise.
        Distinguish "missing" from "empty file" by inspecting the
        return type: `None` is missing; `StoredBlob(data=b"")` is an
        intentionally empty blob.
        """
        ...

    async def delete(self, *, bucket: str, key: str) -> bool:
        """Delete the blob at `bucket/key`.

        Returns `True` when the key existed and was removed, `False`
        when the key was already absent. Never raises 404.
        """
        ...

    async def list_keys(
        self,
        *,
        bucket: str,
        prefix: str = "",
        limit: int = 100,
    ) -> list[str]:
        """List keys in `bucket` whose name starts with `prefix`.

        Returns up to `limit` keys, sorted lexicographically. Empty
        list when the bucket is empty or no keys match. The default
        `limit=100` matches Supabase Storage's default page size.
        """
        ...

    async def signed_url(
        self,
        *,
        bucket: str,
        key: str,
        expires_in_seconds: int = DEFAULT_SIGNED_URL_TTL_SECONDS,
        ttl_reason: Optional[str] = None,
    ) -> str:
        """Pre-signed URL for direct downloads.

        TTL rule (`validate_signed_url_ttl`): default 600 s; a value above
        600 s needs a non-empty `ttl_reason`; above 3600 s (or < 1) raises
        `ValueError`. Every backend, Fake included, enforces it.

        Format depends on backend:
        - Fake: `fake://storage/<bucket>/<key>?expires=<unix-ts>`
        - Local: `file:///<root>/<bucket>/<key>?expires=<unix-ts>` (dev-only)
        - Supabase: HTTPS URL signed by Supabase's `create_signed_url`.

        Adapters MAY return a URL even for missing keys (Supabase does);
        consumers wanting existence-checks-first should call `exists`.
        """
        ...

    async def exists(self, *, bucket: str, key: str) -> bool:
        """`True` when a blob is stored at `bucket/key`."""
        ...


__all__ = [
    "DEFAULT_SIGNED_URL_TTL_SECONDS",
    "MAX_SIGNED_URL_TTL_SECONDS",
    "StorageBackend",
    "validate_signed_url_ttl",
]
