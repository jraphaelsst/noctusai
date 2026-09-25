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


#: P0c contract §C2: widened from `IdentityExtractor` alone — two `Fonte`s
#: now route THIS factory to a differently-shaped extractor (`CrednetExtractor`
#: / `CartaoCnpjExtractor`, see `_FACTORY_SHAPED_EXTRATORES` below), which
#: share the CALLING convention (`.extract(bytes, *, mimetype=, filename=)`)
#: but not the return-type Protocol.
ExtractorFactory = Callable[[Optional[str], Optional[str]], Any]

#: `Fonte.extrator` dotted paths that are — like `make_identity_extractor`
#: itself — a `make_*_extractor(*, real, org_id, provider, max_pages=None)`
#: FACTORY, callable with exactly the same three keyword args this module
#: already resolves for the identity extractor. `_build_identity_extractor`
#: routes a `tipo_documento` here when its `Fonte.extrator` is one of these
#: — NOT merely "is not the identity factory": `comprovante_endereco`'s own
#: `Fonte.extrator` (`documents.address.find_endereco`) is a PURE text
#: parser, `(text: str) -> EnderecoLido`, no `real=`/`org_id=`/`provider=`
#: kwargs at all — routing it here would call it with the wrong signature
#: and it is not what reads an address upload anyway (`extrair_identidade`
#: reads `IdentityFields.endereco` off the SAME identity extractor;
#: `find_endereco` is a different, unrelated consumer of this catalog).
_FACTORY_SHAPED_EXTRATORES: frozenset[str] = frozenset(
    {
        "noctusai_lib.integrations.documents.serasa_crednet.make_crednet_extractor",
        "noctusai_lib.integrations.documents.cartao_cnpj.make_cartao_cnpj_extractor",
        # S2 contract `sw-negociacao-extracao-contract.md` §D/§E1 — the same
        # `(*, real, org_id, provider)` factory calling convention; page
        # targeting (`janela_paginas`/`max_paginas_visao`) is each factory's
        # OWN default, never resolved here.
        "noctusai_lib.integrations.documents.guia_itbi.make_guia_itbi_extractor",
        (
            "noctusai_lib.integrations.documents.financiamento_imobiliario"
            ".make_proposta_financiamento_extractor"
        ),
        (
            "noctusai_lib.integrations.documents.financiamento_imobiliario"
            ".make_contrato_financiamento_extractor"
        ),
    }
)


def _build_identity_extractor(
    org_id: Optional[str],
    tipo_documento: Optional[str] = None,
    *,
    resolve_provider: Callable[[Optional[str]], str] = resolve_vision_provider,
) -> Any:
    """One org's extractor for ONE document type, with ITS manually-selected
    vision provider AND (for the identity family) the page cap ITS DOCUMENT
    TYPE requires.

    🔴 P0c contract §C2 — WIDENED: for `serasa_crednet` / `cartao_cnpj`, this
    resolves `fontes.FONTES[tipo_documento].extrator` (via `fontes.
    resolver_extrator`) and calls THAT factory instead of `make_identity_
    extractor` — see `_FACTORY_SHAPED_EXTRATORES`' docstring for exactly
    which tipos qualify and why `comprovante_endereco` deliberately does
    not. Both factories default `max_pages=None` (every page) on their own,
    so this branch passes none — `serasa_crednet`'s own contract already
    wants that (§B: "participações can sit on page 2"), and passing nothing
    lets each factory's own default apply rather than reusing the identity
    family's `-1`-sentinel convention (`paginas_maximas`), which is not
    these factories' contract.

    One org's identity extractor, with ITS manually-selected vision
    provider AND the page cap ITS DOCUMENT TYPE requires.

    🔴 THE PROVIDER IS RESOLVED PER EXTRACTION, NOT PER PROCESS.
    `resolve_provider` (bound to `resolve_vision_provider` by default) is
    called here — inside the factory — so a switch flipped in Settings
    takes effect on the very next upload, not on the next deploy. Mirrors
    `matriculas.deps._build_transcriber` for this half. This was already
    true before `tipo_documento` existed on this factory — resolving the
    provider once per factory construction is UNCHANGED behaviour, not
    something this fix added; the factory is still built once per request
    (or once per stalled row, in the sweep), exactly as before.

    There is NO fallback for the provider: if the selected vendor's key is
    missing or its account is empty, the extraction fails saying so. Before
    this wiring existed, `make_identity_extractor` was called with no
    `provider=` at all, so an org's `llm_vision_provider` setting was
    silently ignored and every identity read kept hitting OpenAI regardless
    — the exact defect that stranded `social_wiring.cliente_documentos` rows
    behind OpenAI's 2026-09-17 quota exhaustion while the org's Anthropic key
    sat unused.

    `resolve_provider` is an injectable collaborator
    (`KB § PATTERNS/backend/di-test-seam.md`, "inject the collaborator")
    for exactly one reason: `resolve_vision_provider`'s tier-1 lookup
    (`resolve_api_key_detail` -> `build_api_key_store()` ->
    `get_admin_client()`) constructs a REAL Supabase client whenever no
    `store=` override reaches it, and that constructor raises
    (`SupabaseException: supabase_url is required`) in any environment with
    no Supabase config — CI included. A test that calls this factory
    directly (to prove `tipo_documento` -> `max_pages` without going through
    a whole HTTP request) needs a way to skip that chain entirely; a fake
    `resolve_provider=lambda org_id: "openai"` does that without touching
    live credentials, real or fake HTTP, or `resolve_vision_provider`'s own
    internals. No real caller passes this override — every real caller
    keeps the default, so production resolution is untouched.

    🔴 `tipo_documento` CLOSES THE OTHER GAP THE SAME COMMIT FOUND.
    Both real callers of `extrair_identidade` (the upload route and the
    recovery sweep) pre-build the extractor through this factory BEFORE
    `extrair_identidade` ever loads the document row — so
    `extrair_identidade`'s own `extractor or make_identity_extractor(...,
    max_pages=paginas_maximas(tipo_documento))` fallback always
    short-circuits in production and the type-driven page cap never ran.
    `paginas_maximas` stays the ONE place that policy lives
    (`identidade_extracao_service.TIPOS_LEITURA_INTEGRAL`); this factory
    only looks it up, keyed on the type its caller already has in hand.

    The import is deferred, not module-level: `identidade_extracao_service`
    imports `BUCKET` from THIS module, and importing it back at module scope
    here would close that cycle — same shape, same reason, as
    `certidoes.deps._build_default_service`'s own lazy `import service`.

    `tipo_documento=None` (or any type outside `TIPOS_LEITURA_INTEGRAL`)
    resolves to `paginas_maximas`'s own "not specified" sentinel (`-1`),
    which lets the seed adapter apply its unchanged 3-page default —
    behaviour-preserving for every type that does not need a whole read.
    """
    from app.modules.card_hub.proveniencia import fontes

    fonte = fontes.FONTES.get(str(tipo_documento or ""))
    if fonte is not None and fonte.extrator in _FACTORY_SHAPED_EXTRATORES:
        fabrica = fontes.resolver_extrator(fonte)
        return fabrica(real=True, org_id=org_id, provider=resolve_provider(org_id))

    from app.modules.card_hub.identidade_extracao_service import paginas_maximas

    return make_identity_extractor(
        real=True,
        org_id=org_id,
        max_pages=paginas_maximas(str(tipo_documento or "")),
        provider=resolve_provider(org_id),
    )


def get_identity_extractor_factory() -> ExtractorFactory:
    """FastAPI dependency — builds the identity extractor for one org AND
    one document type.

    A FACTORY rather than an instance because the extractor is org-bound
    (per-org LLM key resolution + budget accounting) — AND, since this fix,
    type-bound (the page-cap policy) — while the dependency is resolved once
    per request, and because the extraction itself runs as a detached
    background task after the response is sent. Callers pass
    `(org_id, tipo_documento)`; `tipo_documento` may be omitted (`None`)
    only where the caller has not resolved the document row yet — every real
    caller in this module has it in hand by the time it builds the
    extractor.

    Tests MUST override this seam
    (`app.dependency_overrides[get_identity_extractor_factory] = ...`)
    with a `FakeIdentityExtractor`
    (`KB § PATTERNS/backend/di-test-seam.md` Class-B). The real one calls a
    vision model: an un-overridden test would either hit a provider or fail
    on a missing key, and neither is the behaviour under test.
    """
    return _build_identity_extractor


def get_conflict_notification_service() -> Any:
    """FastAPI dependency — the admin notifier for `cliente_campo_conflitos`
    rows an identity extraction opens (owner decision D1: a machine value
    that disagrees with the record is a conflict AND a notification).

    Built exactly like `matriculas.deps.get_notification_service` —
    `build_notification_service(get_admin_client())`, the one construction
    path — and handed to the background task, which outlives the request
    (hence the admin client, never the caller's token). Resolves
    NOC-REMEDIATE[identidade-conflito-notificacao]. Tests override it
    (`app.dependency_overrides`) with a recording fake.
    """
    from app.services.notification_service import build_notification_service

    return build_notification_service(get_admin_client())


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


def card_hub_config() -> Any:
    """The social-wiring `CardHubConfig` (`app.modules.card_hub.config.CARD_HUB`).

    The ONE deferred import of it: `config` composes this module's own
    collaborators (the SW timeline gatherers in `timeline_service`, the
    identity-extraction hook in `identidade_extracao_service`), and those
    import the thin seed shims (`services`, `documentos_service`, ...) that
    need the config back — a module-level import in either direction would
    close that cycle. Same shape, same reason, as
    `_build_identity_extractor`'s own lazy import above. Resolved per call
    (a `sys.modules` lookup after the first), never cached here.
    """
    from app.modules.card_hub.config import CARD_HUB

    return CARD_HUB


__all__ = [
    "BUCKET",
    "card_hub_config",
    "ExtractorFactory",
    "SignatureAdapterFactory",
    "get_card_hub_client",
    "get_conflict_notification_service",
    "get_identity_extractor_factory",
    "get_signature_adapter_factory",
    "get_storage_backend",
]
