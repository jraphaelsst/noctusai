"""DI seams for the `empresas` module.

Same shape `imovel_hub/deps.py` documents: the canonical `app.dependencies.
get_scoped_admin_client` wrapped zero-arg (FastAPI would otherwise expose its
defaulted `schema=` as a query param), and a separate function object per
module so `app.dependency_overrides` can stub THIS module's client without
re-pointing `card_hub`'s or `imovel_hub`'s.
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


def get_empresas_client() -> Any:
    """FastAPI dependency — the `social_wiring`-scoped admin client."""
    return get_scoped_admin_client()


#: Documents live in the SAME bucket as client/imóvel documents, under their
#: own path prefix — see `documento_store.DocumentoStore`'s own docstring
#: for why the org-first key segment is what the storage policy matches on.
BUCKET = "social-wiring-documentos"
PREFIXO = "empresas"

_storage_cache: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()


def get_storage_backend() -> StorageBackend:
    """FastAPI dependency — blob storage for empresa documents (Cartão CNPJ).

    Tests MUST override this with a `FakeStorageBackend`
    (`KB § PATTERNS/backend/di-test-seam.md` Class-B) — `MockSupabaseClient.
    storage` is a bare `MagicMock()` that would silently "succeed" against
    garbage signed URLs otherwise.
    """
    admin = get_admin_client()
    cached = _storage_cache.get(admin)
    if cached is not None:
        return cached
    if not hasattr(admin, "storage"):
        backend: StorageBackend = FakeStorageBackend()
    else:
        backend = make_storage_backend(kind="supabase", client=admin)
    _storage_cache[admin] = backend
    return backend


def get_cartao_extractor_factory():
    """FastAPI dependency — the Cartão CNPJ extractor factory.

    Reuses `card_hub.deps.get_identity_extractor_factory()` verbatim rather
    than building a second one: its widened routing (P0c contract §C2,
    `_FACTORY_SHAPED_EXTRATORES`) already resolves `tipo_documento=
    'cartao_cnpj'` to `make_cartao_cnpj_extractor` — a second factory here
    would only be a duplicate of that same routing decision, one more seam
    to keep in step with it.

    Tests MUST override this (`ScriptedCartaoCnpjExtractor` /
    `FakeCartaoCnpjExtractor` — `tests/support/fake_documents_p0c.py`) —
    the real one resolves an org's vision credentials and can reach a
    provider.
    """
    from app.modules.card_hub.deps import get_identity_extractor_factory

    return get_identity_extractor_factory()


def get_empresa_notification_service() -> Any:
    """FastAPI dependency — the admin notifier for `empresa_campo_
    conflitos` rows (contract §H6). Built exactly like `imovel_hub.deps.
    get_imovel_notification_service` — `build_notification_service(admin)`,
    a separate function object so a test can override this module's
    notifier without re-pointing `card_hub`'s or `imovel_hub`'s."""
    from app.services.notification_service import build_notification_service

    return build_notification_service(get_admin_client())


__all__ = [
    "BUCKET",
    "PREFIXO",
    "get_cartao_extractor_factory",
    "get_empresa_notification_service",
    "get_empresas_client",
    "get_storage_backend",
]
