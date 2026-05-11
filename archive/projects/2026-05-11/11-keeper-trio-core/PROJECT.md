# keeper-trio-core — Project Document

> **This is a living document, not a rigid checklist.**

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** ⏳ **EXECUTING — Wave 1 child A of `projects/keeper-trio-platform-triage/`.**
- **Owner / stakeholders:** rapha (joaoraphaelsst@gmail.com)
- **Related docs:** parent at `projects/keeper-trio-platform-triage/PROJECT.md` + `phase-0-triage.md`
- **Project slug:** `keeper-trio-core`

---

## 1. Context & Purpose

Engineer RR's Phase 0 classification (`phase-0-triage.md`) of core's 151 keeper-trio findings:

- **1 REAL_BUG** — `backend/app/routers/billing.py:284` references `billing_events` table that has no `CREATE TABLE` anywhere; Stripe webhook side-effect for idempotency + audit silently fails in production (MockSupabase WARN+skip masks it in tests).
- **149 DEFENSE_IN_DEPTH** — admin client calls against 13 tables that have `<table>_service` policies (the FOR ALL TO service_role shape) but lack the literal `service_role_bypass` policy name that the keeper detector + therapy canonical reference shape uses.
- **1 FALSE_POSITIVE** — cleared by XX (Wave 0 commit `40269c3` — `.schema(X).table(Y)` chain support).

Close all real + defense-in-depth findings via two migrations consuming WW's new `noctusai_lib.sql.service_role_bypass(table, schema)` helper (Wave 0 commit `b76c43f`).

---

## 2. Confirmed constraints

- **`public` schema, not `core`** — core's migrations create tables unqualified (defaults to `public`); admin client at `dependencies.py:40` uses `schema="public"`. The triage doc's example showing `core.billing_events` was based on intent; actual landing is `public.billing_events`.
- **Existing `<table>_service` policies stay** — 49+ defense-in-depth policies in `001_noctusai_core.sql:357+` (e.g. `noctus_users_service`, `subscriptions_service`). Renaming them would re-open keeper findings. We add NEW `service_role_bypass`-named policies alongside.
- **Single 001 convention NOT applicable here** — core has 14 migrations already (001 + 002–028 with gaps); the platform's "single 001 per product" rule applies to greenfield products. Core is post-greenfield. We add new numbered migrations.
- **WW helper is canonical** — `noctusai_lib.sql.service_role_bypass(table, schema="public")` emits the byte-equal shape: `CREATE POLICY "service_role_bypass" ON public.<table> FOR ALL TO service_role USING (true) WITH CHECK (true);`. Tests guard drift.
- **Migration mirror rule** — applied SQL via Supabase MCP `apply_migration` must match the `.sql` file byte-for-byte.

---

## 3. Design principles

1. **One concern per migration** — 029 creates `billing_events` (REAL_BUG fix); 030 adds the 13-table `service_role_bypass` backfill (DEFENSE_IN_DEPTH cluster).
2. **Option A over Option B** — separate backfill migration rather than amending `001_noctusai_core.sql` in place. Two reasons: (a) core has 14 numbered migrations already — amending 001 would diverge from convention used by 002-028; (b) Option A keeps the audit trail explicit ("the 2026-05-11 keeper-trio backfill").
3. **Consume the seed helper** — every `CREATE POLICY` line emitted by `noctusai_lib.sql.service_role_bypass(table, schema="public")`. No hand-rolled SQL. Drift would surface in helper tests + this migration simultaneously.
4. **Idempotent** — `CREATE TABLE IF NOT EXISTS` + `DROP POLICY IF EXISTS … BEFORE CREATE POLICY` so re-applying is a no-op.

---

## 3a. Seed-first analysis

- **Cross-product master-tree child** — the seed already absorbed the `service_role_bypass` policy emission via WW's Wave 0. This child consumes the helper; per-product code count = 14 backfill `CREATE POLICY` lines + 1 `CREATE TABLE` (irreducible — these are core's specific tables).
- **No further seed extraction opportunity** — the policy emitter is already the seed. The 13 backfill calls are sibling products' equivalent.

---

## 4. Scope

- **In scope:**
  - Create `public.billing_events` table + `service_role_bypass` policy on it.
  - Backfill `service_role_bypass` policies on 12 existing tables flagged by the detector.
  - Tests covering migration file shape (existence, RLS enabled, policy name literal).
  - Re-run `cli.py --review --product core` to confirm 0 admin_bypass + 0 unknown_table.
- **Out of scope:**
  - Renaming/removing existing `<table>_service` policies (keeper findings would re-open).
  - Detector tuning (XX Wave 0 already cleared cross-schema FP).
  - Other products' backfills (sibling Wave 1 children handle erp / mailing / pf).

---

## 5. Architecture / Data Model

### Migration 029 — `029_billing_events.sql`

Creates `public.billing_events`:
```
stripe_event_id TEXT PRIMARY KEY     -- Stripe idempotency anchor
event_type      TEXT NOT NULL
stripe_customer_id TEXT
org_id          UUID
payload         JSONB NOT NULL
created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Plus:
- `CREATE INDEX` on `event_type`, `stripe_customer_id`, `org_id`, `created_at` (Stripe webhook query patterns).
- `ALTER TABLE … ENABLE ROW LEVEL SECURITY`.
- `CREATE POLICY "service_role_bypass" ON public.billing_events FOR ALL TO service_role USING (true) WITH CHECK (true);` — closes the unknown_table + admin_bypass findings on `billing_events`.

### Migration 030 — `030_service_role_bypass_backfill.sql`

12 `CREATE POLICY "service_role_bypass" ON public.<table> FOR ALL TO service_role USING (true) WITH CHECK (true);` lines for:

| Table | Detector hit count |
|---|---|
| noctus_users | 43 |
| subscriptions | 32 |
| roles | 16 |
| licenses | 14 |
| plans | 11 |
| webhook_endpoints | 6 |
| webhook_deliveries | 5 |
| org_settings | 5 |
| audit_logs | 5 |
| api_keys | 5 |
| platform_settings | 4 |
| notifications | 2 |

(billing_events covered by 029; 13th table is its own migration.)

Each policy wrapped in `DROP POLICY IF EXISTS "service_role_bypass" ON public.<table>;` for idempotency.

---

## 6. Implementation phases

### Phase 0 — Audit + decide A-vs-B ✅ *(2026-05-11)*

- [x] Read triage doc core section.
- [x] Read `001_noctusai_core.sql:357+` for existing admin policies.
- [x] Inspect billing.py:284 + detector regex.
- [x] **Decide Option A** (separate backfill migration). Rationale in §3 principle 2.
- [x] Confirm `public` schema (not `core`) via `dependencies.py:40` + grep.
- [x] Tally 13 affected tables from baseline `--review`.
- [x] Baseline `cli.py --review --product core`: 150 findings (1 unknown_table + 149 admin_bypass).

### Phase 1 — REAL_BUG fix (billing_events) ✅ *(2026-05-11)*

- [x] Write `029_billing_events.sql` using `noctusai_lib.sql.service_role_bypass` helper output.
- [x] Apply via `mcp__claude_ai_Supabase__apply_migration`.
- [x] Verify table exists via `mcp__claude_ai_Supabase__list_tables`.

### Phase 2 — DEFENSE_IN_DEPTH backfill ✅ *(2026-05-11)*

- [x] Write `030_service_role_bypass_backfill.sql` — 12 backfill policies via helper.
- [x] Apply via `mcp__claude_ai_Supabase__apply_migration`.

### Phase 3 — Verification ✅ *(2026-05-11)*

- [x] `cli.py --review --product core` → 0 admin_bypass + 0 unknown_table.
- [x] `pytest tests/` → green.

### Phase 4 — Close ✅ *(2026-05-11)*

- [x] Update §11 change log.
- [x] Write findings.md.
- [x] Commit + push branch (orchestrator FFs).

---

## 7. Open questions

None — all answered in Phase 0.

## 8. Dependencies & blockers

- Wave 0 prerequisites: ✅ both `b76c43f` (WW helper) + `40269c3` (XX detector) in base.

## 9. Success criteria

- [x] `cli.py --review --product core` shows 0 admin_bypass + 0 unknown_table.
- [x] Live DB has `public.billing_events` table + `service_role_bypass` policy.
- [x] Migration `.sql` files match applied SQL byte-for-byte (mirror rule).
- [x] No pytest regressions.

## 10. How to use this plan

Wave 1 child of master-tree. Engineer YY executes; orchestrator FFs branch to main + archives.

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | **Dispatched by master-tree** with §16.7 worktree-base preamble + §17.6 Write-authorization. Engineer YY executed Phases 0-4. | claude-opus-4-7 |
| 2026-05-11 | **Phase 0** — Decided Option A (separate backfill migration). Tallied 13 affected tables matching triage doc exactly. Confirmed `public` schema. Baseline 150 findings. | YY |
| 2026-05-11 | **Phase 1** — Shipped `029_billing_events.sql` (`public.billing_events` table + 4 indexes + RLS enabled + `service_role_bypass` policy via WW helper). Applied via Supabase MCP. | YY |
| 2026-05-11 | **Phase 2** — Shipped `030_service_role_bypass_backfill.sql` (12 backfill policies via WW helper). Applied via Supabase MCP. | YY |
| 2026-05-11 | **Phase 3** — Re-run: 0 admin_bypass + 0 unknown_table (150 → 0). pytest green. | YY |
| 2026-05-11 | **Phase 4** — Branch pushed; orchestrator FFs. | YY |

## 12. No-leftovers constraint

- Folder archives via orchestrator at master-tree close.
