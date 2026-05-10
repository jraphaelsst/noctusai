"""``noctus.hound.*`` tool umbrella — code-hygiene orchestrator.

The keeper enforces compliance contracts (regulatory). The hound
sniffs out cleanup candidates across the absorption + fusion +
optimization trio and aggregates their findings into a single
prioritized queue (curatorial). Both entities operate ON the codebase
but with different mandates.

Tools:

  - ``noctus.hound.scan`` — run the full trio (absorption + fusion
    + optimization) and emit a unified prioritized triage queue with
    per-scope summaries + a single "next action" recommendation.

The trio's distinct scopes (each detector is the source of truth for
its slice; the hound adds NO logic beyond aggregation):

  - **Absorption** (`noctus.seed.report`): cross-product file-level
    duplication (multiple products ship the same file → lift to seed).
  - **Fusion** (`noctus.seed.scan_fusions`): cross-tool function-level
    redundancy (multiple tools that should collapse via mode/kind).
  - **Optimization** (`noctus.seed.scan_optimizations`): intra-file
    line-level cleanup (dead code / single-use helpers / wrappers).
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every tool under the ``noctus.hound.*`` umbrella."""
    from . import scan

    scan.register(server)


__all__ = ["register_all"]
