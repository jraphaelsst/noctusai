"""Visual-asset storage for IgIg — Módulo 4.

Consumes the seed's storage seam (`noctusai_lib.integrations.storage`), which
already ships the same Protocol + Fake + Real + factory shape as the
persistence seam: `SupabaseStorageBackend` in production,
`LocalFilesystemStorageBackend` for native dev, `FakeStorageBackend` in tests.
Nothing bespoke is written here — the product only chooses a backend and owns
its key layout.

The DB stores a storage KEY, never bytes (see `igig.peca`), so swapping
backends changes this module and nothing else.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path

from noctusai_lib.integrations.storage import StorageBackend, make_storage_backend

from app.config import settings
from app.database import get_admin_client

logger = logging.getLogger(__name__)

__all__ = ["get_storage", "chave_da_peca", "reset_storage"]


@lru_cache(maxsize=1)
def get_storage() -> StorageBackend:
    """The process's storage backend, built once.

    Cached because the Supabase backend holds a client. `kind` comes from
    config so tests can select `fake` without patching anything.
    """
    kind = settings.igig_storage_kind
    backend = make_storage_backend(
        kind=kind,  # type: ignore[arg-type]
        root_dir=Path(settings.igig_storage_root) if kind == "local" else None,
        client=get_admin_client() if kind == "supabase" else None,
    )
    logger.info("igig storage backend: %s (kind=%s)", type(backend).__name__, kind)
    return backend


def chave_da_peca(org_id: str, pauta_id: str, nome_arquivo: str) -> str:
    """Key layout for an uploaded peça.

    Org-first so a storage-level policy (or a bucket listing) can be scoped
    per tenant without parsing the rest of the path.
    """
    seguro = Path(nome_arquivo).name  # strip any traversal the client sent
    return f"{org_id}/pautas/{pauta_id}/{seguro}"


def reset_storage() -> None:
    """Drop the cached backend. Tests only."""
    get_storage.cache_clear()
