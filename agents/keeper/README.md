# Keeper

The platform's fixer and improver. One agent, three capabilities.

## Usage

```bash
python -m agents.keeper                          # Full: validate → discover
python -m agents.keeper --heal                   # Fix loop → discover
python -m agents.keeper --heal --product mailing # Fix one product
python -m agents.keeper --validate               # CI mode (fast, deterministic)
python -m agents.keeper --discover               # Proposals only
python -m agents.keeper --advisory               # Include AI advisory
```

Also runs as:
```bash
python -m agents                                 # Routes to keeper
```

## Three Capabilities

### Validate (`--validate`)
Checks platform compliance. Deterministic, fast, zero AI. Safe for CI — exits 1 on failure.

Checks:
- `seed_compliance` — products use seed framework (`create_product_app`, `createProductApp`, no boilerplate routers)
- `path_references` — all paths to `seed/backend/lib` and `seed/frontend/lib` are correct

### Heal (`--heal`)
Fix loop: detect → auto-fix deterministic issues → verify → repeat until clean.

- **Deterministic issues** → auto-fixed (missing deps, old paths, boilerplate files)
- **Non-deterministic issues** → proposals created for human review
- After clean → runs discover automatically

Max 10 iterations. Logs every fix applied.

### Discover (`--discover`)
Find improvements, generate proposals. File analyzers + AI brain.

Analyzers:
- `pattern_finder` — duplicated functions, inline hooks, similar services
- `dependency_audit` — version mismatches, missing seed deps
- `structure_analyzer` — expected files, code metrics
- `test_coverage` — test layers per product

AI brain (GPT-4o): semantic analysis, cross-product reasoning, prioritized proposals.

All findings → proposals in `agents/proposals/`. Never auto-fixes.

## Proposal Lifecycle

1. Keeper discovers issue → proposal created in `proposals/`
2. Human reviews → accepts, rejects, or defers
3. Proposals are deduplicated — same finding, same proposal, regardless of run count

## AI

Requires `OPENAI_API_KEY` in root `.env`. Used for:
- AI advisory: reads CLAUDE.md rules, validates code (non-blocking)
- AI brain: semantic analysis, cross-product reasoning, proposals

Without the key, everything still works — just without AI features.

## Architecture

```
agents/keeper/
  main.py              Entry point + orchestration
  checks/              Validation (deterministic)
    seed_compliance.py  Seed framework compliance
    path_references.py  Path correctness
    ai_advisory.py      AI-powered rule validation
  analyzers/            Discovery (analysis)
    pattern_finder.py   Code duplication
    dependency_audit.py Version consistency
    structure_analyzer.py File structure + metrics
    test_coverage.py    Test layer compliance
  ai_brain.py           AI reasoning over findings
  fixes.py              Auto-fix functions
  proposer.py           Proposal generation + dedup

# Proposals live at agents/proposals/ (shared across all agents)
```
