# NoctusAI MCP Server

Platform dev toolkit. All development tools in one place — 28 MCP tools + CLI.

## For AI agents (MCP)

Agents call structured tools directly. No shell commands, no parsing.

```
→ noctusai_agent_context()           ← Full platform overview
→ noctusai_get_product("mailing")    ← Product structure + endpoints
→ noctusai_validate()                ← Compliance score: 100/100
→ noctusai_heal()                    ← Auto-fix loop until clean
→ noctusai_ai_discover()             ← AI-powered improvement proposals
```

## For humans (CLI)

```bash
python mcp/noctusai/cli.py --validate       # Check compliance
python mcp/noctusai/cli.py --heal            # Fix loop until clean
python mcp/noctusai/cli.py --analyze         # Run all analyzers
python mcp/noctusai/cli.py --discover        # AI-powered discovery
python mcp/noctusai/cli.py --metrics         # Code metrics
python mcp/noctusai/cli.py --test            # Run all backend tests
python mcp/noctusai/cli.py --build           # Build all frontends
python mcp/noctusai/cli.py --sync-prompts    # Sync MASTER-PROMPTs
python mcp/noctusai/cli.py --proposals       # List proposals
```

## 28 Tools

| Category | Tools |
|----------|-------|
| **Context** | agent_context, product_context |
| **Products** | list_products, get_product, platform_metrics |
| **Scaffold** | scaffold_product, available_ports |
| **Compliance** | validate, validate_product |
| **Heal** | heal (auto-fix loop) |
| **Analyzers** | analyze, analyze_patterns, analyze_deps, analyze_tests |
| **AI** | ai_discover, ai_advisory |
| **Master Prompts** | sync_master_prompt, sync_all_master_prompts, check_master_prompt |
| **Testing** | run_tests, run_all_tests, build_frontend, build_all_frontends |
| **Diff & Quality** | diff_against_seed, find_orphans, check_api_consistency |
| **Proposals** | list_proposals, accept_proposal, reject_proposal |

## Setup

```bash
python3 -m venv mcp/noctusai/.venv
source mcp/noctusai/.venv/bin/activate
pip install -r mcp/noctusai/requirements.txt
```

Claude Code config (`.claude/settings.local.json`):
```json
{
  "mcpServers": {
    "noctusai": {
      "command": "mcp/noctusai/.venv/bin/python",
      "args": ["mcp/noctusai/server.py"],
      "cwd": "/Users/rapha/Documents/repository/NoctusAI/noctusai"
    }
  }
}
```

## Architecture

```
mcp/noctusai/
  server.py          MCP server (28 tools)
  cli.py             CLI for humans
  tools/
    products.py      Product introspection
    context.py       Agent context
    compliance.py    Seed compliance checks
    analyzers.py     Pattern/dep/structure/test analysis
    fixes.py         Auto-fix + heal loop
    proposals.py     Proposal management
    ai_brain.py      OpenAI reasoning
    master_prompts.py MASTER-PROMPT sync
    scaffold.py      Product scaffolding
    testing.py       Test runner + frontend builder
    diff.py          Diff, orphans, API consistency
  proposals/         Shared proposals
  .venv/             MCP deps (separate from main venv)
```
