"""`IntegrationNotConfigured` — the one marker for "this integration is
deliberately OFF because its configuration is absent" (2026-10-10).

The fleet had 20+ `*NotConfigured` / `*NaoConfigurado` exception types, each in
its own hierarchy (Vista, Fernet encryption, e-mail, LLM, signature, billing
gateways, ...), all meaning the same thing: fail-closed on missing config — a
503, never a silent fallback. Nothing could recognise that class as a whole,
so `check_stand_in_conformance` (leg A: resolve the product's DI graph against
REAL objects in a config-less subprocess) reported each one as a stand-in
violation, when it is the integration correctly refusing to run.

Mix it in alongside the existing base — it is a plain class (no Exception
layout), so it never changes the MRO's exception behaviour, `except` clauses
or `isinstance` checks against the original hierarchy::

    class VistaConfigError(VistaError, IntegrationNotConfigured): ...

Recognise it BY TYPE, never by message text, including through a wrapper
that re-raises (`raise api_error(503, ...) from exc`)::

    is_integration_not_configured(exc)  # walks __cause__ / __context__

Dependency-free on purpose (imported by low-level modules — no cycles).
"""
from __future__ import annotations

__all__ = ["IntegrationNotConfigured", "is_integration_not_configured"]


class IntegrationNotConfigured:
    """Marker mixin: raised because required configuration is absent."""


def is_integration_not_configured(exc: BaseException | None) -> bool:
    """True if `exc`, or any exception it was raised from/during, carries the
    marker. Cycle-safe."""
    seen: set[int] = set()
    while exc is not None and id(exc) not in seen:
        if isinstance(exc, IntegrationNotConfigured):
            return True
        seen.add(id(exc))
        exc = exc.__cause__ or exc.__context__
    return False
