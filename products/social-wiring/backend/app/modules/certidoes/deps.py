"""DI seams for the `certidoes` module.

Same two seams every document-touching module in this product declares — the
schema-scoped client and the blob backend — wrapped in this module's OWN
zero-arg functions for the two reasons `imovel_hub/deps.py` records:
`get_scoped_admin_client(schema=...)` has a defaulted parameter FastAPI would
expose as a query parameter, and `app.dependency_overrides` keys on the
function object, so a distinct wrapper is what lets a test stub this module's
client without also re-pointing `card_hub`'s or `imovel_hub`'s.

🔴 WHY THE SERVICE-ROLE CLIENT AND NOT `get_user_client(token)`
---------------------------------------------------------------
The ERP router read through the caller's JWT-bound client and switched to the
admin client only for the background half. That worked there because its RLS
was `created_by = auth.uid()` on ALL commands. Migration 091 scopes reads to
the org and routes every WRITE through service-role (see its header), which is
the shape every other table in this schema uses — so a user-client insert would
simply be refused.

The org boundary therefore lives in application code: every query in
`service.py` and `routers/certidoes.py` carries an explicit
`.eq("org_id", str(org_id))` against the org the auth dep resolved. That is the
same posture `imovel_hub` / `card_hub` / `pipeline` already run on, and the
reason `table_reads.paged_rows` takes `org_id` as a required positional.
"""
from __future__ import annotations

import weakref
from typing import Any

from noctusai_lib.integrations.storage import (
    FakeStorageBackend,
    StorageBackend,
    make_storage_backend,
)

from app.dependencies import get_admin_client, get_scoped_admin_client


def get_certidoes_client() -> Any:
    """FastAPI dependency — the `social_wiring`-scoped admin client."""
    return get_scoped_admin_client()


#: Certidões live in the SAME bucket as client and imóvel documents, under
#: their own path prefix. A second bucket would need its own object-RLS
#: policies and its own retention wiring for no gain — the separation that
#: matters is the key prefix, which is what the policies actually match on.
BUCKET = "social-wiring-documentos"

#: The path segment after the org id. Keys read `{org_id}/certidoes/{consulta_id}/{file}`.
PREFIXO = "certidoes"

_storage_cache: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()


def storage_for(client: Any) -> StorageBackend:
    """The blob backend for a RAW supabase client.

    Split out of the FastAPI dependency below because the background half of
    this module (the TJSP scheduler, the recovery sweep) needs a backend too
    and has no request to resolve a dependency from.

    A client with no `.storage` attribute is the sqlite/mock local-dev
    fallback, which has no Supabase Storage surface at all — it gets a
    `FakeStorageBackend`. That is a stated fallback for a known environment,
    not a silent one: the alternative is an `AttributeError` an hour into a
    scheduled sweep.
    """
    cached = _storage_cache.get(client)
    if cached is not None:
        return cached
    if not hasattr(client, "storage"):
        backend: StorageBackend = FakeStorageBackend()
    else:
        backend = make_storage_backend(kind="supabase", client=client)
    _storage_cache[client] = backend
    return backend


def get_storage_backend() -> StorageBackend:
    """FastAPI dependency — blob storage for certidão PDFs.

    Bound to the RAW admin client, not `get_certidoes_client()`: `.storage`
    lives on the top-level Supabase client and never on a `.schema(...)`-derived
    proxy.

    Tests MUST override this seam with a `FakeStorageBackend` rather than
    relying on the mock fallback — `MockSupabaseClient.storage` is a bare
    `MagicMock()` that answers ANY call with another MagicMock, so an
    un-overridden test would silently "succeed" against garbage.
    """
    return storage_for(get_admin_client())


__all__ = [
    "BUCKET",
    "PREFIXO",
    "get_certidoes_client",
    "get_storage_backend",
    "storage_for",
]
