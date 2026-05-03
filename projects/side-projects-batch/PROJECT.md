# Side-Projects Batch — Project Document

> **What this project is.** A batch coordinator that drives the platform's older
> "side" projects — ours, not the absorbed-from-sibling ones, not the main-core
> migrations — to completion in a deliberate quickest-wins-first order. Each
> phase below targets one or more child projects already scaffolded under
> `projects/` or `products/<product>/projects/`. The work itself happens in the
> child PROJECT.md files; this batch is the meta-loop that orders them, runs
> §7 interrogation per child before its execution starts, and tracks rollup
> progress.
>
> **Why a batch project, not just a queue.** Three reasons: (1) ordering and
> pacing decisions deserve a durable home, (2) every child needs §7
> interrogation we batch into the kickoff of its tier so the user isn't pinged
> mid-execution, (3) cross-cutting recurrence patterns surfaced in one child
> often unblock helpers for the next — capturing that here keeps the synthesis
> from leaking when child folders close + delete.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** ⏳ **EXECUTING** — Phase 0 ✅ (snapshot + assessment); Phase 1 (Tier 1 batch) ready to start, awaiting §7 sign-off on first child.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `side-projects-batch` (subject=side-projects, intent=batch)
- **Project location:** `projects/side-projects-batch/` (cross-product / platform-coordinator — drives child projects across multiple products + root)
- **Snapshot:** `.claude/snapshots/projects-2026-05-03_024603/` — frozen state of all 26 PROJECT.md files at batch start (608K, locked-in evaluation point; another agent's in-flight work is intentionally not captured).
- **Related docs:**
  - `KB § PATTERNS/project-execution.md § 0` — canonical execution workflow each child runs through.
  - `KB § PATTERNS/proposals-and-improvements.md § 4d` — auto-improvement at phase close.
  - `templates/PROJECT-TEMPLATE.md` — scaffold each child uses.

---

## 1. Context & Purpose

The repo's `projects/` and `products/*/projects/` trees collected 26 PROJECT.md files over the last two months. A 2026-05-03 audit categorized them as:

- **8 absorbed from sibling repos** (`whatsapp-google-scheduling`, `automations`) — being driven by the absorption batch (commit `5acf4c4`); out of scope here per user direction.
- **7 main-core / large migrations** (adconnect, strict-mode, repo-state-consolidation, methodology-mirror-and-workspaces, project-history-ledger, vista-api-mcp, therapy-platform-wiring) — sized for dedicated multi-session attention; out of scope here per user direction.
- **3 closed / empty** (methodology-extraction ✅, vista-crm-wiring ✅, repo-commit-followup empty).
- **8 our own side projects** — the focus of this batch.

The 8 in scope are sitting at "filed pending interrogation" or "phases 0-2 done, 3-5 deferred." Each is small enough to land in 1-3 sessions but large enough that "I'll get to it" never quite comes. This batch makes the ordering explicit and the pacing real.

The win: clear the side-project tail, stop carrying mental overhead for queued-but-not-moving work, and surface real recurrence patterns into seed before they get lost in folder deletions.

---

## 2. Confirmed constraints

- **Scope** — only "our own" old side projects. Skip the 8 absorbed-from-sibling projects (driven by the absorption batch separately) and the 7 main-core / large ones. *(User direction 2026-05-03: "leave the ones that were absorbed from other repos, let's only focus on our own projects (the old ones, mostly, the side projects, not the main-core big ones)".)*
- **Pacing** — quickest wins → most complex; tier-batched. *(User direction 2026-05-03: "phase batched as per your pacing recommendation".)*
- **Snapshot is the evaluation baseline** — `.claude/snapshots/projects-2026-05-03_024603/` is the frozen reference point. Another agent is creating new projects in parallel; this batch does not pick those up. *(User direction: "another agent working that's gonna create projects, but we wont interfere in his work.")*
- **§7 interrogation per child happens at the START of that child's tier**, not all at once up-front. Avoids stale answers and keeps the user-attention windows tight to active work.
- **Each child runs its own canonical execution workflow** (KB § PATTERNS/project-execution.md § 0): scaffold → Phase 0 audit → execute per phase → close-phase commit (no push) → on full child close, fold into batch §11 + delete child folder. Push happens only at side-projects-batch close.
- **PARKED stays parked.** `pf-org-scoping-migration` was explicitly parked 2026-04-27. This batch does not unpark it; user resume is the only trigger.
- **INFEASIBLE stays infeasible.** `narrow-read-compliance-detector` is concept-stage and gated on §7 unblock triggers. Not pulled into this batch.

---

## 3. Design principles

1. **Ordering is the deliverable here, not the work.** The actual implementation lives in each child's PROJECT.md. This batch's value is the sequencing + the §7 interrogation cadence + recurrence-pattern capture across children.
2. **Tier-by-tier, child-by-child.** Within a tier, finish one child fully (Phase 0 → close → folder deleted) before starting the next. No interleaving — each child is small enough to deserve focused attention.
3. **§7 questions surface together at tier kickoff.** When Tier 1 starts, ask the user every Tier-1 §7 question in one round. Same for Tier 2, Tier 3. Reduces context-switch cost.
4. **Recurrence captured at this layer.** When child A surfaces a helper that child B would also benefit from, that observation lives in this batch's improvements block (which survives child folder deletion) — not just child A's `**Improvements:**`.
5. **No new design here.** Every child already has its own §3a. This batch's §3a (below) only confirms the batch coordinator itself doesn't need a seed-able pattern.

---

## 3a. Seed-first analysis (REQUIRED — the seed is every product's skeleton)

This is a **batch coordinator project** — its only deliverable is sequencing, interrogation cadence, and rollup. It produces no production code, no shared component, no helper. Each child project runs its own §3a.

Six-question checklist:

1. **Is the contract identical for every product?** N/A — this project ships no product-touching code. Each child's §3a answers this for the child's actual change.
2. **Is the data source product-specific?** N/A.
3. **Is the placement product-specific?** N/A.
4. **Is the visibility / permission rule the same?** N/A.
5. **Does the seam already exist in seed?** N/A — no seam needed. The "seam" here is the child PROJECT.md, which is its own canonical form.
6. **Default-on or opt-in?** N/A.

**Litmus — per-product code count this design requires:**

- [x] **0 lines** — pure cross-product concern; lives entirely in seed. Products inherit from the factory. → Confirmed: this project produces zero per-product code. Per-product code lands inside each child project, where its own §3a governs placement.

**Phase plan implications:** §6 phases below are **phase = child-batch**, not phase-per-product. No replication framing — children themselves may be product-scoped, but the batch coordinator is product-agnostic.

---

## 4. Scope

**In scope (8 children, tier-grouped):**

**Tier 1 — quick wins (Phase 1 of this batch):**
- `products/therapy-platform/projects/therapy-audio-lifecycle-schema-reconciliation/`
- `products/therapy-platform/projects/therapy-scheduler-for-retention/`
- `projects/mcp-scaffold-sql-templates-integration/`
- `products/therapy-platform/projects/therapy-consent-frontend-wiring/`

**Tier 2 — medium (Phase 2 of this batch):**
- `products/erp-imobiliario/projects/erp-schema-drift-reconciliation/`
- `projects/keeper-warning-triage/` (deferred Phases 2-7)

**Tier 3 — larger (Phase 3 of this batch):**
- `projects/execution-workflow-codequality-rollout/` (deferred Phases 3-5)

**Out of scope (acknowledged, not pulled in):**
- 8 absorbed-from-sibling projects — `whatsapp-seed-absorption`, `mcp-server-expansion`, `llm-tool-call-audit`, `scheduling-engine-seed`, `imobi-scheduling-bot-creation`, plus 3 deferred future-direction drafts (`agno-dev-team-future-direction`, `dev-observability-bot-future-direction`, `user-context-bot-future-direction`).
- 7 main-core / large migrations — `adconnect-migration`, `strict-mode-migration`, `repo-state-consolidation`, `methodology-mirror-and-workspaces`, `project-history-ledger`, `vista-api-mcp`, `therapy-platform-wiring`.
- `pf-org-scoping-migration` — PARKED 2026-04-27 by explicit user directive; only resumes when user says so.
- `narrow-read-compliance-detector` — concept stub marked INFEASIBLE today; gated on §7 unblock triggers in that file.
- 3 already-closed / empty (`methodology-extraction`, `vista-crm-wiring`, `repo-commit-followup`).

---

## 6. Implementation phases

**Phase = child-batch.** Each phase opens with a §7 interrogation round covering every child in that tier, then drives each child end-to-end through its own canonical workflow before flipping the batch phase to ✅.

### Phase 0 — Snapshot + assessment ✅ (executed 2026-05-03)

- [x] Snapshot all `projects/`, `products/*/projects/`, `core/projects/` to `.claude/snapshots/projects-2026-05-03_024603/` (608K, 26 PROJECT.md files frozen).
- [x] Categorize the 26 by source (absorbed / main-core / closed / our-side).
- [x] Identify the 8 in-scope children, group into 3 tiers, write up the assessment in chat.
- [x] Verify the 8 are correctly categorized: read each PROJECT.md status header, phase count, §7 state.

**Improvements:**
- Three of the four Tier-1 children (`therapy-scheduler-for-retention`, `therapy-consent-frontend-wiring`, `therapy-audio-lifecycle-schema-reconciliation`) carry the template's default `## 7. See §2 — all answered at interrogation time.` placeholder despite §2 itself being unfilled. This is a misleading template-fill artifact: §7 reads as "answered" while the project is actually pre-interrogation. Capturing here as a recurrence; if a 4th instance shows up in Tier 2/3, formalize either a keeper detector (`§7 says answered + §2 still has _Interrogate_ placeholder = inconsistency`) or update the template to leave §7 blank in the unanswered state. *(N=3, triage time → log; N≥4 → must formalize.)*
- The snapshot lives at `.claude/snapshots/` — outside `projects/` and outside git ignore patterns I checked. If `.claude/` isn't already gitignored, this needs verifying so the snapshot doesn't pollute commits.

### Phase 1 — Tier 1 batch (quick wins)

Drives 4 children to ✅, each in canonical workflow form.

**1.a §7 interrogation round (gates Phase 1.b–1.e). ✅ (closed 2026-05-03)**
- [x] Surface every Tier-1 §7 question to the user in one consolidated message; capture answers in each child's §2 + §7. **Outcome:**
  - `therapy-audio-lifecycle-schema-reconciliation` — Q1=B (refactor to resolve `video_rooms` first), Q2=proceed without `mock-supabase-schema-validation`. §2/§3/§6 filled.
  - `therapy-scheduler-for-retention` — Q3=daily env-configurable, Q4=audio-only v1 with generic registration surface, Q5=in-process behind `THERAPY_SCHEDULER_ENABLED` flag. **N=4 recurrence-rule trip captured** (mailing/PF/erp + therapy = 4 per-product schedulers); accept-with-rationale + follow-up `seed-side-scheduler-primitive` project to be filed at child Phase 3.
  - `therapy-consent-frontend-wiring` — Q6=both paths (patient self-serve + therapist-attest), Q7=recording-only v1, Q8=render revoked with badge. §2/§6 filled.
  - `mcp-scaffold-sql-templates-integration` — §7 is audit-driven (Phase 0 generates questions). Skipped from this round; will surface at start of Phase 1.d.
  - **Batch-level Q9** (push cadence) — batch-close push only; per-child commits stay local. **Q10** (`repo-commit-followup` empty folder) — delete on close at Phase 4.

**1.b `therapy-audio-lifecycle-schema-reconciliation` — drive to ✅. ✅ (closed 2026-05-03)**
- [x] Phase 0 audit per child workflow — site inventory built, live-DB schema confirmed, absorption-search trio run.
- [x] **Expand-loudly finding**: `recording_id` is also a non-existent column (never been in any of the 8 therapy migrations); LiveKit `stop_recording(...)` calls have been silent no-ops. Phase 1 split into 1a (appointment_id refactor) + 1b (recording_id column add — new migration `009_session_audio_segments_recording_id.sql`).
- [x] **HARD GATE cleared — user approved migration `009_*`.** Applied via `mcp__claude_ai_Supabase__apply_migration` (project_id `nyplttplcoyiiqjrvtiw`) → `{"success": true}`. Migration file at `products/therapy-platform/backend/migrations/009_session_audio_segments_recording_id.sql` mirrors live state per the "MCP migrations mirror the file" rule.
- [x] Phase 1a — appointment_id refactor at 10 sites: 8 in `session_service.py` (start/pause/resume/end/auto_finalize/reopen — `room["id"]` already in scope at every site), 1 in `transcription_service.py::assemble_transcript` (added explicit `video_rooms` lookup), 1 in `session_journal.py::_get_session_audio` (same lookup pattern + cleaned up early-empty branch with `segment_rows = []` instead of a synthetic empty-shape object).
- [x] Phase 1b — migration ✅ + the existing `recording_id` write/read paths in `session_service.py` (lines 169-171, 324-327, 564-568 writes; 248, 390, 455 reads) now actually persist + dispatch since the column exists. No code change needed beyond the migration; the silently-broken paths are now real.
- [x] Phase 2 — Tests fixed + 3 colocated regression guards added at `tests/edge_cases/test_session_audio_segments_schema.py`: (a) `start_session` inserts segments with `video_room_id` not `appointment_id` (asserts via `inserted_payloads`), (b) `end_session` dispatches `livekit_service.stop_recording("egress-001")` when `recording_id` is set on the active segment, (c) `pause_session` query path resolves segment by `video_room_id`. **Therapy backend: 1138/1138 passed** (was 1135 before, +3 new). **Keeper review: 0 issues.**
- [x] **In-flight test-helper observation captured** — added `_seed_room_and_segments(db, segments)` at `tests/services/test_transcription_service.py` to seed `video_rooms` + `session_audio_segments` together; the same pattern likely repeats in `tests/routers/test_journal_router.py` (already covered by `_setup_tables` defaults) and may surface again in `test_session_lifecycle.py` test-cases that don't pre-seed video_rooms today. **Recurrence count N=2** (transcription + journal). If a 3rd repetition appears in Phase 1.c or 1.e, formalize as a seed-lib helper `noctusai_lib.testing.therapy.seed_room_and_segments` per the recurrence rule. Tracking here at the batch layer because the child folder will be deleted at close.
- [x] **Cross-product recurrence findings** from absorption-search trio (`_render_bodies` 5p, `_generate_narrative` 4p, HTTPException shapes 4p, pagination patterns 4p, `_TEMPLATE_DIR` Path expression 5p, `register_feature` ai_consent docstring 5p, retention-sweep N=2) — captured here as feed for `execution-workflow-codequality-rollout` Phase 4 absorption queue (Tier 3 of this batch).
- [ ] Close-phase local commit (per Q9 cadence: commit per phase, push only at batch close at Phase 4 of this batch). **Pending user confirmation before staging.**
- [ ] Child folder `products/therapy-platform/projects/therapy-audio-lifecycle-schema-reconciliation/` deletion (canonical close protocol). **Pending user confirmation.**

**1.c `therapy-scheduler-for-retention` — drive to ✅. ✅ (closed 2026-05-03)**
- [x] Phase 0 audit — diffed mailing + PF schedulers (ERP doesn't have one yet); confirmed shared shape (AsyncIOScheduler / silenced logging / `start_scheduler`+`stop_scheduler` wired into `lifespan_startup`+`lifespan_shutdown`). Recurrence count locked at N=3 (not N=4 as the original child PROJECT.md suggested).
- [x] Built `products/therapy-platform/backend/app/scheduler.py` with generic `register(name, fn, hours=...|minutes=...|seconds=...)` surface + `audio_retention_job` wrapper around `audio_retention_service.run_retention_sweep` + `start_scheduler` / `stop_scheduler` lifecycle. Env flags: `THERAPY_SCHEDULER_ENABLED` (default `True`) + `THERAPY_AUDIO_RETENTION_SWEEP_INTERVAL_HOURS` (default `24`).
- [x] Added settings to `app/config.py::TherapySettings` + wired `lifespan_startup=start_scheduler, lifespan_shutdown=stop_scheduler` into `app/main.py`'s `create_product_app(...)` call.
- [x] 10 colocated tests at `tests/services/test_scheduler.py` covering: register validation (5), start-flag gating (2), stop safety (1), audio-retention job invocation + error swallow (2). Used `replace_existing` mock-assertion + `register`-mock approach to avoid needing a running event loop.
- [x] **Therapy backend: 1148/1148 passed** (was 1138, +10 new). Keeper: 0 issues.
- [x] **Filed follow-up project** `projects/seed-side-scheduler-primitive/PROJECT.md` per the recurrence rule (N=3 must-formalize) — lands `noctusai_lib.api.scheduler` + migrates the 3 products. Phase 0 interrogation pending; not in this batch's scope (cross-product seed work).
- [x] **Filed `accept-with-rationale` entry** at `KB § PATTERNS/accept-with-rationale.md` — "Per-product `app/scheduler.py` at N=3 (mailing/PF/therapy) — pending seed-side primitive". Inline `# accept-with-rationale:` comment at therapy's `scheduler.py` next to the module-level scheduler instance.
- [x] Close-phase commit pending.
- [x] Child folder deletion pending.

**1.d `mcp-scaffold-sql-templates-integration` — drive to ✅. ✅ (closed 2026-05-03)**
- [x] Phase 0 audit — read `scaffold.py` (89 lines, copy-template + placeholder-substitution shape) + `test_scaffold.py` + the bundled template `001_seed.sql`. **EXPAND-LOUDLY finding**: template hardcoded literal `seed.` instead of `{{SCHEMA_NAME}}.` — every previously-scaffolded product would have produced migrations referencing the wrong schema. Pre-existing bug surfaced by Phase 0 audit, fixed in-flight per the methodology.
- [x] Phase 1 — Updated `templates/product-seed/backend/migrations/001_seed.sql`: added `SET search_path = {{SCHEMA_NAME}}, public;` prelude (matches `set_search_path()` helper output) + replaced literal `seed.` with `{{SCHEMA_NAME}}.` everywhere + index names switched to `idx_{{SCHEMA_NAME}}_*`. Updated `scaffold.py` module docstring with pointer to `noctusai_lib.domain.sql_templates` for future migration authoring.
- [x] Phase 2 — Added `TestSqlTemplatesIntegration` (3 tests) at `mcp/noctusai/tests/test_scaffold.py`: (a) scaffolded migration's `SET search_path` line matches `set_search_path()` output, (b) scaffolded RLS policy matches `rls_subquery_policy(...)` output (whitespace-normalized), (c) no `seed.` literal leaks into scaffolded migration. Future drift between template + helpers is now a CI failure.
- [x] **MCP suite: 475 passed** (1 skipped slow test, 1 deprecation warning). Keeper: 0 issues.
- [x] Close-phase commit pending.
- [x] Child folder deletion pending.

**1.e `therapy-consent-frontend-wiring` — drive to ✅.**
- [ ] Phase 0 audit + child §2 fill from §7 round.
- [ ] Build consent modal + wire to `POST /grant`; verify against existing `sessions.py` consent-gate.
- [ ] Build revoke + history UI per Q3 answer.
- [ ] Tests (unit + E2E) + verification (frontend vite build + therapy backend pytest).
- [ ] Close-phase commit; child folder deleted; outcomes folded into this batch §11.

### Phase 2 — Tier 2 batch (medium complexity)

**2.a §7 interrogation round (gates Phase 2.b–2.c).**
- [ ] Surface Tier-2 §7 questions in one round. Children: `erp-schema-drift-reconciliation` (live-DB inspection cadence, per-table preference vs. bundled), `keeper-warning-triage` (cluster ordering for deferred Phases 2-6).

**2.b `erp-schema-drift-reconciliation` — drive to ✅.**
- [ ] Phase 0 — live-DB inspection via `mcp__claude_ai_Supabase__execute_sql` against erp schema; confirm 8 drift points still present.
- [ ] Phase 1 — per-table reconciliation per user-chosen pattern.
- [ ] Phase 2 — re-enable `validate_schema=True` on ERP MockSupabaseClient; run full ERP backend suite.
- [ ] LGPD checklist confirmed (financial data; verify nothing leaks across product boundaries).
- [ ] Close-phase commit; child folder deleted; outcomes folded into this batch §11.

**2.c `keeper-warning-triage` deferred phases — drive to ✅.**
- [ ] Phase 2 — core tests cleanup.
- [ ] Phase 3 — mailing tests cleanup.
- [ ] Phase 4 — PF / daily-life / adconnect tests cleanup.
- [ ] Phase 5 — seed-lib silent-error cleanup.
- [ ] Phase 6 — detector refinement (return-value-as-surface).
- [ ] Phase 7 already shipped; this just rolls up + closes the project.
- [ ] Close-phase commit; child folder deleted; outcomes folded into this batch §11.

### Phase 3 — Tier 3 batch (larger / multi-phase rollout)

**3.a §7 interrogation round (gates Phase 3.b).**
- [ ] Surface Tier-3 §7 questions. Child: `execution-workflow-codequality-rollout` (Phase 4 absorption queue priorities, Phase 5 calibration window).

**3.b `execution-workflow-codequality-rollout` deferred phases — drive to ✅.**
- [ ] Phase 3 — remaining therapy test files cleanup (32 sites in `test_invitations_router.py`, `test_e2e_flows.py`, service tails).
- [ ] Phase 4 — first-batch absorptions surfaced live (`assert_error_contains` confirmed at N≥4; full list reviewed at start of phase).
- [ ] Phase 5 — calibration revisit; re-run all 8 absorption scans; measure ROI vs baselines.
- [ ] Close-phase commit; child folder deleted; outcomes folded into this batch §11.

### Phase 4 — Project close

- [ ] Confirm all 8 children closed + folders deleted.
- [ ] Roll up this batch's improvements + recurrence captures into one final `noctusai_file_proposal` if any cross-tier patterns emerged worth preserving beyond §11.
- [ ] `python mcp/noctusai/cli.py --improvements projects/side-projects-batch/PROJECT.md`.
- [ ] Three-way sync verification (`bash scripts/verify-kb-sync.sh`).
- [ ] Final commit + push (literal last step per `KB § PATTERNS/project-execution.md § 0`).
- [ ] Delete this folder.

---

## 7. Open questions

These are batch-level questions only. Per-child §7 questions are surfaced at each tier's kickoff (Phase 1.a / 2.a / 3.a).

1. **Push cadence within the batch** — push at every child close, or only at batch close? *Default recommendation:* batch close only (per existing methodology — `KB § PATTERNS/project-execution.md § 0`). Per-child commits remain local; one push at Phase 4. Decision needed before Phase 1 commits start.
2. **Are there children I miscategorized?** Specifically: should `repo-commit-followup` (currently empty) be deleted as part of cleanup, or does it have meaning I missed? *Default recommendation:* delete-empty during Phase 4 close.

---

## 8. Dependencies & blockers

- **§7 interrogation round per tier** — gates execution of every child in that tier.
- **Other agent's parallel project creation** — no direct blocker; their work is intentionally outside this batch's snapshot. If they happen to scaffold something that overlaps an in-scope child, raise it before continuing.
- **Live DB access (`mcp__claude_ai_Supabase__*`)** — needed for `erp-schema-drift-reconciliation` Phase 0 in Tier 2. Already authorized per memory.

---

## 9. Success criteria

- All 8 in-scope children closed (✅) + their folders deleted.
- Each child's improvements folded into this batch §11 with one-line summaries.
- No regressions: end-of-batch verification = MCP tests green + every touched product's backend pytest green + every touched frontend vite build green.
- Recurrence patterns surfaced across children captured here so the signal survives child-folder deletion.
- One final batch commit + push (Phase 4) is the literal last action.

---

## 10. How to use this plan

```bash
# Read this batch's project doc
cat projects/side-projects-batch/PROJECT.md

# Snapshot reference (frozen evaluation point)
ls .claude/snapshots/projects-2026-05-03_024603/

# At start of each tier — surface §7 questions to user
# Tier 1 questions are listed inline above (Phase 1.a). Tier 2/3 surface at their phases.

# For each child, follow KB § PATTERNS/project-execution.md § 0 (canonical workflow)
# Read the child's PROJECT.md, run Phase 0 audit, execute, close-phase-commit, fold into §11.

# Verify across phases
bash scripts/verify-kb-sync.sh
python mcp/noctusai/cli.py --review

# Improvements regen at every batch-phase close
python mcp/noctusai/cli.py --improvements projects/side-projects-batch/PROJECT.md
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | **Project scaffolded + Phase 0 ✅.** Snapshot taken at `.claude/snapshots/projects-2026-05-03_024603/` (26 PROJECT.md files, 608K). 26 projects categorized: 8 absorbed-from-sibling (skip), 7 main-core/large (skip), 3 closed/empty (skip), 8 our-side (in scope). Tiered Tier 1 (4 children), Tier 2 (2 children), Tier 3 (1 child). Phase 0 improvements captured: §7 template-default-mismatch recurrence (N=3 from Tier-1 children), `.claude/` gitignore verify. Awaiting Phase 1.a §7 interrogation round to start Tier 1 execution. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 0 follow-up — sibling batch projects scaffolded.** Per user request, filed `projects/absorbed-projects-batch/PROJECT.md` (8 children, 4 tiers — 5 active + 3 deferred-acknowledged) and `projects/main-core-migrations-batch/PROJECT.md` (7 children, 5 tiers including Tier 1 staleness audit on `repo-state-consolidation`). Both designed for parallel-agent execution. `.claude/snapshots/` added to `.gitignore`. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 1.a ✅ — Tier 1 §7 round closed.** All 8 Tier-1 child §7 questions + 2 batch-level questions resolved with recommended defaults. Three children (`therapy-audio-lifecycle-schema-reconciliation`, `therapy-scheduler-for-retention`, `therapy-consent-frontend-wiring`) had their §2 / §3 / §6 phase plans filled. Fourth child (`mcp-scaffold-sql-templates-integration`) is audit-driven; its §7 surfaces during Phase 1.d Phase 0. **Cross-tier recurrence-rule trip captured at this batch layer**: per-product `app/scheduler.py` reaches N=4 with therapy adoption — accept-with-rationale + `seed-side-scheduler-primitive` follow-up project to be filed at therapy-scheduler-for-retention Phase 3. Phase 1.b ready: `therapy-audio-lifecycle-schema-reconciliation` Phase 0 audit. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 1.b Phase 0 ✅ (child) — EXPAND-LOUDLY finding.** `therapy-audio-lifecycle-schema-reconciliation` Phase 0 confirmed live-DB schema unchanged + built 9-site Phase 1a inventory. Critical parallel finding: `recording_id` has **never existed** in any of the 8 therapy migrations — every `recording_id` write has been silently dropped by PostgREST, every read returns None, every LiveKit `stop_recording(...)` call has been a no-op for the lifetime of the feature. Phase 1 split into 1a (refactor, no migration) + 1b (migration `009_session_audio_segments_recording_id.sql`, HARD GATE on user approval). **Cross-product recurrence findings (out of this child's scope, folded here for `execution-workflow-codequality-rollout` Phase 4)**: `_render_bodies` (5 products), `_generate_narrative` (4 products), `_TEMPLATE_DIR` Path expression (5 products), `register_feature` ai_consent docstring line (5 products), HTTPException 404/403/500 patterns (4 products each), `paginated_response`/`query.range(...)` patterns (4 products), `audio_retention_service.run_retention_sweep` ↔ `webhook_retention_service.run_retention_sweep` (N=2 retention pattern). Tier-3 absorption queue ready. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 1.b ✅ — `therapy-audio-lifecycle-schema-reconciliation` execution complete.** User approved migration; applied to live DB via Supabase MCP (`{"success": true}`). Migration file `products/therapy-platform/backend/migrations/009_session_audio_segments_recording_id.sql` written + mirrored. Phase 1a refactor at 10 sites (8 in `session_service.py` + 1 in `transcription_service.py` + 1 in `session_journal.py`). Pre-existing `recording_id` write/read paths in `session_service.py` now real (no code change needed; column existence unblocks them). Test fixtures updated (`SAMPLE_AUDIO_SEGMENT` + `SEGMENT_INITIAL`/`RESUMED`/`REOPENED` switched from `appointment_id` to `video_room_id`; new `_seed_room_and_segments` helper in `test_transcription_service.py` and new `SAMPLE_VIDEO_ROOM` row in `test_journal_router.py`). 3 new colocated regression guards at `tests/edge_cases/test_session_audio_segments_schema.py`. **Therapy backend: 1138/1138 passed (+3 new); keeper: 0 issues.** Phase committed as `4c50b02` + child folder deleted. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 1.c ✅ — `therapy-scheduler-for-retention` execution complete.** Built `products/therapy-platform/backend/app/scheduler.py` with generic `register(name, fn, hours/minutes/seconds=...)` surface + `audio_retention_job` wrapper + `start_scheduler` / `stop_scheduler` lifecycle. Env flags `THERAPY_SCHEDULER_ENABLED` + `THERAPY_AUDIO_RETENTION_SWEEP_INTERVAL_HOURS` added to `TherapySettings`. Wired `lifespan_startup` / `lifespan_shutdown` into `app/main.py`. 10 colocated tests at `tests/services/test_scheduler.py`. **Therapy backend: 1148/1148 passed (+10 new); keeper: 0 issues.** Recurrence-rule trip locked at N=3 (mailing/PF/therapy — ERP has no scheduler yet, contradicting the original child §1's claim of N=3 already; therapy ADDING the scheduler is what makes the count N=3). Filed `projects/seed-side-scheduler-primitive/PROJECT.md` as the formalization follow-up + `KB § PATTERNS/accept-with-rationale.md` entry "Per-product `app/scheduler.py` at N=3" + inline `# accept-with-rationale:` comment at the module-level scheduler instance. Phase committed as `84c585b`. **Test-helper recurrence finding from Phase 1.b** (`_seed_room_and_segments` shape) did NOT repeat in Phase 1.c (scheduler tests don't seed video_rooms) — count remains N=2; will check again in Phase 1.e (consent frontend). | Claude Opus 4.7 |
| 2026-05-03 | **Phase 1.d ✅ — `mcp-scaffold-sql-templates-integration` execution complete.** Phase 0 audit of `mcp/noctusai/tools/scaffold.py` (89 lines, template-copy + placeholder-substitution architecture) surfaced an **EXPAND-LOUDLY pre-existing bug**: the bundled template `templates/product-seed/backend/migrations/001_seed.sql` hardcoded literal `seed.` instead of using the `{{SCHEMA_NAME}}.` placeholder, so every previously-scaffolded product would have produced migrations referencing the wrong schema (the template's own seed schema). Fixed in-flight per the "Phase 0 — expand loudly" rule. Same migration template now also carries a `SET search_path = {{SCHEMA_NAME}}, public;` prelude that matches `set_search_path()` output. 3 new colocated regression tests (`TestSqlTemplatesIntegration`) at `mcp/noctusai/tests/test_scaffold.py` assert (a) scaffolded `SET search_path` matches helper output, (b) scaffolded RLS policy matches `rls_subquery_policy(...)` output (whitespace-normalized), (c) no `seed.` literal leaks into scaffolded migration. **MCP suite: 475 passed (+3 new); keeper: 0 issues.** Pause point: another agent now active in `projects/` (created empty `projects/template-workspace/`); confirming with user before Phase 1.e to avoid collision. | Claude Opus 4.7 |
