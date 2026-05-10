# SPDD ↔ CDD+TDD merge analysis

> Captured: 2026-05-09
> Status: **first-pass analysis, deferred for later evaluation.** Not a decision; not a plan.
> Related: `spdd-article-summary.md` (the SPDD reference) and `KNOWLEDGE-BASE/INSTRUCTIONS/00-MASTER.md` (CDD+TDD canonical definition).

---

## 1 · The question

Should the repo's existing **CDD+TDD** methodology partially absorb elements from **SPDD**, while keeping CDD+TDD as the spine? If so, which elements?

User-stated framing: *"keep the methodologies we already have but enhance them merging with this new spdd."*

## 2 · Side-by-side baseline

| Dimension | Repo (CDD+TDD) | SPDD |
|---|---|---|
| Primary artifact | Context (prompts, tools, memory, skills, retrieval pipelines — many shapes) | Structured prompt (single fixed REASONS Canvas markdown file per feature) |
| Spec granularity | Flexible — phases produce deliverables; PROJECT.md per project | Method-signature precision in Operations |
| Validation | Evals + tests at every layer of the pyramid (unit / real-DB / integration / agent evals / E2E), LLM-as-judge | API tests first → code review → unit tests last |
| Sequencing | 7 design phases (discovery → spec) before code | 6-step workflow (story → analysis → canvas → code → tests) |
| Tooling | MCP as integration protocol; pytest / vitest / playwright + custom eval harness; `noctusai_*` MCP toolkit | `openspdd` CLI: `/spdd-story`, `/spdd-analysis`, `/spdd-reasons-canvas`, `/spdd-generate`, `/spdd-prompt-update`, `/spdd-sync`, `/spdd-api-test` |
| Drift handling | Regression evals catch context drift; "docs stay in sync with code" rule | Two-way sync: prompt-first for behavior changes, code-first + sync-back for refactors |
| Scope | End-to-end agentic workflow design (skills, MCP, orchestration, UI, data) | Single feature per Canvas, code-generation focused |
| Bias | Eval-heavy, broad-scope | Codegen-heavy, tight-loop |
| Anti-pattern shared | "No workarounds" / "correct solutions only" | "Don't hand-edit the Canvas, never confuse logic with refactor" |

## 3 · Where SPDD overlaps so heavily that adoption would be redundant

| SPDD element | Already covered in CDD+TDD by |
|---|---|
| `/spdd-story` story decomposition | `templates/PROJECT-TEMPLATE.md` + project-execution methodology + features methodology (`feedback_features_methodology`) |
| Step 2 clarify-analysis (human-led) | Phase 1 Discovery + Phase 2 Core Features (with TDD lens) in `04-DESIGN-PHASES.md` |
| Step 3 `/spdd-analysis` strategic context | Phase 3 + Phase 4 design phases; absorption-search sextet; `noctus.dev.scan_*` tools |
| API-test-before-code-review (Step 5) | Finish-the-session rule + agentic test pyramid Layer 0/1/2 |
| Step 6 unit tests last | Eval pyramid + regression evals + `noctus.dev.run_tests` |
| Versioned prompts as first-class artifacts | "Docs stay in sync with code" three-way sync (KB ↔ CLAUDE.md ↔ memory) |
| Norms (cross-cutting standards) | `CLAUDE.md` §1 universal rules + `CLAUDE/<topic>.md` topical files |
| Safeguards (non-negotiable boundaries) | LGPD-first, security review, webhook signature verification, no-silent-errors rule |

→ **Conclusion: ~70% of SPDD is duplicate naming for what's already shipped here.** Wholesale adoption would mostly be relabeling.

## 4 · Where SPDD genuinely adds something CDD+TDD doesn't have

### 4a · The REASONS Canvas as a per-feature §6 artifact (HIGH POTENTIAL)

The repo's PROJECT.md template has a `§6 Detailed phase plan` but it's project-shaped (multi-phase, scope-scoped). SPDD's Canvas is **feature-shaped** with a fixed 7-part structure (R / E / A / S / O / N / S).

**What this could buy:**
- Tighter engineer subagent briefs in branching-first parallel dispatches. Engineer is told "here's your REASONS Canvas, build Operations 1–4" — narrower context, less interpretation drift.
- Operations-down-to-method-signatures gives a concrete handoff target between architect (orchestrator) and engineer (subagent).
- Per-feature Canvas could become the artifact engineers write to / update via subagent, rather than free-form `findings.md` + commit messages.

**What this risks:**
- Collides with **"Estimate off evidence, not structure"** (CLAUDE.md §1 universal rule). SPDD goes structure-first to method signatures; the repo's rule says open the files first, especially seed/cross-cutting code, before specifying. Specifying Operations to method-signature precision before reading the seed is the exact slip that rule was written against.
- Adds another markdown artifact per feature on top of: `PROJECT.md`, `findings.md`, `live-patterns-log.md`, phase_learnings SQLite, accept-with-rationale catalog. Already a lot.

**Mitigation if adopted:** confine REASONS Canvas to Phase 5 / Phase 7 of the 7-design-phases sequence — only AFTER discovery + analysis + data-model phases have read the existing seed/code. Never use Canvas as a discovery tool.

### 4b · "Fix the prompt first, then the code" two-way sync (MEDIUM-HIGH POTENTIAL)

Current CDD+TDD rule: *"Docs stay in sync with code. Every commit must include documentation updates."* — but it's vague on **direction**. When behavior changes, do you update KB first or code first?

SPDD's two-path discipline is sharper:
- **Behavior change** → prompt/spec first → regenerate code.
- **Refactor (no behavior)** → code first → sync back to spec.

**What this could buy:**
- Removes ambiguity in the existing three-way sync (KB ↔ CLAUDE.md ↔ memory). Could extend to four-way when a per-feature Canvas exists.
- Captures a discipline already implicit in some repo flows but not codified.
- Pairs naturally with the existing `noctusai_lgpd_flag(...)` / `noctus.dev.phase_learning_log` pattern of "decide first, write later."

**What this risks:**
- Adds a rule to a methodology already dense with rules.
- The two-way distinction can over-apply — many edits are mixed (behavior + refactor in same patch). Need clear examples.

**Mitigation if adopted:** lift as a single CLAUDE.md §1 bullet, ≤80 words, pointing to a KB pattern doc. Frame as a refinement of three-way sync, not a new methodology.

### 4c · Prompt-as-versioned-artifact for high-stakes features (LOW-MEDIUM POTENTIAL)

For LGPD / payments / auth / cross-product migration features specifically, having a frozen REASONS Canvas committed alongside the PR could improve auditability — answering "what was the design intent at the time?" months later.

**Risk:** scope creep into "every PR needs a Canvas" — turns into ceremony. Limit to flagged-high-stakes features only.

### 4d · Slash-command CLI encoding workflows (LOW POTENTIAL — already covered)

SPDD ships `/spdd-*` commands. The repo already has `noctusai_*` MCP toolkit + Skills (`update-config`, `loop`, `schedule`, `security-review`) which serve the same role. Adopting `openspdd` itself would conflict with the **MCP keep-list** (noctusai + supabase only). If the `/spdd-prompt-update` and `/spdd-sync` workflows prove valuable, they would be implemented as `noctus.dev.*` MCP tools, not as a parallel CLI.

## 5 · Elements to explicitly REJECT

| Element | Why reject |
|---|---|
| `openspdd` CLI as a parallel toolchain | Violates MCP keep-list rule; would fragment the `noctus.*` namespace. |
| Operations-to-method-signature precision used as a discovery tool | Direct conflict with "Estimate off evidence, not structure." Only acceptable AFTER reading seed/cross-cutting code. |
| API-tests-before-deep-code-review as the default test ordering | Conflicts with the agentic test pyramid + real-DB integration tests (Layer 0). API tests are fine as one layer, not as the pre-review gate. |
| SPDD's framing of "tests are not less important, just later" | The repo's eval pyramid is broader (semantic + behavioral assertions, LLM-as-judge); SPDD's test framing is narrower (functional + regression). |
| Canvas as an alternative to PROJECT.md | PROJECT.md already does scope-scoping + phasing + §11 change log. Canvas would duplicate. Canvas should LIVE INSIDE a project's `proposals/` or §6, not replace PROJECT.md. |

## 6 · Risks of adoption right now

1. **Mid-validation of branching-first orchestration.** Memory entry `feedback_TEMP_methodology_validation_in_progress` explicitly says branching-first is in real-time validation; adding another methodology layer mid-validation muddies the speed-gain telemetry.
2. **No N=2 / N=3 evidence.** Per the **DRY recurrence rule**, formalizing without evidence is premature. We need at least 2 concrete cases where a Canvas would have prevented a slip — none captured yet.
3. **Senior-architect skew bias.** SPDD's own caveat ("can look like a method reserved for senior architects") collides with the repo's branching-first orchestration model where engineer subagents (less context, narrow brief) execute. SPDD's per-feature Canvas might be useful AS THE ENGINEER BRIEF, but that's an unproven hypothesis.
4. **Methodology budget.** CLAUDE.md §1 is already at the bullet-density limit. New §1 bullet >80 words is forbidden. Any SPDD absorption needs to fit as ≤80-word bullets pointing to KB depth.
5. **Three-way sync overhead.** Every methodology change demands KB ↔ CLAUDE.md (or topical) ↔ memory updates same session. Adding SPDD-derived rules costs three-way-sync time.

## 7 · Decision points for future evaluation

When this folder is reopened, work through these in order:

1. **Has any project in the last N weeks shown a recurring slip that a REASONS Canvas would have prevented?** If yes — quote 2 instances. If no — defer further. (Recurrence-rule discipline.)
2. **Does branching-first orchestration retrospective data show engineer subagents lacking spec precision?** If yes — REASONS Canvas as engineer-brief is a candidate. If no — defer.
3. **Is the "fix prompt first vs refactor + sync back" distinction surfacing as a real ambiguity in three-way sync work?** If yes — formalize as CLAUDE.md §1 bullet. If no — defer.
4. **Are there candidate PR types (LGPD / payments / auth / cross-product migration) where committed-Canvas-alongside-PR would have answered a "why did we design it this way?" question?** If yes — pilot on next instance. If no — defer.
5. **Could `noctus.dev.*` MCP tools encode `/spdd-prompt-update` and `/spdd-sync` workflows without adopting `openspdd`?** Almost certainly yes — sketch the tool signatures.

## 8 · Provisional recommendation (TO BE RE-EVALUATED)

If adopted, adopt **only two elements**:

1. **REASONS Canvas as a §6 sub-template inside `PROJECT.md`** (or `features/<slug>.md`) — not as a replacement, as an enrichment. Used post-Phase 4 (data model) only, never as a discovery tool. Operations precision capped at "what an engineer subagent needs to execute," not "method-signature precision."
2. **The "behavior-change → prompt first / refactor → code first + sync back" rule** as a CLAUDE.md §1 bullet (≤80 words) refining the existing three-way sync.

**Reject everything else** as duplicate, conflicting, or unproven.

**Do not adopt either of these without N=2 evidence first.**

## 9 · What this doc is NOT

- Not a plan. (The decision points in §7 must be answered before planning.)
- Not a CLAUDE.md edit. (No three-way sync triggered.)
- Not a memory entry. (User explicitly deferred.)
- Not a recommendation to adopt. (Provisional only — re-evaluate against §6 risks.)

## 10 · Cross-references

- SPDD reference: `projects/spdd-evaluation/spdd-article-summary.md`
- CDD+TDD canonical: `KNOWLEDGE-BASE/INSTRUCTIONS/00-MASTER.md`
- 7 design phases: `KNOWLEDGE-BASE/INSTRUCTIONS/04-DESIGN-PHASES.md`
- Test pyramid: `KNOWLEDGE-BASE/INSTRUCTIONS/05-TESTING-EVALS.md`
- Project execution: `KNOWLEDGE-BASE/PATTERNS/project-execution.md`
- Recurrence rule: `KNOWLEDGE-BASE/PATTERNS/project-execution.md § 2.7`
- Three-way sync rule: `CLAUDE.md §1`
- Estimate-off-evidence rule: `CLAUDE.md §1` + `KNOWLEDGE-BASE/01-PHILOSOPHY.md`
- Branching-first orchestration: `CLAUDE.md §1` + memory `feedback_branching_first_orchestration`
