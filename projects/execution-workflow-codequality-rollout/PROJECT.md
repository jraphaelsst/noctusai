# Execution-Workflow Code-Quality Rollout — Project Document

> **What this project is.** The consolidation point for the methodology + tooling refinements landed across the late-April 2026 session: refined `KB § PATTERNS/project-execution.md § 0` workflow with absorption-scan integration + per-phase verification checklists, the absorption-search sextet (8 MCP scans), and the rollout of all this to the in-flight cleanup queue.
>
> **Written for a zero-context reader.** If you pick this up cold: read §1 + §3 + §6.

- **Created:** 2026-04-28
- **Last updated:** 2026-04-28
- **Status:** ⏳ **EXECUTING** — Phase 0 + Phase 1 shipped (methodology + tools); Phases 2-5 (apply across queue + measure ROI) deferred.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `execution-workflow-codequality-rollout` (subject=execution-workflow, intent=rollout)
- **Project location:** `projects/execution-workflow-codequality-rollout/` (cross-product / platform-infra — methodology + tooling apply everywhere)
- **Related docs:**
  - `KB § PATTERNS/project-execution.md § 0 The execution workflow` — the refined canonical loop (just shipped)
  - `KB § 06-AGENTS.md § Cross-cutting utilities § Absorption-search sextet` — the 8 scans (just shipped)
  - `~/.claude/.../memory/feedback_execution_workflow.md` — the methodology memory entry (just refined)
  - `~/.claude/.../memory/feedback_absorption_search_standing_duty.md` — the standing-duty memory entry
  - **Sister projects in flight:**
    - `projects/keeper-warning-triage/` — parent triage of the 564 first-run warnings
    - `projects/platform-logging-standardization/` — silent-error refactor (closed)
    - `products/therapy-platform/projects/therapy-tests-no-self-patch/` — first user of the refined workflow

---

## 1. Context & Purpose

User directive 2026-04-28 (paraphrased through the session arc):

> *"Vamos aproveitar to search for absorption opportunities to the seed along the way. We have mcp function for that. Revise it and assert it's solid enough for the job. If not, enrich it so it is. Please opt for the optimized version best-related to code-quality for future implementations. Let's document this, so all future agents are aligned with best optimal execution methods for each phase. Let's add a final verification step. Run absorption scan again after all done and let's re-enrich docs. Run your tests as per your past work, then let's merge findings, improvements and corrections, and start a new project on that, so we break this process through and doc steps, so we keep track."*

The session refined two things together:

1. **The execution workflow** — added pre-phase absorption-scan, mid-phase scan checkpoints, phase-end + project-end verification checklists. Codified in `KB § PATTERNS/project-execution.md § 0`.
2. **The absorption-search tooling** — added 6 new MCP scans on top of the existing 2: `scan_cross_product_helpers`, `scan_service_line_recurrence`, `scan_block_patterns`, `scan_within_product_helpers`, `scan_pydantic_model_shapes`, `scan_test_fixture_recurrence`, `scan_migration_patterns`. Total 8 scans = the **Absorption-search sextet** documented in `KB § 06-AGENTS.md`.

This project tracks the consolidation + rollout so future sessions can pick up cleanly.

---

## 2. Confirmed constraints

- **Code-quality bias** *(user directive 2026-04-28)*: when choosing between a quick path and a thorough path at any step, pick thorough. The 5-30 min Phase 0 prevents 2-8 hr of mis-scope; the 30 sec scan rerun prevents the 4th `_safe_float`; the 60 sec phase-end verification prevents the green-now-red-on-merge surprise.
- **Methodology is non-negotiable.** Future agents follow the refined workflow end-to-end — no skipping the absorption scan, no skipping the verification checklist.
- **Tool quality before tool quantity** — better to have 8 well-calibrated scans than 12 noisy ones. New detectors land only after first-run FP rate is ≤25%.

---

## 3. Done / In Progress / Deferred — current state

### ✅ Done (this session)

**Methodology refinement** (`KB § PATTERNS/project-execution.md § 0`):
- Added **PRE-PHASE** stage between SCAFFOLD and EXECUTE — runs Phase 0 audit + targeted absorption scans before any code lands.
- Added **mid-phase scan checkpoint** rule inside EXECUTE (every 5-10 file edits, re-run relevant scan).
- Added **PHASE-END VERIFICATION CHECKLIST** (5 items: tests + keeper + scan rerun + KB sync + §6↔§11 self-check).
- Added **PROJECT-END VERIFICATION CHECKLIST** (8 items: builds + backend tests + MCP tests + keeper + sync verifiers + final scan sweep + three-way sync + summary).
- Codified **code-quality bias** as a top-level note.

**Tool refinement** (`mcp/noctusai/tools/recurrence.py`):
- 8 scans total (was 1 at session start). The 6 new ones:
  1. `scan_cross_product_helpers` — function/class names across products (HIGH-signal — first-run 14/14 real high-severity)
  2. `scan_service_line_recurrence` — verbatim service/router lines (≥60 chars + has `(`) across products
  3. `scan_block_patterns` — AST-walks try/except, normalizes identifiers, hashes shape; 79% real-rate on 28 high-severity findings
  4. `scan_within_product_helpers` — helpers duplicated within one product (closes "cross-product-only" gap)
  5. `scan_pydantic_model_shapes` — BaseModel field-set recurrence
  6. `scan_test_fixture_recurrence` — fixtures across product test trees with stricter blacklist
  7. `scan_migration_patterns` — 5 SQL probes (RLS subquery, FK index, search_path, audit trigger, updated_at trigger)
- All 8 wired into both CLI (`--scan-helpers`, `--scan-service-lines`, `--scan-blocks`, `--scan-within-product`, `--scan-pydantic`, `--scan-test-fixtures`, `--scan-migrations`) and MCP server.
- 35/35 recurrence tests pass + 116/116 broader MCP test suite pass.

**Calibration** (documented in `tools/recurrence.py` end-of-file):
- FP rate on `scan_block_patterns` high-severity: **79% real, 21% shape-similarity FP** (generic `db.table` patterns).
- Token-savings benchmark: **93%** for cross-product helper recurrence, **99%** for project status digest, ~slight cost for trivial symbol grep (JSON wrapping).
- Tool maturity: **SOLID** for discovery / audit / sweep workflows.

**Documentation sync (three-way verified):**
- KB: `§ PATTERNS/project-execution.md § 0` refined; `§ 06-AGENTS.md § Cross-cutting utilities` lists 8 scans + 5 second-wave gap decisions + FP rate + token-savings benchmark.
- CLAUDE.md: refined "execution workflow" rule pointer; existing "absorption-search standing duty" rule.
- Memory: `feedback_execution_workflow.md` updated with pre-phase scan + verification checklists; `feedback_absorption_search_standing_duty.md` reflects 8 scans (was 3 at first authoring).
- 43/43 memory files in MEMORY.md index, all KB-anchored, all CLAUDE.md keyword-matched.

**Quality gates:**
- KB sync ✓
- Three-way sync ✓ (43/43)
- 116/116 MCP tests pass
- Keeper score 100/100, 0 critical, 0 high, 272 warning (all queued monkeypatch debt)

### ⏳ In Progress

- ~~**Therapy `test_messaging_router.py` cleanup** (40 sites, biggest tail)~~ — **✅ Phase 2 closed 2026-04-29: zero self-monkeypatches in target file. 60 → 32 therapy-wide, 260 → 232 platform-wide.** Next-up is Phase 3 (other therapy files — `test_invitations_router.py`, `test_e2e_flows.py`, service tails — 32 sites) OR jump to Phase 4 (first-batch absorptions, including the `assert_error_contains` recurrence trip surfaced during Phase 2).

### 🅿️ Deferred (queued)

- **Apply refined workflow + absorption-scan sextet** to remaining cleanup queue:
  - `therapy-tests-no-self-patch` Phases 0-6 (72 sites)
  - core test cleanup (44 sites)
  - ERP test cleanup (102 sites)
  - mailing / PF / daily-life small tails
- **Seed-lib shim cleanup** ✅ (closed 2026-04-30, `projects/seed-lib-shim-cleanup/` deleted) — Step 3 of the 3-step layered-namespace migration. 18 shims deleted (15 `.py` + 3 folder shims), 96 product files + 11 mcp files + seed-lib internals rewritten via sed. Layer-direction violation surfaced + fixed: `roles.py` moved from `api/` to `primitives/` (it's pure constants). 5,086 tests pass after the sweep.
- **Time-handling absorption** ✅ (closed 2026-04-30, `projects/timeutil-absorption/` deleted) — Triggered by a date-rollover bug caught at UTC 00:47 on 2026-05-01. Landed `noctusai_lib.primitives.timeutil` with `now_utc` / `today_utc` / `current_month_ref` / `current_day_ref` + `frozen_time(dt)` context manager. 12 production sites + 4 test files migrated to use the canonical helpers; 14 `datetime.utcnow()` deprecations swept. The bug class (test mixing `date.today()` with `datetime.now(timezone.utc)` for the same period) is now structurally impossible to reintroduce in code that uses the helpers. 5,111 tests pass after the sweep.
- **First-batch absorptions** identified by the scans (each is its own follow-up project):
  - `noctusai_lib.domain.digest` ✅ (closed 2026-04-30, `projects/digest-pipeline-absorption/` deleted) — Wave C absorbed the narrative-pipeline shape (`narrative` + `render_with_narrative` + `build_and_send`). 4 adopters: Core audit / PF monthly / Daily Life weekly / Mailing campaign. ERP metas digest accepted-with-rationale (no LLM, structural-data outlier). 232 seed-lib tests + 2,602 product tests in the touched products green; full platform 5,099 tests pass.
  - `noctusai_lib.domain.sql_templates` ✅ (closed 2026-05-01, `projects/sql-templates-absorption/` deleted) — Wave A landed authoring-time helpers (`set_search_path`, `updated_at_function`, `updated_at_trigger`, `rls_subquery_policy`) for the 88+21+14 recurring SQL DDL shapes. **Scope shift caught at Phase 0**: the original framing assumed Python-style code duplication, but per-schema DDL is correct-shape recurrence (schema-qualified functions can't be shared). Existing migration files stay verbatim (replay-log rule); helpers are authoring-time for fresh migrations + scaffold tool. 19 tests cover exact output shapes. KB § PATTERNS/database-rls.md + § 04-SHARED-LIBRARY.md updated. Follow-up `mcp-scaffold-sql-templates-integration` filed for wiring into `mcp/noctusai/tools/scaffold.py`.
  - `noctusai_lib.primitives.parsing.{safe_float, safe_json_loads, safe_money_format, parse_iso_datetime}` — already absorbed pre-Step 3; per-product copies retiring opportunistically as files are touched.
  - `noctusai_lib.testing.{db_with_grants, _fake_build, _fake_fetch}` — absorbs test scaffolding
  - `@noctusai/lib/hooks/useMetas` (frontend) — absorbs the Metas gamification CRUD hook quartet
- **Calibration revisit (1-2 weeks out)** — recompute FP rate after real absorption work has shipped; update `tools/recurrence.py` end-of-file calibration block.
- **Second-wave gaps explicitly deferred** (low ROI):
  - Cross-language pattern recurrence (Python ↔ TS pairs)
  - Decorator usage patterns (`@router.get` shapes)

---

## 6. Phase plan

### Phase 0 — Methodology + tooling shipped ✅ (2026-04-28)
- [x] Refine `KB § PATTERNS/project-execution.md § 0` with absorption-scan integration + 2 verification checklists
- [x] Update `KB § 06-AGENTS.md § Cross-cutting utilities` with 8 scans + calibration + token-savings + second-wave decisions
- [x] Update CLAUDE.md "execution workflow" rule
- [x] Update memory `feedback_execution_workflow.md` (refinement) + verify `feedback_absorption_search_standing_duty.md` is current
- [x] Verify three-way sync clean (43/43 memory files)

**Improvements:** none identified — the refinement was a focused doc + rule update, no surprises.

### Phase 1 — 8 MCP scans + tests + wiring ✅ (2026-04-28)
- [x] Build `scan_cross_product_helpers` + tests + CLI/server wire
- [x] Build `scan_service_line_recurrence` + tests + CLI/server wire
- [x] Build `scan_block_patterns` (AST normalization) + tests + CLI/server wire
- [x] Build `scan_within_product_helpers` + tests + CLI/server wire
- [x] Build `scan_pydantic_model_shapes` + tests + CLI/server wire
- [x] Build `scan_test_fixture_recurrence` + tests + CLI/server wire
- [x] Build `scan_migration_patterns` (5 SQL probes) + tests + CLI/server wire
- [x] Manual FP review of 28 `scan_block_patterns` high-severity findings — 79% real
- [x] Token-savings benchmark across 4 representative workflows
- [x] Document everything in `tools/recurrence.py` end-of-file calibration block

**Improvements:**
- The `_HELPER_NAME_BLACKLIST` initially missed Portuguese router handler names (`criar`, `atualizar`, `excluir`, `listar`, `obter`); extended after first within-product scan surfaced noise. Still possible more languages will need entries (the blacklist is English + Portuguese only today).
- The `scan_block_patterns` FP rate (21%) comes from generic `db.table` accesses — could improve by tracking which dotted-paths are "boundary-shaped" (already a list in `compliance.py::_BOUNDARY_ACCESSOR_NAMES`) and treating them as part of the signature normalization. Filed as a Phase 4 follow-up.
- `scan_pydantic_model_shapes` returned 1 finding — likely Pydantic schemas are mostly product-bound by design; the scan is low-yield but cheap. Keep, recheck after a few absorption rounds.

### Phase 2 — Apply workflow to therapy `test_messaging_router.py` ✅ (executed 2026-04-29)
- [x] Phase 0 audit per refined workflow: read `messaging.py` + `messaging_service.py`, ran absorption scans on messaging surface (`send_message` cross-product N=2 different domains, accept-with-rationale).
- [x] Pattern decision: **Pattern 3 (seed real data)**, NOT Pattern 1 (DI). Service helpers are DB-bound (query `conversation_participants`, check blocks, insert messages); patching them neuters authorization logic.
- [x] Proof-of-concept: refactored `test_start_conversation_with_self_fails` end-to-end (2026-04-28). Real validation guard runs; assertion uses platform's `{"error": {"message": ...}}` exception-handler shape (caught during refactor — recurrence trigger for an `assert_error_message_contains` helper if it lands at N=2+).
- [x] **Sites 2-40 cleared (2026-04-29): all 28 remaining `@patch("app.routers.messaging.messaging_service.<helper>", ...)` decorators removed.** TestStartConversation (4 sites — user-to-user / user-to-clinic / user-to-support / duplicate use seeded `conversation_participants` to take the find-existing branch since `MockSupabaseClient` doesn't reflect inserts back into SELECT state). TestGetMessages (3 sites: success seeds participants + messages; non-participant uses empty seed because the mock doesn't apply filter args — empty `[]` is the correct shape for "not a participant"; pagination same as success). TestMarkAsRead (1). TestDeleteMessage (3: sender / non-sender / not-found). TestReportMessage (1 — message lookup seed). TestArchiveConversation (2). TestMuteConversation (2). TestBlockUser (3 — `block_user_hides_conversations` now reads `inserted_payloads` to verify the real side-effect, not `mock.assert_called_once()`). TestUnblockUser (3). TestUnreadCount (2). 2 new seed helpers added: `_seed_conversation_for_clinic`, `_seed_conversation_for_support`.
- [x] Unused imports cleaned: `from unittest.mock import patch, AsyncMock` line removed.
- [x] **Phase-end verification:** 48/48 tests pass; `check_no_self_monkeypatch` for the file = 0 (was 28); therapy-wide self-patch hits 60 → 32; platform-wide 260 → 232.

**Improvements (live capture during Phase 2 execution):**
- The current patched tests assert only `mock_find.assert_called_once()` — they verify the helper was CALLED, not what it DOES. Pattern 3 conversion strengthens every test by exercising real authorization/block-check/participant-validation logic. The patched tests weren't testing anything meaningful — this validates the rule's intent.
- Platform exception-handler shape (`{"error": {"code": ..., "message": ...}}`) differs from FastAPI default (`{"detail": ...}`). Test assertions need `body.get("error", {}).get("message", "")`. Will recur 40+ times across this file — Phase-end will file `assert_error_message_contains(resp, expected)` helper if recurrence rule trips. **2026-04-29 outcome:** the helper was added at first refactor (`_assert_error_contains`); it landed at N≥4 within this file alone. **Recurrence trip — N=3+: MUST formalize.** Filed as Phase-4 absorption candidate `noctusai_lib.testing.assert_error_contains(resp, expected_substring)`. Defer to Phase 4 (first-batch absorptions); the file-local helper stays until then.
- **`MockSupabaseClient` doesn't apply filter args** — `.eq("col", val).execute()` returns the full seeded data regardless of `val`. Several tests had to flip from "seed wrong row to deny access" → "seed empty list" because the mock doesn't filter. Documented inline in `test_get_messages_non_participant_denied`. Existing memory `feedback_no_silent_errors.md` covers the broader principle of explicit-shape testing; future agents learning the mock should read the contract docstrings in `seed/backend/lib/noctusai_lib/testing/mocks.py`.
- **Pattern 3 + auto-id new-create-flow gap:** when a router does INSERT-then-query (e.g. `find_or_create_conversation` creates a conv then `send_message` queries its participants), the mock's INSERT auto-id doesn't appear in subsequent SELECTs because the mock isn't stateful. The pragmatic workaround (used in TestStartConversation) is to seed the find-existing branch end-state. This is a real limitation surfaced by Pattern 3 — an alternative future shape would be a stateful mock that reflects inserts back. Filed as a watch-item; not blocking.

### Phase 3 — Apply workflow to remaining therapy files 🅿️ DEFERRED
- [ ] `test_invitations_router.py`, `test_e2e_flows.py`, service tails (32 sites total).
- [ ] Project-end verification checklist when therapy reaches 0.
- [ ] Severity ratchet: detector severity for therapy product flips to `high`.

### Phase 4 — First-batch absorptions (the real DRY-into-seed work) 🅿️ DEFERRED
- [ ] `noctusai_lib.digest` — 5-product `_render_bodies`/`_generate_narrative`/`_aggregate`/`_fetch_window`/`_empty_output` consolidation. **Highest leverage** — single biggest absorption identified.
- [ ] `noctusai_lib.parsing` — `_safe_float`, `_safe_json_loads`, `_fmt_brl` / `_format_money`, `parse_iso_datetime` (the 22-site pattern).
- [ ] `noctusai_lib.sql` templates — `SET search_path` prelude + `audit_trigger(table)` + `updated_at_trigger(table)` helpers (176+42 occurrences absorbed).
- [ ] `noctusai_lib.testing` — `_db_with_grants` + `_fake_build` + `_fake_fetch` + Stateful mock builders.
- [ ] `@noctusai/lib/hooks/useMetas` quartet — Metas gamification frontend.
- [ ] Each is a SEPARATE follow-up project filed when picked up.

### Phase 5 — Calibration revisit + tool maturity check 🅿️ DEFERRED (1-2 weeks out)
- [ ] After Phase 4 absorptions ship, re-run all 8 scans.
- [ ] Recompute FP rate per scan.
- [ ] Update `tools/recurrence.py` end-of-file calibration block.
- [ ] Decide: any second-wave gaps (cross-language, decorators) worth building now? Re-evaluate based on what slipped through the first batch.

---

## 10. How to use this project

```bash
# Refresh state any time:
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --status                          # cross-project state
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --validate                        # keeper score
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --check-three-way-sync            # KB↔CLAUDE.md↔memory parity

# Absorption-search sextet (run before/after each phase per the refined workflow):
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --scan-helpers
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --scan-service-lines
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --scan-blocks
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --scan-within-product
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --scan-pydantic
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --scan-test-fixtures
mcp/noctusai/.venv/bin/python mcp/noctusai/cli.py --scan-migrations

# Verify the refined workflow's checklists pass:
bash scripts/verify-kb-sync.sh                                                       # KB sync
mcp/noctusai/.venv/bin/python -m pytest mcp/noctusai/tests/ -q                       # MCP toolkit tests

# Read the canonical workflow doc:
cat KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md | head -110                # § 0 The execution workflow
```

---

## 11. Change log

| Date | Change | Who |
|---|---|---|
| 2026-04-28 | **Project scaffolded.** Consolidates the late-April 2026 methodology + tooling refinements: refined `§ 0 The execution workflow` with PRE-PHASE absorption scan, mid-phase scan checkpoints, PHASE-END VERIFICATION (5 items), PROJECT-END VERIFICATION (8 items); built 6 new MCP scans (8 total in the absorption-search sextet); manual FP review of 28 high-severity block findings (79% real); 4-workflow token-savings benchmark (93-99% on discovery workflows). Phase 0 + Phase 1 ✅; Phases 2-5 (apply across the cleanup queue + measure ROI + revisit calibration) deferred for sequential execution. Quality gates: KB sync ✓, three-way sync ✓ (43/43 memory files), 116/116 MCP tests pass, keeper 100/100 / 0 critical / 0 high / 272 warning (queued monkeypatch debt). | Claude Opus 4.7 |
| 2026-04-28 | **Phase 2 STARTED — refined workflow's first end-to-end use.** Phase 0 audit on therapy `test_messaging_router.py` (40 sites) ✅: pattern decision = Pattern 3 (seed real data), not Pattern 1 (DI) — `messaging_service` helpers are DB-bound, not external-boundary. PRE-PHASE absorption scans run on messaging surface; `send_message` N=2 cross-product (ERP=WAHA, therapy=in-app) flagged accept-with-rationale (different domains). Proof-of-concept refactor: 1 site (`test_start_conversation_with_self_fails`) converted from `@patch(...)` to no-patch, real validation guard exercised end-to-end. **Discovered platform exception-handler shape** (`{"error": {"message": ...}}` vs FastAPI default `{"detail": ...}`) — will need a helper if recurrence trips at N=2+. Test passes; full file 48/48 green; keeper count 40→39 in target file, 272→271 platform-wide. **Refined workflow validated: PRE-PHASE absorption scan + Phase 0 audit + Pattern decision before code edits** is the right shape — caught the platform error-shape detail before running through 40 sites blind. Sites 2-40 (39 remaining) deferred for sequential execution per phase-by-phase cadence. | Claude Opus 4.7 |
| 2026-04-28 | **Phase 2 PROGRESS — 11 more sites cleared (cumulative 12/40, 28 remaining).** Added `_seed_conversation_for_user(...)`, `_seed_block(...)`, `_assert_error_contains(...)` test-helpers; converted `test_start_conversation_with_blocked_user_fails`, all 7 `TestListConversations.*`, and 2 `TestSendMessage` validation-failure paths. **Real bug surfaced by Pattern 3:** `test_send_text_message` patched assertion (`data["content"] == "Olá, como você está?"`) didn't match the request content (`"Olá, tudo bem?"`) — patch was hiding a content-mismatch the test should have caught. Filed as deferred (blocked on mock-infra). **MockSupabaseClient mock-infra gap caught:** `insert(...).execute()` doesn't surface inserted row in `result.data`, breaking happy-path Pattern 3 conversions. **File follow-up: `mcp-mock-supabase-insert-returns-row`** — would unlock all happy-path INSERT-shaped tests across the platform (likely N=10+ across products). **Calibration revisit run** — all 8 absorption scans show **zero net change** vs baselines (216/75/52/241/12/1/88/3 totals unchanged), confirming the 11-site refactor introduced no new recurrence. **Recurrence rule trip in this file alone:** `_assert_error_contains` used 4× already; lock-in candidate for `noctusai_lib.testing.assert_error_contains(resp, expected)`. Full file 48/48 green; platform monkeypatch 272→261, score 100/100, KB sync ✓, three-way sync ✓ (43/43). | Claude Opus 4.7 |
| 2026-04-29 | **Mock-infra fix landed — `MockRequestBuilder.insert(...).execute()` returns inserted rows with auto-id, matching real Supabase.** Refined workflow's full loop applied: Phase 0 audit (read mocks.py + identified MockQueryBuilder._data flow) → PRE-PHASE absorption scan (no relevant N=2+) → EXECUTE → phase-end verification. **Implementation:** new code path in `MockRequestBuilder.insert(...)` builds response_rows with auto-generated `id` (`mock-<table>-<n>`) when not provided. **Back-compat shim** preserves the legacy "seeded data drives insert response" quirk (any `set_table_data(name, [...])` call OR constructor-seeded `MockSupabaseClient(data=[...])` flips `_explicitly_seeded` and falls back to legacy behavior). **Side-effect cleanup:** core's redundant `MockRequestBuilder`/`MockQueryBuilder` overrides (a less-correct half-fix of the same problem from years ago) removed; core now inherits the canonical seed-lib mock. 3 explicit insert-failure tests migrated to `set_sequential_responses(...)` (the canonical pattern for queueing specific responses). **Side-effect absorption win:** `scan_test_fixture_recurrence` high-severity dropped 17→14 (removed 3 cross-product MockRequestBuilder/MockQueryBuilder duplicates). **Verification:** core 457/457, erp 1798/1798, therapy 1135/1135, mailing 201/201, PF 576/576, daily-life 233/233, seed-lib 187/187 — **4,587 tests green** platform-wide. KB sync ✓, three-way sync ✓ (43/43), keeper 100/100 / 0 crit / 0 high / 260 warning. **Phase 2 next-up:** the previously-deferred `test_send_text_message` is now Pattern 3-converted (real `send_message` runs the full insert path); 27 sites remain in `test_messaging_router.py`, 32 sites in other therapy files. | Claude Opus 4.7 |
| 2026-04-29 | **Phase 2 ✅ COMPLETE — therapy `test_messaging_router.py` reaches zero self-monkeypatches.** All 28 remaining `@patch("app.routers.messaging.messaging_service.<helper>", ...)` decorators removed in this session. **Platform-wide self-monkeypatch count 260 → 232; therapy product 60 → 32; target file 28 → 0.** Two new seed helpers landed (`_seed_conversation_for_clinic`, `_seed_conversation_for_support`) to cover the full participant-shape range. **Three discoveries during execution:** (a) `MockSupabaseClient` does NOT apply filter args — `.eq("col", val).execute()` returns the whole seeded list regardless of `val`. Several denied-access tests had to flip from "seed wrong row" to "seed empty" because filtering would not reject the wrong row. Documented inline in `test_get_messages_non_participant_denied`. (b) Pattern 3 + auto-id shows a **stateful-mock gap**: `find_or_create_conversation` INSERTs a conv, then `send_message` SELECTs participants for that conv — but the mock does not reflect inserts back into SELECT state. Workaround: seed the find-existing branch end-state. Filed as watch-item, not blocking. (c) `_assert_error_contains` recurrence — used N≥4 within this file alone. **Recurrence rule trip — N=3+: MUST formalize.** Filed as Phase-4 absorption candidate `noctusai_lib.testing.assert_error_contains(resp, expected_substring)`. **Verification:** therapy 1135/1135, full file 48/48; `check_no_self_monkeypatch` for the file = 0. **Auxiliary fixes shipped same session** (split lineage from this rollout but adjacent): (a) Removed the back-compat shim from `MockRequestBuilder.insert(...)` per user "no dead code on my codebase" directive — `_explicitly_seeded` flag deleted, legacy seeded-data-drives-insert quirk gone; insert always returns inserted rows with auto-id. 7 happy-path/insert-failure tests migrated to `set_sequential_responses(...)` (canonical pattern). All 4,431 product backend tests green after migration. (b) `platform-logging-standardization` Phase 6 + 7 closed (folder deleted): new `KB § PATTERNS/logging.md`, new `check_detector_has_regression_test` meta-detector (severity `high`, enforces every `check_*` ships with a colocated test), 3 regression tests. CLAUDE.md + INDEX.md + 06-AGENTS.md + testing.md all amended. Memory entry filed. (c) MCP venv `supabase` now pinned `>=2.9.1,<2.10` in seed-lib `pyproject.toml` (matched product exact-pin; was 2.29.0 dropping `ClientOptions.storage`); MCP requirements gain explicit `pytest`/`pytest-asyncio`/`fakeredis` test deps. **MCP suite 399/399 pass.** **Phase 2 closed; next-up:** Phase 3 (other therapy test files — `test_invitations_router.py`, `test_e2e_flows.py`, service tails — 32 sites) OR jump to Phase 4 (first-batch absorptions including the `assert_error_contains` recurrence trip + the formal stateful-mock evaluation). | Claude Opus 4.7 |
