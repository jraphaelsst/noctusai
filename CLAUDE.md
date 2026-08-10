# CLAUDE.md · v4.0 — router (synthesis)

> **Auto-loaded every session.** Two jobs: (a) §1 the always-on behavioral rules (rule + one-clause why + `→` pointer, one line each); (b) routing into `CLAUDE/<topic>.md` (topical), `.claude/skills/` (procedures, auto-triggered), `.claude/agents/` (specialists), and `KNOWLEDGE-BASE/` (depth). Bodies live at the pointers — never inline (the auto-loaded budget compounds every reply). Can't find a rule → open its `KB § …` pointer or `KB § INDEX.md`.
>
> **The router stays pointer-only** — `§1` carries PRINCIPLE + the MAP; PROCEDURE lives in `.claude/skills/noc-*` (auto-trigger on phrases), depth in KB. Enforced by `check_claude_md_router` (`KB § PATTERNS/common/claude-md-router-discipline.md`), not habit.

---

<!-- NEW-SESSION-CONTEXTUALIZATION -->
## 0 · New session — "contextualize"

Fresh/clean-context agent AND the user says "contextualize" (or you don't know this platform) → **skill `noc-contextualize`** → read `/CONTEXTUALIZE.md` first, then do the task. Already-oriented agent → NO-OP, skip (don't re-read CONTEXTUALIZE.md).

---

## 1 · Universal rules (rule + one-clause why; depth at the pointer)

- **Vocabulary — methodology, not doctrine.** Hierarchical framing runs counter to how this team works. → `KB § 01-PHILOSOPHY.md`
- **Seed first. Always.** The seed IS the approach; a customization not through a named seam is a structural fork. → `KB § 03-SEED-ARCHITECTURE.md` · skill `noc-new-product`
- **Verify the seed ships it.** A planned "consume" silently becomes a "seed-build" if only the Protocol/Fake ships. → `KB § 03-SEED-ARCHITECTURE.md`
- **Seed IO modules ship Fake+Real+factory.** Half-shipped seed IO generates consumer-side forks. → `KB § PATTERNS/backend/seed-fake-real-adapter.md`
- **Seed defaults = canonical answer, not consumer-#1 coincidence.** A coincidence default silently misroutes consumers #2..N. → `KB § PATTERNS/architect/seed-canonical-defaults.md`
- **No incomplete commits.** One real side + one placeholder side lies about maturity; "scaffolded" ≠ "complete." → `KB § 03-SEED-ARCHITECTURE.md`
- **Product-internal-wiring.** route-exists ≠ wired; a page must show real data ∧ own its CRUD. → `KB § PATTERNS/frontend/product-internal-wiring.md` · skill `noc-wiring-audit`
- **No quick fixes.** A fix touching N products for one reason is at the wrong level — go to the root. → `KB § 01-PHILOSOPHY.md`
- **No workarounds / no monkey-patching (incl. tests).** Patching our own guard means the test no longer exercises it. → `KB § PATTERNS/compliance/testing.md`
- **Auth tests: assert strict `== 401`, never `in (401, 404|422)`.** The non-401 branch is a false-green (route-absent ∨ validation-before-auth); only static AST catches it. → `KB § PATTERNS/compliance/auth-boundary-false-green.md`
- **Estimate off evidence, not structure.** Cross-cutting layers hide cost; open the files before sizing. → `KB § 01-PHILOSOPHY.md`
- **Codebase is source of truth — for SOLUTIONS, not just facts.** Docs/memory/reports drift; verify against the tree first. Grep for the existing mechanism BEFORE designing one — a correct fix for a solved problem ships as a fork. → `KB § 01-PHILOSOPHY.md` · `KB § PATTERNS/common/methodology-execution-discipline.md`
- **Cache-first search — reach for a cache BEFORE grep / Read.** Semantic via `*_search`, structural via `noctus.graph.*`; grep/Read are confirmation tools, not discovery. → `KB § PATTERNS/common/cache-as-agent-tool.md`
- **Fix-on-contact for pre-existing debt.** Surface-only = a silent-error one level up; fix in-flight then surface. → `KB § 01-PHILOSOPHY.md`
- **Drift-fix-on-contact.** Git leftovers (untracked-at-root, orphan branches, uncommitted worktrees) + broken methodology pointers + stale process artifacts: PAUSE → resolve → surface-if-blocked → update docs the resolution touches → continue. Silent-skip = silent-error shape. → `KB § PATTERNS/common/drift-fix-on-contact.md` · skill `noc-self-branch`
- **NEVER `--no-verify` (commit OR push).** Commit-no-verify skips ALL keepers; 5 rationalization shapes catalogued + blocked. → `KB § PATTERNS/common/bypass-rationalization-anti-patterns.md`
- **Gate↔methodology sync.** A gate ships its compliance-by-construction mechanism same-commit (refuse-not-null; gate=backstop) — never gate-only or worked-around. → `KB § PATTERNS/common/gate-methodology-sync.md`
- **DRY — the recurrence rule.** N=2 → triage; N=3+ MUST formalize; shipping the 4th instance is forbidden. → `KB § PATTERNS/architect/project-execution.md` · skill `noc-hygiene`
- **Repetitive procedure → skill at N≥2.** Same multi-step orient→act procedure repeats ⇒ codify as a `.claude/skills/noc-*` skill — DRY for procedures, sibling of code-DRY + methodology-codification pipeline. → `KB § PATTERNS/common/repetitive-task-skill-codification.md` · skill `skill-creator`
- **Build-learn-cache mindset (not only during dev).** Body-DRY: every artifact accumulates 8 knowledge categories AS WE BUILD, cached sidecar ∨ noc-graph node, append-only. → `KB § PATTERNS/common/build-learn-cache-mindset.md`
- **Products consume canonical organs.** Organ-shaped FE components in `products/<slug>/` MUST import from `@noctusai/lib/...` — no local re-implementations. Named-seam extensions allowed when DECLARED. Enforced by `check_canonical_organ_consumption`. → `KB § PATTERNS/architect/products-consume-canonical-organs.md` · skill `noc-organ-consume-check`
- **Consent routes are seed-mounted — never re-declare per-product.** A local re-declaration shadows Google OAuth + Meta App Review URLs fleet-wide. → `KB § PATTERNS/frontend/consent-routes-mandate.md`
- **Componentize everything.** If another product will need it, build it shared from day one. → `KB § 04-SHARED-LIBRARY.md`
- **Reading & research discipline.** Whole-file reads waste budget; narrow-read + delegate breadth to Explore. → `KB § PATTERNS/common/agent-reading-discipline.md`
- **Replication-to-seed symmetry.** The trigger is LANGUAGE — "per-product X" IS the slip; right count = zero. → `KB § PATTERNS/architect/project-execution.md` · agent `architect`
- **AST-first.** If a compiler/type-checker parses the file, edit it via libcst/ts-morph, never regex. → `KB § PATTERNS/common/ast.md`
- **Flag MCP-first / AST-first opportunities proactively.** Silent skipping = silent-error shape. → `KB § 01-PHILOSOPHY.md`
- **MCP-first scripts.** A new automation IS an agent-exposable capability → a `noctus.dev.*` tool. → `KB § PATTERNS/architect/mcp-first-scripts.md`
- **Hygiene scanning.** Run hound/mole/keeper-analog sweeps before walking away; teardown = salvage-before-delete via a tool. → `KB § PATTERNS/common/storage-hygiene.md` · skill `noc-hygiene`
- **Learning posture — one loop, four rules.** Friction is a learning event on BOTH axes (process ∧ craft); safety nets firing IS the methodology working; every surfaced pattern is a hardening opportunity announced LOUDLY; triage lands at decision time with paperwork. → `KB § PATTERNS/common/learning-posture-family-index.md`
- **Branching — ONE unified methodology.** Worktree isolation is the primitive: isolate off `origin/dev` → integrate clean → never switch a shared HEAD. → `KB § PATTERNS/common/branching.md` · skill `noc-self-branch`
- **`main` is production; `dev` is integration.** Everyday work + pushes → `dev`; `main`/`prod` only by explicit consent; **prod-deploy promotes a dev-fleet-validated build** (deploy+smoke on dev, never first-contact); branch model is phased (target `prod`=code-only). → `KB § PATTERNS/architect/git-branch-model.md` · skill `noc-ship`
- **Prod-exposure-surface registration IS the promotion decision — the user's, never an agent's.** An agent may RECORD that decision (canonical phrase, verified against the harness-written transcript), never invent one. → `KB § PATTERNS/devops/prod-exposure-consent.md`
- **Orchestration & dispatch — one framework, nine rules.** Branching-first + parallelization-first posture, the `task_branch` dispatch primitive, contract-first FE↔BE, wave/collision-class, inline-vs-dispatch cutoff, PROJECT-and-notes, background-work discipline, and the lenses trailer. → `KB § PATTERNS/common/orchestration-family-index.md`
- **Self-branching mode.** 🔴 ABSOLUTE: never work on `dev`; every writing task auto-isolates off `origin/dev`. Gated, not trusted — a work commit on `dev`/`main`/`prod` in the primary checkout is REFUSED by `check_primary_checkout_commit` (nothing failed at commit time, so discipline alone never held). → `KB § PATTERNS/common/self-branching-mode.md` · skill `noc-self-branch`
- **Knowledge lifecycle — one chain, five rules.** What we LEARN is captured (findings · scoped-auto-improvement), absorbed before archive (persistent-files · learn-before-archive), and planned across sessions (roadmaps). Capture without absorption loses it. → `KB § PATTERNS/common/knowledge-lifecycle-family-index.md`
- **Pilot-products-first refactor cadence.** Prove a seed/lib change on 3 pilots before fan-out. → `KB § PATTERNS/architect/project-execution.md`
- **No silent errors.** No `except: pass`, no silent fallback, no deferral without a named destination; ambiguity → ask. → `KB § 01-PHILOSOPHY.md`
- **Remediation markers.** A batch-able deferral lives in-code as `NOC-REMEDIATE[<class>]` — the named destination. → `KB § PATTERNS/common/remediation-markers.md`
- **Doc discipline — one surface-set, eight rules.** The always-on docs (CLAUDE.md router · MEMORY.md topic-router · 8-way sync · doc-propagation · symbology · lossless-refactor · durable-self-contained · keeper-check-before-doc'ing) are load-bearing infrastructure with their own budgets and gates. → `KB § PATTERNS/common/doc-discipline-family-index.md`
- **Agent-context architecture — lean L1 over canonical depth.** `.claude/agents/<name>.md` is the specialist INDEX (rule + `→` pointer); `owns_kb:` declares domain; KB holds depth; agent-context cache holds the compact extract. Keepers `check_agent_kb_alignment` + `check_agent_context_cache_freshness` enforce. → `KB § PATTERNS/common/agent-context-architecture.md`
- **Cache platform — one framework, six rules.** The keeper-mirror caches (vector search · noc-graph · locking · auto-freshness · portability · the vectorize→embed→cache pipeline) compose into ONE contract; a session that needs cache mechanics needs all of them. → `KB § PATTERNS/common/cache-family-index.md`
- **Context budget discipline.** The auto-loaded budget compounds every reply. MCP keep-list: `noctusai`+`supabase`+`n8n`+`waha`. → `KB § 01-PHILOSOPHY.md`
- **Versioning — SemVer with explicit pre-release stages.** `MAJOR.MINOR.PATCH[-alpha|beta|rc]`; contract bumps follow Conventional-Commits→SemVer; source of truth `/VERSION`. → `KB § PATTERNS/common/versioning.md`
- **Sibling workspaces consume noc read-only, whole.** Trimming the inherited surface breaks seed-first analysis + sync. → `KB § PATTERNS/architect/seed-workspace.md`
- **Divergent-architecture absorptions → house container model.** One container, `serve_spa`, seed base image; no fleet carve-out. → `KB § PATTERNS/devops/containerization.md §12a` · skill `noc-absorb-product`
- **Parallel-agent collision protocol.** Twice-reverted → STOP, wait, continue non-colliding; no collision-report project. → `KB § PATTERNS/architect/project-execution.md`
- **No lying loading states — gate `loading` on `isPending || isFetching`, never `isLoading`.** TanStack v5 `isLoading` is false during a background refetch, so an `isEmpty` branch renders "no data" over data that exists; keeper `check_lying_loading_state`. → `KB § PATTERNS/frontend/lying-loading-state.md`
- **An RLS read-policy that filters a category makes every FE branch on it DEAD — and the two halves must name the same roles.** `status_pagina='desenvolvimento'` was returned to nobody, so the dev/owner branch never ran and shipped pages stayed invisible; keeper `check_status_pagina_role_parity`. → `KB § PATTERNS/frontend/status-pagina-dev-visibility.md`
- **Hand-maintained lists drift and break the fleet — derive, don't sync by hand; gate pre-push.** Slug sets ∧ lockfile-embedded seed snapshots discovered in CI *after* promotion; keepers `check_hardcoded_product_slug_set` + `check_product_lockfile_dep_sync`. → `KB § PATTERNS/devops/product-lockfile-and-slug-drift.md`
- **Per-branch green ≠ integration green — re-run gates on the MERGED tip before bless.** File-disjoint isn't effect-disjoint; derived artifacts (baselines/lockfiles/parity/barrels) couple parallel slices. → `KB § PATTERNS/common/methodology-execution-discipline.md`
- **Verify PASS/FAIL by exit code, never a piped `tail` — `cmd | tail` returns tail's status.** A trimmed pipe converts "did it pass?" into "did tail run?" (always yes); use `pipefail` or capture `rc=$?`. → `KB § PATTERNS/common/methodology-execution-discipline.md`

---

## 2 · The Map (open on-demand)

**Topical behavioral rules** (`CLAUDE/<topic>.md`, read by discipline): `backend.md` · `frontend.md` · `projects.md` · `platform.md`.

**Specialist subagents** (`.claude/agents/`): `architect` · `security` · `compliance-reviewer` (advisors — read-only, consulted) · `backend-engineer` · `frontend-engineer` · `devops-engineer` · `engineer-seed` (executors — worktree + commit-own-branch-only) · `skill-scout` (vendors skills in-home) · `orchestrator-operator`. **Tech-lead = the orchestrator** (the conversational session that owns all git/merge/deploy; no agent file). → `KB § 06-AGENTS.md` · `KB § PATTERNS/architect/dev-team.md`.

**Procedure skills** (`.claude/skills/`, auto-trigger on phrases): `noc-contextualize` · `noc-new-product` · `noc-absorb-product` · `noc-ship` · `noc-branch-dispatch` · `noc-self-branch` · `noc-wiring-audit` · `noc-container-debug` · `noc-hygiene` · `noc-roadmap` · `noc-wrap-up` · `noc-verify-seed` · `noc-triage` · `noc-organ-consume-check` · `noc-contract-first` · `noc-mcp-tool` · `noc-archive-absorb` · `skill-creator`.

**Slash commands** (`.claude/commands/`, user-invoked via `/<name>`): `/contextualize` (fresh-agent graph-shaped orientation) · `/codify` (drain codification pipeline) · `/gc` (methodology garbage-collection — the codify exhaust) · `/vector-status` (cache health overview) · `/baselines` (kb + code ratification status) · `/codification-radar` (s1/s2 → s3 promotion candidates) · `/cost-report` (vector-costs.ndjson analysis) · `/verify-pass` (verify-pending pass scaffolding) · `/refresh-caches` (orchestrated all-cache refresh).

**§1 family indexes** (`KB § PATTERNS/common/*-family-index.md`): a §1 family line is a router hop — the member rules live at the pointer **verbatim**. `cache` · `orchestration` · `knowledge-lifecycle` · `doc-discipline` · `learning-posture`. → `KB § PATTERNS/common/methodology-gc.md`

**Architecture & depth** (KB): philosophy → `01-PHILOSOPHY.md` · landscape → `02-LANDSCAPE.md` · seed → `03-SEED-ARCHITECTURE.md` · shared-lib → `04-SHARED-LIBRARY.md` · infra → `05-INFRASTRUCTURE.md` · MCP toolkit/agents → `06-AGENTS.md` · gamification → `07-GAMIFICATION.md`.

**Full pattern + integration + guide + per-product catalog → `KB § INDEX.md`** (the canonical map; not duplicated here). High-traffic patterns: backend · frontend · testing · database-rls · core-url-routing · dev-prod-parity · branching · containerization · product-internal-wiring · accept-with-rationale.

---

## 3 · When to read what (residual — most workflows auto-route via `.claude/skills/noc-*`)

| Situation | First stop |
|---|---|
| Fresh session / orientation | skill `noc-contextualize` |
| Writing backend / frontend code | `CLAUDE/backend.md` / `CLAUDE/frontend.md` + matching `KB § PATTERNS/` |
| Create/scaffold/absorb a product · deploy/ship · branch/dispatch · self-branch · wiring audit · container debug · cleanup | the matching `noc-*` skill (auto-triggers) |
| Need a specialist opinion mid-flight (design / security / compliance) | dispatch agent `architect` / `security` / `compliance-reviewer` (read-only advisors) |
| Starting/closing a project; touching `*-PROJECT.md` | `CLAUDE/projects.md` + `KB § PATTERNS/architect/project-execution.md` |
| Migration · auth wiring · OAuth/integration · LGPD · anything else | `KB § INDEX.md` → the relevant pattern/integration |

---

## 4 · Sync rule

CLAUDE.md, `CLAUDE/<topic>.md`, `.claude/skills/`, `.claude/agents/`, and `KB § INDEX.md` stay in sync — add/rename/delete a KB file or a skill/agent and every referencing layer updates the same commit.

**Pre-commit hook enforces it** (`scripts/hooks/pre-commit`): syncs `products/seed/`→`templates/product-seed/` if staged; runs `noctus.dev.kb_sync` to regenerate counts + **block** on any unresolved `KB § …` pointer in `CLAUDE.md`/`CLAUDE/*.md`/`.claude/{agents,skills,commands}/`/`KB/**`, any KB doc missing from `INDEX.md`, or any `products/<slug>/` lacking a `02-LANDSCAPE.md` roster row; and runs `check_claude_md_router` (`--check-claude-md-router`) to **block** a re-bloated router when `CLAUDE.md` is staged — word budget, per-rule shape, **and the §1 rule-COUNT ceiling** (`KB § PATTERNS/common/claude-md-router-discipline.md` · `KB § PATTERNS/common/methodology-gc.md`).

Manual: `python mcp/noctusai/cli.py --verify-kb-sync` · `--check-claude-md-router` · `--update-kb-counts [--check]`. Fresh clone: `bash scripts/install-hooks.sh`. Bypass (rarely correct): `git commit --no-verify`.

> Throughout, `KB § X` = `KNOWLEDGE-BASE/X`.
