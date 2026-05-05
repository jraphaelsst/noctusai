"""Blob storage — canonical Protocol+Fake+Real+factory.

Lifted 2026-05-04 by `projects/seed-hardening-from-youtube-crawler/`
Phase 3.2 to formalize the N=3 storage recurrence (therapy attachments,
ERP matriculas/certidoes, mailing CSV imports — all DIY today). New
storage-touching products consume the seed surface; existing products
migrate in their own follow-up projects.

**What ships:**

- `BlobMetadata`, `StoredBlob` value objects.
- `StorageBackend` Protocol with async methods:
  - `put(*, bucket, key, data, content_type, metadata)` → `BlobMetadata`
  - `get(*, bucket, key)` → `StoredBlob | None` (None on missing, no raise)
  - `delete(*, bucket, key)` → `bool` (False if missing, no raise)
  - `list_keys(*, bucket, prefix, limit)` → `list[str]`
  - `signed_url(*, bucket, key, expires_in_seconds)` → `str`
  - `exists(*, bucket, key)` → `bool`
- `FakeStorageBackend` — deterministic in-memory; tests / dev default.
- `LocalFilesystemStorageBackend` — bytes-on-disk; dev convenience.
  Buckets are sub-dirs under `root_dir`. `signed_url` returns `file://`
  URLs (clearly dev-only; expiry NOT enforced).
- `SupabaseStorageBackend` — wraps `supabase.storage.from_(bucket)`.
  Translates 404 to `None` / `False` for `get` / `delete` / `exists`;
  logs every other vendor error at WARN before re-raising.
- `make_storage_backend(kind=..., **config)` — factory.

**Three concrete consumers planned (existing call sites unchanged
during this lift):**

- `products/therapy-platform/backend/app/services/attachment_service.py`
- `products/erp-imobiliario/backend/app/services/storage_service.py`
- `products/mailing/backend/app/services/csv_import.py`

Migrations to consume the seed surface land as per-product follow-up
projects (out-of-scope for this lift).
"""

from noctusai_lib.integrations.storage.factory import make_storage_backend
from noctusai_lib.integrations.storage.fake import FakeStorageBackend
from noctusai_lib.integrations.storage.local import LocalFilesystemStorageBackend
from noctusai_lib.integrations.storage.protocol import StorageBackend
from noctusai_lib.integrations.storage.types import BlobMetadata, StoredBlob


def __getattr__(name: str):  # pragma: no cover - simple lazy proxy
    """Lazy-load `SupabaseStorageBackend` on first access.

    Keeps the fake / local path importable in slim environments that
    don't ship `supabase` / `storage3`. Mirrors the lazy-import pattern
    used by `google_calendar` for the heavy SDK adapters.
    """
    if name == "SupabaseStorageBackend":
        from noctusai_lib.integrations.storage.supabase import (
            SupabaseStorageBackend,
        )

        return SupabaseStorageBackend
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "BlobMetadata",
    "FakeStorageBackend",
    "LocalFilesystemStorageBackend",
    "StorageBackend",
    "StoredBlob",
    "SupabaseStorageBackend",
    "make_storage_backend",
]
