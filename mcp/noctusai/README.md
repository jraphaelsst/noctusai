# NoctusAI MCP Server — Platform Dev Toolkit

**30 tools** for agent-driven development on the NoctusAI monorepo. Every tool is available both as an MCP tool (agents call it directly) and as a CLI flag (humans run it in a terminal).

---

## Quick reference

| Goal | CLI | MCP tool |
|---|---|---|
| Full platform context | — | `noctusai_agent_context` |
| One product's structure | — | `noctusai_product_context(slug)` |
| List all products + counts | — | `noctusai_list_products` |
| Code metrics per product | `--metrics` | `noctusai_platform_metrics` |
| Scaffold a new product | — | `noctusai_scaffold_product` |
| Next available ports | — | `noctusai_available_ports` |
| Seed compliance score | `--validate` | `noctusai_validate` |
| Review (observation-only, LLM-backed proposals) | `--review` | `noctusai_review` |
| Pattern/dep/test analysis | `--analyze` | `noctusai_analyze` |
| Duplicated functions | — | `noctusai_analyze_patterns` |
| Dep version mismatch | — | `noctusai_analyze_deps` |
| Test coverage gaps | — | `noctusai_analyze_tests` |
| AI-assisted discovery | `--discover` | `noctusai_ai_discover` |
| AI rule advisory | — | `noctusai_ai_advisory` |
| Sync one product's MASTER-PROMPT | — | `noctusai_sync_master_prompt(slug)` |
| Sync all MASTER-PROMPTs | `--sync-prompts` | `noctusai_sync_all_master_prompts` |
| Check one MASTER-PROMPT staleness | — | `noctusai_check_master_prompt(slug)` |
| Run one product's tests | — | `noctusai_run_tests(slug)` |
| Run all tests | `--test` | `noctusai_run_all_tests` |
| Build one frontend | — | `noctusai_build_frontend(slug)` |
| Build all frontends | `--build` | `noctusai_build_all_frontends` |
| Diff product vs seed | — | `noctusai_diff_against_seed(slug)` |
| Orphaned files in product | — | `noctusai_find_orphans(slug)` |
| API consistency check | — | `noctusai_check_api_consistency(slug)` |
| KB ↔ CLAUDE.md sync check | `--verify-kb-sync` | — |
| Shared-library catalog | `--catalog` | `noctusai_catalog` |
| **Project → improvements.md (retrospective)** | `--improvements PROJECT` | `noctusai_improvements(project_path)` |
| List proposals | `--proposals` | `noctusai_list_proposals` |
| Accept proposal | — | `noctusai_accept_proposal(filename)` |
| Reject proposal | — | `noctusai_reject_proposal(filename, reason)` |

---

## When agents use what

Agents should default to invoking an MCP tool rather than shelling out to the CLI. The MCP tool returns structured data; the CLI is formatted for humans.

**Start-of-session discovery** — agents new to the repo call `noctusai_agent_context` first. For product-specific work, follow up with `noctusai_product_context(slug)`.

**Before any code change** — call `noctusai_catalog` (check for existing shared-lib symbols + duplicate signals) and `noctusai_analyze_patterns` (find existing duplications the change might absorb or worsen).

**After any code change** — call `noctusai_review` scoped to the affected product. The review pass detects seed-compliance issues deterministically and asks an LLM (OpenAI) to author one proposal per issue in `products/<product>/proposals/`. **It never modifies code** — you triage each proposal and apply the fixes yourself. (The former `noctusai_heal` auto-fix loop was retired — deterministic text rewrites could corrupt code and the string-match checks rotted as the seed evolved.)

**When executing a project** — tick phase headers live, append an `**Improvements:**` block to the just-completed phase capturing learnings, then *always* call `noctusai_improvements(project_path)`. The generated `improvements.md` is the project's retrospective knowledge base — read first when any phase is reworked.

**Before shipping a PR** — run `noctusai_validate` (compliance score) and `noctusai_analyze_tests` (coverage gaps). If the change touched the seed or a shared lib, re-run `noctusai_catalog` to confirm no new orphans or duplications.

---

## Tool catalog — grouped

### Context & discovery
- `noctusai_agent_context` — Full platform overview for a fresh agent. Call first.
- `noctusai_product_context(slug)` — One product's structure + MASTER-PROMPT + README.
- `noctusai_list_products` — All products with router/service/page/hook counts.
- `noctusai_get_product(slug)` — Detailed structure: endpoints, config, tests, migrations.
- `noctusai_platform_metrics` — Code metrics (lines, routers, services, pages) per product.

### Scaffolding
- `noctusai_scaffold_product(name, slug, schema, backend_port, frontend_port, icon?)` — Create a new product from the seed template.
- `noctusai_available_ports` — Find the next free backend + frontend port pair.

### Compliance + review
- `noctusai_validate` — Compliance score (0–100) + issues list for all products.
- `noctusai_validate_product(slug)` — Same, scoped to one product.
- `noctusai_review(product?)` — **Observation-only.** Detect seed-compliance issues deterministically, then ask an LLM (OpenAI, requires `OPENAI_API_KEY`) to author one proposal per issue in `products/<product>/proposals/`. **Never modifies code.** Falls back to skeleton proposals if the LLM is unavailable so nothing is silently dropped.

### Pattern & dependency analysis
- `noctusai_analyze` — Run all analyzers at once.
- `noctusai_analyze_patterns` — Duplicated functions + inline hooks.
- `noctusai_analyze_deps` — Python dep version consistency across products.
- `noctusai_analyze_tests` — Three-layer test coverage gaps.

### AI-assisted review
- `noctusai_ai_discover` — AI reads analyzer findings and proposes improvements. Requires `OPENAI_API_KEY`.
- `noctusai_ai_advisory` — AI reads `CLAUDE.md` rules and audits recent code. Requires `OPENAI_API_KEY`.

### MASTER-PROMPT sync
- `noctusai_sync_master_prompt(slug)` — Regenerate the structural sections of one product's MASTER-PROMPT from the filesystem.
- `noctusai_sync_all_master_prompts` — Same for every product.
- `noctusai_check_master_prompt(slug)` — Is a MASTER-PROMPT stale? (changed code, unchanged prompt)

### Testing & building
- `noctusai_run_tests(slug)` — Run pytest for one product.
- `noctusai_run_all_tests` — All products.
- `noctusai_build_frontend(slug)` — `vite build` for one frontend.
- `noctusai_build_all_frontends` — All frontends.

### Diff & quality
- `noctusai_diff_against_seed(slug)` — Compare a product's structural files against the seed.
- `noctusai_find_orphans(slug)` — Files defined but not imported anywhere.
- `noctusai_check_api_consistency(slug)` — Response-pattern consistency (`success_response`/`paginated_response`).

### Catalog (shared-library observation)
- `noctusai_catalog` — Scans `seed/backend/lib` + `seed/backend/framework` for every public symbol; scans every product's backend for imports; produces `mcp/noctusai/catalog.md` with:
  - Every symbol + its importers + import count.
  - **Orphans** (lib symbols with zero importers).
  - **Single-consumer** (informational — one product uses this symbol).
  - **Duplicate candidates** (same name in 2+ products, not already in lib).

  Conventions for resolving its findings live at `KNOWLEDGE-BASE/CONTEXT/PATTERNS/shared-library-conventions.md`.

### Improvements (phase retrospective) — **MANDATORY after phase tick**
- `noctusai_improvements(project_path)` — Parses a project file and regenerates `improvements.md` in the project's folder. Surfaces:
  - Each completed phase's `**Improvements:**` block — observations, refactor candidates, edge cases, tech debt captured *while implementing that phase*.
  - Completed phases missing an improvements block (nudge to back-fill).
  - Items carried from §4 "Out of scope" (deferred candidates).
  - Unresolved items from §7 "Open questions".

  **It does NOT preview upcoming phases.** Those live in §6 of the project. The improvements log is a *retrospective* — what the build of each phase taught us, for future reworkers of that phase.

  **When to call**: every time a phase header flips from `- [ ]` to `- [x]`, after appending the `**Improvements:**` block. Non-optional.

  Full conventions at `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md`.

### Proposals
- `noctusai_list_proposals(agent?)` — Pending proposals, optionally filtered by agent.
- `noctusai_accept_proposal(filename)` — Mark accepted.
- `noctusai_reject_proposal(filename, reason)` — Mark rejected with a reason.

### Sync checks (CLI-only)
- `--verify-kb-sync` — Verifies `CLAUDE.md` pointers resolve and all KB docs are indexed in `KNOWLEDGE-BASE/INDEX.md`. Enforced by pre-commit hook.

---

## CLI examples

```bash
# Context
python mcp/noctusai/cli.py                          # default: validate + analyze summary

# Validate
python mcp/noctusai/cli.py --validate

# Review one product (observation-only; files proposals, never edits code)
python mcp/noctusai/cli.py --review --product erp-imobiliario

# Analyze all + JSON
python mcp/noctusai/cli.py --analyze --json

# Catalog (shared-lib observation)
python mcp/noctusai/cli.py --catalog

# Plan projection (after ticking a phase)
python mcp/noctusai/cli.py --improvements task.md

# Tests + builds
python mcp/noctusai/cli.py --test
python mcp/noctusai/cli.py --build

# Proposals
python mcp/noctusai/cli.py --proposals
```

---

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

---

## Architecture

```
mcp/noctusai/
  server.py               MCP server — 30 tools exposed via stdio
  cli.py                  CLI for humans — same tools, human-formatted
  requirements.txt        Tool deps (separate from product venvs)
  tools/                  One module per tool family
    context.py            agent_context, product_context
    products.py           list_products, get_product_structure
    analyzers.py          duplications, inline hooks, deps, test coverage, metrics
    compliance.py         seed compliance score + issue list
    review.py             observation-only review (detect → LLM-author → propose; NEVER edits code)
    proposals.py          proposal CRUD
    ai_brain.py           OpenAI-backed reasoning (findings → proposals)
    master_prompts.py     MASTER-PROMPT sync + staleness check
    scaffold.py           new-product scaffolding from seed template
    testing.py            pytest runner + vite builder
    diff.py               product↔seed diff, orphan files, API consistency
    kb_sync.py            CLAUDE.md ↔ KB INDEX sync verifier
    catalog.py            shared-library observation (symbols, orphans, duplicates)
    improvements.py       project → improvements.md retrospective
  tests/                  pytest suite for every tool
  .venv/                  MCP-only deps
```

Each tool is **stateless** and **idempotent**: re-running never corrupts state, every run scans the filesystem fresh. Output files (`catalog.md`, `improvements.md`) are overwritten, never edited in place.

---

## Conventions enforced by this toolkit

- **`noctusai_catalog`** enforces the "shared-library first" rule — run it before writing anything that might already exist in `noctusai_lib`, and after any change to the seed to verify no new orphans/duplicates shipped. See `KNOWLEDGE-BASE/CONTEXT/PATTERNS/shared-library-conventions.md`.
- **`noctusai_improvements`** enforces the "retrospective-per-phase" rule — projects are living documents, and each phase captures learnings inline as an `**Improvements:**` block. The tool aggregates these into `improvements.md` next to the project file, so future reworkers of a phase read the original-build friction before touching anything. See `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md`.
- **`noctusai_review`** enforces the "no violations ship" rule *without* touching code. Every detected issue becomes a proposal the human triages. Referenced from `CLAUDE.md → Engineering Philosophy → MCP toolkit reviews after every change (observation-only)`.
