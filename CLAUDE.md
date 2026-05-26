# CLAUDE.md · v4.0 — router (synthesis)

> **Auto-loaded every session.** Two jobs: (a) §1 the always-on behavioral rules (rule + one-clause why + `→` pointer, one line each); (b) routing into `CLAUDE/<topic>.md` (topical), `.claude/skills/` (procedures, auto-triggered), `.claude/agents/` (specialists), and `KNOWLEDGE-BASE/` (depth). Bodies live at the pointers — never inline (the auto-loaded budget compounds every reply). Can't find a rule → open its `KB § …` pointer or `KB § INDEX.md`.
>
> **The router stays pointer-only** — `§1` carries PRINCIPLE + the MAP; PROCEDURE lives in `.claude/skills/noc-*` (auto-trigger on phrases), depth in KB. Enforced by `check_claude_md_router` (`KB § PATTERNS/claude-md-router-discipline.md`), not habit.

---

<!-- NEW-SESSION-CONTEXTUALIZATION -->
## 0 · New session — "contextualize"

Fresh/clean-context agent AND the user says "contextualize" (or you don't know this platform) → **skill `noc-contextualize`** → read `/CONTEXTUALIZE.md` first, then do the task. Already-oriented agent → NO-OP, skip (don't re-read CONTEXTUALIZE.md).

---

## 1 · Universal rules (rule + one-clause why; depth at the pointer)

- **Vocabulary — methodology, not doctrine.** Hierarchical framing runs counter to how this team works. → `KB § 01-PHILOSOPHY.md`
- **Seed first. Always.** The seed IS the approach; a customization not through a named seam is a structural fork. → `KB § 03-SEED-ARCHITECTURE.md` · skill `noc-new-product`
- **Verify the seed ships it.** A planned "consume" silently becomes a "seed-build" if only the Protocol/Fake ships. → `KB § 03-SEED-ARCHITECTURE.md`
- **Seed IO modules ship Fake+Real+factory.** Half-shipped seed IO generates consumer-side forks. → `KB § PATTERNS/seed-fake-real-adapter.md`
- **Seed defaults = canonical answer, not consumer-#1 coincidence.** A coincidence default silently misroutes consumers #2..N. → `KB § PATTERNS/seed-canonical-defaults.md`
- **No incomplete commits.** One real side + one placeholder side lies about maturity; "scaffolded" ≠ "complete." → `KB § 03-SEED-ARCHITECTURE.md`
- **Product-internal-wiring.** route-exists ≠ wired; a page must show real data ∧ own its CRUD. → `KB § PATTERNS/product-internal-wiring.md` · skill `noc-wiring-audit`
- **No quick fixes.** A fix touching N products for one reason is at the wrong level — go to the root. → `KB § 01-PHILOSOPHY.md`
- **No workarounds / no monkey-patching (incl. tests).** Patching our own guard means the test no longer exercises it. → `KB § PATTERNS/testing.md`
- **Estimate off evidence, not structure.** Cross-cutting layers hide cost; open the files before sizing. → `KB § 01-PHILOSOPHY.md`
- **Codebase is source of truth.** Docs/memory/reports drift; verify against the tree first, code wins. → `KB § 01-PHILOSOPHY.md`
- **Fix-on-contact for pre-existing debt.** Surface-only = a silent-error one level up; fix in-flight then surface. → `KB § 01-PHILOSOPHY.md`
- **DRY — the recurrence rule.** N=2 → triage; N=3+ MUST formalize; shipping the 4th instance is forbidden. → `KB § PATTERNS/project-execution.md` · skill `noc-hygiene`
- **Componentize everything.** If another product will need it, build it shared from day one. → `KB § 04-SHARED-LIBRARY.md`
- **Reading & research discipline.** Whole-file reads waste budget; narrow-read + delegate breadth to Explore. → `KB § PATTERNS/agent-reading-discipline.md`
- **Replication-to-seed symmetry.** The trigger is LANGUAGE — "per-product X" IS the slip; right count = zero. → `KB § PATTERNS/project-execution.md` · agent `architect`
- **AST-first.** If a compiler/type-checker parses the file, edit it via libcst/ts-morph, never regex. → `KB § PATTERNS/ast.md`
- **Flag MCP-first / AST-first opportunities proactively.** Silent skipping = silent-error shape. → `KB § 01-PHILOSOPHY.md`
- **MCP-first scripts.** A new automation IS an agent-exposable capability → a `noctus.dev.*` tool. → `KB § PATTERNS/mcp-first-scripts.md`
- **Hygiene scanning.** Run hound/mole/keeper-analog sweeps before walking away; teardown = salvage-before-delete via a tool. → `KB § PATTERNS/storage-hygiene.md` · skill `noc-hygiene`
- **Triage at decision time.** "Accept" is a real landing only with paperwork; recurrence flips accept→formalize. → `KB § PATTERNS/accept-with-rationale.md`
- **Safety nets capture failures → learnings → methodology evolves.** The net firing IS the methodology working. → `KB § 01-PHILOSOPHY.md`
- **Always-hardening posture.** Every surfaced pattern (incl. explanation-as-signal) is a methodology-improvement opportunity; announce LOUDLY, apply before ship. → `KB § 01-PHILOSOPHY.md` · skills `skill-scout` / `codify`
- **Branching — ONE unified methodology.** Worktree isolation is the primitive: isolate off `origin/dev` → integrate clean → never switch a shared HEAD. → `KB § PATTERNS/branching.md` · skill `noc-self-branch`
- **`main` is production; `dev` is integration.** Everyday work + pushes → `dev`; `main`/`prod` only by explicit per-action consent. → `KB § PATTERNS/branching-and-merging.md §0` · skill `noc-ship`
- **Branching-first orchestration.** Orchestrator=architect (stays with user), subagents=engineers; inline below the cutoff. → `KB § 01-PHILOSOPHY.md` · skill `noc-branch-dispatch`
- **Parallelization-first orchestration.** Real specialized-agents-in-parallel is the DEFAULT mindset (each `.claude/agents/<name>` brings its lens); serial / inline only when shared-state, single-coherent-voice, or below the inline cutoff. → `KB § PATTERNS/parallelization-first-orchestration.md` · skill `noc-branch-dispatch`
- **Self-branching mode.** 🔴 ABSOLUTE: never work on `dev`; every writing task auto-isolates off `origin/dev`. → `KB § PATTERNS/self-branching-mode.md` · skill `noc-self-branch`
- **Knowledge tracking — durable findings.** findings.md = what-we-LEARNED; in-flight comms processed same commit, not parked. → `KB § 01-PHILOSOPHY.md`
- **Wave-based dispatch + collision-class.** Merge cleanliness is decided at DISPATCH (C1/C2/C3), not at merge. → `KB § PATTERNS/branching-and-merging.md §18/§21`
- **Pilot-products-first refactor cadence.** Prove a seed/lib change on 3 pilots before fan-out. → `KB § PATTERNS/project-execution.md`
- **No silent errors.** No `except: pass`, no silent fallback, no deferral without a named destination; ambiguity → ask. → `KB § 01-PHILOSOPHY.md`
- **Remediation markers.** A batch-able deferral lives in-code as `NOC-REMEDIATE[<class>]` — the named destination. → `KB § PATTERNS/remediation-markers.md`
- **Doc-propagation sync.** A rule/tool change lives in KB ↔ CLAUDE.md ↔ memory ↔ tool-code the same commit. → `KB § 01-PHILOSOPHY.md`
- **Durable surfaces self-contained.** A config/script ref into `projects/`/`archive/` breaks loudly when archived. → `KB § 01-PHILOSOPHY.md`
- **Symbol-first for dense / AI-intended docs.** Lossless-swap test gates each prose→symbol swap; `→`=routes, `⇒`=implies. → `KB § PATTERNS/doc-symbology.md`
- **Context budget discipline.** The auto-loaded budget compounds every reply. MCP keep-list: `noctusai`+`supabase`+`n8n`+`waha`. → `KB § 01-PHILOSOPHY.md`
- **Lossless doc-refactor.** Changing the doc-set itself is methodology surgery — lossless proven, not asserted. → `KB § PATTERNS/lossless-doc-refactor.md`
- **CLAUDE.md is the always-on router — keep it pointer-only.** §1 = principle + map (one-line rule + `→` pointer); procedures in skills, depth in KB; re-bloat is gated. → `KB § PATTERNS/claude-md-router-discipline.md`
- **Sibling workspaces consume noc read-only, whole.** Trimming the inherited surface breaks seed-first analysis + sync. → `KB § PATTERNS/seed-workspace.md`
- **Divergent-architecture absorptions → house container model.** One container, `serve_spa`, seed base image; no fleet carve-out. → `KB § PATTERNS/containerization.md §12a` · skill `noc-absorb-product`
- **Parallel-agent collision protocol.** Twice-reverted → STOP, wait, continue non-colliding; no collision-report project. → `KB § PATTERNS/project-execution.md`

---

## 2 · The Map (open on-demand)

**Topical behavioral rules** (`CLAUDE/<topic>.md`, read by discipline): `backend.md` · `frontend.md` · `projects.md` · `platform.md`.

**Specialist subagents** (`.claude/agents/`): `architect` · `security` · `compliance-reviewer` (advisors — read-only, consulted) · `backend-engineer` · `frontend-engineer` · `devops-engineer` · `engineer-default` (executors — worktree + commit-own-branch-only) · `skill-scout` (vendors skills in-home) · `orchestrator-operator`. **Tech-lead = the conversational session** (owns all git/merge/deploy; no agent file). → `KB § 06-AGENTS.md` · `KB § PATTERNS/dev-team.md`.

**Procedure skills** (`.claude/skills/`, auto-trigger): `noc-contextualize` · `noc-new-product` · `noc-absorb-product` · `noc-ship` · `noc-branch-dispatch` · `noc-self-branch` · `noc-wiring-audit` · `noc-container-debug` · `noc-hygiene` · `skill-creator` (+ `codify`).

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
| Starting/closing a project; touching `*-PROJECT.md` | `CLAUDE/projects.md` + `KB § PATTERNS/project-execution.md` |
| Migration · auth wiring · OAuth/integration · LGPD · anything else | `KB § INDEX.md` → the relevant pattern/integration |

---

## 4 · Sync rule

CLAUDE.md, `CLAUDE/<topic>.md`, `.claude/skills/`, `.claude/agents/`, and `KB § INDEX.md` stay in sync — add/rename/delete a KB file or a skill/agent and every referencing layer updates the same commit.

**Pre-commit hook enforces it** (`scripts/hooks/pre-commit`): syncs `products/seed/`→`templates/product-seed/` if staged; runs `noctus.dev.kb_sync` to regenerate counts + **block** on any unresolved `KB § …` pointer in `CLAUDE.md`/`CLAUDE/*.md`/`.claude/agents/*.md`/`KB/**`, any KB doc missing from `INDEX.md`, or any `products/<slug>/` lacking a `02-LANDSCAPE.md` roster row; and runs `check_claude_md_router` (`--check-claude-md-router`) to **block** a re-bloated router when `CLAUDE.md` is staged (`KB § PATTERNS/claude-md-router-discipline.md`).

Manual: `python mcp/noctusai/cli.py --verify-kb-sync` · `--check-claude-md-router` · `--update-kb-counts [--check]`. Fresh clone: `bash scripts/install-hooks.sh`. Bypass (rarely correct): `git commit --no-verify`.

> Throughout, `KB § X` = `KNOWLEDGE-BASE/X`.
