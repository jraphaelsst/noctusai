"""``noctus.seed.*`` tool umbrella — seed-system absorption + capability tools.

Read-only diagnostics (today):

- ``scan_repetition`` — find files duplicated across N≥2 products. Surface
  candidates for absorption into seed.
- ``list_capabilities`` — enumerate what the seed currently provides (factories
  in ``noctusai_seed``, library exports in ``noctusai_lib``). So future
  scaffolds inherit instead of inventing.
- ``audit_drift`` — for files that mirror ``templates/product-seed/`` shapes,
  diff each product against the canonical. Surface convergence candidates.

Mutation tools (later, after read-only output reveals the right shapes):

- ``absorb_file`` — move a duplicated file into seed; rewrite product copies
  into imports.
- ``specify_capability`` — declare a new seed capability via guided template.
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every seed-umbrella tool on the given FastMCP server."""
    from . import audit_drift
    from . import list_capabilities
    from . import scan_repetition

    audit_drift.register(server)
    list_capabilities.register(server)
    scan_repetition.register(server)


__all__ = ["register_all"]
