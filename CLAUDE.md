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
- **Estimate off evidence, not structure.** Cross-cutting layers hide cost; open the files before sizing. → `KB § 01-PHILOSOPHY.md`
- **Codebase is source of truth.** Docs/memory/reports drift; verify against the tree first, code wins. → `KB § 01-PHILOSOPHY.md`
- **Fix-on-contact for pre-existing debt.** Surface-only = a silent-error one level up; fix in-flight then surface. → `KB § 01-PHILOSOPHY.md`
- **Drift-fix-on-contact.** Git leftovers (untracked-at-root, orphan branches, uncommitted worktrees) + broken methodology pointers + stale process artifacts: PAUSE → resolve → surface-if-blocked → update docs the resolution touches → continue. Silent-skip = silent-error shape. → `KB § PATTERNS/common/drift-fix-on-contact.md` · skill `noc-self-branch`
- **DRY — the recurrence rule.** N=2 → triage; N=3+ MUST formalize; shipping the 4th instance is forbidden. → `KB § PATTERNS/architect/project-execution.md` · skill `noc-hygiene`
- **Componentize everything.** If another product will need it, build it shared from day one. → `KB § 04-SHARED-LIBRARY.md`
- **Reading & research discipline.** Whole-file reads waste budget; narrow-read + delegate breadth to Explore. → `KB § PATTERNS/common/agent-reading-discipline.md`
- **Replication-to-seed symmetry.** The trigger is LANGUAGE — "per-product X" IS the slip; right count = zero. → `KB § PATTERNS/architect/project-execution.md` · agent `architect`
- **AST-first.** If a compiler/type-checker parses the file, edit it via libcst/ts-morph, never regex. → `KB § PATTERNS/common/ast.md`
- **Flag MCP-first / AST-first opportunities proactively.** Silent skipping = silent-error shape. → `KB § 01-PHILOSOPHY.md`
- **MCP-first scripts.** A new automation IS an agent-exposable capability → a `noctus.dev.*` tool. → `KB § PATTERNS/architect/mcp-first-scripts.md`
- **Hygiene scanning.** Run hound/mole/keeper-analog sweeps before walking away; teardown = salvage-before-delete via a tool. → `KB § PATTERNS/common/storage-hygiene.md` · skill `noc-hygiene`
- **Triage at decision time.** "Accept" is a real landing only with paperwork; recurrence flips accept→formalize. → `KB § PATTERNS/common/accept-with-rationale.md`
- **Safety nets capture failures → learnings → methodology evolves.** The net firing IS the methodology working. → `KB § 01-PHILOSOPHY.md`
- **Always-hardening posture.** Every surfaced pattern (incl. explanation-as-signal) is a methodology-improvement opportunity; announce LOUDLY, apply before ship. → `KB § 01-PHILOSOPHY.md` · skills `skill-scout` / `codify`
- **Branching — ONE unified methodology.** Worktree isolation is the primitive: isolate off `origin/dev` → integrate clean → never switch a shared HEAD. → `KB § PATTERNS/common/branching.md` · skill `noc-self-branch`
- **`main` is production; `dev` is integration.** Everyday work + pushes → `dev`; `main`/`prod` only by explicit per-action consent. → `KB § PATTERNS/architect/branching-and-merging.md §0` · skill `noc-ship`
- **Branching-first orchestration.** Orchestrator=architect (stays with user), subagents=engineers; inline below the cutoff. → `KB § 01-PHILOSOPHY.md` · skill `noc-branch-dispatch`
- **Parallelization-first orchestration.** Real specialized-agents-in-parallel is the DEFAULT mindset (each `.claude/agents/<name>` brings its lens); serial / inline only when shared-state, single-coherent-voice, or below the inline cutoff. → `KB § PATTERNS/architect/parallelization-first-orchestration.md` · skill `noc-branch-dispatch`
- **Don't block on background tasks — keep working in parallel.** Idle-polling a running bash/agent burns session budget; queue independent background work + foreground docs/gates instead, consolidate on completion. → `KB § PATTERNS/common/dont-block-on-background.md`
- **Dispatch via `task_branch`, NEVER Agent `isolation: "worktree"`.** 🔴 Agent's built-in isolation forks from arbitrary base (NOT `origin/dev`) — Wave-1 N=4 stale-base. Two-level branching: (1) architect self-branches off `origin/dev`, (2) `noctus.dev.task_branch action=start` per engineer (forks off architect's branch), (3) dispatch INTO that worktree. → `KB § PATTERNS/architect/parallelization-first-orchestration.md`
- **Inline = empersonate the specialist.** When inline-deving (no dispatch), the architect still ROUTES by domain: switch lens to backend-engineer / frontend-engineer / devops-engineer / compliance-reviewer / security per task domain. Apply each specialist's discipline + owns_kb until the task's commit, then switch. Same rationale as dispatch decisions; only difference is empersonation vs. dispatch. → `KB § PATTERNS/architect/parallelization-first-orchestration.md`
- **Lenses-applied commit trailer (optional, observability).** Inline-deved commits SHOULD carry a `Lenses: <name>[, <name>...]` trailer (e.g., `Lenses: backend-engineer, devops-engineer`) — makes inline-empersonation auditable via `git log --grep "Lenses:"`; OPTIONAL today, no keeper; valid names mirror `.claude/agents/` + `tech-lead`. → `KB § PATTERNS/common/lenses-applied-trailer.md`
- **Self-branching mode.** 🔴 ABSOLUTE: never work on `dev`; every writing task auto-isolates off `origin/dev`. → `KB § PATTERNS/common/self-branching-mode.md` · skill `noc-self-branch`
- **Knowledge tracking — durable findings.** findings.md = what-we-LEARNED; in-flight comms processed same commit, not parked. → `KB § 01-PHILOSOPHY.md`
- **Wave-based dispatch + collision-class.** Merge cleanliness is decided at DISPATCH (C1/C2/C3), not at merge. → `KB § PATTERNS/architect/branching-and-merging.md §18/§21`
- **Pilot-products-first refactor cadence.** Prove a seed/lib change on 3 pilots before fan-out. → `KB § PATTERNS/architect/project-execution.md`
- **No silent errors.** No `except: pass`, no silent fallback, no deferral without a named destination; ambiguity → ask. → `KB § 01-PHILOSOPHY.md`
- **Remediation markers.** A batch-able deferral lives in-code as `NOC-REMEDIATE[<class>]` — the named destination. → `KB § PATTERNS/common/remediation-markers.md`
- **Doc-propagation sync.** A rule/tool change lives in KB ↔ CLAUDE.md ↔ memory ↔ tool-code the same commit. → `KB § 01-PHILOSOPHY.md`
- **Keeper-check before doc'ing.** Query the local keeper-pattern cache before authoring any gated doc (agent/skill/CLAUDE.md/MEMORY.md/KB) — author from the live contract, not memory; the cache mirrors `compliance.py` via pre-commit refresh + lazy rebuild + `check_keeper_cache_freshness`. → `KB § PATTERNS/common/keeper-pattern-cache.md` · `KB § PATTERNS/common/keeper-check-before-docing.md`
- **Agent-context architecture — lean L1 over canonical depth.** `.claude/agents/<name>.md` is the specialist INDEX (rule + `→` pointer, mirrors CLAUDE.md §1); frontmatter `owns_kb:` declares full-domain territory; KB holds depth; agent-context cache (`.claude/cache/agent-context.sqlite`, Phase B SHIPPED) holds the compact extract. Keepers `check_agent_kb_alignment` + `check_agent_context_cache_freshness` enforce ownership + body-pointer mirror + cache mirror. → `KB § PATTERNS/common/agent-context-architecture.md`
- **Scoped auto-improvement + consult-before-editing.** Every dispatch returns the two-leg footer (`drift-found:` for OUTSIDE-brief leftovers + `scoped-improvement:` for IN-slice slips). Tech-lead RESOLVES on-contact; engineers SURFACE, never resolve unilaterally. Surfaces land durable in `project-history/auto-improvement.ndjson` + queryable in `.claude/cache/auto-improvement.sqlite`; consult the cache BEFORE editing any doc/agent (sibling of keeper-check-before-doc'ing). Keeper `check_auto_improvement_cache_freshness`. → `KB § PATTERNS/common/scoped-auto-improvement.md`
- **Dispatch with PROJECT — return with notes.** Tech-lead writes PROJECT.md §4a Dispatch routing (slice→lens + codification expectations s1/s2/s3/s4 + routes-not-taken) BEFORE dispatch; engineer/inline-lens reads PROJECT.md, executes, returns a **delivery note** (`kind="delivery"`). Alt route mid-flight ⇒ **surface note** (`kind="surface"`) + BLOCK until tech-lead approves/rejects/adapts with rationale. Reuses `projects/<slug>/proposals/`; notes = concept-layer via `kind` param on `noctus.dev.file_proposal`. → `KB § PATTERNS/common/dispatch-with-project-and-notes.md`
- **KB vector search — markdown canonical, vector DB is enrichment.** 4th keeper-mirror cache (`.claude/cache/kb-embeddings.sqlite`, sqlite-vec + OpenAI embed via seed lib); ADDITIVE semantic-search + `kb_neighbors`/`kb_similar`/`kb_validate_owns_kb`/generic `vector_*` primitives. Markdown stays canonical. Keeper `check_kb_vector_canonical` advisory-only. → `KB § PATTERNS/common/kb-vector-search.md`
- **noc-graph — structured graph of the platform.** 8th keeper-mirror (`.claude/cache/noc-graph.sqlite`); materializes code+KB+memory+harness+landscape+cli+history as queryable nodes/edges; fresh agents reach `/contextualize` + `noctus.graph.*` instead of composing 5 scans; keeper `check_noc_graph_cache_freshness` advisory-only. → `KB § PATTERNS/architect/noc-graph.md` · skill `noc-contextualize`
- **Persistent-files absorption.** Durable context in `projects/`/`.claude/worktrees/` (findings.md, PROJECT.md decisions, lessons) MUST land in KB/memory BEFORE archive or teardown — recovery pointer preserves access, absorption preserves the learning; both legs fire. → `KB § PATTERNS/common/persistent-files-absorption.md`
- **Roadmap tracking — multi-session project plans.** Multi-slice initiatives live in `project-history/roadmaps/<slug>-YYYY-MM.md` (durable, mutable, structured — `projects/` is ephemeral, KB is methodology-only, ndjson is event-shaped). Goal + slice table + decision log + open questions + retrospective. Absorb lessons → KB/memory on close. → `KB § PATTERNS/common/roadmap-tracking.md`
- **Durable surfaces self-contained.** A config/script ref into `projects/`/`archive/` breaks loudly when archived. → `KB § 01-PHILOSOPHY.md`
- **Symbol-first for dense / AI-intended docs.** Lossless-swap test gates each prose→symbol swap; `→`=routes, `⇒`=implies. → `KB § PATTERNS/common/doc-symbology.md`
- **Context budget discipline.** The auto-loaded budget compounds every reply. MCP keep-list: `noctusai`+`supabase`+`n8n`+`waha`. → `KB § 01-PHILOSOPHY.md`
- **Lossless doc-refactor.** Changing the doc-set itself is methodology surgery — lossless proven, not asserted. → `KB § PATTERNS/common/lossless-doc-refactor.md`
- **CLAUDE.md is the always-on router — keep it pointer-only.** §1 = principle + map (one-line rule + `→` pointer); procedures in skills, depth in KB; re-bloat is gated. → `KB § PATTERNS/common/claude-md-router-discipline.md`
- **7-way sync — methodology surfaces stay aligned.** Seven first-class surfaces (CLAUDE.md / MEMORY.md / `.claude/agents/` / KB / CONTEXTUALIZE.md / `.claude/skills/` / `.claude/commands/`) carry the methodology; a rule added to one MUST touch the others where applicable. Enforced by `check_seven_way_sync`. → `KB § PATTERNS/common/seven-way-sync.md`
- **Versioning — SemVer with explicit pre-release stages.** `MAJOR.MINOR.PATCH[-alpha|beta|rc]`; methodology contract bumps follow Conventional Commits → SemVer mapping; single source of truth at `/VERSION`. → `KB § PATTERNS/common/versioning.md`
- **Cache-locking discipline — WAL mode on every keeper-mirror SQLite cache.** Default rollback-journal mode lets a hung writer lock-storm every reader; WAL = readers never block writers. → `KB § PATTERNS/common/cache-locking-discipline.md`
- **Cache auto-freshness — caches stay aligned across pull / checkout / edit boundaries.** Pre-commit (in-session) + `post-merge` + `post-checkout` git hooks + `refresh_all_caches(only_stale=True)` orchestrator — closed loop, no staleness window. → `KB § PATTERNS/common/cache-auto-freshness.md`
- **Sibling workspaces consume noc read-only, whole.** Trimming the inherited surface breaks seed-first analysis + sync. → `KB § PATTERNS/architect/seed-workspace.md`
- **Divergent-architecture absorptions → house container model.** One container, `serve_spa`, seed base image; no fleet carve-out. → `KB § PATTERNS/devops/containerization.md §12a` · skill `noc-absorb-product`
- **Parallel-agent collision protocol.** Twice-reverted → STOP, wait, continue non-colliding; no collision-report project. → `KB § PATTERNS/architect/project-execution.md`

---

## 2 · The Map (open on-demand)

**Topical behavioral rules** (`CLAUDE/<topic>.md`, read by discipline): `backend.md` · `frontend.md` · `projects.md` · `platform.md`.

**Specialist subagents** (`.claude/agents/`): `architect` · `security` · `compliance-reviewer` (advisors — read-only, consulted) · `backend-engineer` · `frontend-engineer` · `devops-engineer` · `engineer-seed` (executors — worktree + commit-own-branch-only) · `skill-scout` (vendors skills in-home) · `orchestrator-operator`. **Tech-lead = the conversational session** (owns all git/merge/deploy; no agent file). → `KB § 06-AGENTS.md` · `KB § PATTERNS/architect/dev-team.md`.

**Procedure skills** (`.claude/skills/`, auto-trigger on phrases): `noc-contextualize` · `noc-new-product` · `noc-absorb-product` · `noc-ship` · `noc-branch-dispatch` · `noc-self-branch` · `noc-wiring-audit` · `noc-container-debug` · `noc-hygiene` · `noc-roadmap` · `skill-creator`.

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
