# therapy-platform-drift-sweep — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-10
- **Last updated:** 2026-05-10
- **Status:** 🚨 **READY FOR EXECUTION — PRODUCTION-CORRECTNESS RISK.** Filed under user signal "create projects for deferrals/parks that happen along the way." Engineer GG's therapy P4 (commit `a56a39e`) found N=12 migration drift cases — code references tables that don't exist in live therapy.* schema. 1 fixed inline (commission_overrides); 11 remain. MockSupabase WARN+skip masked them for 7+ days. Real Supabase = "relation does not exist" 500 OR silent-no-op.
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

### Phase 0 — Audit + disambiguation

- [ ] Re-grep each of the 11 drift cases — confirm Engineer GG's count + line numbers.
- [ ] Per `sessions` callsite: read body to determine `appointments` vs `session_records` mapping.
- [ ] Per `ai_prompt_*`: grep for consumers; if zero, mark for deletion.

### Phase 1 — Mechanical renames

- [ ] libcst codemod rename for the 9 pure cases (anamneses, therapist_reviews, goals, reminder_configs, clinic_therapist_configs, settings_history, therapeutic_journal, financial_transactions, clinic_therapist_configs).
- [ ] `sessions` disambiguation per callsite (2 sites in review_service).
- [ ] AST-first (libcst); NEVER sed/regex.

### Phase 2 — ai_prompt_* decision + close

- [ ] Product-owner decision OR delete dead code if no consumer.
- [ ] Run `pytest products/therapy-platform/backend/ -q` with `strict_unknown_tables=True` in conftest — should be green (or surface any remaining drift).
- [ ] Keeper review — 0 issues.
- [ ] Tick + Improvements + §11 + archive.

## 7. Open questions

- Q1: `ai_prompt_settings` + `ai_prompt_history` — build feature (new migration + tables) or remove dead code? **Default rec: REMOVE** — zero evidence of consumer; routers/settings.py:82-125 looks like scaffold that never shipped.

## 8. Dependencies & blockers

- None.

## 9. Success criteria

- [ ] Zero code references to drift names.
- [ ] `strict_unknown_tables=True` test conftest passes.
- [ ] therapy-platform pytest + keeper green.

## 10. How to use this plan

Single-engineer dispatch via worktree. Mechanical refactor with one product-owner decision.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-10 | **Filed under user signal "create projects for deferrals/parks that happen along the way."** Engineer GG's therapy P4 close (commit `a56a39e`) found N=12 migration drift. 1 fixed inline; 11 remain. **PRODUCTION-CORRECTNESS RISK** — MockSupabase WARN+skip masked these; real Supabase will fail. Mechanical refactor + product-owner decision on ai_prompt_*. | claude-opus-4-7 |

## 12. No-leftovers constraint

- Folder archives via `noctus.dev.archive` on close.
