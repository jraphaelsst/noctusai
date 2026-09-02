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
from dataclasses import dataclass
from typing import Any, Callable

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



# ─── The service surface, as an injectable object ────────────────────
#
# 🔴 WHY THE ROUTER DOES NOT CALL `service.*` DIRECTLY
# -----------------------------------------------------
# It used to, and the tests then had to reach into `app.modules.certidoes.
# service` and swap functions out with `patch.object` to stop a route from
# firing the real InfoSimples pipeline. That is the self-monkeypatch class
# CLAUDE.md § 1 forbids, and for a reason worth restating: a test that
# replaces our function is no longer exercising the wiring it claims to
# cover, and the replacement leaks to every other test in the process.
#
# The honest seam is the one below. The router receives its collaborator
# instead of reaching for a module global; production always gets
# `_DEFAULT_SERVICE` (every field the real function); a test overrides
# `get_certidoes_service` via `app.dependency_overrides` with a
# `dataclasses.replace(...)` of it, substituting the ONE operation under
# test and keeping the rest real. Nothing in the production module is ever
# mutated, so nothing leaks.
#
# Fields hold plain functions rather than being methods: `replace(svc,
# processar_consulta=fake)` is then a one-liner per test, and the type of
# each field documents the operation's shape.
# → KB § PATTERNS/backend/di-test-seam.md (seam 1, DI kwarg/object)


@dataclass(frozen=True)
class CertidoesService:
    """Every service-layer operation the HTTP layer invokes.

    One object rather than eleven separate dependencies: the router needs
    most of them per request, and a test that substitutes one wants the
    other ten to stay real.
    """

    check_required_credentials: Callable
    processar_consulta: Callable
    schedule_tjsp_for_org: Callable
    status_counts_por_consulta: Callable
    recover_stale_processando: Callable
    read_certidao_bytes: Callable
    delete_storage_files: Callable
    process_manual_upload: Callable
    cancelar_processamento: Callable
    queued_tjsp_for_org: Callable
    tjsp_cooldown_status: Callable


def _build_default_service() -> CertidoesService:
    """The production wiring — every field the real service function.

    Built lazily inside a function (not at import) so `deps` does not import
    `service` at module scope: `service` imports `deps` for `BUCKET`/`PREFIXO`,
    and a module-level import here would close that cycle.
    """
    from app.modules.certidoes import service

    return CertidoesService(
        check_required_credentials=service.check_required_credentials,
        processar_consulta=service.processar_consulta,
        schedule_tjsp_for_org=service.schedule_tjsp_for_org,
        status_counts_por_consulta=service.status_counts_por_consulta,
        recover_stale_processando=service.recover_stale_processando,
        read_certidao_bytes=service.read_certidao_bytes,
        delete_storage_files=service.delete_storage_files,
        process_manual_upload=service.process_manual_upload,
        cancelar_processamento=service.cancelar_processamento,
        queued_tjsp_for_org=service.queued_tjsp_for_org,
        tjsp_cooldown_status=service.tjsp_cooldown_status,
    )


_default_service: CertidoesService | None = None


def get_certidoes_service() -> CertidoesService:
    """FastAPI dependency — the service operations this router invokes.

    Tests override this seam rather than patching `service.*`::

        svc = dataclasses.replace(
            build_default_service(), processar_consulta=fake
        )
        app.dependency_overrides[get_certidoes_service] = lambda: svc
    """
    global _default_service
    if _default_service is None:
        _default_service = _build_default_service()
    return _default_service


def build_default_service() -> CertidoesService:
    """A FRESH all-real service object — the base a test calls
    `dataclasses.replace(...)` on. Deliberately not the cached singleton, so
    a test can never mutate what production hands out."""
    return _build_default_service()


__all__ = [
    "BUCKET",
    "CertidoesService",
    "build_default_service",
    "get_certidoes_service",
    "PREFIXO",
    "get_certidoes_client",
    "get_storage_backend",
    "storage_for",
]
