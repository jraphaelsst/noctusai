"""``noctusai_lib.components`` — organ catalog + validation signal.

The seed's **body layer**: derived validation semantics for reusable
components (organs). Consumers call :func:`derive_validation_status` to
classify a component; :func:`compute_signal_inputs` does the heavy lifting
(test lookup, NOC-REMEDIATE scan, recent bugfix commit count).

Design decisions:
- ``validated`` is a 5-gate AND — a single gap drops to ``emerging``.
- ``shelfware`` is the zero-consumer case — "available but not wired."
  Naming this honestly prevents the silent "available" anti-pattern.
- ``unknown`` is reserved for genuinely missing data (not a lazy fallback).
- Threshold constants live here so cross-product consumers can tune them.

KB § PATTERNS/architect/component-list-and-validation.md.
"""

from __future__ import annotations

from .validation_signal import (
    CONSUMERS_THRESHOLD,
    BUGFIX_WINDOW_DAYS,
    compute_signal_inputs,
    derive_validation_status,
)

__all__ = [
    "CONSUMERS_THRESHOLD",
    "BUGFIX_WINDOW_DAYS",
    "compute_signal_inputs",
    "derive_validation_status",
]
