"""``noctus.seed.*`` tool umbrella — seed-system absorption + capability tools.

Read-only diagnostics (today):

- ``scan_repetition`` — find files duplicated across N≥2 products. Surface
  candidates for absorption into seed.
- ``list_capabilities`` — enumerate what the seed currently provides (factories
  in ``noctusai_seed``, library exports in ``noctusai_lib``). So future
  scaffolds inherit instead of inventing.
- ``audit_drift`` — for files that mirror ``templates/product-seed/`` shapes,
  diff each product against the canonical. Surface convergence candidates.
- ``report`` — rollup that cross-references scan_repetition + audit_drift
  into a single prioritized triage queue (P0 highest leverage → P5 review
  only).
- ``scan_fusions`` — meta-detector for MCP-tool fusion opportunities.
  Scores tool pairs by namespace co-prefix, parameter overlap, return-key
  overlap, and description-noun overlap. Surfaces "what rollup tool
  should I build next" candidates, just like ``scan_repetition`` surfaces
  "what file should I absorb next".
- ``scan_optimizations`` — third leg of the trio. Intra-file scope:
  dead code, single-call helpers, no-op wrappers, verbose tool
  descriptions, oversized shim docstrings, lone constants. Surfaces
  "what can I delete or inline within this file?".

Mutation tools (later, after read-only output reveals the right shapes):

- ``absorb_file`` — move a duplicated file into seed; rewrite product copies
  into imports.
- ``specify_capability`` — declare a new seed capability via guided template.
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every seed-umbrella tool on the given FastMCP server."""
    from . import absorb_file
    from . import audit_drift
    from . import list_capabilities
    from . import report
    from . import scan_fusions
    from . import scan_optimizations
    from . import scan_repetition
    from . import specify_capability

    absorb_file.register(server)
    audit_drift.register(server)
    list_capabilities.register(server)
    report.register(server)
    scan_fusions.register(server)
    scan_optimizations.register(server)
    scan_repetition.register(server)
    specify_capability.register(server)


__all__ = ["register_all"]
