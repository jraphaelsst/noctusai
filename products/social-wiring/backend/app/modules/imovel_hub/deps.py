"""DI seams for the `imovel_hub` module.

🔴 THE SCOPED CLIENT IS **NOT** A FOURTH COPY.
`app.dependencies.get_scoped_admin_client` is the canonical, already-cached
schema-scoped client — its own docstring records the three local copies
(`leads/deps`, `portal_roi_service`, `clientes_router`) that it formalized
and deliberately did not migrate. `card_hub/deps.py` wrote a fourth before
it existed. This module consumes the canonical one instead.

It is wrapped in a zero-arg function rather than used directly, for two
reasons that both matter:

1. `get_scoped_admin_client(schema="social_wiring")` has a defaulted
   parameter, and FastAPI would read that as a **query parameter** named
   `schema` on every route depending on it — a silent API-surface leak.
2. `app.dependency_overrides` keys on the function OBJECT. A distinct
   wrapper per slice is what lets a test stub this module's client without
   also re-pointing `card_hub`'s.
"""
from __future__ import annotations

import weakref
from dataclasses import dataclass
from typing import Any, Callable, Optional

from noctusai_lib.integrations.documents import (
    MatriculaExtractor,
    make_matricula_extractor,
)
from noctusai_lib.integrations.storage import (
    FakeStorageBackend,
    StorageBackend,
    make_storage_backend,
)

from app.dependencies import get_admin_client, get_scoped_admin_client
from app.services.api_keys_store import resolve_vision_provider


def get_imovel_hub_client() -> Any:
    """FastAPI dependency — the `social_wiring`-scoped admin client."""
    return get_scoped_admin_client()


#: Documents live in the SAME bucket as client documents, under a different
#: path prefix. A second bucket would need its own object-RLS policies and
#: its own retention wiring for no gain — the separation that matters is the
#: key prefix, which is what the policies actually match on.
BUCKET = "social-wiring-documentos"

_storage_cache: "weakref.WeakKeyDictionary[Any, Any]" = weakref.WeakKeyDictionary()


def get_storage_backend() -> StorageBackend:
    """FastAPI dependency — blob storage for imóvel documents.

    Same shape as `card_hub.deps.get_storage_backend`, and bound to the RAW
    admin client for the same reason: `.storage` lives on the top-level
    Supabase client, never on a `.schema(...)`-derived proxy.

    Tests MUST override this seam with a `FakeStorageBackend` rather than
    relying on the sqlite/mock fallback — `MockSupabaseClient.storage` is a
    bare `MagicMock()` that answers ANY call with another MagicMock, so an
    un-overridden test would silently "succeed" against garbage signed URLs
    instead of failing loudly.
    """
    admin = get_admin_client()
    cached = _storage_cache.get(admin)
    if cached is not None:
        return cached
    if not hasattr(admin, "storage"):
        # sqlite local-dev fallback — no Supabase Storage surface at all.
        backend: StorageBackend = FakeStorageBackend()
    else:
        backend = make_storage_backend(kind="supabase", client=admin)
    _storage_cache[admin] = backend
    return backend


MatriculaExtractorFactory = Callable[[Optional[str]], MatriculaExtractor]


def _build_matricula_extractor(org_id: Optional[str]) -> MatriculaExtractor:
    """One org's matrícula extractor, with ITS manually-selected vision
    provider — mirrors `card_hub.deps._build_identity_extractor` /
    `matriculas.deps._build_transcriber`.

    Before this wiring existed, `make_matricula_extractor` was called with
    no `provider=` at all, so an org's `llm_vision_provider` setting was
    silently ignored here exactly as it was in `card_hub` — the SAME gap,
    on the sibling extractor that shares `DocumentTextLadder`.
    """
    return make_matricula_extractor(
        real=True, org_id=org_id, provider=resolve_vision_provider(org_id)
    )


def get_matricula_extractor_factory() -> MatriculaExtractorFactory:
    """FastAPI dependency — builds the matrícula extractor for one org.

    A FACTORY rather than an instance, mirroring
    `card_hub.deps.get_identity_extractor_factory`: the extractor is
    org-bound (per-org LLM key resolution + budget accounting) while the
    dependency resolves once per request, and the extraction itself runs
    detached after the response is sent.

    Tests MUST override this seam with a `FakeMatriculaExtractor`. The real
    one can reach a vision model: an un-overridden test would either hit a
    provider or fail on a missing key, and neither is the behaviour under
    test.
    """
    return _build_matricula_extractor


@dataclass(frozen=True)
class EstruturaSeams:
    """The two IO legs of `documentos_service.extrair_estrutura` (migration
    118) — text off the bytes, fields off the text. `None` = the real ones
    (`_extrair_texto` / `_analisar_estrutura`), which resolve credentials
    and can reach a transcription/LLM provider."""

    extract_text: Optional[Callable[..., Any]] = None
    analyze_estrutura: Optional[Callable[..., Any]] = None


def get_estrutura_seams() -> EstruturaSeams:
    """FastAPI dependency — the structured read's IO seams.

    Tests MUST override this (the `fake_extractor` fixtures do), for the
    same reason `get_matricula_extractor_factory` must be: the real legs
    resolve an org's credentials and can reach a provider, so an
    un-overridden upload test was reaching out of the sandbox (found
    2026-09-22 while wiring the structured read into `/api/matriculas/
    extrair`)."""
    return EstruturaSeams()


def get_imovel_notification_service() -> Any:
    """FastAPI dependency — the notifier for `imovel_campo_conflitos`
    (migration 154, D1). Built exactly like `matriculas.deps.
    get_notification_service` (`build_notification_service(admin)`); a
    separate function object so a test can override this module's notifier
    without re-pointing the matrículas one (`dependency_overrides` keys on
    the function)."""
    from app.services.notification_service import build_notification_service

    return build_notification_service(get_admin_client())


__all__ = [
    "BUCKET",
    "EstruturaSeams",
    "get_estrutura_seams",
    "get_imovel_notification_service",
    "MatriculaExtractorFactory",
    "get_imovel_hub_client",
    "get_matricula_extractor_factory",
    "get_storage_backend",
]
