# ERP Schema-Drift Reconciliation — Project Document

> **Living document.** Revise phases as work progresses; update §11 Change Log.
>
> **Written for a zero-context reader.** Assume the next agent has not seen the conversation that produced this project.

- **Created:** 2026-04-24
- **Last updated:** 2026-04-24
- **Status:** Scaffolded from `mock-supabase-schema-validation` Phase 3 rollout (2026-04-24). Not yet interrogated. §7 gate before Phase 1 begins.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Related docs:**
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/testing.md § Schema validation` — the validator that surfaced these drifts (default-on `MockSupabaseClient(validate_schema=True)` since 2026-04-24; the originating `mock-supabase-schema-validation` project shipped + archived).
  - `products/therapy-platform/projects/therapy-audio-lifecycle-schema-reconciliation/PROJECT.md` — the sibling reconciliation project (same shape, different product).
  - `CLAUDE.md § MCP migrations mirror the file` + `KB § PATTERNS/database-rls.md`.
- **Project slug:** `erp-schema-drift-reconciliation`
- **Project location:** `products/erp-imobiliario/projects/erp-schema-drift-reconciliation/` (single-product scope).

---

## 1. Context & Purpose

The `mock-supabase-schema-validation` project (2026-04-24) added a validator that cross-references `MockSupabaseClient` filter/select/insert calls against columns parsed from the authoritative migration files. When Phase 3 rolled out validation to ERP with `MockSupabaseClient(validate_schema=True, schema="erp")`, **~8 known drift points surfaced**:

| Table | Drift | Code uses | Migration defines |
|---|---|---|---|
| `erp.ativos` | wrong-name | `descricao` | `descricao_seo` |
| `erp.ativos` | missing-col | `org_id` | (not present) |
| `erp.clientes` | missing-col | `org_id` (on insert) | (not present) |
| `erp.lancamentos` | missing-col | `contrato_id` | (not present) |
| `erp.lancamentos` | missing-col | `referencia` | (not present) |
| `erp.metas` | wrong-name | `meta_vgv` | `meta_pretendida` / `meta_realizada` |
| `erp.profiles` | wrong-name | `avatar_url` | `avatar` |
| `erp.profiles` | missing-col | `org_id` | (not present) |
| `erp.whatsapp_config` | missing-col | `webhook_secret` | (not present) |

Each of these is **either a real runtime bug** (code filters on a nonexistent column, getting silent-fail PostgREST errors) **or a migration-file drift from the live DB** (column exists live but missing from the numbered migration files — violates "MCP migrations mirror the file" rule).

Resolving each requires reconciling what the live DB actually has against what migration files define + what code uses. Per the compliance-audit `Q3` pattern, **the live DB is authoritative; migration files and code reconcile to it.**

---

## 2. Confirmed constraints

**Not yet interrogated.** §7 below is the hard gate.

Candidate constraints:
- **Live-DB is authoritative.** Every drift row resolves to either (a) migration file adds missing DDL to match live, or (b) code changes to use the real column. Not both unless the column should legit be renamed.
- **One finding per commit.** Each drift row is its own fix + migration + code change bundled.
- **Test-validation flip at end.** Once all drifts reconciled, flip `products/erp-imobiliario/backend/tests/conftest.py` `validate_schema=True, schema="erp"` and confirm 1765/1765 still passes.

---

## 3. Design principles

1. **Live DB is truth.** Use `mcp__claude_ai_Supabase__execute_sql` to inspect the live `information_schema.columns` for each flagged table; reconcile file + code to it.
2. **Per-finding proposal.** One proposal per drift row; apply-inline-then-delete.
3. **Test-validation re-enabled last.** The `validate_schema=False` opt-out in conftest.py is the gate; don't flip it until all findings green.

---

## 4. Scope

### In scope
- Reconcile every drift row in §1.
- Add any missing migration files to the `products/erp-imobiliario/backend/migrations/` series mirroring the live DB.
- Update ERP runtime code where the code column reference is the wrong one.
- Flip `validate_schema=True, schema="erp"` in conftest.py at project close.

### Out of scope
- Adding new ERP features.
- Schema changes that extend beyond reconciling existing drift (e.g., "also add a `created_by` column while we're in here").
- Therapy's equivalent drift — handled by `therapy-audio-lifecycle-schema-reconciliation`.

---

## 5. Architecture / Data Model

None — reconciliation only.

---

## 6. Implementation phases

### Phase 0 — Live-DB inspection + interrogation
- [ ] Use Supabase MCP to query `information_schema.columns` for each of the 8 affected tables; produce the authoritative column list per table.
- [ ] For each drift row: determine whether the live DB has the column code uses, or whether code is broken.
- [ ] Answer §7 Open Questions with user.
- [ ] File phase-0 proposal; apply inline + delete.

### Phase 1 — Per-table reconciliation (bundled)
- [ ] `erp.ativos`: reconcile `descricao` / `descricao_seo` + `org_id`. Migration file or code fix.
- [ ] `erp.clientes`: reconcile `org_id` on insert. Migration file or code fix.
- [ ] `erp.lancamentos`: reconcile `contrato_id` + `referencia`. Migration file or code fix.
- [ ] `erp.metas`: reconcile `meta_vgv` vs `meta_pretendida`/`meta_realizada`.
- [ ] `erp.profiles`: reconcile `avatar_url` / `avatar` + `org_id`.
- [ ] `erp.whatsapp_config`: reconcile `webhook_secret`.
- [ ] File phase-1 proposal; apply inline + delete.

### Phase 2 — Re-enable validation + close
- [ ] Flip `MockSupabaseClient(validate_schema=False, schema="erp")` → `True` in ERP conftest.py.
- [ ] Run full ERP test suite — must stay green (1765+ passing).
- [ ] Remove the "Schema-validation rationale" docstring block in conftest.py (no longer needed).
- [ ] Update PROJECT status to `✅ All phases shipped`; §11 entry.

---

## 7. Open questions

**Hard gate before Phase 1.**

1. **Migration-file order** — should the reconciliation go in a single `NNN_schema_drift_reconciliation.sql` migration, or split per-table? *Recommendation: single migration; keeps the reconciliation atomic and reviewable.*
2. **Code-or-migration priority** — when code uses `avatar_url` and migration has `avatar`, which is authoritative: code or migration? *Recommendation: match live DB. If the column is actually named `avatar` in prod, rename in code. If prod already has `avatar_url`, add ALTER TABLE migration to rename.*
3. **org_id on tables that don't have it** — multiple ERP tables (ativos, clientes, profiles) reference `org_id` in code but don't have it in migrations. Does prod have the column? If yes → add migration. If no → likely code uses the wrong name (maybe `organizacao_id` or joins through `profiles.org_id` that doesn't exist)? *Needs live-DB inspection via MCP.*

---

## 8. Dependencies & blockers

- User availability for §7.
- Supabase MCP blanket approval (already standing per CLAUDE.md).

---

## 9. Success criteria

- All 8 drift rows reconciled (live DB + migration file + code all agree per table).
- ERP conftest.py flips `validate_schema=True, schema="erp"`.
- ERP test suite passes 1765+/1765+.
- `mock-supabase-schema-validation` project's Phase 4 keeper detector no longer has a rationale-only opt-out entry for erp.

---

## 10. How to use this project

- **Single source of truth.** Update as work progresses.
- **Live-tick tasks.** Flip `- [ ]` → `- [x]` live.
- **Phase-by-phase cadence.** Default pause after each phase.
- **Apply-inline-then-delete** per repo default.

### Verification commands

```bash
cd /Users/rapha/Documents/repository/NoctusAI/noctusai/products/erp-imobiliario/backend && /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/ -q
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-04-24 | Scaffolded from `templates/PROJECT-TEMPLATE.md` at conclusion of `mock-supabase-schema-validation` Phase 3 ERP rollout, which surfaced 8 schema drift points via `validate_schema=True`. Candidate constraints captured in §2; §7 hard-gated on user interrogation; Phase 1 has per-table sub-tasks ready to execute. | Claude Opus 4.7 |
