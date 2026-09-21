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
from typing import Any, Callable, Optional

from noctusai_lib.integrations.documents import (
    IdentityExtractor,
    make_identity_extractor,
)
from noctusai_lib.integrations.signature import SignatureAdapter, make_signature_adapter
from noctusai_lib.integrations.storage import (
    FakeStorageBackend,
    StorageBackend,
    make_storage_backend,
)

from app.dependencies import get_admin_client
from app.services.api_keys_store import resolve_vision_provider

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


ExtractorFactory = Callable[[Optional[str]], IdentityExtractor]


def _build_identity_extractor(org_id: Optional[str]) -> IdentityExtractor:
    """One org's identity extractor, with ITS manually-selected vision
    provider — mirrors `matriculas.deps._build_transcriber` exactly.

    🔴 THE PROVIDER IS RESOLVED PER EXTRACTION, NOT PER PROCESS.
    `resolve_vision_provider` is called here — inside the factory — so a
    switch flipped in Settings takes effect on the very next upload, not on
    the next deploy.

    There is NO fallback: if the selected vendor's key is missing or its
    account is empty, the extraction fails saying so. Before this wiring
    existed, `make_identity_extractor` was called with no `provider=` at
    all, so an org's `llm_vision_provider` setting was silently ignored and
    every identity read kept hitting OpenAI regardless — the exact defect
    that stranded `social_wiring.cliente_documentos` rows behind OpenAI's
    2026-09-17 quota exhaustion while the org's Anthropic key sat unused.
    """
    return make_identity_extractor(
        real=True, org_id=org_id, provider=resolve_vision_provider(org_id)
    )


def get_identity_extractor_factory() -> ExtractorFactory:
    """FastAPI dependency — builds the identity extractor for one org.

    A FACTORY rather than an instance because the extractor is org-bound
    (per-org LLM key resolution + budget accounting) while the dependency is
    resolved once per request, and because the extraction itself runs as a
    detached background task after the response is sent.

    Tests MUST override this seam
    (`app.dependency_overrides[get_identity_extractor_factory] = ...`)
    with a `FakeIdentityExtractor`
    (`KB § PATTERNS/backend/di-test-seam.md` Class-B). The real one calls a
    vision model: an un-overridden test would either hit a provider or fail
    on a missing key, and neither is the behaviour under test.
    """
    return _build_identity_extractor


SignatureAdapterFactory = Callable[[Optional[str]], SignatureAdapter]


def get_signature_adapter_factory() -> SignatureAdapterFactory:
    """FastAPI dependency — builds the e-signature adapter for one org.

    A FACTORY rather than an instance for the same reason
    `get_identity_extractor_factory` is one, plus a second: building the
    real D4Sign adapter (`real=True`) can raise `ProvedorNaoConfigurado`,
    and that has to surface at the EXACT point `assinatura_service` is
    about to call the provider — after every 400/404/409/422(versão)
    precondition it checks first (contract §3.1's error-table order). If
    this dependency built the adapter eagerly here, a credential-less org
    would see 422 before a genuinely malformed request's own 400, which is
    the wrong error to show first.

    Tests MUST override this seam
    (`app.dependency_overrides[get_signature_adapter_factory] = ...`) with
    one returning a `FakeSignatureAdapter`
    (`KB § PATTERNS/backend/di-test-seam.md` Class-B). The real one calls
    D4Sign: an un-overridden test would either hit the provider or 422 on
    missing credentials, and neither is the behaviour under test.
    """
    return lambda org_id: make_signature_adapter(real=True, org_id=org_id)


__all__ = [
    "BUCKET",
    "ExtractorFactory",
    "SignatureAdapterFactory",
    "get_card_hub_client",
    "get_identity_extractor_factory",
    "get_signature_adapter_factory",
    "get_storage_backend",
]
