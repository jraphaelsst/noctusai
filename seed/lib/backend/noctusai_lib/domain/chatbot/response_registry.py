"""Vendor-neutral connector-response-shape registry.

A diagnostics primitive: record ONE representative JSON payload per
observed *response shape* of an external connector (WAHA, Twilio, a
CRM webhook, …) so drift in a vendor's payload structure is visible
without spamming storage with every duplicate-shaped sample. Runtime
code treats captured samples as compatibility context, never as strict
contracts.

Reconciled 2026-05-16 from the live-validated
`youtube-crawler/app/services/waha_response_registry.py`
(`projects/social-wiring-absorption/` W1.E1, manifest
`waha-response-registry`).

Reconcile decision (vendor split per project §3.7 — integrations are
independent seed modules):

  - The validated source was WAHA-and-SQLite-specific (it imported the
    product `settings`, gated on ``database_backend == "sqlite"``, and
    wrote to a `waha_response_samples` table). That **WAHA-specific
    SQLite sink is Engineer WHATSAPP's** (`noctusai_lib.integrations.
    whatsapp`) — it composes this generic seam.
  - What lands in seed here is the **vendor-neutral** core: the pure
    shape/fingerprint helpers (no IO, deterministic) + a
    `ResponseRegistry` Protocol + an in-memory `FakeResponseRegistry`
    + a factory. Per `KB § PATTERNS/seed-fake-real-adapter.md` the IO
    sink is the variable part; the shape-derivation is pure logic and
    is shared.

Composition contract for Engineer WHATSAPP (W1.E2): wrap a SQLite (or
Postgres) sink behind the :class:`ResponseRegistry` Protocol and reuse
:func:`json_shape` + :func:`shape_fingerprint` + :func:`sample_key`
verbatim — do NOT re-derive the shape algorithm vendor-side.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Protocol, runtime_checkable


def json_shape(value: Any) -> Any:
    """Deterministic structural skeleton of a JSON value.

    Recurses dicts (sorted keys), dedups list-element shapes (first 5),
    and collapses scalars to type tags (``"int"``/``"str"``/…). Two
    payloads with the same structure produce an identical shape — the
    basis for dedup. Pure; no IO."""
    if isinstance(value, dict):
        return {key: json_shape(value[key]) for key in sorted(value.keys())}
    if isinstance(value, list):
        if not value:
            return []
        seen: list[Any] = []
        for item in value[:5]:
            item_shape = json_shape(item)
            if item_shape not in seen:
                seen.append(item_shape)
        return seen
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    return "str"


def shape_fingerprint(shape: Any) -> str:
    """Stable 16-hex fingerprint of a :func:`json_shape` result."""
    shape_json = json.dumps(shape, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(shape_json.encode("utf-8")).hexdigest()[:16]


def sample_key(
    *,
    source: str,
    direction: str,
    fingerprint: str,
    event_type: str | None = None,
    http_status: int | None = None,
) -> str:
    """Composite dedup key — one stored sample per
    (source, direction, event_type, http_status, shape)."""
    return "|".join(
        [
            source,
            direction,
            event_type or "",
            str(http_status or ""),
            fingerprint,
        ]
    )


@runtime_checkable
class ResponseRegistry(Protocol):
    """The connector-sample sink surface. A vendor module (e.g.
    WAHA/SQLite) implements this; the chatbot/connector layer calls
    :meth:`record` best-effort and never fails on capture errors.

    `@runtime_checkable` per the seed adapter convention
    (`KB § PATTERNS/seed-fake-real-adapter.md`)."""

    def record(
        self,
        *,
        source: str,
        direction: str,
        payload: Any,
        event_type: str | None = None,
        http_status: int | None = None,
        handling_notes: str | None = None,
    ) -> None:
        """Persist the first sample for each distinct response shape;
        bump an observed-count on repeats. Best-effort by contract —
        capture failures must never propagate to the caller."""
        ...


class FakeResponseRegistry:
    """In-memory :class:`ResponseRegistry` — the default for tests + dev
    paths with no SQLite/Postgres sink. Keeps one sample per
    :func:`sample_key` and an observed-count, so tests can assert dedup
    behaviour without touching a database."""

    def __init__(self) -> None:
        self.samples: dict[str, dict[str, Any]] = {}

    def record(
        self,
        *,
        source: str,
        direction: str,
        payload: Any,
        event_type: str | None = None,
        http_status: int | None = None,
        handling_notes: str | None = None,
    ) -> None:
        if payload is None:
            return
        shape = json_shape(payload)
        fingerprint = shape_fingerprint(shape)
        key = sample_key(
            source=source,
            direction=direction,
            fingerprint=fingerprint,
            event_type=event_type,
            http_status=http_status,
        )
        existing = self.samples.get(key)
        if existing is None:
            self.samples[key] = {
                "sample_key": key,
                "source": source,
                "direction": direction,
                "event_type": event_type,
                "http_status": http_status,
                "schema_fingerprint": fingerprint,
                "schema_shape": shape,
                "payload": payload,
                "handling_notes": handling_notes,
                "observed_count": 1,
            }
        else:
            existing["observed_count"] += 1


def make_response_registry(
    *, sink: ResponseRegistry | None = None
) -> ResponseRegistry:
    """Factory — returns the provided vendor ``sink`` if given, else a
    :class:`FakeResponseRegistry`. The Real adapter is vendor-specific
    (Engineer WHATSAPP's WAHA/SQLite sink) and is injected here rather
    than constructed, keeping seed free of any vendor dependency."""
    return sink if sink is not None else FakeResponseRegistry()


__all__ = [
    "FakeResponseRegistry",
    "ResponseRegistry",
    "json_shape",
    "make_response_registry",
    "sample_key",
    "shape_fingerprint",
]
