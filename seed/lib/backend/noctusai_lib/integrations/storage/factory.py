"""Factory for `StorageBackend` — Fake / Local / Supabase, by `kind`.

Mirrors the canonical Protocol+Fake+Real+factory shape established by
`integrations/google_calendar` + `google_maps` + `youtube`. The
factory is the single seam consumers reach for:

```python
from noctusai_lib.integrations.storage import make_storage_backend

# Tests / dev — hermetic.
storage = make_storage_backend(kind="fake")

# Local dev with real bytes-on-disk semantics.
storage = make_storage_backend(kind="local", root_dir=Path("/tmp/blobs"))

# Production.
storage = make_storage_backend(kind="supabase", client=supabase_client)
```

The `kind` literal makes invalid backends a static-type error rather
than a runtime surprise.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from noctusai_lib.integrations.storage.fake import FakeStorageBackend
from noctusai_lib.integrations.storage.local import LocalFilesystemStorageBackend
from noctusai_lib.integrations.storage.protocol import StorageBackend


def make_storage_backend(
    *,
    kind: Literal["fake", "local", "supabase"],
    root_dir: Path | str | None = None,
    client: Any = None,
    **_: Any,
) -> StorageBackend:
    """Build a `StorageBackend`.

    - `kind="fake"` — returns `FakeStorageBackend()` (hermetic, in-memory).
    - `kind="local"` — returns `LocalFilesystemStorageBackend(root_dir)`;
      `root_dir` is REQUIRED.
    - `kind="supabase"` — returns `SupabaseStorageBackend(client)`;
      `client` is REQUIRED.

    Lazy import of `SupabaseStorageBackend` keeps the fake/local path
    importable even in slim environments that don't ship `supabase` /
    `storage3` (the import itself is cheap; deferring it follows the
    same shape as `google_calendar.get_calendar_adapter`).
    """
    if kind == "fake":
        return FakeStorageBackend()

    if kind == "local":
        if root_dir is None:
            raise ValueError(
                "make_storage_backend(kind='local') requires root_dir="
            )
        return LocalFilesystemStorageBackend(root_dir)

    if kind == "supabase":
        if client is None:
            raise ValueError(
                "make_storage_backend(kind='supabase') requires client="
            )
        # Lazy import — supabase / storage3 may be slim-environment-absent.
        from noctusai_lib.integrations.storage.supabase import (
            SupabaseStorageBackend,
        )

        return SupabaseStorageBackend(client)

    raise ValueError(f"Unsupported storage backend kind: {kind!r}")


__all__ = ["make_storage_backend"]
