# 11 — MCP Dev Toolkit

> Platform development tools exposed as an MCP server at `mcp/noctusai/`.

## Tools (28 total)

### Context
- noctusai_agent_context — full platform overview
- noctusai_product_context — product structure + docs

### Products
- noctusai_list_products, noctusai_get_product, noctusai_platform_metrics

### Scaffold
- noctusai_scaffold_product, noctusai_available_ports

### Compliance
- noctusai_validate, noctusai_validate_product

### Heal
- noctusai_heal — auto-fix loop

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
python mcp/noctusai/cli.py --heal
python mcp/noctusai/cli.py --analyze
python mcp/noctusai/cli.py --discover
python mcp/noctusai/cli.py --metrics
python mcp/noctusai/cli.py --test
python mcp/noctusai/cli.py --build
python mcp/noctusai/cli.py --proposals
```

## Architecture

```
mcp/noctusai/
  server.py         MCP server (28 tools)
  cli.py            CLI for humans
  tools/            Tool implementations
  proposals/        Shared proposals
  .venv/            Separate venv for MCP deps
  README.md
```
