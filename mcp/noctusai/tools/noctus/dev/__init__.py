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
    from . import agent_context
    from . import ai_brain
    from . import auto_author_scaffolds
    from . import auto_improvement
    from . import analyzers
    from . import archive
    from . import audit_product
    from . import batch_speed_gains
    from . import brief_ledger
    from . import brief_similarity_radar
    from . import build
    from . import canonical_test_audit
    from . import catalog
    from . import component_bundle
    from . import check_framework_deps
    from . import component_list
    from . import cache_deploy_mirror
    from . import cache_telemetry
    from . import cleanup_worktrees
    from . import code_baseline
    from . import code_embeddings
    from . import code_recurrence_promote
    from . import codification_radar
    from . import codify
    from . import compliance
    from . import dispatch_budget
    from . import dispatch_token_log
    from . import dispatch_warmup
    from . import doc_to_code_drift
    from . import engineer_output_linter
    from . import context
    from . import cost_evaluation
    from . import diff
    from . import deploy_image
    from . import deploy_pull
    from . import disk_usage
    from . import dispatch_preflight
    from . import engineer_brief_compose
    from . import find_reusable_component
    from . import findings
    from . import organ_knowledge
    from . import orphan_branch_sweeper
    from . import product_centroid_drift
    from . import remote_branch_hygiene
    from . import salvage_before_delete
    from . import scan_repetition_semantic
    from . import session_end_sweep
    from . import unified_query
    from . import history
    from . import improvements
    from . import kb_baseline
    from . import kb_embeddings
    from . import kb_recurrence_radar
    from . import keeper_pattern
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
    from . import refresh_all_caches
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
    from . import scan_remediation_markers
    from . import scan_unified
    from . import scan_wiring
    from . import session_review
    from . import smoke_fleet
    from . import sso_smoke
    from . import stamp_seed_version
    from . import status
    from . import corpus_embeddings
    from . import memory_embeddings
    from . import noc_graph_cache
    from . import version_guard
    from . import supabase_advisors
    from . import sync_seed_template
    from . import surface_to_tech_lead
    from . import list_pending_surfaces
    from . import respond_and_resume
    from . import dispatch_resume
    from . import task_branch
    from . import testing
    from . import three_way_sync
    from . import tmp_cleanup
    from . import vector_calibration
    from . import vector_costs
    from . import vectorize
    from . import vps
    from . import vps_exec_sql

    agent_context.register(server)
    ai_brain.register(server)
    analyzers.register(server)
    archive.register(server)
    audit_product.register(server)
    auto_author_scaffolds.register(server)
    auto_improvement.register(server)
    batch_speed_gains.register(server)
    brief_ledger.register(server)
    brief_similarity_radar.register(server)
    build.register(server)
    cache_deploy_mirror.register(server)
    cache_telemetry.register(server)
    canonical_test_audit.register(server)
    catalog.register(server)
    component_bundle.register(server)
    check_framework_deps.register(server)
    component_list.register(server)
    cleanup_worktrees.register(server)
    code_baseline.register(server)
    code_embeddings.register(server)
    code_recurrence_promote.register(server)
    codification_radar.register(server)
    codify.register(server)
    compliance.register(server)
    context.register(server)
    cost_evaluation.register(server)
    diff.register(server)
    deploy_image.register(server)
    deploy_pull.register(server)
    disk_usage.register(server)
    dispatch_budget.register(server)
    dispatch_preflight.register(server)
    dispatch_token_log.register(server)
    dispatch_warmup.register(server)
    doc_to_code_drift.register(server)
    engineer_brief_compose.register(server)
    engineer_output_linter.register(server)
    find_reusable_component.register(server)
    findings.register(server)
    organ_knowledge.register(server)
    orphan_branch_sweeper.register(server)
    product_centroid_drift.register(server)
    remote_branch_hygiene.register(server)
    salvage_before_delete.register(server)
    scan_repetition_semantic.register(server)
    session_end_sweep.register(server)
    unified_query.register(server)
    history.register(server)
    improvements.register(server)
    kb_baseline.register(server)
    kb_embeddings.register(server)
    kb_recurrence_radar.register(server)
    keeper_pattern.register(server)
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
    refresh_all_caches.register(server)
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
    scan_remediation_markers.register(server)
    scan_unified.register(server)
    scan_wiring.register(server)
    session_review.register(server)
    smoke_fleet.register(server)
    sso_smoke.register(server)
    stamp_seed_version.register(server)
    status.register(server)
    corpus_embeddings.register(server)
    memory_embeddings.register(server)
    noc_graph_cache.register(server)
    version_guard.register(server)
    supabase_advisors.register(server)
    sync_seed_template.register(server)
    surface_to_tech_lead.register(server)
    list_pending_surfaces.register(server)
    respond_and_resume.register(server)
    dispatch_resume.register(server)
    task_branch.register(server)
    testing.register(server)
    three_way_sync.register(server)
    tmp_cleanup.register(server)
    vector_calibration.register(server)
    vector_costs.register(server)
    vectorize.register(server)
    vps.register(server)
    vps_exec_sql.register(server)


__all__ = ["register_all"]
