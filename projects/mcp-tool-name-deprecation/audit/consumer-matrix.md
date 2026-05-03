# Consumer-reference matrix for mcp-tool-name-deprecation Phase 0

Generated: 2026-05-03 · 60 tools scanned

**Search scope** (excluding `.claude/snapshots/` which is a frozen point-in-time reference, not a live consumer):
- `.claude/settings.local.json`
- `.claude/mcp_servers.json`
- `.github/`
- `scripts/`
- `KNOWLEDGE-BASE/`
- `projects/`
- `products/`
- `core/`
- `CLAUDE.md`
- `CLAUDE/`
- `README.md`
- `templates/`
- `mcp/noctusai/cli.py`

---

## Retirement priority by coupling (low coupling → easy to retire first)

### Zero non-self references — 1 tools (safest to retire first)
- `noctusai_lgpd_list`

### Low coupling (1-3 references) — 48 tools
- `noctus.dev.agent_context` (1 refs)
- `noctus.dev.analyze_patterns` (1 refs)
- `noctus.dev.catalog` (1 refs)
- `noctus.dev.product_context` (1 refs)
- `noctus.dev.review` (3 refs)
- `noctus.dev.review_session` (2 refs)
- `noctus.dev.validate` (2 refs)
- `noctusai_accept_proposal` (1 refs)
- `noctusai_agent_context` (2 refs)
- `noctusai_ai_advisory` (1 refs)
- `noctusai_ai_discover` (1 refs)
- `noctusai_analyze` (3 refs)
- `noctusai_analyze_deps` (1 refs)
- `noctusai_analyze_patterns` (3 refs)
- `noctusai_analyze_tests` (1 refs)
- `noctusai_available_ports` (1 refs)
- `noctusai_build_all_frontends` (1 refs)
- `noctusai_build_frontend` (1 refs)
- `noctusai_build_parallel` (1 refs)
- `noctusai_catalog` (2 refs)
- `noctusai_check_api_consistency` (1 refs)
- `noctusai_check_master_prompt` (1 refs)
- `noctusai_check_three_way_sync` (1 refs)
- `noctusai_diff_against_seed` (1 refs)
- `noctusai_find_orphans` (1 refs)
- `noctusai_get_product` (1 refs)
- `noctusai_list_products` (1 refs)
- `noctusai_list_promotions` (1 refs)
- `noctusai_list_proposals` (1 refs)
- `noctusai_platform_metrics` (1 refs)
- `noctusai_product_context` (2 refs)
- `noctusai_promote_from_seed_workspace` (3 refs)
- `noctusai_proposal_template` (2 refs)
- `noctusai_refs` (3 refs)
- `noctusai_reject_proposal` (1 refs)
- `noctusai_run_all_tests` (1 refs)
- `noctusai_run_tests` (1 refs)
- `noctusai_scaffold_product` (3 refs)
- `noctusai_scan_block_patterns` (1 refs)
- `noctusai_scan_migration_patterns` (1 refs)
- `noctusai_scan_pydantic_model_shapes` (1 refs)
- `noctusai_scan_recurrence` (3 refs)
- `noctusai_scan_service_line_recurrence` (3 refs)
- `noctusai_scan_test_fixture_recurrence` (1 refs)
- `noctusai_scan_within_product_helpers` (1 refs)
- `noctusai_sync_all_master_prompts` (1 refs)
- `noctusai_sync_master_prompt` (1 refs)
- `noctusai_validate_product` (1 refs)

### Medium coupling (4-10 references) — 10 tools
- `noctusai_count_tokens` (5 refs)
- `noctusai_improvements` (4 refs)
- `noctusai_lgpd_flag` (9 refs)
- `noctusai_outline_python` (6 refs)
- `noctusai_outline_typescript` (4 refs)
- `noctusai_review` (7 refs)
- `noctusai_review_session` (4 refs)
- `noctusai_scan_cross_product_helpers` (4 refs)
- `noctusai_status` (4 refs)
- `noctusai_validate` (9 refs)

### High coupling (11+ references) — 1 tools
- `noctusai_file_proposal` (15 refs)

---

## Per-tool consumer matrix

| Tool | # refs | Consumer files |
|---|---|---|
| `noctus.dev.agent_context` | 1 | `projects/mcp-tool-name-deprecation/PROJECT.md` |
| `noctus.dev.analyze_patterns` | 1 | `projects/mcp-tool-name-deprecation/PROJECT.md` |
| `noctus.dev.catalog` | 1 | `projects/mcp-tool-name-deprecation/PROJECT.md` |
| `noctus.dev.product_context` | 1 | `projects/mcp-tool-name-deprecation/PROJECT.md` |
| `noctus.dev.review` | 3 | `projects/mcp-server-fastmcp-switch/PROJECT.md`, `projects/mcp-tool-name-deprecation/PROJECT.md`, `projects/session-review-baseline/PROJECT.md` |
| `noctus.dev.review_session` | 2 | `projects/mcp-server-fastmcp-switch/PROJECT.md`, `projects/session-review-baseline/PROJECT.md` |
| `noctus.dev.validate` | 2 | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/mcp-tool-conventions.md`, `projects/mcp-tool-name-deprecation/PROJECT.md` |
| `noctusai_accept_proposal` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_agent_context` | 2 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `projects/mcp-tool-name-deprecation/PROJECT.md` |
| `noctusai_ai_advisory` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_ai_discover` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_analyze` | 3 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `projects/mcp-server-fastmcp-switch/PROJECT.md`, `projects/mcp-tool-name-deprecation/PROJECT.md` |
| `noctusai_analyze_deps` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_analyze_patterns` | 3 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `projects/mcp-server-fastmcp-switch/PROJECT.md`, `projects/mcp-tool-name-deprecation/PROJECT.md` |
| `noctusai_analyze_tests` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_available_ports` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_build_all_frontends` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_build_frontend` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_build_parallel` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_catalog` | 2 | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md`, `projects/mcp-tool-name-deprecation/PROJECT.md` |
| `noctusai_check_api_consistency` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_check_master_prompt` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_check_three_way_sync` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_count_tokens` | 5 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md`, `projects/main-core-migrations-batch/PROJECT.md`, `projects/mcp-server-fastmcp-switch/PROJECT.md` |
| `noctusai_diff_against_seed` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_file_proposal` | 15 | `.claude/settings.local.json`, `CLAUDE/projects.md`, `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`, `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md` + 10 more |
| `noctusai_find_orphans` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_get_product` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_improvements` | 4 | `KNOWLEDGE-BASE/CONTEXT/01-PHILOSOPHY.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md`, `products/therapy-platform/projects/therapy-platform-wiring/PROJECT.md` |
| `noctusai_lgpd_flag` | 9 | `CLAUDE/platform.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/lgpd.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/llm-tool-audit.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md`, `KNOWLEDGE-BASE/INDEX.md` + 4 more |
| `noctusai_lgpd_list` | 0 | *(none)* |
| `noctusai_list_products` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_list_promotions` | 1 | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md` |
| `noctusai_list_proposals` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_outline_python` | 6 | `.claude/settings.local.json`, `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/accept-with-rationale.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/agent-reading-discipline.md`, `projects/mcp-server-fastmcp-switch/PROJECT.md` + 1 more |
| `noctusai_outline_typescript` | 4 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/agent-reading-discipline.md`, `projects/mcp-server-fastmcp-switch/PROJECT.md`, `projects/session-review-baseline/PROJECT.md` |
| `noctusai_platform_metrics` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_product_context` | 2 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `projects/mcp-tool-name-deprecation/PROJECT.md` |
| `noctusai_promote_from_seed_workspace` | 3 | `KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md`, `KNOWLEDGE-BASE/INDEX.md`, `templates/seed-workspace-README.md` |
| `noctusai_proposal_template` | 2 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `projects/mcp-server-fastmcp-switch/PROJECT.md` |
| `noctusai_refs` | 3 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/agent-reading-discipline.md`, `projects/mcp-server-fastmcp-switch/PROJECT.md` |
| `noctusai_reject_proposal` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_review` | 7 | `.claude/settings.local.json`, `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/agent-reading-discipline.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/ast.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md` + 2 more |
| `noctusai_review_session` | 4 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/agent-reading-discipline.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/ast.md`, `projects/session-review-baseline/PROJECT.md` |
| `noctusai_run_all_tests` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_run_tests` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_scaffold_product` | 3 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md`, `projects/imobi-scheduling-bot-creation/PROJECT.md` |
| `noctusai_scan_block_patterns` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_scan_cross_product_helpers` | 4 | `.claude/settings.local.json`, `CLAUDE.md`, `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/agent-reading-discipline.md` |
| `noctusai_scan_migration_patterns` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_scan_pydantic_model_shapes` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_scan_recurrence` | 3 | `.claude/settings.local.json`, `CLAUDE.md`, `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_scan_service_line_recurrence` | 3 | `.claude/settings.local.json`, `CLAUDE.md`, `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_scan_test_fixture_recurrence` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_scan_within_product_helpers` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_status` | 4 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/agent-reading-discipline.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/seed-workspace.md`, `projects/mcp-server-fastmcp-switch/PROJECT.md` |
| `noctusai_sync_all_master_prompts` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_sync_master_prompt` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
| `noctusai_validate` | 9 | `.claude/settings.local.json`, `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/mcp-tool-conventions.md`, `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md`, `products/mailing/proposals/evaluations/20260419-014952-mailing/claude-opus-4-7-20260419-015135-remove-product-level-health.py-in-mailing-—-delega.md` + 4 more |
| `noctusai_validate_product` | 1 | `KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md` |
