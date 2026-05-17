"""WAHA response-shape registry — observability side-car.

Promoted per the in-home manifest
`projects/social-wiring-absorption/reference/.promotions/waha-response-registry.md`
(originally the `waha_response_registry` service of the retired
`youtube-crawler` product, consolidated into `social-wiring` 2026-05-16).

Why this exists
---------------
WAHA responses vary across versions AND engines (WEBJS vs NOWEB). The
session-status endpoint alone may return a session object, a bare
status string, or a list. Hard-coding ONE envelope shape is fragile.
This registry captures every observed shape with a stable fingerprint
+ an operator handling note, so future schema drift is *visible*
(``SELECT *`` the samples and see every variant) instead of producing
a silent mis-parse.

WAHA response shapes observed live (reproduced here because the
workspace ``backend/WAHA_RESPONSE_FORMATS.md`` is NOT in-home — Wave 2
product-port MUST carry that file forward):

  - ``GET /api/sessions/{s}``  → ``{"name": "...", "status": "WORKING", ...}``
  - ``GET /api/sessions``      → ``[{"name": ..., "status": ...}, ...]``
  - bare status (older WAHA)   → ``"WORKING"`` (string, not an object)
  - ``POST /api/sendText``     → ``{"_data": {"id": {"remote": "<jid>@c.us"}}, ...}``
  - inbound webhook media      → ``payload.media.url ==
    "<WAHA_EXTERNAL_BASE>/api/files/<session>/<id>.<ext>"``

Six-layer rationale (from the manifest): integration adapter side-car
— observability for the WAHA HTTP surface, adjacent to the WAHA client
+ adapters that live in `noctusai_lib.integrations.whatsapp` per
`KB § PATTERNS/whatsapp-chatbot-seed.md`.

Shape: Protocol + Fake + Real + factory per
`KB § PATTERNS/seed-fake-real-adapter.md`. Real persists samples (one
row per distinct fingerprint per ``source``/``direction``); Fake keeps
an in-memory dict keyed by fingerprint for unit tests that exercise
WAHA error paths without polluting the dev DB. The persistence side
(SQLite/Supabase schema) is the consumer's — the Real here delegates
to an injected ``ResponseSampleSink`` so the registry stays storage-
agnostic (the chatbot ``message_store`` seam, or a product table).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


def fingerprint_response(payload: Any) -> str:
    """Stable, vendor-neutral structural fingerprint of a JSON value.

    Captures the *shape* (key names + nesting + container types), NOT
    the values — two responses with the same structure but different
    data fingerprint identically, so a registry row is created once per
    distinct shape. Lists fingerprint by their first element's shape
    (homogeneous-list assumption holds for WAHA collection endpoints).
    """
    skeleton = _skeleton(payload)
    canonical = json.dumps(skeleton, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def _skeleton(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _skeleton(v) for k, v in sorted(value.items())}
    if isinstance(value, list):
        return ["[]" if not value else _skeleton(value[0])]
    return type(value).__name__


@dataclass(frozen=True)
class ResponseSample:
    """One observed WAHA response shape."""

    fingerprint: str
    source: str
    """WAHA endpoint / event family (``session_status``, ``send_text``,
    ``inbound_webhook`` …) — WAHA-specific but pluggable per the
    manifest's seed-first note."""
    direction: str
    """``inbound`` | ``outbound`` — relative to the app."""
    handling_note: str
    """Operator-facing note: how this shape is parsed / what changed."""
    example: dict[str, Any] | None = None


@runtime_checkable
class ResponseSampleSink(Protocol):
    """Storage seam the Real registry persists samples through.

    Kept storage-agnostic (the manifest: "migration goes through
    noctusai_lib's shared-schema mechanism OR stays per-product"). The
    consumer wires a product table / the chatbot message_store seam.
    """

    def upsert_sample(self, sample: ResponseSample) -> None: ...

    def known_fingerprints(self) -> set[str]: ...


@runtime_checkable
class ResponseRegistry(Protocol):
    """Records every distinct WAHA response shape exactly once.

    ``record(...)`` returns ``True`` when the shape is NEW (drift /
    first observation — worth an operator glance), ``False`` when it's
    a fingerprint already on file.
    """

    def record(
        self,
        payload: Any,
        *,
        source: str,
        direction: str,
        handling_note: str = "",
    ) -> bool: ...


class FakeResponseRegistry:
    """In-memory registry (no persistence). The Fake half.

    Drops persistence, keeps a dict keyed by fingerprint — exactly the
    shape the manifest's promotion-step 3 asks for.
    """

    def __init__(self) -> None:
        self.samples: dict[str, ResponseSample] = {}

    def record(
        self,
        payload: Any,
        *,
        source: str,
        direction: str,
        handling_note: str = "",
    ) -> bool:
        fp = fingerprint_response(payload)
        if fp in self.samples:
            return False
        self.samples[fp] = ResponseSample(
            fingerprint=fp,
            source=source,
            direction=direction,
            handling_note=handling_note,
            example=payload if isinstance(payload, dict) else None,
        )
        return True

    def clear(self) -> None:
        """Reset between test cases."""
        self.samples.clear()


class PersistentResponseRegistry:
    """Persists distinct shapes through an injected sink. The Real half.

    Deduplicates against the sink's ``known_fingerprints()`` so a shape
    already on file is not re-written; a NEW shape is upserted and
    ``record`` returns ``True`` so the caller can log the drift.
    """

    def __init__(self, sink: ResponseSampleSink) -> None:
        self._sink = sink

    def record(
        self,
        payload: Any,
        *,
        source: str,
        direction: str,
        handling_note: str = "",
    ) -> bool:
        fp = fingerprint_response(payload)
        if fp in self._sink.known_fingerprints():
            return False
        self._sink.upsert_sample(
            ResponseSample(
                fingerprint=fp,
                source=source,
                direction=direction,
                handling_note=handling_note,
                example=payload if isinstance(payload, dict) else None,
            )
        )
        return True


def get_response_registry(
    *,
    sink: ResponseSampleSink | None = None,
) -> ResponseRegistry:
    """Return `PersistentResponseRegistry` when a sink is supplied;
    `FakeResponseRegistry` otherwise.

    Mirrors `get_whatsapp_client()` / `get_webhook_dedup()` factory
    shape per `KB § PATTERNS/seed-fake-real-adapter.md`. The presence
    of a storage sink is the configured-vs-not signal.
    """
    if sink is None:
        return FakeResponseRegistry()
    return PersistentResponseRegistry(sink)
