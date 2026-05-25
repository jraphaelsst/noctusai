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
    from . import check_framework_deps
    from . import cleanup_worktrees
    from . import compliance
    from . import context
    from . import cost_evaluation
    from . import diff
    from . import deploy_image
    from . import deploy_pull
    from . import disk_usage
    from . import dispatch_preflight
    from . import findings
    from . import history
    from . import improvements
    from . import lgpd
    from . import master_prompts
    from . import merge_debt
    from . import mole
    from . import outline
    from . import outline_python
    from . import outline_typescript
    from . import phase_learnings
    from . import predeploy_check
    from . import products
    from . import promotion
    from . import propagate
    from . import proposals
    from . import recurrence
    from . import refs
    from . import release
    from . import review
    from . import salvage_worktree
    from . import scaffold
    from . import scaffold_keeper
    from . import scaffold_mcp_tool
    from . import scaffold_memory
    from . import scaffold_migration
    from . import scaffold_seed_adapter
    from . import scan_unified
    from . import scan_wiring
    from . import session_review
    from . import smoke_fleet
    from . import sso_smoke
    from . import stamp_seed_version
    from . import status
    from . import supabase_advisors
    from . import sync_seed_template
    from . import task_branch
    from . import testing
    from . import three_way_sync
    from . import vps

    ai_brain.register(server)
    analyzers.register(server)
    archive.register(server)
    audit_product.register(server)
    batch_speed_gains.register(server)
    build.register(server)
    catalog.register(server)
    check_framework_deps.register(server)
    cleanup_worktrees.register(server)
    compliance.register(server)
    context.register(server)
    cost_evaluation.register(server)
    diff.register(server)
    deploy_image.register(server)
    deploy_pull.register(server)
    disk_usage.register(server)
    dispatch_preflight.register(server)
    findings.register(server)
    history.register(server)
    improvements.register(server)
    lgpd.register(server)
    master_prompts.register(server)
    merge_debt.register(server)
    mole.register(server)
    outline.register(server)
    outline_python.register(server)
    outline_typescript.register(server)
    phase_learnings.register(server)
    predeploy_check.register(server)
    products.register(server)
    promotion.register(server)
    propagate.register(server)
    proposals.register(server)
    recurrence.register(server)
    refs.register(server)
    release.register(server)
    review.register(server)
    salvage_worktree.register(server)
    scaffold.register(server)
    scaffold_keeper.register(server)
    scaffold_mcp_tool.register(server)
    scaffold_memory.register(server)
    scaffold_migration.register(server)
    scaffold_seed_adapter.register(server)
    scan_unified.register(server)
    scan_wiring.register(server)
    session_review.register(server)
    smoke_fleet.register(server)
    sso_smoke.register(server)
    stamp_seed_version.register(server)
    status.register(server)
    supabase_advisors.register(server)
    sync_seed_template.register(server)
    task_branch.register(server)
    testing.register(server)
    three_way_sync.register(server)
    vps.register(server)


__all__ = ["register_all"]
