"""DI seams for the `card_hub` module.

Two schema-scoped/underlying-object-scoped caches, mirroring
`app/routers/clientes_router.py::get_clientes_client` exactly (same
`MockSupabaseClient.schema()` data-loss bug, same fix — see that
function's docstring). This module deliberately does NOT import
`clientes_router.get_clientes_client` directly: that file belongs to a
different slice's ownership boundary (this module never edits it), and
keeping the caches structurally identical but independently keyed avoids
a cross-module import into a router file this slice must not touch.
"""
from __future__ import annotations

import weakref
from typing import Any

from noctusai_lib.integrations.storage import (
    FakeStorageBackend,
    StorageBackend,
    make_storage_backend,
)

from app.dependencies import get_admin_client

_SCHEMA = "social_wiring"

_scoped_cache: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()


def get_card_hub_client() -> Any:
    """FastAPI dependency — the `social_wiring`-scoped admin client,
    cached by the underlying admin-client object (never by re-deriving
    `.schema()` per call, which loses every prior write against
    `MockSupabaseClient` — see `clientes_router.py`'s identical seam)."""
    admin = get_admin_client()
    cached = _scoped_cache.get(admin)
    if cached is None:
        cached = admin.schema(_SCHEMA)
        _scoped_cache[admin] = cached
    return cached


BUCKET = "social-wiring-documentos"

_storage_cache: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()


def get_storage_backend() -> StorageBackend:
    """FastAPI dependency — the blob storage backend for card documents.

    Production resolves a real `SupabaseStorageBackend` bound to the RAW
    admin client (`get_admin_client()` — NOT the schema-scoped wrapper;
    `.storage` lives on the top-level Supabase client, never on a
    `.schema(...)`-derived proxy).

    Tests MUST override this via
    `app.dependency_overrides[get_storage_backend] = lambda: FakeStorageBackend()`
    (`KB § PATTERNS/backend/di-test-seam.md` Class-B) rather than relying
    on the sqlite/mock fallback below — `MockSupabaseClient.storage` is a
    bare `MagicMock()` that answers ANY call with another MagicMock, so an
    un-overridden test would silently "succeed" against garbage signed
    URLs instead of failing loudly.
    """
    admin = get_admin_client()
    cached = _storage_cache.get(admin)
    if cached is not None:
        return cached
    if not hasattr(admin, "storage"):
        # sqlite local-dev fallback (`settings.database_backend ==
        # "sqlite"`) — no Supabase Storage surface at all. Degrades to
        # the hermetic fake rather than raising, mirroring
        # `app.dependencies`'s own `_use_sqlite` local-dev branches.
        backend: StorageBackend = FakeStorageBackend()
    else:
        backend = make_storage_backend(kind="supabase", client=admin)
    _storage_cache[admin] = backend
    return backend


__all__ = ["BUCKET", "get_card_hub_client", "get_storage_backend"]
