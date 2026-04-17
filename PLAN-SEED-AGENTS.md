# [HISTORICAL] Plan: Seed Agents — Guardian + Scientist

> **STATUS: OBSOLETE.** This plan was executed and evolved into the MCP Dev Toolkit at `mcp/noctusai/`.
> The `agents/` directory has been deleted. All 28 tools now live in the MCP server.
> See `KNOWLEDGE-BASE/CONTEXT/11-AGENTS.md` for the current architecture.

> ~~Two AI-powered agents that protect and evolve the seed infrastructure.~~
> ~~Location: `agents/` at repo root.~~

---

## The Two Agents

### 1. Seed Guardian (Stability Agent)

**Purpose:** Monitor, validate, and ensure the seed and all products stay healthy, in sync, and structurally correct. This agent is the immune system — it detects problems before they become bugs.

**Personality:** Conservative, precise, zero tolerance for drift. If something breaks the seed contract, it reports immediately.

**What it does:**
- [ ] Validates that every product's `main.py` uses `create_product_app()` from `noctusai_seed`
- [ ] Validates that every product's `App.tsx` uses `createProductApp()` from `@noctusai/seed`
- [ ] Detects structural code duplication (product re-implementing what the seed provides)
- [ ] Runs all product test suites and reports failures
- [ ] Checks that `seed/lib/` imports work across all products
- [ ] Checks that `seed/framework/` imports work across all products
- [ ] Validates path references (requirements.txt, vite.config.ts, tsconfig.json, tailwind.config.ts)
- [ ] Detects when a product diverges from the seed pattern (added its own health.py, notificacoes.py, etc.)
- [ ] Validates RLS policies follow the standard `(SELECT auth.jwt()) ->> 'org_id'` pattern
- [ ] Checks that CLAUDE.md and KNOWLEDGE-BASE are in sync with actual code
- [ ] Reports a health score per product (0-100) based on seed compliance

**Output:** JSON report with per-product health scores, issues found, and recommended fixes.

**Schedule:** Runs on-demand or via cron (e.g., daily, or after every commit).

### 2. Seed Scientist (Innovation Agent)

**Purpose:** Experiment, discover, and propose improvements to the seed infrastructure. This agent is the R&D department — it explores what could be better, builds prototypes, tests them in isolation, and presents results for human approval.

**Personality:** Creative, exploratory, data-driven. It tries things, fails fast, and learns. It never merges — it proposes.

**What it does:**
- [ ] Analyzes the seed framework for improvement opportunities (performance, DX, maintainability)
- [ ] Researches new patterns from the FastAPI/React ecosystem that could strengthen the seed
- [ ] Proposes new shared components by analyzing code patterns across products (finds duplication)
- [ ] Builds prototype improvements in isolated branches (never touches main)
- [ ] Runs benchmarks comparing current vs proposed implementations
- [ ] Generates "improvement proposals" with: problem, solution, trade-offs, benchmark results
- [ ] Tests proposed changes against all product test suites before proposing
- [ ] Explores AI-powered features that could be added to the seed (e.g., AI-assisted error handling, smart caching, auto-generated API docs)
- [ ] Investigates security improvements (dependency audits, new auth patterns, OWASP compliance)
- [ ] Watches for upstream changes in key dependencies (FastAPI, Supabase, React) that affect the seed

**Output:** Improvement proposals as markdown files with: problem statement, proposed solution, code diff, test results, risk assessment.

**Schedule:** Runs on-demand or weekly. Always in isolated branches. Never auto-merges.

---

## Technical Architecture

### Stack
- **Runtime:** Python (backend agents) + Node.js (frontend analysis)
- **AI Models:** API-based, multi-provider
  - Anthropic Claude API (primary — analysis, code review, proposals)
  - OpenAI API (secondary — embeddings for code similarity, alternative perspectives)
- **Execution:** CLI scripts that can be run locally or via CI/CD
- **Output:** JSON reports + Markdown proposals

### Folder Structure

```
agents/
  README.md                     Overview and usage instructions
  shared/                       Shared utilities for both agents
    config.py                   API keys, model selection, repo paths
    models.py                   AI model wrappers (Anthropic, OpenAI)
    repo.py                     Repo analysis utilities (file reading, git, imports)
    report.py                   Report generation (JSON + Markdown)
  guardian/                     Seed Guardian agent
    README.md                   Guardian-specific docs
    main.py                     Entry point: `python -m agents.guardian`
    checks/                     Individual validation checks
      __init__.py
      seed_compliance.py        Validate products use seed framework
      path_references.py        Validate all shared/framework paths
      code_duplication.py       Detect structural code copied from seed
      test_runner.py            Run all product test suites
      rls_validation.py         Validate RLS policy patterns
      doc_sync.py               Check CLAUDE.md + KNOWLEDGE-BASE accuracy
    scoring.py                  Health score calculator (0-100 per product)
    reporter.py                 Generate health report (JSON + Markdown)
  lab/                          Seed Scientist agent
    README.md                   Scientist-specific docs
    main.py                     Entry point: `python -m agents.scientist`
    analyzers/                  Analysis modules
      __init__.py
      pattern_finder.py         Find repeated patterns across products
      dependency_audit.py       Check for outdated/vulnerable deps
      ecosystem_scanner.py      Research new patterns from ecosystem
      performance_profiler.py   Benchmark seed operations
    proposer.py                 Generate improvement proposals
    experimenter.py             Run experiments in isolated branches
    proposals/                  Generated proposals (gitignored initially)
      .gitkeep
  requirements.txt              Agent dependencies (anthropic, openai, etc.)
```

---

## Implementation Plan

### Phase 1 — Foundation (agents/ scaffolding + shared utilities)

- [ ] Create `agents/` folder structure
- [ ] Create `agents/README.md` with usage docs
- [ ] Create `agents/requirements.txt` (anthropic, openai, pyyaml, rich)
- [ ] Build `agents/shared/config.py` — load API keys from .env, model selection
- [ ] Build `agents/shared/models.py` — wrappers for Claude API + OpenAI API
- [ ] Build `agents/shared/repo.py` — repo analysis helpers:
  - `list_products()` — find all products in products/
  - `read_file(path)` — read any file
  - `find_imports(file)` — extract import statements
  - `get_product_structure(product)` — map a product's file tree
  - `run_tests(product)` — execute pytest for a product
- [ ] Build `agents/shared/report.py` — report formatting (JSON, Markdown, console)

### Phase 2 — Seed Guardian (stability agent)

- [ ] Build `agents/guardian/checks/seed_compliance.py`:
  - Check every product's main.py imports `create_product_app` from `noctusai_seed`
  - Check every product's App.tsx imports from `@noctusai/seed`
  - Report: compliant / non-compliant / partially-migrated
- [ ] Build `agents/guardian/checks/path_references.py`:
  - Scan all requirements.txt for correct `seed/backend/lib` path
  - Scan all vite.config.ts for correct `seed/frontend/lib/src` path
  - Scan all tsconfig.json for correct paths
  - Scan all tailwind.config.ts for correct paths
- [ ] Build `agents/guardian/checks/code_duplication.py`:
  - Use AI (Claude API) to analyze product files vs seed framework
  - Detect when a product has its own health router, notification proxy, or team router
  - Detect when a product re-implements get_current_user, get_org_id, etc.
- [ ] Build `agents/guardian/checks/test_runner.py`:
  - Run `pytest` for each product backend
  - Capture pass/fail counts
  - Report broken products
- [ ] Build `agents/guardian/checks/rls_validation.py`:
  - Parse migration SQL files
  - Check all RLS policies use `(SELECT auth.jwt())` pattern (not bare `auth.uid()`)
  - Check all functions have `SET search_path`
- [ ] Build `agents/guardian/checks/doc_sync.py`:
  - Use AI to compare CLAUDE.md rules against actual code patterns
  - Flag rules that don't match reality
  - Flag code patterns not documented in CLAUDE.md
- [ ] Build `agents/guardian/scoring.py`:
  - Weight each check category
  - Calculate 0-100 score per product
  - Calculate overall platform health score
- [ ] Build `agents/guardian/reporter.py`:
  - JSON report for CI/CD consumption
  - Markdown report for human review
  - Console output with colors (via rich)
- [ ] Build `agents/guardian/main.py`:
  - CLI: `python -m agents.guardian` (run all checks)
  - CLI: `python -m agents.guardian --product erp` (single product)
  - CLI: `python -m agents.guardian --check seed_compliance` (single check)
  - Output: report to console + optional file

### Phase 3 — Seed Scientist (innovation agent)

- [ ] Build `agents/scientist/analyzers/pattern_finder.py`:
  - Scan all products for repeated code patterns
  - Use AI (Claude API) to identify extraction opportunities
  - Suggest what should become shared components or seed framework additions
- [ ] Build `agents/scientist/analyzers/dependency_audit.py`:
  - Check all requirements.txt and package.json for outdated packages
  - Check for known vulnerabilities (query PyPI, npm audit)
  - Suggest updates with risk assessment
- [ ] Build `agents/scientist/analyzers/ecosystem_scanner.py`:
  - Use AI to research latest FastAPI, Supabase, React best practices
  - Compare current seed patterns against ecosystem recommendations
  - Generate "what we could adopt" reports
- [ ] Build `agents/scientist/analyzers/performance_profiler.py`:
  - Benchmark key seed operations (app startup, auth flow, database client creation)
  - Identify bottlenecks
  - Suggest optimizations
- [ ] Build `agents/scientist/proposer.py`:
  - Generate structured improvement proposals (Markdown):
    - Problem statement
    - Proposed solution (with code)
    - Trade-offs and risks
    - Test results / benchmarks
    - Implementation effort estimate
  - Save to `agents/scientist/proposals/`
- [ ] Build `agents/scientist/experimenter.py`:
  - Create isolated git branches for experiments
  - Apply proposed changes
  - Run all tests to verify nothing breaks
  - Report results
  - Clean up branches (never auto-merge)
- [ ] Build `agents/scientist/main.py`:
  - CLI: `python -m agents.scientist` (run all analyzers)
  - CLI: `python -m agents.scientist --analyze patterns` (single analyzer)
  - CLI: `python -m agents.scientist --experiment proposal-001` (run experiment)
  - Output: proposals to `agents/scientist/proposals/`

### Phase 4 — Integration & Automation

- [ ] Add agents to `scripts/setup.sh` (install agent dependencies)
- [ ] Create GitHub Actions workflow for Guardian (runs on PR, blocks merge if score < threshold)
- [ ] Create scheduled Guardian run (daily health check, report to Slack/email)
- [ ] Create scheduled Scientist run (weekly analysis, proposals saved to repo)
- [ ] Add `agents/` section to CLAUDE.md
- [ ] Document in KNOWLEDGE-BASE

---

## AI Model Usage

### Guardian Agent
- **Claude API** — code analysis, doc sync validation, duplication detection
  - Model: `claude-sonnet-4-6` (fast, cost-effective for validation tasks)
  - Use: Send product file + seed framework file → "Is this product correctly inheriting from the seed?"
- **No OpenAI needed** — Guardian is deterministic + Claude analysis

### Scientist Agent
- **Claude API** — pattern analysis, improvement proposals, code generation
  - Model: `claude-sonnet-4-6` for analysis, `claude-opus-4-6` for complex proposals
  - Use: Send codebase context → "What patterns could be extracted? What improvements would strengthen the seed?"
- **OpenAI API** — embeddings for code similarity detection
  - Model: `text-embedding-3-small` for code chunk embeddings
  - Use: Vectorize code blocks across products → find similar implementations → suggest consolidation

### API Key Management
- Keys stored in root `.env` (same as other platform secrets)
- Variables: `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`
- Agents gracefully degrade if a key is missing (skip that provider's features)

---

## Environment Variables (add to .env)

```
# Agent AI Models
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Agent Configuration (optional)
AGENT_GUARDIAN_THRESHOLD=80        # Minimum health score to pass CI
AGENT_SCIENTIST_MODEL=claude-sonnet-4-6  # Default model for scientist analysis
```

---

## Usage Examples

```bash
# Run Guardian — full platform health check
python -m agents.guardian

# Run Guardian — single product
python -m agents.guardian --product mailing

# Run Guardian — single check
python -m agents.guardian --check seed_compliance

# Run Scientist — find improvement opportunities
python -m agents.scientist

# Run Scientist — specific analysis
python -m agents.scientist --analyze patterns

# Run Scientist — test a proposal
python -m agents.scientist --experiment proposal-001
```

---

## Success Criteria

### Guardian
- Detects 100% of seed compliance violations
- Runs in under 2 minutes for the full platform
- Zero false positives (every flagged issue is real)
- JSON report consumable by CI/CD

### Scientist
- Generates at least 1 actionable proposal per week
- Every proposal includes working code + test results
- Never auto-merges (human approval required)
- Proposals have clear accept/reject criteria
