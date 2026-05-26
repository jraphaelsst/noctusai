# CLAUDE.md · v4.0 — router (aggressive/pointer-only)

> **Auto-loaded every session.** Two jobs: (a) §1 the always-on behavioral rules (one line each; depth at the pointer); (b) routing into `CLAUDE/<topic>.md` (topical), `.claude/skills/` (procedures, auto-triggered), `.claude/agents/` (specialists), and `KNOWLEDGE-BASE/` (depth). Bodies live at the pointers — never inline here (the auto-loaded budget compounds every reply). Can't find a rule → open its `KB § …` pointer or `KB § INDEX.md`.
>
> **Skills do the routing now.** Most procedures auto-trigger via `.claude/skills/noc-*` on their trigger phrases — you no longer carry a routing table; the harness injects the workflow on match. §3 holds only the residual non-skill situations.

---

<!-- NEW-SESSION-CONTEXTUALIZATION -->
## 0 · New session — "contextualize"

Fresh/clean-context agent AND the user says "contextualize" (or you don't know this platform) → **skill `noc-contextualize`** → read `/CONTEXTUALIZE.md` first, then do the task. Already-oriented agent → NO-OP, skip (don't re-read CONTEXTUALIZE.md).

---

## 1 · Universal rules (always-on; depth at the pointer)

- **Vocabulary — methodology, not doctrine.** Methodology/rule/principle/pattern; avoid "doctrine." → `KB § 01-PHILOSOPHY.md`
- **Seed first. Always.** Inherit via the factories; customize ONLY through named seams (non-seam = structural fork); run the 4-question test. → `KB § 03-SEED-ARCHITECTURE.md` · skills `noc-new-product` / agent `architect`
- **Verify the seed ships it.** Before any "consume seed X": read `__init__` exports + the real adapter (not just Protocol/Fake); gap+N=1 → ship-against-Fake+surface, N≥2 → file seed project. → `KB § 03-SEED-ARCHITECTURE.md`
- **Seed IO modules ship Fake+Real+factory.** Every seed IO module = Protocol+Fake+Real+factory; half-shipped → consumer-side forks. → `KB § PATTERNS/seed-fake-real-adapter.md`
- **Seed defaults = canonical answer, not consumer-#1 coincidence.** Fallbacks must be the architectural canonical value (else `""`/`None`/typed-error); multi-stage Dockerfile envs re-declare per stage. → `KB § PATTERNS/seed-canonical-defaults.md`
- **No incomplete commits.** Backend ∧ frontend at the same maturity; "scaffolded" ≠ "complete."
- **Product-internal-wiring.** Every UI surface shows REAL data ∧ manages its own data (route-exists ≠ wired; page-scoped CRUD). → `KB § PATTERNS/product-internal-wiring.md` · skill `noc-wiring-audit`
- **No quick fixes.** A fix touching N products for one reason is at the wrong level — go to seed/shared-lib/config.
- **No workarounds / no monkey-patching (incl. tests).** Real API/SDK; DI seam + `inserted_payloads` read-side; `patch.object` external services only. → `KB § 01-PHILOSOPHY.md` · `KB § PATTERNS/testing.md`
- **Estimate off evidence, not structure.** Open the files the change touches before sizing / offering A/B/C. → `KB § 01-PHILOSOPHY.md`
- **Codebase is source of truth.** Docs/memory/reports drift; the first command verifies against the tree; code wins, fix the doc same change. → `KB § 01-PHILOSOPHY.md`
- **Fix-on-contact for pre-existing debt.** Verify-pre-existing → fix in-flight → surface root-cause + solution; surface-only = silent error. → `KB § 01-PHILOSOPHY.md`
- **DRY — the recurrence rule.** N=2 → triage; N=3+ → MUST formalize to seed/shared-lib. → `KB § PATTERNS/project-execution.md` · skill `noc-hygiene`
- **Componentize everything.** Check the shared library before writing new; build shared from day one. → `KB § 04-SHARED-LIBRARY.md`
- **Reading & research discipline.** Narrow-read structure-before-bodies for big/unknown files; delegate breadth to the Explore subagent. → `KB § PATTERNS/agent-reading-discipline.md`
- **Replication-to-seed symmetry.** "per-product X" / "mount across N products" IS the slip; right per-product count for a cross-cutting concern = zero. → `KB § PATTERNS/project-execution.md` · agent `architect`
- **AST-first.** Code edits via libcst/ts-morph/tree-sitter; regex/sed only for prose/search/logs. → `KB § PATTERNS/ast.md`
- **Flag MCP-first / AST-first opportunities proactively.** Spot a missed exposure → apply-now or defer-with-destination; silent skip forbidden. → `KB § 01-PHILOSOPHY.md`
- **MCP-first scripts.** New automation = a `noctus.dev.*` tool, not a `scripts/` one-off (3 named carve-outs). → `KB § PATTERNS/mcp-first-scripts.md`
- **Hygiene scanning.** Run hound/mole/keeper-analog sweeps before walking away; worktree teardown = salvage-before-delete via a tool, never a bare `git worktree remove`. → `KB § PATTERNS/storage-hygiene.md` · skill `noc-hygiene`
- **Triage at decision time.** Every divergence → formalize / refactor / accept-with-rationale (cataloged). → `KB § PATTERNS/accept-with-rationale.md`
- **Safety nets capture failures → learnings → methodology evolves.** The net firing IS the methodology working; capture + three-way-sync. → `KB § 01-PHILOSOPHY.md`
- **Always-hardening posture.** Every surfaced pattern (incl. explanation-as-signal) = a methodology-improvement opportunity; announce LOUDLY (`**Methodology improvement spotted**`), apply before ship (or surface-only under concurrency), three-way-sync. → `KB § 01-PHILOSOPHY.md` · skills `skill-scout` / `codify`
- **Branching — ONE unified methodology.** Isolate writes in a worktree off `origin/dev` → integrate clean → never switch a shared `HEAD`. → `KB § PATTERNS/branching.md` · skills `noc-self-branch` / `noc-branch-dispatch`
- **`main` is production; `dev` is integration.** Everyday work + pushes → `dev`; `main`/`prod` only by explicit per-action consent (FF-only); engineers never touch `dev`/`main`/`prod`. → `KB § PATTERNS/branching-and-merging.md §0` · skill `noc-ship`
- **Branching-first orchestration.** Parallelize by default; orchestrator=architect (stays with user), subagents=engineers; inline cutoff `<100 LoC ∧ <3 files ∧ single-phase`. → `KB § 01-PHILOSOPHY.md` · skill `noc-branch-dispatch`
- **Self-branching mode.** 🔴 ABSOLUTE: NEVER work on `dev` — every writing task auto-isolates in a worktree off `origin/dev`; integrate worktree-explicit (not MCP) when a peer is live. → `KB § PATTERNS/self-branching-mode.md` · skill `noc-self-branch`
- **Knowledge tracking — durable findings.** Non-trivial work keeps a root `findings.md`; in-flight comms processed same commit, not parked. → `KB § 01-PHILOSOPHY.md`
- **Wave-based dispatch + collision-class.** Wave N+1 after Wave N FF-merges; classify C1/C2/C3 at dispatch, not at merge. → `KB § PATTERNS/branching-and-merging.md §18/§21` · skill `noc-branch-dispatch`
- **Pilot-products-first refactor cadence.** Seed/lib change proves on 3 pilots (`erp-imobiliario`·`therapy-platform`·`social-wiring`) before fan-out. → `KB § PATTERNS/project-execution.md`
- **No silent errors.** No `except: pass`, no silent fallback, no deferral without a named destination; ambiguity → ask; "✓" only when the tail is green. → `KB § 01-PHILOSOPHY.md`
- **Remediation markers.** Batch-able deferral → `NOC-REMEDIATE[<class>]: … — <date>` in-code (the named destination); never on an `except`. → `KB § PATTERNS/remediation-markers.md`
- **Doc-propagation sync.** Any rule/tool-behavior change → KB ↔ CLAUDE.md ↔ memory ↔ tool-code same commit. → `KB § 01-PHILOSOPHY.md`
- **Durable surfaces self-contained.** Never anchor KB/CLAUDE/CI/scripts to `projects/`/`archive/`; inline substance, cite code; `noctus.dev.archive` gates it. → `KB § 01-PHILOSOPHY.md`
- **Symbol-first for dense / AI-intended docs.** Use the doc-symbology glossary (`∧ ∨ ¬ ⇒ ↔` · status icons · `s1-s4` · `[F]/[R]/[A]`); `→`=routes, `⇒`=implies. NOT for errors/first-paragraph/quoted-user/commits. → `KB § PATTERNS/doc-symbology.md`
- **Context budget discipline.** CLAUDE.md=router · `CLAUDE/*`=topical · `.claude/skills/`=procedures · `.claude/agents/`=specialists · KB=depth · `MEMORY.md`=index. MCP keep-list: `noctusai`+`supabase`+`n8n`+`waha`. Skills keep-list: `update-config`/`loop`/`schedule`/`security-review`/`codify` + the `noc-*` workspace skills. → `KB § 01-PHILOSOPHY.md`
- **Lossless doc-refactor.** Changing the doc-set itself = methodology surgery (diff gates + gated-aggressiveness ladder + always-doc-the-trim). → `KB § PATTERNS/lossless-doc-refactor.md`
- **Sibling workspaces consume noc read-only, whole.** Never modify/trim noc; additions via the promotion manifest; inherit whole. → `KB § PATTERNS/seed-workspace.md`
- **Divergent-architecture absorptions → house container model.** One container, `serve_spa`, `FROM noctus-seed-*-base`, two compose projects on `noctus-net`. → `KB § PATTERNS/containerization.md §12a` · skill `noc-absorb-product`
- **Parallel-agent collision protocol.** Twice-reverted → STOP, wait, continue non-colliding; no collision-report project. → `KB § PATTERNS/project-execution.md`

---

## 2 · The Map (open on-demand)

**Topical behavioral rules** (`CLAUDE/<topic>.md`, read by discipline): `backend.md` · `frontend.md` · `projects.md` · `platform.md`.

**Specialist subagents** (`.claude/agents/`): `architect` · `security` · `compliance-reviewer` (advisors — read-only, consulted) · `backend-engineer` · `frontend-engineer` · `engineer-default` (executors — worktree + commit-own-branch-only) · `skill-scout` (vendors skills in-home) · `orchestrator-operator`. **Tech-lead = the conversational session** (owns all git/merge/deploy; no agent file). → `KB § 06-AGENTS.md` · `KB § PATTERNS/dev-team.md`.

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

**Pre-commit hook enforces it** (`scripts/hooks/pre-commit`): syncs `products/seed/`→`templates/product-seed/` if staged; runs `noctus.dev.kb_sync` to regenerate auto-derived counts and to **block** the commit on any unresolved `KB § …`/`KNOWLEDGE-BASE/…` pointer in `CLAUDE.md`/`CLAUDE/*.md`/`.claude/agents/*.md`/`KB/**`, any KB doc missing from `INDEX.md`, or any `products/<slug>/` lacking a `02-LANDSCAPE.md` roster row.

Manual: `python mcp/noctusai/cli.py --verify-kb-sync` · `--update-kb-counts [--check]`. Fresh clone: `bash scripts/install-hooks.sh`. Bypass (rarely correct): `git commit --no-verify`.

> Throughout, `KB § X` = `KNOWLEDGE-BASE/X`.
