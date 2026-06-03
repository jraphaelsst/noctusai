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
- **Codebase is source of truth.** Docs/memory/reports drift; verify against the tree first, code wins. → `KB § 01-PHILOSOPHY.md`
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
- **Triage at decision time.** "Accept" is a real landing only with paperwork; recurrence flips accept→formalize. → `KB § PATTERNS/common/accept-with-rationale.md`
- **Safety nets capture failures → learnings → methodology evolves.** The net firing IS the methodology working. → `KB § 01-PHILOSOPHY.md`
- **Learn from friction on BOTH axes — process ∧ craft.** A fired gate or recurring bug is a learning event, never a bypass; close the loop (nothing dangles). → `KB § PATTERNS/common/methodology-execution-discipline.md` · `product-dev-learning-ground.md`
- **Always-hardening posture.** Every surfaced pattern (incl. explanation-as-signal) is a methodology-improvement opportunity; announce LOUDLY, apply before ship. → `KB § 01-PHILOSOPHY.md` · skills `skill-scout` / `codify`
- **Branching — ONE unified methodology.** Worktree isolation is the primitive: isolate off `origin/dev` → integrate clean → never switch a shared HEAD. → `KB § PATTERNS/common/branching.md` · skill `noc-self-branch`
- **`main` is production; `dev` is integration.** Everyday work + pushes → `dev`; `main`/`prod` only by explicit consent; **prod-deploy promotes a dev-fleet-validated build** (deploy+smoke on dev, never first-contact); branch model is phased (target `prod`=code-only). → `KB § PATTERNS/architect/git-branch-model.md` · skill `noc-ship`
- **Branching-first orchestration.** Orchestrator=architect (stays with user), subagents=engineers; inline below the cutoff. → `KB § 01-PHILOSOPHY.md` · skill `noc-branch-dispatch`
- **Parallelization-first orchestration.** Real specialized-agents-in-parallel is the DEFAULT mindset (each `.claude/agents/<name>` brings its lens); serial / inline only when shared-state, single-coherent-voice, or below the inline cutoff. → `KB § PATTERNS/architect/parallelization-first-orchestration.md` · skill `noc-branch-dispatch`
- **FE↔BE contract-first dispatch — default for connected BE/FE work.** Author the endpoint contract (shapes/field-names/envelope-vs-bare/status) FIRST; both build to it. → `KB § PATTERNS/architect/fe-be-contract-first-dispatch.md`
- **Don't block on background tasks — keep working in parallel.** Idle-polling a running bash/agent burns session budget; queue independent background work + foreground docs/gates instead, consolidate on completion. → `KB § PATTERNS/common/dont-block-on-background.md`
- **Dispatch via `task_branch`, NEVER Agent `isolation: "worktree"`.** 🔴 Agent isolation forks from an arbitrary base (NOT `origin/dev`) — stale-base bug. Two-level: self-branch off `origin/dev` → `task_branch action=start` per engineer → dispatch in. → `KB § PATTERNS/architect/parallelization-first-orchestration.md`
- **Inline = empersonate; don't over-inline.** Inline-dev in the specialist's lens (discipline + owns_kb); orchestrator leverage = fan-out — serial inline bulk-build is slow + incomplete; break big modules into dispatches, 3rd inline build step ⇒ dispatch. → `KB § PATTERNS/architect/parallelization-first-orchestration.md`
- **Lenses-applied commit trailer (optional).** Inline-deved commits carry a `Lenses: <name>` trailer → auditable via `git log --grep "Lenses:"`. → `KB § PATTERNS/common/lenses-applied-trailer.md`
- **Self-branching mode.** 🔴 ABSOLUTE: never work on `dev`; every writing task auto-isolates off `origin/dev`. → `KB § PATTERNS/common/self-branching-mode.md` · skill `noc-self-branch`
- **Knowledge tracking — durable findings.** findings.md = what-we-LEARNED; in-flight comms processed same commit, not parked. → `KB § 01-PHILOSOPHY.md`
- **Wave-based dispatch + collision-class.** Merge cleanliness is decided at DISPATCH (C1/C2/C3), not at merge. → `KB § PATTERNS/architect/branching-and-merging.md §18/§21`
- **Pilot-products-first refactor cadence.** Prove a seed/lib change on 3 pilots before fan-out. → `KB § PATTERNS/architect/project-execution.md`
- **No silent errors.** No `except: pass`, no silent fallback, no deferral without a named destination; ambiguity → ask. → `KB § 01-PHILOSOPHY.md`
- **Remediation markers.** A batch-able deferral lives in-code as `NOC-REMEDIATE[<class>]` — the named destination. → `KB § PATTERNS/common/remediation-markers.md`
- **Doc-propagation sync.** A rule/tool change lives in KB ↔ CLAUDE.md ↔ memory ↔ tool-code the same commit. → `KB § 01-PHILOSOPHY.md`
- **Keeper-check before doc'ing.** Query the local keeper-pattern cache before authoring any gated doc (agent/skill/CLAUDE.md/MEMORY.md/KB) — author from the live contract, not memory; the cache mirrors `compliance.py` via pre-commit refresh + lazy rebuild + `check_keeper_cache_freshness`. → `KB § PATTERNS/common/keeper-pattern-cache.md` · `KB § PATTERNS/common/keeper-check-before-docing.md`
- **Agent-context architecture — lean L1 over canonical depth.** `.claude/agents/<name>.md` is the specialist INDEX (rule + `→` pointer); `owns_kb:` declares domain; KB holds depth; agent-context cache holds the compact extract. Keepers `check_agent_kb_alignment` + `check_agent_context_cache_freshness` enforce. → `KB § PATTERNS/common/agent-context-architecture.md`
- **Scoped auto-improvement + consult-before-editing.** Dispatches surface `drift-found:`/`scoped-improvement:`; tech-lead RESOLVES, engineers SURFACE; consult BEFORE editing any doc/agent; log open entries with a `resolve_when` so landed drift self-closes. → `KB § PATTERNS/common/scoped-auto-improvement.md`
- **Dispatch with PROJECT — return with notes.** Tech-lead writes PROJECT.md §4a routing before dispatch; engineer/inline-lens returns a `delivery` note, or a `surface` note + BLOCK when re-routing mid-flight. → `KB § PATTERNS/common/dispatch-with-project-and-notes.md`
- **KB vector search — markdown canonical, vector DB is enrichment.** 4th keeper-mirror cache (`.claude/cache/kb-embeddings.sqlite`, sqlite-vec + OpenAI embed via seed lib); ADDITIVE semantic-search + `kb_neighbors`/`kb_similar`/`kb_validate_owns_kb`/generic `vector_*` primitives. Markdown stays canonical. Keeper `check_kb_vector_canonical` advisory-only. → `KB § PATTERNS/common/kb-vector-search.md`
- **noc-graph — structured graph of the platform.** 8th keeper-mirror (`.claude/cache/noc-graph.sqlite`); materializes code+KB+memory+harness+landscape+cli+history as queryable nodes/edges; fresh agents reach `/contextualize` + `noctus.graph.*` instead of composing 5 scans; keeper `check_noc_graph_cache_freshness` advisory-only. → `KB § PATTERNS/architect/noc-graph.md` · skill `noc-contextualize`
- **Persistent-files absorption.** findings.md/PROJECT.md/lessons MUST land in KB/memory BEFORE archive — recovery pointer + absorption both legs. → `KB § PATTERNS/common/persistent-files-absorption.md`
- **Learn-before-archive.** Before any destructive op preserve what would be LOST; tool `noctus.dev.salvage_before_delete`. → `KB § PATTERNS/common/learn-before-archive.md`
- **Roadmap tracking — multi-session project plans.** Multi-slice initiatives live in `project-history/roadmaps/<slug>-YYYY-MM.md` (durable, mutable — `projects/` is ephemeral, ndjson is event-shaped). Goal + slice table + decision log + retrospective. Absorb lessons → KB/memory. → `KB § PATTERNS/common/roadmap-tracking.md`
- **Durable surfaces self-contained.** A config/script ref into `projects/`/`archive/` breaks loudly when archived. → `KB § 01-PHILOSOPHY.md`
- **Symbol-first for dense / AI-intended docs.** Lossless-swap test gates each prose→symbol swap; `→`=routes, `⇒`=implies. → `KB § PATTERNS/common/doc-symbology.md`
- **Context budget discipline.** The auto-loaded budget compounds every reply. MCP keep-list: `noctusai`+`supabase`+`n8n`+`waha`. → `KB § 01-PHILOSOPHY.md`
- **Lossless doc-refactor.** Changing the doc-set itself is methodology surgery — lossless proven, not asserted. → `KB § PATTERNS/common/lossless-doc-refactor.md`
- **CLAUDE.md is the always-on router — keep it pointer-only.** §1 = principle + map (one-line rule + `→` pointer); procedures in skills, depth in KB; re-bloat is gated. → `KB § PATTERNS/common/claude-md-router-discipline.md`
- **8-way sync — methodology surfaces stay aligned.** Eight first-class surfaces (CLAUDE.md / MEMORY.md / `.claude/agents/` / KB / CONTEXTUALIZE.md / `.claude/skills/` / `.claude/commands/` / `.claude/cache/`) carry methodology PROSE or consumption — caches are the live agent read path. Enforced by `check_eight_way_sync` (composes per-surface sub-keepers). → `KB § PATTERNS/common/eight-way-sync.md`
- **Versioning — SemVer with explicit pre-release stages.** `MAJOR.MINOR.PATCH[-alpha|beta|rc]`; contract bumps follow Conventional-Commits→SemVer; source of truth `/VERSION`. → `KB § PATTERNS/common/versioning.md`
- **Cache-locking discipline — WAL + busy_timeout on every keeper-mirror SQLite cache.** WAL = readers never block the writer; busy_timeout = a contending writer waits instead of erroring `database is locked` (WAL doesn't serialize writer-vs-writer). Single helper `cache_backend.apply_locking_pragmas`. → `KB § PATTERNS/common/cache-locking-discipline.md`
- **Cache auto-freshness — two-tier + heal-on-contact.** Structural caches refresh pre-commit AND self-heal on check (`settle_structural_caches`, zero-OpenAI); embedding caches warn-only. → `KB § PATTERNS/common/cache-auto-freshness.md`
- **Cache-portable architecture — TWO-TIER persistent + machine-portable.** Tier-1 local (shared by all worktrees of this repo); Tier-2 prod pgvector mirror; auto-pull-on-empty for fresh-clone bootstrap. → `KB § PATTERNS/common/cache-portable-architecture.md`
- **Vectorize → embed → cache (the unified pipeline).** Any vectorize/embed/cache slice follows the SAME 3-leg pipeline: (1) caching-architecture decision (extend before spawn), (2) embed via `noctusai_lib.integrations.llm` (cost-log), (3) cache with source-sha invariant + 3-leg mirror contract. → `KB § PATTERNS/common/vectorize-embed-cache-framework.md`
- **Sibling workspaces consume noc read-only, whole.** Trimming the inherited surface breaks seed-first analysis + sync. → `KB § PATTERNS/architect/seed-workspace.md`
- **Divergent-architecture absorptions → house container model.** One container, `serve_spa`, seed base image; no fleet carve-out. → `KB § PATTERNS/devops/containerization.md §12a` · skill `noc-absorb-product`
- **Parallel-agent collision protocol.** Twice-reverted → STOP, wait, continue non-colliding; no collision-report project. → `KB § PATTERNS/architect/project-execution.md`

---

## 2 · The Map (open on-demand)

**Topical behavioral rules** (`CLAUDE/<topic>.md`, read by discipline): `backend.md` · `frontend.md` · `projects.md` · `platform.md`.

**Specialist subagents** (`.claude/agents/`): `architect` · `security` · `compliance-reviewer` (advisors — read-only, consulted) · `backend-engineer` · `frontend-engineer` · `devops-engineer` · `engineer-seed` (executors — worktree + commit-own-branch-only) · `skill-scout` (vendors skills in-home) · `orchestrator-operator`. **Tech-lead = the orchestrator** (the conversational session that owns all git/merge/deploy; no agent file). → `KB § 06-AGENTS.md` · `KB § PATTERNS/architect/dev-team.md`.

**Procedure skills** (`.claude/skills/`, auto-trigger on phrases): `noc-contextualize` · `noc-new-product` · `noc-absorb-product` · `noc-ship` · `noc-branch-dispatch` · `noc-self-branch` · `noc-wiring-audit` · `noc-container-debug` · `noc-hygiene` · `noc-roadmap` · `noc-wrap-up` · `noc-verify-seed` · `noc-triage` · `noc-organ-consume-check` · `skill-creator`.

**Slash commands** (`.claude/commands/`, user-invoked via `/<name>`): `/contextualize` (fresh-agent graph-shaped orientation) · `/codify` (drain codification pipeline) · `/vector-status` (cache health overview) · `/baselines` (kb + code ratification status) · `/codification-radar` (s1/s2 → s3 promotion candidates) · `/cost-report` (vector-costs.ndjson analysis) · `/verify-pass` (verify-pending pass scaffolding) · `/refresh-caches` (orchestrated all-cache refresh).

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

**Pre-commit hook enforces it** (`scripts/hooks/pre-commit`): syncs `products/seed/`→`templates/product-seed/` if staged; runs `noctus.dev.kb_sync` to regenerate counts + **block** on any unresolved `KB § …` pointer in `CLAUDE.md`/`CLAUDE/*.md`/`.claude/agents/*.md`/`KB/**`, any KB doc missing from `INDEX.md`, or any `products/<slug>/` lacking a `02-LANDSCAPE.md` roster row; and runs `check_claude_md_router` (`--check-claude-md-router`) to **block** a re-bloated router when `CLAUDE.md` is staged (`KB § PATTERNS/common/claude-md-router-discipline.md`).

Manual: `python mcp/noctusai/cli.py --verify-kb-sync` · `--check-claude-md-router` · `--update-kb-counts [--check]`. Fresh clone: `bash scripts/install-hooks.sh`. Bypass (rarely correct): `git commit --no-verify`.

> Throughout, `KB § X` = `KNOWLEDGE-BASE/X`.
