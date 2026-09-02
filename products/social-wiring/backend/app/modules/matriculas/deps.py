"""DI seams for the `matriculas` module.

The transcriber is exposed as a FACTORY rather than an instance, mirroring
`imovel_hub.deps.get_matricula_extractor_factory` / `card_hub.deps.
get_identity_extractor_factory` and for the same reason: the transcriber is
org-bound (per-org LLM key resolution + budget accounting) while the
dependency resolves once per request, and the transcription itself runs
detached, after the response is already sent.

The admin client is wrapped in a zero-arg function rather than used
directly, for the two reasons `imovel_hub/deps.py` records: a defaulted
`schema` parameter would surface as a query parameter on every route, and
`app.dependency_overrides` keys on the function OBJECT, so a distinct
wrapper per module is what lets a test stub this module's client without
re-pointing another's.
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from noctusai_lib.integrations.documents import (
    DocumentTranscriber,
    make_document_transcriber,
)

from app.dependencies import get_admin_client, get_scoped_admin_client

#: `(org_id | None) -> DocumentTranscriber`.
TranscriberFactory = Callable[[Optional[str]], DocumentTranscriber]


def get_matriculas_client() -> Any:
    """FastAPI dependency — the `social_wiring`-scoped admin client.

    Used for the DETACHED half of the work only (the background task and
    the recovery sweep), never for the request path: the request path goes
    through the caller's own token so RLS — not application code — decides
    which org's rows are reachable. See `router.py`'s module docstring.
    """
    return get_scoped_admin_client()


def get_background_client() -> Any:
    """The raw admin client the background task writes through.

    A background task outlives the request that spawned it, so it cannot
    use the caller's token: by the time a long vision pass finishes the
    token may be expired, and the write would fail with nothing left to
    report it to. Service-role bypasses RLS, which is exactly why every
    write in `service.py` carries an explicit `org_id` predicate.
    """
    return get_admin_client()


def get_transcriber_factory() -> TranscriberFactory:
    """FastAPI dependency — builds the seed transcriber for one org.

    Tests MUST override this seam. The real transcriber can reach a vision
    model: an un-overridden test would either hit a provider or fail on a
    missing key, and neither is the behaviour under test.
    """
    return lambda org_id: make_document_transcriber(real=True, org_id=org_id)


__all__ = [
    "TranscriberFactory",
    "get_background_client",
    "get_matriculas_client",
    "get_transcriber_factory",
]
