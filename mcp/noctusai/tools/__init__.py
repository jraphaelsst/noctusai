"""MCP tool registration tree.

Each tool module exposes a ``register(server)`` function that calls
``server.tool(name=..., description=...)(handler)`` for every tool it
owns. ``register_all`` calls them all in alphabetical order.

To add a new tool module, drop a file into ``tools/``, add a top-level
``register(server)`` to it, and wire it into ``register_all`` below.

Lazy-loading discipline: each module is imported inside ``register_all``
so the server's import-time stays light. Heavy deps in tool modules
(e.g. ``ai_brain`` pulls in OpenAI when invoked) only fire when the
registrar runs.
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every tool in this package on the given FastMCP server."""
    from . import ai_brain
    from . import analyzers
    from . import build
    from . import catalog
    from . import compliance
    from . import context
    from . import cost_evaluation
    from . import diff
    from . import improvements
    from . import lgpd
    from . import master_prompts
    from . import outline_python
    from . import outline_typescript
    from . import products
    from . import promotion
    from . import proposals
    from . import recurrence
    from . import refs
    from . import review
    from . import scaffold
    from . import session_review
    from . import status
    from . import testing
    from . import three_way_sync

    ai_brain.register(server)
    analyzers.register(server)
    build.register(server)
    catalog.register(server)
    compliance.register(server)
    context.register(server)
    cost_evaluation.register(server)
    diff.register(server)
    improvements.register(server)
    lgpd.register(server)
    master_prompts.register(server)
    outline_python.register(server)
    outline_typescript.register(server)
    products.register(server)
    promotion.register(server)
    proposals.register(server)
    recurrence.register(server)
    refs.register(server)
    review.register(server)
    scaffold.register(server)
    session_review.register(server)
    status.register(server)
    testing.register(server)
    three_way_sync.register(server)


__all__ = ["register_all"]
