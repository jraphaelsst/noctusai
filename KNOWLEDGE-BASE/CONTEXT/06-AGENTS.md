# 06 — MCP Dev Toolkit

> Platform development tools exposed as an MCP server at `mcp/noctusai/`.
> Tool count is derived from `_tool(` invocations in `mcp/noctusai/server.py::list_tools()`.

## Tools

<!-- kb-counts:start:mcp_tools -->
**35 tools total** (auto-counted from `mcp/noctusai/server.py`).
<!-- kb-counts:end:mcp_tools -->

### Context
- noctusai_agent_context — full platform overview
- noctusai_product_context — product structure + docs

### Products
- noctusai_list_products, noctusai_get_product, noctusai_platform_metrics

### Scaffold
- noctusai_scaffold_product, noctusai_available_ports

### Compliance
- noctusai_validate, noctusai_validate_product

### Review (observation-only — never modifies code)
- noctusai_review — detect seed-compliance issues + surface them for authoring. Three modes:
  - `mode=agent` (default): returns the issue list + a review prompt the in-session agent uses. The agent fills `templates/PROPOSAL-TEMPLATE.md` per issue using session context and files via `noctusai_file_proposal`. Zero LLM cost at this layer.
  - `mode=headless`: OpenAI `gpt-4o-mini` authors proposals (for CI / cron / solo CLI without an agent).
  - `mode=evaluate`: writes OpenAI + agent proposals side-by-side to `mcp/noctusai/proposals/evaluations/<ts>/` for comparison.
  - Replaces the retired `noctusai_heal`. See `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md` for the full protocol (two capture triggers, phase → proposal flow, promote boundary).
- noctusai_proposal_template — return `templates/PROPOSAL-TEMPLATE.md` content so agents get a consistent starting point.
- noctusai_file_proposal — write a filled-template proposal to `mcp/noctusai/proposals/` (or an evaluation subfolder).

### Analyzers
- noctusai_analyze, noctusai_analyze_patterns, noctusai_analyze_deps, noctusai_analyze_tests

### AI
- noctusai_ai_discover, noctusai_ai_advisory

### Master Prompts
- noctusai_sync_master_prompt, noctusai_sync_all_master_prompts, noctusai_check_master_prompt

### Testing
- noctusai_run_tests, noctusai_run_all_tests, noctusai_build_frontend, noctusai_build_all_frontends

### Diff & Quality
- noctusai_diff_against_seed, noctusai_find_orphans, noctusai_check_api_consistency

### Proposals
- noctusai_list_proposals, noctusai_accept_proposal, noctusai_reject_proposal

## CLI (for humans)

```bash
python mcp/noctusai/cli.py --validate
python mcp/noctusai/cli.py --review      # observation-only; files LLM-authored proposals, NEVER edits code
python mcp/noctusai/cli.py --analyze
python mcp/noctusai/cli.py --discover
python mcp/noctusai/cli.py --metrics
python mcp/noctusai/cli.py --test
python mcp/noctusai/cli.py --build
python mcp/noctusai/cli.py --proposals
python mcp/noctusai/cli.py --verify-kb-sync
```

## Architecture

```
mcp/noctusai/
  server.py         MCP server
  cli.py            CLI for humans
  tools/            Tool implementations
  proposals/        Shared proposals
  .venv/            Separate venv for MCP deps
  README.md
```
