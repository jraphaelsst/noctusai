# Main-Core Migrations Batch — Project Document

> **What this project is.** A batch coordinator that drives the 7
> "main-core / large migration" projects in the repo to completion. These
> are the heavyweight initiatives — multi-product migrations, framework
> rewrites, concept-stage research-then-build projects. Each phase below
> targets one or more child projects already scaffolded under `projects/`
> or `products/<product>/projects/`. The implementation work itself lives
> in each child's PROJECT.md; this batch is the meta-loop that orders
> them, runs §7 interrogation per child before its execution starts, and
> tracks rollup progress.
>
> **Why a batch project.** These 7 children are heterogeneous and big.
> Without a coordinator they get half-done in parallel and the user pays
> context-switching cost across them. A batch enforces sequence + hard
> ordering rules (e.g. resume-blocked children first, concept-stage
> children only after interrogation), and gives the parallel agent a
> single entry point that survives child-folder deletion.
>
> **Run-by.** Designed for a parallel agent that did not see the
> conversation that produced it. §1 inlines context, §2 quotes user
> direction, §5 names every file, §7 questions are paired with
> evidence-backed recommendations, §10 commands are copy-paste ready.
> Snapshot `.claude/snapshots/projects-2026-05-03_024603/` is the frozen
> evaluation reference.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** ⏳ **EXECUTING (Phase 0 ✅, Phase 1 ✅ Path B subsumed, Phase 2.a ✅ child re-scoped + filed standalone, Phase 3.a ✅ child §7 round closed, Phase 3.b child Phase 0 ✅, Phase 3.b child Phase 1 ✅)** — Tier 1 closed via Path B (folder deleted). Tier 2 §7 complete + child Phase 2.b deferred. Tier 3 child Phase 0 + Phase 1 both complete 2026-05-03. Phase 1 shipped `noctusai_lib.integrations.supabase_identity` (UserIdentity + fetch helpers, 20 tests) + fixed seed-lib's broken `require_role` via `make_require_role` factory (6 tests) + retired therapy-platform's local `_fetch_user_identity` (with N+1→bulk optimization). Therapy backend 1143/1143, seed-lib 448/448, frontend vite build all green; keeper + KB sync clean. **Next:** Phase 3.b child Phase 2 (admin Tier A known regressions — `/api/admin/appointments`, `/api/admin/financials/{summary,transactions,commissions}` GET, DELETE `/api/admin/financials/commissions/:id`, plus admin/dashboard + admin/suspend 404s). Awaiting user "continue" per child cadence.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `main-core-migrations-batch` (subject=main-core-migrations, intent=batch)
- **Project location:** `projects/main-core-migrations-batch/` (cross-product / platform-coordinator — drives 7 child projects across root + products)
- **Sibling batches** running in parallel (do not duplicate work):
  - `projects/side-projects-batch/PROJECT.md` — our older non-absorbed side projects (8 children).
  - `projects/absorbed-projects-batch/PROJECT.md` — sibling-repo absorption projects (8 children).
- **Snapshot:** `.claude/snapshots/projects-2026-05-03_024603/` — frozen state of all 26 PROJECT.md files at batch start.
- **Related docs:**
  - `KB § PATTERNS/project-execution.md § 0` — canonical execution workflow each child runs through.
  - Each child's `PROJECT.md` — the real work specs.

---

## 1. Context & Purpose

The repo's `projects/` and `products/*/projects/` trees collected 26 PROJECT.md files. After excluding 8 absorption children (driven by `absorbed-projects-batch`), 8 our-side children (driven by `side-projects-batch`), and 3 already-closed/empty entries, **7 main-core / large migration children remain**:

- `projects/repo-state-consolidation/` (563 lines, paused at user direction 2026-04-28; Phase 0 ✅): 11-commit consolidation of working-tree drift.
- `projects/strict-mode-migration/` (54 lines, deferred): TypeScript strict mode across all frontends.
- `projects/methodology-mirror-and-workspaces/` (470 lines, concept-deferred): steps (b)+(c) of the methodology-extraction trilogy. §6 intentionally empty pending §7 + user reactivation.
- `projects/project-history-ledger/` (414 lines, concept — interrogation pending): global change-log + token-tracking mechanism for AI-training data.
- `projects/vista-api-mcp/` (409 lines, concept — interrogation pending): first-party Vista MCP server.
- `projects/adconnect-migration/` (267 lines, scaffolded): full B2B marketplace product migration into the seed framework. Custom JWT auth.
- `products/therapy-platform/projects/therapy-platform-wiring/` (463 lines, design drafted, awaiting user sign-off): 9-phase admin-console end-to-end sweep.

These are "big" — each is multi-session work. Some are blocked on user resume (`repo-state-consolidation`), some on §7 sign-off (`therapy-platform-wiring`, the three concept-stage), some are simply deferred (`strict-mode-migration`).

The win: clear sequencing so the parallel agent picks up each in the right state, doesn't restart already-shipped work, and surfaces staleness (especially `repo-state-consolidation` which may be partially subsumed by parallel commits in the recent history).

---

## 2. Confirmed constraints

- **Scope** — only the 7 main-core / large migration children. *(User direction 2026-05-03: "Absorbed from sibling repos, Main-core big migrations, please create projects for their implementation as well... i'm gonna use a parallel agent to start working on them".)*
- **Each child runs its own canonical execution workflow** (`KB § PATTERNS/project-execution.md § 0`): scaffold → Phase 0 audit → execute per phase → close-phase commit (no push) → on full child close, fold into batch §11 + delete child folder. Push happens only at this batch's close.
- **Resume-blocked children come first.** `repo-state-consolidation` was paused 2026-04-28 by explicit user choice ("Path C: dont commit yet, let's finish whats left to be delivered of value, then we checkpoint it"). It's the only child whose Phase 0 is already done — but **it may be stale** because commits have happened in parallel since the pause (recent history shows `5acf4c4`, `d4b571f`, `a3e87e2`, `e1ba4e3`, `146abe3`). Phase 1 of this batch must staleness-audit the consolidation plan before resuming.
- **§7 interrogation per child happens at the START of that child's tier**, not all up front. The 3 concept-stage children (`methodology-mirror-and-workspaces`, `project-history-ledger`, `vista-api-mcp`) have rich §7s — surface them all together at Tier 4 kickoff.
- **`therapy-platform-wiring`'s Phase 0 is mandatory and rigorous.** The whole project's Phases 2-9 reference rows in the Phase 0 inventory table (§5.4). Phase 0 is the discovery artifact; phases 2-9 cannot be reordered ahead of it.
- **`adconnect-migration` is a full product migration.** Treat as multi-session work; do not commit half-states. Custom JWT auth needs framework-extension plan, not custom-stays.
- **No leftovers from sibling paths.** `vista-api-mcp` references the repo-root `VISTA-API-MCP-GUIDE.md` (904-line portable spec) — keep that survival path intact.
- **Snapshot lives at `.claude/snapshots/`** — already gitignored (`.claude/snapshots/` added to `.gitignore` 2026-05-03).

---

## 3. Design principles

1. **Resume-blocked children first.** Anything paused with Phase 0 done gets a staleness audit + resume decision before any new child starts. Closing in-flight work beats opening new work.
2. **Concept-stage children only after design + research.** `vista-api-mcp`, `project-history-ledger`, `methodology-mirror-and-workspaces` need §7 sign-off before even Phase 0 starts. Treat their interrogation rounds as gating, not optional.
3. **Smallest deferred → biggest deferred.** Within tiers of similar status, finish the smallest first (`strict-mode-migration` 54 lines) before opening a wide-angle one (`adconnect-migration` 267 lines, `therapy-platform-wiring` 463 lines).
4. **One child at a time within a tier.** No interleaving — each is large enough that interleaving wastes context-window reads.
5. **Recurrence captured at this batch layer.** When child A surfaces a helper that child B would also benefit from, that observation lives in this batch's improvements block (which survives child folder deletion).

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

This is a **batch coordinator project** — its only deliverable is sequencing, interrogation cadence, and rollup. It produces no production code. Each child runs its own §3a where applicable.

Six-question checklist:

1. **Is the contract identical for every product?** N/A — this batch ships no product-touching code. Per-child §3a's answer this for the child's actual change.
2. **Is the data source product-specific?** N/A.
3. **Is the placement product-specific?** N/A.
4. **Is the visibility / permission rule the same?** N/A.
5. **Does the seam already exist in seed?** N/A.
6. **Default-on or opt-in?** N/A.

**Litmus — per-product code count this design requires:**

- [x] **0 lines** — pure cross-product concern; lives entirely in seed. Products inherit from the factory. → Confirmed: this batch produces zero per-product code. Per-product code lands inside each child project, where its own §3a governs placement.

**Phase plan implications:** §6 phases below are **phase = child-tier**, not phase-per-product. No replication framing.

---

## 4. Scope

**In scope (7 children, tier-grouped):**

**Tier 1 — resume-blocked (Phase 1 of this batch):**
- `projects/repo-state-consolidation/` (Phase 0 ✅; staleness audit + resume decision required).

**Tier 2 — short + foundational (Phase 2 of this batch):**
- `projects/strict-mode-migration/` (54 lines — much smaller than the others; surface area is well-bounded; lands TS strict across frontends).

**Tier 3 — well-scoped product wiring (Phase 3 of this batch):**
- `products/therapy-platform/projects/therapy-platform-wiring/` (463 lines, 9 phases; Phase 0 inventory is the gate for Phases 2-9).

**Tier 4 — concept → execution (Phase 4 of this batch):**
- `projects/vista-api-mcp/` (409 lines, concept — interrogation pending). External-repo guide already shipped at `VISTA-API-MCP-GUIDE.md`.
- `projects/project-history-ledger/` (414 lines, concept — interrogation pending). Interlocks with `noctusai_count_tokens`.
- `projects/methodology-mirror-and-workspaces/` (470 lines, concept-deferred — workflow-constraint trigger gates reactivation).

**Tier 5 — full product migration (Phase 5 of this batch):**
- `projects/adconnect-migration/` (267 lines; scaffolded but not migrated; B2B marketplace, custom JWT auth, full migration scope).

**Out of scope (handled by sibling batches, do not pull in):**
- 8 our-side children — driven by `projects/side-projects-batch/PROJECT.md`.
- 8 absorption children — driven by `projects/absorbed-projects-batch/PROJECT.md`.
- 3 already-closed / empty (`methodology-extraction`, `vista-crm-wiring`, `repo-commit-followup`) — no project-level action required.
- `pf-org-scoping-migration` — product-scoped (lives at `products/personal-finance/projects/`); PARKED 2026-04-27 by explicit user directive; in `side-projects-batch` out-of-scope list.
- `narrow-read-compliance-detector` — concept stub marked INFEASIBLE today; gated on §7 unblock triggers.

---

## 6. Implementation phases

**Phase = tier-batch.** Each phase opens with a §7 interrogation round covering every child in that tier (except Tier 1 which is resume-decision, and Tier 4 which packages 3 concept-stage children together), then drives each child end-to-end through its own canonical workflow before flipping the batch phase to ✅.

### Phase 0 — Categorize + scaffold batch ✅ (executed 2026-05-03)

- [x] Identify the 7 main-core / large migration children among the 26 total in the snapshot.
- [x] Tier them: Tier 1 resume-blocked, Tier 2 short-foundational, Tier 3 product-wiring, Tier 4 concept-stage trio, Tier 5 full-product migration.
- [x] Scaffold this batch project from `templates/PROJECT-TEMPLATE.md`.

**Improvements:**
- `repo-state-consolidation` may be partially stale: Phase 0 was 2026-04-28 and shipped commits have happened since (`5acf4c4`, `d4b571f`, `a3e87e2`, `e1ba4e3`, `146abe3`, `0a562d0`). A future agent picking up this batch must read `git log --since=2026-04-28` and reconcile against the consolidation plan in §6 of that child before resuming. Captured here at the batch layer because it survives child-folder deletion.
- `vista-api-mcp` and `VISTA-API-MCP-GUIDE.md` (904-line repo-root portable guide) are interlocked: the in-repo MCP build (this child) consumes the guide as source-of-truth. If the guide gets updated externally, surface the diff at child Phase 0.

### Phase 1 — Tier 1: resume `repo-state-consolidation` ✅ (Path B — subsumed + closed 2026-05-03)

**1.a Staleness audit (gates Phase 1.b).** ✅
- [x] Read `projects/repo-state-consolidation/PROJECT.md` §6 (Phases 1-4 commit allocation table).
- [x] Run `git log --since=2026-04-28 --oneline` and reconcile against §6: 35+ commits shipped between 2026-04-28 and 2026-05-03; every load-bearing target of the original 11-commit plan has landed.
- [x] >50% threshold breached on every §6 commit category — flip to "subsumed; close" path.
- [x] No user §7 round needed — verdict is unambiguous (see verdict-evidence in Improvements).

**1.b' Subsume + close `repo-state-consolidation`** ✅ *(Path B: scope already shipped.)*
- [x] Document what shipped vs. what was planned (verdict-evidence below).
- [x] Delete child folder per close protocol; no Phase 4 push needed (commits already in remote).

**Improvements (Phase 1 — Path B verdict-evidence):**
- **`core/` → `products/core/` migration (commit #2 of original plan):** ✅ subsumed. `core/` no longer exists at root; `products/core/{backend,frontend,MASTER-PROMPT.md}` populated; landed via the `core-seed-wiring` project's close.
- **Root cleanup (commit #3):** ✅ subsumed. `TODO-*.md`, `PLAN-SEED-AGENTS.md`, `ROADMAP-v2.2-v2.4.md`, `TESTING-GUIDE.md`, `task.md`, `improvements.md`, `AI-EXPANSION-PROJECT.md` all gone from root and from the git index. `NEXT-STEPS.md`, `OPENAI.md`, `LGPD-WARNINGS.md` all tracked.
- **Seed framework + lib evolution (commit #4):** ✅ subsumed via `62dce54` (seed-lib layered architecture), `bfe4f83` (scheduler primitive formalization), `07afb18` (digest helper trio), `e1ba4e3` (webhook signature verifier), and the `context-budget-overhaul` series.
- **Product migrations (commits #5-8):** ✅ subsumed. Every product is on `create_product_app` / `createProductApp` per the absorption batch (`5acf4c4`) and the per-product seed-wiring closes that landed since.
- **MCP toolkit modernization (commit #9):** ✅ subsumed via the `mcp-server-expansion` project (`bfe4f83`, `b3af71f`, `9d90f99`) plus dotted-naming + Pydantic schema absorption.
- **PROJECT.md scaffolds (commit #10):** ✅ subsumed. The active `projects/` tree now reflects current work; closed projects deleted; `archive/projects/` houses PARKED + INFEASIBLE entries (`9447b6b`).
- **Infra cleanup (commit #11):** ✅ subsumed. Scripts, templates, requirements, n8n, .github, .gitignore all in tracked state through pre-commit hook chain commits.
- **Current working-tree drift (~18 entries) is parallel-agent in-flight work, NOT legacy drift** — it belongs to `scheduling-engine-seed`, `session-review-baseline`, `send-message-consolidation`, and the MCP `session_review` tool. Collision protocol applies — this batch coordinator MUST NOT touch those files. The original Path B "delete child folder" close-commit is therefore deferred: the folder deletion lands inline this session, but the commit is held until the parallel agents finish (per `KB § PATTERNS/project-execution.md § 2.9 collision protocol`).
- **Lesson for the batch layer:** the original consolidation-plan threat model — "uncommitted drift accumulates because no one commits as they ship" — was solved structurally during 2026-04-28 → 2026-05-03 by the **commit-per-phase methodology** (`KB § PATTERNS/project-execution.md § 2.10`). The 35+ commits in that window each closed a specific phase, leaving the working tree near-empty by default. Confirms the methodology is doing what was hoped.

### Phase 2 — Tier 2: `strict-mode-migration`

The original child PROJECT.md was a 54-line checklist planning strict mode across all 8 frontends. Phase 2.a §7 round (2026-05-03) surfaced honest cost/leverage tradeoff to user → user retired the 8-frontend ambition and locked the seed-boundary scope (fw + lib + CI gate). Child PROJECT.md rewritten to PROJECT-TEMPLATE.md format with Phase 0 audit findings inlined. Phase 2.b execution intentionally deferred to a separate fresh-session agent per user direction "lets go with C. file it as a separate project so i can clear this session."

**2.a §7 interrogation round (gates Phase 2.b).** ✅
- [x] Read original `projects/strict-mode-migration/PROJECT.md` (54-line checklist, predates modern template).
- [x] Surveyed strict state across 11 frontend tsconfigs + ran tsc baseline on lib (24 TS2307 module-resolution errors; lib has never been tsc-checked standalone).
- [x] Surfaced honest cost/leverage assessment to user (full 8-frontend sweep is low-leverage; seed-boundary is the high-leverage subset).
- [x] User locked scope: Option C (fw + lib + CI gate). Original 8-frontend ambition retired and slated for accept-with-rationale paperwork at child's Phase 5.
- [x] Child PROJECT.md rewritten to PROJECT-TEMPLATE.md format with §3a Seed-first analysis, Phase 0 findings, Phases 1-4 ready-to-execute.

**2.b `strict-mode-migration` — drive to ✅.** *(Deferred to separate session by user direction.)*
- [ ] Phase 1 — Lib: install peer-dep types as devDeps, get standalone tsc green in non-strict.
- [ ] Phase 2 — Lib: flip strict, fix errors (no `!`-assertion masking).
- [ ] Phase 3 — Framework: create tsconfig.json with strict:true from day 1, fix errors.
- [ ] Phase 4 — CI gate: `.github/workflows/seed-typecheck.yml` runs both checks on PR.
- [ ] Phase 5 — Paperwork: file accept-with-rationale entry for per-product strict as opt-in over time.
- [ ] Close-phase commit; child folder deleted; outcomes folded into this batch §11.

### Phase 3 — Tier 3: `therapy-platform-wiring`

Most-rigorous of the in-scope children. Phase 0 produces a discovery inventory (§5.4 in the child) that gates Phases 2-9. Resists shortcuts.

**3.a §7 interrogation round (gates Phase 3.b).** ✅ *(2026-05-03)*
- [x] Read `products/therapy-platform/projects/therapy-platform-wiring/PROJECT.md` §7. All 8 §7 items decided: 3 by user (Q1/Q3/Q5), 4 carry default recommendations (Q2/Q4/Q7 + meta), 2 already resolved by parallel-agent drift-realignment audit (Q6/Q8). User decisions captured verbatim in child §7 + child §11 entry.
- [x] Confirm scope per child §2 ("widest A ⇒ B ⇒ C: fix known regressions → admin sweep → close pre-existing scaffolding debt → widen to whole product"); user did not narrow → A⇒B⇒C confirmed.

**3.b `therapy-platform-wiring` — drive to ✅.**
- [x] Phase 0 — discovery + inventory ✅ *(2026-05-03)*. Gap table populated at child §5.4.1-5.4.9; ~58 gap rows surfaced; 7 systemic patterns (A-G) captured; Phases 6-9 promoted from placeholders to concrete sub-tasks; §7 design batch (Q9-Q14) surfaced for user sign-off before Phase 1. Deletion-candidate batch empty per child §5.4.7. Keeper review clean (0 issues, 0 proposals). User signed off Q9-Q14 with *"go on with your recommendations"*.
- [x] Phase 1 — shared identity resolver ✅ *(2026-05-03)*. Shipped `noctusai_lib.integrations.supabase_identity` (UserIdentity + fetch_user_identities + fetch_user_identity, 20 tests green). **Bonus seed-lib bug fix:** broken `require_role` (passes `_get_supabase_client=None` blindly) replaced with `make_require_role(get_current_user_fn, get_user_role_fn)` factory matching `make_get_current_user` shape; 6 new tests. Therapy-platform absorption: `admin_service.py::_fetch_user_identity` retired (32 lines deleted); `_therapist_row_to_dto` signature uses `UserIdentity`; N+1 loop converted to bulk pre-fetch. `dependencies.py` switched to seed factory. KB catalog updated. **Verification:** therapy-platform backend 1143/1143 ✅, seed-lib 448/448 ✅, frontend vite build clean, keeper 0 issues, KB sync OK. **Deferred to Phase 4:** `routers/settings.py` inline `_require_role`/`_require_admin` helpers (signature-different from Depends-factory; refactoring 11 endpoints is scaffolding-debt scope) + orphan `test_notificacoes_router.py` audit.
- [ ] Phase 2 — admin Tier A: known regressions.
- [ ] Phase 3 — admin Tier B: DTO normalization sweep.
- [ ] Phase 4 — admin Tier C: pre-existing scaffolding debt.
- [ ] Phase 5 — reject flow wiring.
- [ ] Phase 6-9 — therapist + patient + clinic + public surfaces (placeholders; shape decided by Phase 0).
- [ ] Close-phase commit; child folder deleted; outcomes folded into this batch §11.

### Phase 4 — Tier 4: concept → execution trio (3 children)

All three are concept-stage with §6 intentionally empty pending §7 + user reactivation. Surface all three §7s in one round; user decides which (if any) to promote to Phase 0 + execution.

**4.a §7 interrogation round (gates Phase 4.b–4.d).**
- [ ] Read `projects/vista-api-mcp/PROJECT.md` §7. Surface open questions (location / lang / adapter-reuse decisions per project status).
- [ ] Read `projects/project-history-ledger/PROJECT.md` §7. Surface open questions.
- [ ] Read `projects/methodology-mirror-and-workspaces/PROJECT.md` §7. Surface open questions, especially Q11 (workflow-constraint reactivation evidence).
- [ ] User decides per child: **promote** (run Phase 0 + execution), **revise concept** (rewrite § design), or **leave deferred** (close Phase 4 with that child intact).

**4.b `vista-api-mcp` — drive to ✅** *(if promoted).*
- [ ] Phase 0 — audit `VISTA-API-MCP-GUIDE.md` (the 904-line repo-root portable spec is source-of-truth) + decide in-repo location, language, adapter-reuse with existing `app/integrations/vista/`.
- [ ] Phases 1-N — execute per Phase 0 design.
- [ ] Close-phase commit; child folder deleted; outcomes folded into this batch §11.

**4.c `project-history-ledger` — drive to ✅** *(if promoted).*
- [ ] Phase 0 — audit + design (interlocks with `noctusai_count_tokens`).
- [ ] Phases 1-N — execute per Phase 0 design.
- [ ] Close-phase commit; child folder deleted; outcomes folded into this batch §11.

**4.d `methodology-mirror-and-workspaces` — drive to ✅** *(if promoted).*
- [ ] Phase 0 — confirm workflow-constraint reactivation trigger fired (per child §7 Q11). If not, leave deferred and close Phase 4 with this child intact.
- [ ] Phases 1-N — execute steps (b)+(c) per child design once reactivated.
- [ ] Close-phase commit; child folder deleted; outcomes folded into this batch §11.

### Phase 5 — Tier 5: `adconnect-migration`

Largest scope of the 7: full product migration into the seed framework. Custom JWT auth is the central design problem (framework-extension vs. product-custom — the seed-first rule says framework-extension).

**5.a §7 interrogation round (gates Phase 5.b).**
- [ ] Read `projects/adconnect-migration/PROJECT.md` §7. Surface open questions.
- [ ] Confirm migration scope per child §2 + §4. User signs off on JWT-auth strategy (framework-extension vs. product-custom) before Phase 0 starts.

**5.b `adconnect-migration` — drive to ✅.**
- [ ] Phase 0 — audit current adconnect/ scaffold state; decide migration sequence.
- [ ] Phases 1-N — backend + frontend migration into `create_product_app` / `createProductApp`; JWT auth flows through framework seam.
- [ ] LGPD checklist per `KB § PATTERNS/lgpd.md` (B2B marketplace data is regulated).
- [ ] Tests + verification (full backend pytest + frontend vite build + cross-product no-regression sweep).
- [ ] Close-phase commit; child folder deleted; outcomes folded into this batch §11.

### Phase 6 — Project close

- [ ] Confirm Tier 1-5 children closed + folders deleted (or Tier 4 concept-stages confirmed deferred per user decision).
- [ ] Roll up this batch's improvements + recurrence captures into one final `noctusai_file_proposal` if any cross-tier patterns emerged worth preserving beyond §11.
- [ ] `python mcp/noctusai/cli.py --improvements projects/main-core-migrations-batch/PROJECT.md`.
- [ ] Three-way sync verification (`bash scripts/verify-kb-sync.sh`).
- [ ] Final commit + push (literal last step per `KB § PATTERNS/project-execution.md § 0`).
- [ ] Delete this folder.

---

## 7. Open questions

Batch-level questions only. Per-child §7 questions are surfaced at each tier's kickoff (Phase 1.a / 2.a / 3.a / 4.a / 5.a).

1. **`repo-state-consolidation` staleness verdict** — Phase 0 was 2026-04-28; commits `5acf4c4`, `d4b571f`, `a3e87e2`, `e1ba4e3`, `146abe3`, `0a562d0` shipped after. Has the consolidation scope already happened in those commits, or is there still substantial uncommitted drift to consolidate? *Default recommendation:* run staleness audit (Phase 1.a above) before any other Tier 1 work. Outcome decides Path A (resume) vs. Path B (subsume + close). Decision needed before Phase 1 starts.
2. **Tier 4 concept-stage promotion** — are any of `vista-api-mcp`, `project-history-ledger`, `methodology-mirror-and-workspaces` ready to leave concept stage and promote to Phase 0 + execution? *Default recommendation:* surface their §7s together in Phase 4.a; user decides per child. Concept-stage children stay durably documented if not promoted.
3. **`adconnect-migration` JWT auth strategy** — framework-extension or product-custom? *Default recommendation:* framework-extension per the seed-first rule (`CLAUDE.md § Engineering Philosophy § Seed first`). Custom auth is a structural fork unless it flows through a named seam. Decision needed at Phase 5.a §7 round.
4. **Coordination with `side-projects-batch` + `absorbed-projects-batch`** — should the 3 batches run strictly sequentially, or can a parallel agent take Tier 1-2 of this batch while the other batch agents handle their work? *Default recommendation:* parallel-safe — Tier 1 here (`repo-state-consolidation`) is git-tree consolidation, Tier 2 (`strict-mode-migration`) touches frontends only. Cross-product collisions only become real at Tier 3+ (`therapy-platform-wiring`, `adconnect-migration`). Re-coordinate with sibling batch agents before starting Tier 3.

---

## 8. Dependencies & blockers

- **§7 interrogation round per tier** — gates execution of every child in that tier.
- **Staleness audit on Tier 1** — pre-resume hard-gate.
- **User sign-off on Tier 3 (`therapy-platform-wiring`)** — child status is "Design drafted — awaiting user sign-off before Phase 0 kicks off." This batch respects that gate.
- **User decision on Tier 4 promotion** — concept-stage children only execute if promoted in Phase 4.a.
- **`adconnect-migration` framework-extension design** — JWT auth seam may need a new seed-framework hook before migration starts. Surface at Phase 5.a.

---

## 9. Success criteria

- All Tier 1-3 + Tier 5 children closed (✅) + their folders deleted (or `repo-state-consolidation` subsumed-and-closed per Path B).
- Tier 4 children either promoted-and-closed OR confirmed-deferred per user decision in Phase 4.a.
- Each child's improvements folded into this batch §11 with one-line summaries.
- No regressions: end-of-batch verification = MCP tests green + every touched product backend pytest green + every touched frontend vite build green + LGPD checklist (for adconnect).
- Recurrence patterns surfaced across children captured here so the signal survives child-folder deletion.
- One final batch commit + push (Phase 6) is the literal last action.

---

## 10. How to use this plan

```bash
# Read this batch
cat projects/main-core-migrations-batch/PROJECT.md

# Snapshot reference (frozen evaluation point)
ls .claude/snapshots/projects-2026-05-03_024603/

# Tier 1 staleness audit (CRITICAL pre-resume gate)
git log --since=2026-04-28 --oneline
cat projects/repo-state-consolidation/PROJECT.md  # read §6 commit allocation table

# Per-tier §7 interrogation rounds — questions are inline in §6 above

# For each child, follow KB § PATTERNS/project-execution.md § 0 (canonical workflow)
# Read child's PROJECT.md, run Phase 0 audit, execute, close-phase-commit, fold into §11.

# Verify across phases
bash scripts/verify-kb-sync.sh
python mcp/noctusai/cli.py --review

# Improvements regen at every batch-phase close
python mcp/noctusai/cli.py --improvements projects/main-core-migrations-batch/PROJECT.md
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | **Project scaffolded + Phase 0 ✅.** 7 main-core / large migration children categorized into 5 tiers: Tier 1 resume-blocked (`repo-state-consolidation`), Tier 2 short-foundational (`strict-mode-migration`), Tier 3 product-wiring (`therapy-platform-wiring`), Tier 4 concept-stage trio (`vista-api-mcp`, `project-history-ledger`, `methodology-mirror-and-workspaces`), Tier 5 full-product migration (`adconnect-migration`). Phase 0 surfaced staleness risk on `repo-state-consolidation` (Phase 0 was 2026-04-28, multiple commits since) — Tier 1 must staleness-audit first. Awaiting Phase 1.a staleness audit + §7 interrogation round to start Tier 1 execution. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 1 ✅ — Tier 1 closed via Path B (subsumed).** Staleness audit verdict: every load-bearing target in the original `repo-state-consolidation` 11-commit plan has shipped through natural project-close commits between 2026-04-28 and 2026-05-03 (35+ commits in that window). Specifically: `core/` → `products/core/` migration ✅, root TODO/PLAN/ROADMAP cleanup ✅, seed-framework evolution ✅ (via `62dce54` + `bfe4f83` + `07afb18` + `e1ba4e3` + context-budget-overhaul series), product migrations to `create_product_app`/`createProductApp` ✅ (via `5acf4c4` absorption batch + per-product seed-wiring closes), MCP toolkit modernization ✅ (via `mcp-server-expansion` project), PROJECT.md scaffolds + `archive/projects/` housekeeping ✅ (via `9447b6b`), infra cleanup ✅. Current working-tree drift (~18 entries) is parallel-agent in-flight work (`scheduling-engine-seed`, `session-review-baseline`, `send-message-consolidation`, MCP session_review tool), NOT legacy drift — collision protocol applies. **Child folder `projects/repo-state-consolidation/` deleted inline this session** per close protocol; close-commit deferred until parallel agents finish (per `KB § PATTERNS/project-execution.md § 2.9 collision protocol`). Validates the commit-per-phase methodology — the structural fix to the "uncommitted drift" threat model. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 3.b child Phase 1 ✅ — shared identity resolver + Pattern F absorption.** Shipped (a) `noctusai_lib.integrations.supabase_identity` with `UserIdentity` dataclass + `fetch_user_identities()` (bulk) + `fetch_user_identity()` (singular). 20 tests green covering happy path, alias fallbacks, error → empty-shape, dedup, defensive non-string coercion. Sync `def` (supabase-py admin SDK is sync; documented). (b) **Bonus seed-lib bug fix:** discovered `noctusai_lib.api.auth.require_role` was broken at line 195 (passes `_get_supabase_client=None` blindly → RuntimeError; comment "overridden by product wrapper" was misleading — no override existed; verified zero callers monorepo-wide). Replaced with `make_require_role(get_current_user_fn, get_user_role_fn)` factory matching `make_get_current_user` shape. 6 new tests. (c) Therapy-platform absorption: `admin_service.py::_fetch_user_identity` retired (32 lines); `_therapist_row_to_dto` signature changed `Dict[str, str]` → `UserIdentity`; foto_url falls back from auth metadata → row's `photo_url`. **N+1 → bulk:** `list_therapists_for_admin` was N+1 in a loop; now does one bulk pre-fetch then iterates. (d) `dependencies.py` switched to `require_role = make_require_role(get_current_user, get_user_role)` (the local impl was dead code — no router imports it). (e) `KNOWLEDGE-BASE/CONTEXT/04-SHARED-LIBRARY.md` updated with new section + retired/replaced require_role table row. **Verification:** therapy-platform backend `pytest tests/` = 1143/1143 ✅; seed-lib backend = 448/448 ✅ (incl. 26 new); frontend `npx vite build` clean; keeper review = 0 issues, 0 proposals; `verify-kb-sync.sh` clean. **Deferred to child Phase 4:** `routers/settings.py` carries 2 inline role-check helpers (`_require_admin`/`_require_role` taking `user`, returning `user.id`) signature-different from Depends-pattern factory — refactoring 11 endpoints is scaffolding-debt scope. Plus orphan `tests/routers/test_notificacoes_router.py` (no matching router). Both filed as Phase 4 sub-tasks. Collision protocol still active per `KB § PATTERNS/project-execution.md § 2.9` — no commit yet. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 3.b child Phase 0 ✅ — discovery + inventory complete.** 4 parallel Explore agents enumerated: backend (38 routers, 193 routes, **0/38 declare `response_model`**), frontend (~143 unique calls × 26 hooks + 4 direct-fetch pages), migration column refs (44 tables, 500+ refs, only `rejection_reason × {therapist_profiles, clinics}` missing), seed-lib catalog (7 layers). Join surfaced **~58 gap rows + 7 systemic patterns**: A (PT/EN path mismatches × 8 routers / ~30 calls), B (admin namespace not split), C (admin detail endpoints missing), D (4 direct-fetch pages bypass hooks), E (193 routes have no `response_model` — implicit DTO contract via wrappers), F (`require_role` N=3 — 1 seed + 2 local), G (intra-cluster path-shape mismatches). Child §5.4 populated (5.4.1 counts → 5.4.9 keeper review); child Phases 6-9 promoted from placeholders to concrete sub-tasks rooted in §5.4.3 rows; child §7 design batch (Q9-Q14) surfaced for user sign-off before Phase 1 kickoff. **Q3 deletion-candidate batch: empty** — every admin/role page maps to a wired endpoint or a §5.4.3 gap row this project's scope fixes. Keeper review pass clean (`cli.py --review --product therapy-platform`: 0 issues, 0 proposals). **Improvements applied inline:** require_role recurrence flagged for Phase 1 absorption; orphan `tests/routers/test_notificacoes_router.py` flagged for child Phase 4 audit; `clinics` table added to migration 010 scope (the same reject path runs against either table; clinic-side fails today silently masked by the empty-Rejected hack). **Status:** awaiting user sign-off on child §7 Q9-Q13 design batch (default recs in place); Phase 1 starts on signal. Collision protocol still active per `KB § PATTERNS/project-execution.md § 2.9` — no commit yet. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 3.a ✅ — Tier 3 §7 round complete; scope confirmed; Phase 0 ready.** Surfaced child `therapy-platform-wiring` §7 (8 items) to user with evidence-backed recommendations. Premise-check meta-question flagged 2-week age + concurrent parallel-agent drift-realignment audit (which had already pre-resolved Q6 identity-resolver placement = `noctusai_lib/integrations/supabase_identity.py` per 6-layer layout, and Q8 pagination DTO local-first). My initial Q6 rec (`domain.identity`) was less honest than the parallel agent's (`integrations.supabase_identity`) — the resolver wraps Supabase auth.admin SDK, making it an integration adapter, not a domain primitive. Acknowledged the audit's resolutions; surfaced only the remaining 6 items. **User decisions captured (3):** Q1 reject-reason cleared on re-approval (*"yes"*); Q3 page-deletion candidates surfaced as one batch end-of-Phase-0 with one-line rationale per page (*"good call"*); Q5 LGPD 90-day retention + explicit `noctusai_lgpd_flag` at rule-creation per `feedback_lgpd_first` (*"let's go with your option, 90 dias then flag lgpd"*). **Default recommendations accepted (3 + meta):** Q2 (Claude benchmarks during Phase 1), Q4 (Claude flags during Phase 0), Q7 (avatar fallback — Claude during Phase 2 with design log). User direction: *"go on with recommendations"*. **Scope confirmed:** widest A⇒B⇒C — no narrowing requested. Child §7 + §11 + status line updated. **Next batch action:** Phase 3.b — child Phase 0 discovery; awaiting user "continue" before kickoff per child's pause-after-each-phase cadence. Note: parallel-agent collision protocol still active (FastMCP Phase 3 relocation in flight per `mcp-server-fastmcp-switch`); close-commit deferred until parallel work settles. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 2.a ✅ — Tier 2 §7 round complete; child re-scoped + filed standalone.** Surfaced 4 evidence-backed open questions on `strict-mode-migration` (doc-shape upgrade, stale `shared/frontend/` path, frontend count grew 5→8, missing `seed/framework/frontend/tsconfig.json`); user asked the deeper question "does this strict mode project actually add value?". Honest assessment: full 8-frontend sweep is low-leverage (~16-24h, mostly mechanical `!`-assertion fixes that mask the same null risk). User picked the narrower seed-boundary scope ("strict the fw + lib"). Phase 0 audit fired and surfaced 3 findings: lib has never been tsc-checked standalone (24 TS2307 errors from missing peer-dep types — strict-mode errors masked by resolution failures); framework has no tsconfig.json at all; lib + framework export source `.ts` directly so strict tightens types at source-import boundary, propagating to all 8 products via inheritance without per-product migration. Honest re-estimate surfaced (4-8h, vs. originally quoted 2-4h). User accepted Option C (full scope = fw + lib + CI gate + accept-with-rationale paperwork retiring per-product ambition) and asked for it filed as a separate project so this session can close. **Child `projects/strict-mode-migration/PROJECT.md` rewritten** from 54-line checklist to full PROJECT-TEMPLATE.md format with §3a Seed-first analysis, Phase 0 findings inlined, Phases 1-5 ready-to-execute, copy-paste commands in §10. Phase 2.b execution **deferred to fresh-session agent**; this batch's Phase 2.a sub-tasks all ✅. **Next batch action:** Phase 3 — Tier 3 `therapy-platform-wiring` §7 interrogation round (when batch resumes). | Claude Opus 4.7 |
