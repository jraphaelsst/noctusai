"""``noctus.dev.*`` tool umbrella — developer-experience MCP tools.

All modules in this package expose a top-level ``register(server)``
function. ``register_all`` calls them in alphabetical order with lazy
imports so the server's import-time stays light (``ai_brain`` pulls in
OpenAI, ``testing`` shells out to pytest, etc. — only when the registrar
runs do those costs land).
"""

from __future__ import annotations


def register_all(server) -> None:
    """Register every dev-umbrella tool on the given FastMCP server."""
    from . import ai_brain
    from . import analyzers
    from . import archive
    from . import audit_product
    from . import batch_speed_gains
    from . import build
    from . import catalog
    from . import compliance
    from . import context
    from . import cost_evaluation
    from . import diff
    from . import dispatch_preflight
    from . import findings
    from . import history
    from . import improvements
    from . import lgpd
    from . import master_prompts
    from . import mole
    from . import outline
    from . import outline_python
    from . import outline_typescript
    from . import phase_learnings
    from . import products
    from . import promotion
    from . import proposals
    from . import recurrence
    from . import refs
    from . import review
    from . import salvage_worktree
    from . import scaffold
    from . import scaffold_migration
    from . import scan_unified
    from . import session_review
    from . import status
    from . import supabase_advisors
    from . import testing
    from . import three_way_sync

    ai_brain.register(server)
    analyzers.register(server)
    archive.register(server)
    audit_product.register(server)
    batch_speed_gains.register(server)
    build.register(server)
    catalog.register(server)
    compliance.register(server)
    context.register(server)
    cost_evaluation.register(server)
    diff.register(server)
    dispatch_preflight.register(server)
    findings.register(server)
    history.register(server)
    improvements.register(server)
    lgpd.register(server)
    master_prompts.register(server)
    mole.register(server)
    outline.register(server)
    outline_python.register(server)
    outline_typescript.register(server)
    phase_learnings.register(server)
    products.register(server)
    promotion.register(server)
    proposals.register(server)
    recurrence.register(server)
    refs.register(server)
    review.register(server)
    salvage_worktree.register(server)
    scaffold.register(server)
    scaffold_migration.register(server)
    scan_unified.register(server)
    session_review.register(server)
    status.register(server)
    supabase_advisors.register(server)
    testing.register(server)
    three_way_sync.register(server)


__all__ = ["register_all"]
