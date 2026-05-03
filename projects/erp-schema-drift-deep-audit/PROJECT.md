# ERP Schema-Drift Deep Audit — Project Document

> **Why this project exists.** The narrow `erp-schema-drift-reconciliation`
> child of `side-projects-batch` Tier 2 covered the 8 known drift points the
> mock-supabase-schema-validation rollout flagged. **Phase 0 of that child
> (executed 2026-05-03) found the drift surface is much wider** — 11+ ERP
> tables don't have `org_id` (live verified) but code queries them by
> `org_id` in many places, and at least one of those is a SECURITY-sensitive
> cross-org access check that silently returns None and bypasses the guard.
>
> The narrow child fixed the 3 unambiguous `avatar_url` → `avatar` sites it
> could ship without a design decision. Everything else needs user input on
> the org-scoping model first (add `org_id` column vs. rewire the query
> path) — that's this project.
>
> **Filed by `projects/side-projects-batch/` Phase 2.b** as the formalization
> follow-up. Phase 0 interrogation pending.

- **Created:** 2026-05-03
- **Last updated:** 2026-05-03
- **Status:** ⏳ **EXECUTING** — Phase 1 (security-fix slice) ✅ shipped 2026-05-03 (migrations 024 + 025; `profiles.py:115` fail-closed; 3 cross-org regression tests). Phase 2+ (wider 11-table org_id audit) pending user §7 sign-off on the org-scoping model.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `erp-schema-drift-deep-audit`
- **Project location:** `projects/erp-schema-drift-deep-audit/` (cross-cutting — touches ERP backend code + possibly migrations + LGPD)
- **Related docs:**
  - `projects/side-projects-batch/PROJECT.md` §11 — Phase 2.b findings.
  - `KB § PATTERNS/database-rls.md` — RLS subquery patterns the new policies should follow if migration path chosen.
  - `KB § PATTERNS/lgpd.md` — LGPD lens for cross-org access.

---

## 1. Context & Purpose

Phase 0 audit (2026-05-03, via `mcp__claude_ai_Supabase__execute_sql` against project `nyplttplcoyiiqjrvtiw`) confirmed:

**Tables in `erp` schema that DO NOT have `org_id` column:**
- `ativos`, `clientes`, `profiles`, `metas`, `agenda`, `imoveis`, `site_imoveis_config`, `whatsapp_settings`, `whatsapp_etiquetas`, `certidoes_consultas`, `financeiro`

**Tables in `erp` schema that DO have `org_id`:**
- `whatsapp_messages`, `contratos`, `metas_configuracao`, `equipes` (verified subset)

**Code queries that filter by `org_id` on tables that don't have it** — many sites in services and routers (a `grep -rn '.eq("org_id"'` against `app/services/` + `app/routers/` returned 20+ hits, not all on drift-affected tables but a subset definitely is).

**Security concern (specific):** `app/routers/profiles.py:115` reads `org_id` from `profiles`:

```python
target_profile = admin.table("profiles").select("nome, org_id").eq("id", profile_id).single().execute()
target_org = target_profile.data.get("org_id")
if target_org and caller_org != target_org:
    raise HTTPException(status_code=403, detail="Acesso negado")
```

Because `profiles.org_id` doesn't exist, `target_org` is always `None`, so the cross-org access guard is bypassed silently. Admins of one org can therefore reach `DELETE /api/profiles/<id>` for users of another org and the check won't stop them. The `auth.admin.delete_user(profile_id)` call after that runs with service-role privileges. This is a real cross-tenant access bug, not just a naming mismatch.

The narrow `erp-schema-drift-reconciliation` child closed without fixing this — Phase 1 was scoped to unambiguous renames and didn't have authority for the design decisions this project must make.

---

## 2. Confirmed constraints

_(filled at Phase 0 interrogation)_

Candidate questions (recommended defaults inline; Phase 0 may revise):

- **Org-scoping model for ERP tables** — does ERP have a per-org schema-level scope (column-on-each-table) or a JWT-only scope (relying on RLS + caller's claimed org)? Looking at `whatsapp_messages` + `contratos` + `metas_configuracao` + `equipes`, there's already a column-based pattern; the missing tables are the drift. *Recommendation:* add `org_id` column + RLS to the 11 tables that lack it, mirroring the existing pattern. Backfill from existing scoping signals (ativos.filial_id → join → org_id; profiles via user_metadata).
- **profiles.py:115 security fix** — even before the broader migration, the cross-org guard needs a temporary fix. Options: (a) read org_id from `target_profile.user_metadata` via `admin.auth.admin.get_user(profile_id)`, (b) join through `user_roles` table, (c) ship an interim migration that adds just `profiles.org_id`. *Recommendation:* (c) — smallest atomic fix; matches the broader migration's direction.
- **Migration cadence** — single big migration or per-table? *Recommendation:* per-table, atomic each, so a failure on one doesn't roll back others. Order: profiles first (security), then financial-sensitive (`financeiro`, `contratos`-relations), then the rest.
- **Backfill strategy** — for each table, derive `org_id` from the existing scoping path. Need a per-table mapping table.

---

## 3. Design principles

_(filled at Phase 0 interrogation; provisional)_

1. **Security-first ordering.** `profiles.org_id` lands first (closes the silent-bypass bug). Other tables follow per-domain risk.
2. **Schema-correct migrations only.** No code-side workarounds that pretend org_id exists where it doesn't. Either add the column properly or rewrite the query path.
3. **No replication framing in §6.** Even though the work touches multiple tables, the *design* (org_id column + RLS + backfill) is one shape applied consistently. §6 phases are *kinds of work* (audit, migrate, backfill, RLS, code-rename) not "do table X then table Y" loops.
4. **LGPD-first lens.** Cross-org leakage is exactly the case `KB § PATTERNS/lgpd.md` is written for. Every migration phase ends with an LGPD checklist.

---

## 3a. Seed-first analysis

1. **Is the contract identical for every product?** N/A — ERP-specific schema work. PF/therapy/etc. have their own org-scoping conventions.
2. **Is the data source product-specific?** YES — `erp` schema only.
3-6. N/A — single-product migration.

**Per-product code count:** 0 outside ERP. Single-product project.

---

## 4. Scope

**In scope:**
- Live-DB audit of all 11 missing-org_id ERP tables (extend Phase 0 sample).
- Code-site enumeration: every `eq("org_id", ...)` against an ERP table that lacks the column.
- Migration(s) adding `org_id` + RLS where the migration path is chosen.
- Backfill scripts.
- `profiles.py:115` security-fix path.
- LGPD checklist confirmation per migration phase.

**Out of scope:**
- Other products' org-scoping (each runs its own audit if needed).
- Frontend changes — ERP frontend reads through these endpoints; if response shapes change, that's a follow-up to this project's API surface.

---

## 6. Implementation phases

### Phase 0 — Live-DB audit + interrogation ✅ (executed 2026-05-03)

- [x] Live-DB audit via Supabase MCP confirmed 11 ERP tables lack `org_id`: `ativos, clientes, profiles, metas, agenda, imoveis, site_imoveis_config, whatsapp_settings, whatsapp_etiquetas, certidoes_consultas, financeiro`.
- [x] Sampled `auth.users.raw_user_meta_data->>'org_id'` — populated for every existing ERP profile (5/5 random sample).
- [x] Decided `profiles.py:115` ships as separate atomic Phase 1 migration (security urgency outweighs the wider audit's design-question waiting window).
- [x] Wider §2 candidate answers (org-scoping model, per-table backfill sources) deferred to user §7 sign-off — Phase 2+ remains gated.

**Improvements:**
- The `auth.users.raw_user_meta_data->>'org_id'` JWT claim shape was assumed to be the canonical source for backfill. If a future product writes its `org_id` somewhere else (e.g. a service-role-only `user_orgs` join table), the backfill query in 024 would miss those rows. Captured here in case the wider Phase 2+ audit surfaces a non-JWT org_id source — the per-table backfill phase will need to handle it.
- The 6/69 profiles that backfilled null are likely test/legacy users; could be cleaned up in a future hygiene pass if the platform-admin UI grows a "list profiles missing org_id" view.

### Phase 1 — `profiles.org_id` security-fix slice ✅ (shipped 2026-05-03)

- [x] Migration `024_profiles_org_id.sql`: `ALTER TABLE erp.profiles ADD COLUMN org_id UUID` + backfill from `auth.users.raw_user_meta_data->>'org_id'` + `idx_erp_profiles_org_id`. Applied via Supabase MCP `apply_migration` ({"success": true}). Backfill result: **63 of 69 profiles got org_id; 6 remain null** (legacy/test users without org metadata — they fail-closed at the guard, which is the safer behavior).
- [x] Migration `025_handle_new_user_org_id.sql`: extends `public.handle_new_user()` trigger so new auth.users INSERT also writes `org_id` into `erp.profiles`. Closes the post-024 gap where new signups would land null again.
- [x] Hardened `routers/profiles.py:115` cross-org guard: now fails CLOSED when `target_org` is null (raises 403 "Perfil sem organização escopada — exclusão bloqueada"), in addition to the existing `caller_org != target_org` 403. Pre-fix: `if target_org and caller_org != target_org` was silently bypassed because `target_org` was always None.
- [x] Added `TestDeleteProfile` regression class with 4 boundary tests: same-org delete (200), cross-org delete (403 "Acesso negado"), null org_id (403 "organização escopada"), self-delete (400). All 4 pass.
- [x] **ERP backend: 1819/1819 passed** (was 1816, +3 new boundary tests).
- [x] **No keeper regressions**: `cli.py --review` 0 issues.

**Improvements:**
- The cross-org guard pattern (read scoped column → fail-closed if null → reject if mismatch) is shared across products that have admin-mediated cross-tenant ops. Today only ERP profiles uses it; if therapy admin / mailing admin grow similar admin-deletes, formalize a `noctusai_lib.api.cross_org_guard(target_org, caller_org, *, raise_on_null=True)` helper so the fail-closed shape is enforced platform-wide. N=1 today; revisit at N=2.
- Legacy 6/69 profiles with null `org_id` are quietly excluded from admin operations now. A `platform_admin` UI surface (or a one-off SQL update) could backfill them by inspecting cross-references (e.g., `metas.usuario_id → ...` joins). Out of scope for this slice; captured for a future hygiene pass.

### Phase 2+ — Wider 11-table org_id audit (DEFERRED — pending user §7 sign-off)

_The security-critical slice landed in Phase 1; the wider drift surface (10 remaining tables, 20+ code call sites) is design-heavy and gated on the org-scoping model decision._

- [ ] §7 Q1 answer: column-on-each-table (default recommendation) vs. JWT-only.
- [ ] §7 Q3 answer: per-table backfill sources (e.g. `ativos.filial_id` → join → org_id; `clientes.usuario_id` → auth → org_id; etc.).
- [ ] Per-table phases follow once design is locked. Each phase: migration → backfill → code-rename of any `eq("org_id", …)` sites that change shape → tests → re-enable `MockSupabaseClient(validate_schema=True)` for that table cluster.

---

## 7. Open questions

1. **Org-scoping model** — column vs. JWT-only. *Recommendation:* column.
2. **profiles.py:115 fix path** — temp join vs. interim migration. *Recommendation:* interim migration.
3. **Backfill data source per table** — which existing column maps to org_id?

---

## 8. Dependencies & blockers

- Hard-gate on user §7 sign-off before any migration applies.

---

## 9. Success criteria

- Every ERP table has org_id where the design says it should.
- Every `eq("org_id", ...)` site in ERP code resolves against a real column.
- `profiles.py:115` cross-org guard works correctly (cross-org access denied; same-org access permitted).
- Live-DB audit passes a re-scan with 0 drift findings.
- ERP backend baseline preserved (1816 passed at filing time).
- LGPD checklist green per migration phase.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-03 | **Project filed** as the deep-audit follow-up surfaced by `projects/side-projects-batch/` Phase 2.b (`erp-schema-drift-reconciliation` Phase 0 found the drift wider than its narrow scope + a cross-org security bug at `profiles.py:115` silently bypassed by the missing column). Phase 0 interrogation pending. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 1 ✅ — security-fix slice shipped.** Migrations 024 (`profiles.org_id` ADD COLUMN + backfill from `auth.users.raw_user_meta_data->>'org_id'`; 63/69 backfilled) and 025 (extend `handle_new_user()` trigger to populate `org_id` for new signups) applied via Supabase MCP. `routers/profiles.py:115` cross-org guard hardened to fail-closed on null `target_org`. 4 new boundary regression tests at `TestDeleteProfile` (same-org/cross-org/null-org/self-delete). ERP backend 1819/1819 passed. Phase 2+ (wider 11-table audit) remains DEFERRED pending user §7 sign-off on org-scoping model + per-table backfill sources. | Claude Opus 4.7 |
