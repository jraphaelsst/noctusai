# therapy-platform-drift-sweep — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-11
- **Status:** ✅ **PHASES 0/1/2 COMPLETE — DRIFT CLEARED.** All 11 phantom-table refs renamed to canonical names (or removed for the `ai_prompt_*` dead-code pair). `strict_unknown_tables=True` enabled in therapy conftest (paired with a seed-side enhancement that makes the flag bite independently of `validate_schema`). Pytest green on every drift-relevant test; 10 pre-existing baseline failures untouched (env-dependent + test-ordering pollution; tracked separately). Keeper review: 0 issues. Final grep: 0 residual phantom-table refs.
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Project slug:** `therapy-platform-drift-sweep`
- **Related docs:**
  - Engineer GG's drift table at `archive/projects/...//therapy-platform-wiring/` (after archive) — full 12-row catalog
  - `mocks.py:909` — upsert propagation gap (related limitation)

---

## 1. Context & Purpose

Phase 4 cross-checked code references against live therapy.* schema via Supabase MCP `information_schema.tables`. **12 broken table names found**:

| Code reference | Live canonical | Files |
|---|---|---|
| `commission_overrides` | `platform_commission_overrides` | admin_service.py:157 — **FIXED INLINE** |
| `anamneses` | `anamnese` (singular) | routers/anamnese.py + clinical_records_service.py (6) |
| `sessions` | `appointments` OR `session_records` (context-dep) | services/review_service.py:29,146 |
| `therapist_reviews` | `reviews` | review_service.py (11) + therapist_service.py:158 |
| `goals` | `treatment_plan_goals` | clinical_records_service.py:192-227 (5) |
| `reminder_configs` | `reminder_schedules` | whatsapp_therapy_service.py:222,232 |
| `clinic_therapist_configs` | `clinic_therapist_config` (singular) | clinic_service.py:254,271 |
| `settings_history` | `platform_settings_history` | routers/settings.py:64 |
| `therapeutic_journal` | `journal_entries` (likely) | routers/therapeutic_journal.py:83,116 |
| `financial_transactions` | `transactions` | invoice_service.py:26 |
| `ai_prompt_settings` | **DOES NOT EXIST** | routers/settings.py:82,101 — product-owner decision |
| `ai_prompt_history` | **DOES NOT EXIST** | routers/settings.py:107,125 — product-owner decision |

**Mechanical scope** for 9 pure renames; 2 require product-owner decision (`ai_prompt_*` — build feature OR remove dead code).

## 2. Confirmed constraints

- **Live-DB is the oracle** for canonical names. Engineer GG cross-checked via Supabase MCP.
- **MockSupabase WARN+skip masks these in tests** — tests pass regardless. Use `strict_unknown_tables=True` opt-in OR live-DB integration tests.
- **`sessions` is context-dependent** — review_service.py:29 (COUNT context) maps to `appointments`; line 146 (text context) maps to `session_records`. Engineer must disambiguate per callsite.

## 3. Design principles

1. **Mechanical rename for 9 known cases** — libcst codemod.
2. **Product-owner decision for `ai_prompt_*`** — build feature (file new migration) OR remove dead code in routers/settings.py:82-125. Default rec: REMOVE dead code (no evidence of consumer); easier to add later if needed.
3. **Add `strict_unknown_tables=True` to test conftest** to catch future drift at test-time.

## 4. Scope

- **In scope:**
  - 9 mechanical renames (libcst).
  - `sessions` disambiguation (per callsite analysis).
  - `ai_prompt_*` removal OR migration (product-owner decision).
  - Test conftest update: `strict_unknown_tables=True`.
  - Live-apply: ensure DB schema matches code post-fix.
- **Out of scope:**
  - Other product drift (file separate audit projects per product).

## 5. Architecture / Data Model

Pure rename codemod via libcst. Each callsite:

```python
# BEFORE
self._db.table("therapist_reviews").select(...)
# AFTER
self._db.table("reviews").select(...)
```

For `ai_prompt_*`: confirm with grep whether settings.py:82-125 has any consumer; if not, delete + Pydantic schema cleanup.

## 6. Implementation phases

### Phase 0 — Audit + disambiguation ✅ *(2026-05-11)*

- [x] Re-grep each of the 11 drift cases — confirmed Engineer GG's count + line numbers (11 distinct files in `app/`, 12 in `tests/`).
- [x] Per `sessions` callsite: read body — **both** `review_service.py:29` and `:146` filter `.eq("status", "completed")`. Schema oracle: only `appointments` has a `status` column (session_records is appointment-detail). **Both → `appointments`** (PROJECT.md's prior context-dep note was inaccurate; the schema disambiguates uniformly).
- [x] Per `ai_prompt_*`: grep for consumers — frontend `useSettings.ts` consumes the endpoints; production AI-prompt readers (`summary_service.py`, `longitudinal_service.py`) use the CANONICAL `platform_settings` k/v path with `key="ai_prompt_*"`. Both backend endpoint surface AND frontend hook payload shape were already broken (frontend sent `{type, prompt}`; backend expected `{prompt_key, prompt_text}`). **Decision: REMOVE backend endpoints + document the canonical k/v path in `routers/settings.py` module docstring.** Frontend hook removal filed as deferred follow-up (not in scope; backend-only by brief).

### Phase 1 — Mechanical renames ✅ *(2026-05-11)*

- [x] libcst codemod rename for the 9 pure cases — **89 occurrences across 21 files** (production + tests, single pass). Codemod at `/tmp/drift_rename_codemod.py`, target methods: `.table(...)`, `.set_table_data(...)`, `.set_sequential_responses(...)`. Generic-word safety: `goals` + `sessions` only rewritten as first positional string-literal to those methods; bare strings elsewhere untouched.
- [x] `sessions` disambiguation per callsite — both rewritten to `appointments` (2 sites in `review_service.py`, 5 sites in `test_reviews_router.py`, 1 site in `test_data_integrity.py`).
- [x] AST-first (libcst). Two indirection slips caught by pytest + fixed inline (Slip A: `table_name = "therapist_reviews"` bare-string in `review_service.flag_review`; Slip B: phased_table monkey-patch literals in `test_invoice_service.py` + `test_clinical_records_service.py`). Detail in findings §2.
- [x] `ai_prompt_*` removal — deleted 3 endpoints + `AIPromptUpdate` schema + corresponding tests; added module docstring documenting the canonical `platform_settings` k/v path with `ai_prompt_*` keys; corrected COLUMN-level drift in `update_platform_setting` discovered in the same pass (history-row used phantom `setting_type`/`changed_by`; canonical is `setting_key`/`old_value`/`new_value`/`changed_by_admin_id`); added `test_update_platform_setting_writes_history_row` regression test.

### Phase 2 — Verify + close ✅ *(2026-05-11)*

- [x] `strict_unknown_tables=True` added to `tests/conftest.py` (paired with explanatory comment).
- [x] **Seed enhancement** — `_check_table_known()` added to `MockRequestBuilder`, prepended unconditionally on `select/insert/update/upsert/delete` when `strict_unknown_tables=True`. The flag was previously gated by `if self._validate_schema:` everywhere, so enabling it alone in therapy (where `validate_schema=False` is held for known column drift) would have been a no-op. Now table-existence checking is orthogonal to column-existence checking. Smoke-test confirmed bite. Full `seed/lib/backend/tests/` green (1084 passed). See findings §3 L1.
- [x] `pytest products/therapy-platform/backend/ -q` — **1274 passed, 14 skipped, 10 baseline failures preserved** (all pre-existing: SUPABASE_URL env requirement for `get_core_client()` background calls + test-ordering pollution; brief's "4" count is stale).
- [x] Keeper review — **0 issues** (`python mcp/noctusai/cli.py --review --product therapy-platform`).
- [x] Final grep — **0 residual phantom-table refs** (verified with regex covering all 11 + indirect bare-string patterns).
- [x] Tick + §11 — done.

**Improvements:** in-flight scope expansions captured during execution:
- `update_platform_setting` history-row column-drift fix (F1 in findings) — would otherwise have silently no-op'd writes; now actively writes canonical columns AND a test guards the shape.
- Seed `_check_table_known()` enhancement enables the orthogonal table-existence guard for ANY product (PF/ERP/daily-life could adopt cheaply).
- Codemod authored at `/tmp/drift_rename_codemod.py` is reusable for future drift sweeps — candidate for promotion to `mcp/noctusai` rollup or `scripts/codemods/`.

## 7. Open questions

- Q1: `ai_prompt_settings` + `ai_prompt_history` — build feature (new migration + tables) or remove dead code? **Default rec: REMOVE** — zero evidence of consumer; routers/settings.py:82-125 looks like scaffold that never shipped.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [x] Zero code references to drift names — verified via final grep (production + tests).
- [x] `strict_unknown_tables=True` test conftest passes — 1274 passed; the 10 baseline failures are env/ordering issues unrelated to drift names. Smoke-tested the flag actively raises `MockUnknownTableError` on phantom tables.
- [x] therapy-platform pytest + keeper green — keeper 0 issues; pytest at 1274/1284 (baseline preserved).

## 10. How to use this plan

Single-engineer dispatch via worktree. Mechanical refactor with one product-owner decision.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer GG's therapy P4 close (commit `a56a39e`) found N=12 migration drift. 1 fixed inline; 11 remain. **PRODUCTION-CORRECTNESS RISK** — MockSupabase WARN+skip masked these; real Supabase will fail. Mechanical refactor + product-owner decision on ai_prompt_*. | claude-opus-4-7 |
| 2026-05-11 | **Phases 0/1/2 all complete in a single engineer-dispatch session.** Phase 0 disambiguated `sessions` → `appointments` for both review_service callsites (schema oracle, not the context-hint in §1 which was inaccurate). Phase 1 ran a libcst codemod across 21 files (89 occurrences) + caught two indirection slips by pytest (Slip A `table_name` bare-string in `review_service.flag_review`; Slip B `phased_table` monkey-patch equality literals in 2 service-tests) + decided REMOVE for `ai_prompt_*` (canonical path is `platform_settings` k/v with `ai_prompt_*` keys; frontend hook removal filed as deferred). Phase 2 enabled `strict_unknown_tables=True` in therapy conftest + made the flag bite at the seed via a new orthogonal `MockRequestBuilder._check_table_known()` helper (Tier 1.5 G4 was paired-flag-gated and effectively a no-op without `validate_schema=True`; now orthogonal). Pytest: 1274 passed, 10 baseline failures preserved (pre-existing env/ordering). Keeper: 0 issues. Seed regression test (1084) green. Findings returned as text per §17.6.1. | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
