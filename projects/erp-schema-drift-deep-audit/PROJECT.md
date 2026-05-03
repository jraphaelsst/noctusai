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
- **Status:** 📋 **FILED** — Phase 0 interrogation pending. Security concern flagged.
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

### Phase 0 — Live-DB audit + interrogation

- [ ] Enumerate every column in every ERP table; build a checked-in inventory.
- [ ] Run `grep -rn '.eq("org_id"' app/` against ERP backend; cross-reference each call site against the inventory; classify each as "valid (table has org_id)" or "drift (table lacks org_id)".
- [ ] Confirm or revise the §2 candidate answers with the user.
- [ ] Decide whether `profiles.py:115` security fix ships in Phase 1 (separate atomic migration) or as part of the broader migration.

### Phase 1+ — Migrate (designed at Phase 0)

_(per-table phases land here once design is locked)_

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
