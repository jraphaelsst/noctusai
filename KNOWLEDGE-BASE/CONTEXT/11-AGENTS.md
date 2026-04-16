# 11 — Agents

> AI-powered agents that maintain and evolve the platform. Located at `agents/`.

## Current Agents

| Agent | Purpose | Command |
|-------|---------|---------|
| **Keeper** | Fixer + improver — validates, heals, discovers | `python -m agents.keeper` |

## Keeper — Three Capabilities

### Validate (`--validate`)
Deterministic compliance checks. Fast, zero AI, CI-safe. Exits 1 on failure.
- Seed framework compliance (create_product_app, createProductApp, no boilerplate)
- Path reference correctness (seed/backend/lib, seed/frontend/lib)

### Heal (`--heal`)
Fix loop: detect → auto-fix deterministic → propose non-deterministic → repeat.
- Deterministic: missing deps, old paths, boilerplate files → auto-fixed
- Non-deterministic: structural rewrites, AI findings → proposals
- Max 10 iterations, runs discover after clean

### Discover (`--discover`)
File analyzers + AI brain. All findings → proposals (never auto-fix).
- Pattern finder: duplicated functions, inline hooks, similar services
- Dependency audit: version mismatches across products
- Structure analyzer: expected files, code metrics
- Test coverage: test layers per product
- AI brain (GPT-4o): semantic analysis, cross-product reasoning

## Proposals

All agents write proposals to `agents/proposals/`. One folder, all agents.
- Format: `YYYYMMDD-HHMMSS-slug.md`
- Lifecycle: pending → accepted/rejected by human
- Deduplicated: same finding = same proposal, regardless of agent or run count

## Architecture

```
agents/
  __main__.py            → routes to keeper
  proposals/             → shared proposals folder (all agents)
  shared/                → config, models, repo utilities
  keeper/                → fixer + improver
    checks/              → validate (deterministic)
    analyzers/           → discover (file analysis)
    ai_brain.py          → AI reasoning (GPT-4o)
    fixes.py             → auto-fix functions
    proposer.py          → proposal generation + dedup
```

## Development Loop

After any code change: `python -m agents.keeper --heal --product <name>`

The Keeper detects, fixes, verifies, repeats. Deterministic issues auto-fixed. Non-deterministic → proposals. No code ships with known violations.

## Adding New Agents

Each agent gets its own directory under `agents/`:
```
agents/<agent-name>/
  __init__.py
  __main__.py    # python -m agents.<name>
  main.py
  README.md      # required, synced
```

Use `from agents.keeper.proposer import generate_proposal` to write proposals to the shared folder.
