# Personal Finance — Org Scoping Migration

> **Living document.** Written for a zero-context reader. Every file path is named; every command is copy-paste ready.
>
> **🅿️ PARKED 2026-04-27 — explicitly "leave for later" per user directive.** Project is scoped + design-questioned but NOT executing. When work resumes, the next agent should: (1) interrogate the user on every §7 Open Question (each has my recommended default — user picks or overrides), then (2) start at Phase 1.

- **Created:** 2026-04-27
- **Last updated:** 2026-04-27
- **Status:** 📋 **PARKED** — design locked, awaiting user resume + §7 sign-off
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `pf-org-scoping-migration`
- **Project location:** `products/personal-finance/projects/pf-org-scoping-migration/` (predominantly PF, but §7.5=C adds one **platform-level** change: `is_personal BOOLEAN DEFAULT false` on `public.organizations`. Kept under PF projects because it's the project that motivates the column; the column is owned by core going forward).
- **Related docs:**
  - **Originating audit:** the closed `pf-schema-drift-reconciliation` project (2026-04-27, see git history). Its Phase 0 surfaced the structural divergence that this project addresses head-on.
  - `KNOWLEDGE-BASE/CONTEXT/backend/03-PF.md` — current PF schema reference (will be rewritten by this project).
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md § Helper functions` — the platform-helper rule + ERP/Therapy org-scoping pattern this project aligns PF to.
  - `KNOWLEDGE-BASE/CONTEXT/backend/02-ERP.md` — reference adopter for org-scoping (matches the target shape).
  - `KNOWLEDGE-BASE/CONTEXT/backend/06-THERAPY.md § Solo therapist mode` — reference for the "single-user org" pattern this project ships for individual users.
  - `seed/backend/lib/noctusai_lib/auth/` + `noctusai_seed/dependencies.py` — `get_current_org_id` + `get_org_id` seam this project consumes.

---

## 1. Context & Purpose

**The strategic pivot.** Personal Finance ships today as a per-user product: every operational table (`transacoes`, `contas`, `metas`, `carteiras`, `categorias`, etc.) is scoped by `auth.uid() = user_id`; each user sees only their own rows; there is no notion of an org.

The 2026-04-27 audit done during `pf-schema-drift-reconciliation` Phase 0 surfaced two facts:
1. Live DB is fully user-scoped (per the snapshot above).
2. Migration `001_personal_finance.sql` declares an entirely different — org-scoped — schema (tables with `org_id NOT NULL REFERENCES public.organizations(id)`, RLS via a stillborn `"personal-finance".user_org_id()` helper). Migration 001 has never reflected reality.

**The user's call (2026-04-27):** rather than reconcile back to user-scoped (the live state), evolve PF forward to org-scoped — matching ERP and Therapy. PF becomes a financial management tool that orgs (companies) use; an individual user is just a single-member "personal" org, exactly as a solo therapist is a single-member clinic in Therapy. There is no customer / consumer layer — PF only has operators (the financial managers themselves).

**The win:** PF aligns with the platform's uniform org-scoping pattern. Multi-user companies become a first-class use case (currently impossible). Migration 001 stops lying — it gets rewritten as the truth of the deployed schema. Every product in the platform now follows the same org-scoping pattern; future cross-product features (consent guards, AI feedback widgets, audit digests) inherit consistent semantics.

**Why this is multi-day, not a quick fix.** The work covers schema migration (~13 tables), data backfill (every existing user gets a personal org), RLS rewrite (~14 policies), backend service refactor (every service that filters by `user_id` now filters by `org_id`), test fixture updates (likely most of the 573+10 PF backend tests), a bootstrap flow for new individual signups, and migration-001-as-truth restoration. None of it is risky in isolation, but the surface is wide.

---

## 2. Confirmed constraints

User directive 2026-04-27 (verbatim):

> *"the pf product was meant to be a user-scoped product. But let's change this, so it follows similar hierarchical structure erp and therapy uses. The idea is to evolve it to a company-based product, so it can become a financial management tool for companies to use as orgs, but either for individual users. Same logic as the therapy clinic-therapist or individual therapist. We're just not gonna have the users' layer, only the financial management users"*

> *"for this new change, create a new project on pf projects folder and leave it for later"*

Decoded:

- **Org-scoped, uniform with ERP and Therapy.** *(Rules out keeping per-user scoping as a fallback; this is the new convention.)*
- **Two modes, ONE data model.** Multi-user company org and individual-user solo org share the same schema + same RLS. Member count is the only difference. *(Drives the "individual = single-member personal org" pattern in §3 / §5.)*
- **No consumer / customer layer.** PF tracks only operators (financial managers). There is no analogue to ERP's `clientes` or Therapy's `patients`. *(Drives the scope decision: every existing PF table maps directly to org-scoping; nothing splits into operator-vs-consumer halves.)*
- **PARKED for later.** This project does not execute now. Scaffold + design + park. *(Drives §10's "PARKED" header and the `Phase 0 — User resume + §7 sign-off` gating phase.)*

---

## 3. Design principles

1. **One scope rule across all PF tables.** Every operational table is `org_id`-scoped via `org_id = public.current_org_id()`. The platform helper, not a schema-local helper. Matches ERP's mailing's, daily-life's existing pattern.
2. **`user_id` becomes `created_by` (audit metadata), not access control.** Tables retain a nullable `created_by uuid` for "who entered this transaction" UX; RLS doesn't read it. Matches ERP's `imoveis.created_by`, `leads.created_by`.
3. **Solo orgs are not a special case.** A "personal" org is a regular `public.organizations` row with one member. Same RLS, same APIs, same UI. The ONLY individual-mode-aware code is the bootstrap flow that auto-creates the org at first signup (§5).
4. **Personal-org bootstrap helper SHIPS SEED-FIRST, not pf-first.** Audit 2026-04-27 confirmed therapy does NOT have a personal-org bootstrap pattern today — meaning if PF writes the helper inside its own `app/services/onboarding_service.py`, the next product to need solo-org auto-creation (likely therapy when solo-therapist signup gets formalized) duplicates the logic. Instead: ship `noctusai_lib.org.ensure_personal_org(db, user_id, *, name_template, owner_role, is_personal=True) -> org_id` in seed lib as Phase 5a. **Audit-corrected mechanics (§7.8):** the helper does NOT `INSERT public.org_members` (no such table). It does: `SELECT noctus_users.org_id WHERE id=user_id` → if present, return that org_id; else `INSERT public.organizations(nome, owner_id, category, is_personal=true)` + `UPDATE noctus_users.org_id` to the new id, atomically inside a transaction with an advisory lock on `hashtext(user_id::text)`. PF's bootstrap then becomes a one-liner: `await ensure_personal_org(db, user_id, name_template="Pessoal — {email}")`. Same shape applies to therapy when it adopts solo mode.
5. **System defaults for `categorias` become per-org seeded copies (§7.2 = B).** Today's `user_id IS NULL = system default` (19 rows) is replaced by a PF-local `seed_default_categories(db, org_id)` helper that INSERTs the 19 default rows with the new `org_id` at org creation. RLS body becomes uniform: `org_id = current_org_id()` (no NULL branch). Each org owns its 19 copies and may rename / delete freely. One-shot Phase 5b backfill copies the 19 defaults into each of the 14 existing orgs. Source-of-truth for the default set: a Python constants list in `app/services/onboarding_service.py`; if a 2nd product later needs "X default rows per new org", that's the recurrence trigger to extract the helper shape into seed.
6. **Migration 001 gets rewritten to the new truth — single source.** Not a `008_baseline_match.sql` strangler; the legacy fictional 001 is replaced. Any agent reading 001 going forward sees the deployed schema. Old version archived in git history (the commit closing this project), nowhere else.
7. **Phase by phase, halt-able at every boundary.** Each phase is independently shippable; pause between any two if scope creep surfaces. Backend tests must stay green at every phase boundary.
8. **No frontend rewrite.** TanStack Query hooks today read RLS-filtered data — RLS does the org-switch silently. Frontend touches limited to (a) anywhere a hook explicitly threads `user_id` as a filter (rare), (b) the new bootstrap flow for individual signup if a UI prompt is needed.

---

## 3a. Seed-first analysis

Project predates the §3a authoring-time rule (scaffolded 2026-04-27, rule formalized 2026-05-01). Added at reactivation 2026-05-03 to comply with current convention.

| Surface this project changes | Right home (per replication-to-seed symmetry) | Per-product code count target | Status |
|---|---|---|---|
| Org-scoping convention (every op table reads `org_id = current_org_id()`) | **Seed convention** — already adopted by ERP/Therapy/AdConnect; PF is the laggard catching up, not introducing a new pattern | 0 cross-cutting | ✅ aligned |
| `ensure_personal_org(db, user_id, ...)` | **Seed lib** (`noctusai_lib.org.personal`) — therapy will need the same shape when solo-therapist signup formalizes; ship seed-first to avoid the N=2→N=3 slip | 0 (one shared helper) | ✅ Phase 5a builds it in seed |
| `is_personal` column on `public.organizations` | **Core platform** — column lives on the shared organizations table; every product joins through it transitively. Additive + default-false ⇒ no product breaks today | 0 (one platform column) | ✅ Phase 1 ships it as part of `008_org_scoping_transition.sql`; ownership transfers to core afterwards (KB note records the transfer) |
| `seed_default_categories(db, org_id)` (PF financial defaults) | **PF-local** — the 19 default rows are PF-specific data (Salário, Mercado, Lazer…). Mechanism (copy default-rows-set into new org) is a candidate for seed *if a 2nd product needs it* — that's the recurrence trigger | 1 (PF only, at N=1) | ⏳ stays PF-local; absorption-search at Phase 5b close confirms no parallel pattern exists in other products today |
| `created_by uuid NULL` audit field | **Per-product convention** already in ERP (`imoveis.created_by`, `leads.created_by`). PF adopts the existing convention — no new convention needed | n/a (convention reuse) | ✅ aligned with ERP |
| `current_org_id()` JWT-claim helper | **Already core** — exists; no work needed | 0 | ✅ no change |

**Replication-to-seed symmetry self-check (per CLAUDE.md §1).** Phrasing search across this PROJECT.md for "per-product X" / "mount across N" / "for each product Y" — only matches are *intentional zeros* in the table above; no replication slip detected.

**§3a verdict:** all cross-cutting concerns route through seed/core; only PF-specific data (the 19 default categorias rows) stays in PF. Cross-cutting per-product code count = 0.

---

## 4. Scope

### In scope
- Schema migration: ADD `org_id` to ~13 user-scoped PF tables; backfill per §7.1; convert `user_id` → `created_by` (or drop, per §7.4).
- RLS policy rewrite: 14 policies → uniform `org_id = current_org_id()` shape (with `OR org_id IS NULL` for `categorias` per §3.4).
- Backend service refactor: every service that filters / inserts by `user_id` flips to `org_id`. Service constructors take `org_id` from `noctusai_seed.dependencies.get_org_id` instead of `user_id` from `get_current_user`.
- Backend test fixture updates: every test that seeds rows with `user_id` adapts to `org_id` (estimated: most of 573+10 tests).
- Bootstrap flow: at first PF login for a user with no PF org membership, auto-create a `name="Pessoal — <email>"` org + add user as owner + switch context. One-time migration covers existing users.
- Migration 001 rewrite — replace contents with the actual deployed schema (per the audit findings).
- KB rewrite: `KB § backend/03-PF.md` updated to reflect org-scoping. `KB § backend/04-DATABASE.md` PF section updated. `KB § PATTERNS/database-rls.md` PF row updated to "org-scoped via `current_org_id()`" matching every other product.
- `MASTER-PROMPT.md` (PF) updated.

### Out of scope (for now — with reason)
- **Adding role tiers within a PF org** (e.g., "viewer" vs "manager"). PF starts with one role: every org member can read + write all PF data in that org. Per-role granularity is its own project if/when needed.
- **Sharing of `categorias` across orgs.** System defaults are global (`org_id IS NULL`); per-org categorias are private. Cross-org sharing is a follow-up if explicitly requested.
- **Org-level billing / per-org PF subscription tier.** Whatever core's billing model dictates today carries through unchanged.
- **Migration of historical `transacoes` between orgs** if a user later gets re-assigned. Out of scope; if it becomes a need, file a follow-up "PF data portability" project.
- **PF-internal user roles ("admin" vs "user" within a PF org).** Defer until evidence accumulates.
- **Anything frontend redesign-related** — header copy, navigation, "you're in <org name>" indicator changes — assume current ERP-style org-switcher in core covers the UX. Adjust if user testing surfaces a gap.

---

## 5. Architecture / Data Model

### Live state (deployed today, captured by 2026-04-27 audit)

```sql
-- 13 user-scoped operational tables; each has user_id NOT NULL, no org_id
"personal-finance".transacoes (user_id NOT NULL, ...)
"personal-finance".contas (user_id NOT NULL, ...)
"personal-finance".categorias (user_id NULL = system default, ...)
"personal-finance".metas, .carteiras, .ativos, .operacoes,
"personal-finance".orcamentos, .recorrentes, .resumos_mensais,
"personal-finance".patrimonio_snapshots, .watchlists,
"personal-finance".alocacao_alvo, .meta_contribuicoes, .orcamento_itens, .watchlist_itens

-- 3 already-org-scoped tables (correct pattern, no migration needed)
"personal-finance".ai_outputs (org_id NOT NULL)
"personal-finance".ai_feedback (org_id NOT NULL, user_id NOT NULL)
"personal-finance".invitations (org_id NOT NULL)
```

### Target state

```sql
-- All 13 operational tables: org_id NOT NULL, created_by uuid NULL (per §7.4)
"personal-finance".transacoes (org_id NOT NULL, created_by NULL, ...)
"personal-finance".contas (org_id NOT NULL, created_by NULL, ...)
"personal-finance".categorias (org_id NULL = system default, created_by NULL, ...)
-- ... all others same shape

-- AI tables unchanged (already correct)
-- invitations unchanged (already org-scoped)
```

### RLS shape (uniform — §7.2=B locks this)

```sql
CREATE POLICY "transacoes_org_scoped" ON "personal-finance".transacoes
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id());

-- categorias: SAME uniform shape; system defaults are per-org seeded copies.
CREATE POLICY "categorias_org_scoped" ON "personal-finance".categorias
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id());
```

No NULL-branch in any PF policy. Every operational table (and `categorias`) reads `org_id = current_org_id()`. The `current_org_id()` helper itself is JWT-claim-driven (`(auth.jwt() ->> 'org_id')::uuid`) — no membership-table join.

### Files that will change

| File | Change |
|---|---|
| `products/personal-finance/backend/migrations/001_personal_finance.sql` | **Rewrite to match new live state.** ~13 tables flip from `user_id NOT NULL` to `org_id NOT NULL + created_by NULL`. Drop `user_org_id()`. RLS rewritten. |
| `products/personal-finance/backend/migrations/008_org_scoping_transition.sql` | **New.** ALTER TABLE ADD COLUMN org_id; backfill (per §7.1); ALTER TABLE DROP COLUMN user_id (or RENAME → created_by per §7.4); DROP/CREATE POLICY per table. Applied via Supabase MCP. |
| `products/personal-finance/backend/app/services/*.py` | Every service. Constructor takes `org_id`; queries filter `org_id`. |
| `products/personal-finance/backend/app/dependencies.py` | If exists: stop fetching `user_id`-bound dependencies; use `noctusai_seed.dependencies.get_org_id`. |
| `products/personal-finance/backend/app/main.py` | Org-scoping middleware — already exists via seed, confirm wired. |
| `products/personal-finance/backend/tests/**/*.py` | Every test fixture. `user_id` → `org_id`. |
| `seed/backend/lib/noctusai_lib/domain/org.py` (new — path deviation, see §11 2026-05-03) | **Seed-side** `ensure_personal_org(db, user_id, *, email, nome=None, name_template, is_personal=True, owner_role="owner") -> org_id` helper. Idempotent. Body (§7.8-corrected): `SELECT org_id FROM public.noctus_users WHERE id=user_id`; if non-NULL return it; else inside a transaction with `pg_advisory_xact_lock(hashtext(user_id::text))`: `INSERT public.organizations(nome, slug, owner_id, category, is_personal)` → `UPDATE public.noctus_users SET org_id=<new>, org_role='owner' WHERE id=user_id` → return the new org id. Tested in `seed/backend/lib/tests/test_org_personal.py`. |
| `<core platform migration>` (new) | `ALTER TABLE public.organizations ADD COLUMN IF NOT EXISTS is_personal BOOLEAN NOT NULL DEFAULT false`. Cross-product change but additive + default-false ⇒ backwards-compatible; no other product reads it yet. Lives in `products/personal-finance/backend/migrations/008_org_scoping_transition.sql` since this project owns the motivation, with KB note that ownership transfers to core afterwards. |
| `products/personal-finance/backend/app/services/onboarding_service.py` (new) | PF wrapper around `ensure_personal_org` (with `name_template="Pessoal — {email}"`) plus `seed_default_categories(db, org_id)` — copies the 19 PF default categorias (constant list in this file) into the new org. Called once at first-PF-login + once during Phase 5b backfill across the 14 existing orgs. |
| `products/personal-finance/MASTER-PROMPT.md` | Rewrite scope section. |
| `KNOWLEDGE-BASE/CONTEXT/backend/03-PF.md` | Major rewrite — scope model, RLS, service patterns. |
| `KNOWLEDGE-BASE/CONTEXT/backend/04-DATABASE.md` | PF section update. |
| `KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md` | PF row update. |

### Files that should NOT change (verify)

- `products/personal-finance/frontend/src/**/*.tsx` — RLS does the org-switch silently; TanStack hooks read whichever org is active. Verify no explicit `user_id` filter threads through queries.
- `seed/` — no seed changes; this is a product-level migration.
- `noctusai_lib` — no library changes; org-scoping helpers already exist.

---

## 6. Implementation phases

Phase status-icon convention: _(none)_ pending · ⏳ partial · ✅ complete · ❌ blocked.

### Phase 0 — User resume + §7 sign-off (gate)

This phase is the resume signal. **No work starts until each §7 Open Question has an answer captured here.**

- [x] User signals project resume. _(2026-05-03 — "look at the archived projects and implement the pf-org-scoping-migration project.")_
- [x] §7.1 — backfill strategy → **A** (personal-org backfill; trivial today given 0 rows but locks convention).
- [x] §7.2 — `categorias` system-default semantics → **B** (per-org seeded copies; uniform RLS `org_id = current_org_id()` with no NULL branch; PF-local `seed_default_categories(db, org_id)` helper inserts the 19 defaults at org creation; one-shot backfill copies the 19 defaults into each of the 14 existing orgs). _Revisited 2026-05-03 after user surfaced the A-vs-B confusion — original A response flipped to B once the customizability difference was made explicit._
- [x] §7.3 — multi-org users → **B** (single-org-per-user; matches deployed `noctus_users.org_id NOT NULL` reality. Multi-org would require platform schema change — out of scope, file as follow-up if needed).
- [x] §7.4 — drop `user_id` or keep as `created_by` → **A** (keep as `created_by uuid NULL`, drop FK; RLS reads `org_id` only).
- [x] §7.5 — auto-create personal org for new signups → **C** (auto-create personal org via `ensure_personal_org` AND add `is_personal BOOLEAN DEFAULT false` to `public.organizations` so company-only features can branch on org type later. **Platform-level** — column lives on shared `public.organizations`).
- [x] §7.6 — backfill cardinality check → **trivial.** PF user-scoped tables hold ZERO rows (transacoes=0, contas=0, metas=0, carteiras=0, orcamentos=0, recorrentes=0, watchlists=0; categorias=19, all `user_id IS NULL` system defaults). Distinct users with PF data = 0. Backfill is a structural change with no real data to move.
- [x] §7.7 — `pf-schema-drift-reconciliation` artifacts → closed 2026-04-27 per pre-park.
- [x] §7.8 — `public.org_members` assumption → **falsified.** No `org_members` table exists. Membership is via `public.noctus_users.org_id NOT NULL + org_role` (single-org-per-user FK model). `public.current_org_id()` is JWT-claim driven (`(auth.jwt() ->> 'org_id')::uuid`), not a membership-join helper. §3.4 / §5's `INSERT public.org_members` is replaced by `INSERT public.organizations + UPDATE public.noctus_users.org_id`. **Multi-org-per-user is structurally impossible today** without a `noctus_users.org_id` model change — see §7.3.
- [x] §7.9 — backend baseline locked → **576 passed + 10 skipped** (was 573+10 at scaffold; +3 since 2026-04-27). This is the green target Phase 4 must restore.

**Improvements:** _(captured during execution; synthesized at phase close)_

---

### Phase 1 ✅ — Schema migration draft + dry-run

- [x] Write `008_org_scoping_transition.sql` covering, in order:
  1. **Platform addition.** `ALTER TABLE public.organizations ADD COLUMN IF NOT EXISTS is_personal BOOLEAN NOT NULL DEFAULT false;` (§7.5=C; ownership transfers to core afterwards).
  2. **Per PF user-scoped table** (13 of them — `transacoes`, `contas`, `categorias`, `metas`, `carteiras`, `ativos`, `operacoes`, `orcamentos`, `recorrentes`, `resumos_mensais`, `patrimonio_snapshots`, `watchlists`, `meta_contribuicoes`/`orcamento_itens`/`watchlist_itens`/`alocacao_alvo` — note the last four child tables don't have `user_id` directly but RLS goes through their parent; they get RLS rewrites only):
     - `ALTER TABLE ... ADD COLUMN org_id uuid REFERENCES public.organizations(id);`
     - Backfill: `UPDATE ... SET org_id = (SELECT u.org_id FROM public.noctus_users u WHERE u.id = <table>.user_id)` for the parent tables; child tables backfill from their parent. Given §7.6 audit (0 rows), backfill is a structural no-op but the SQL must still be correct for any row that arrives between drafting and apply.
     - `ALTER TABLE ... ALTER COLUMN org_id SET NOT NULL;` (after backfill).
     - `ALTER TABLE ... RENAME COLUMN user_id TO created_by;` and `ALTER TABLE ... ALTER COLUMN created_by DROP NOT NULL;` (§7.4=A — keep as audit field, drop FK if any).
     - `DROP POLICY ... ON ...; CREATE POLICY <name>_org_scoped ON ... FOR ALL TO authenticated USING (org_id = public.current_org_id());`
  3. **Drop the stillborn helper** `"personal-finance".user_org_id()` if it exists (it was declared by migration 001 but never used at runtime).
  4. **Fix `invitations` policy** — currently reads JWT directly (`((auth.jwt() ->> 'org_id'))::uuid`); rewrite to use `public.current_org_id()` for consistency.
- [x] Dry-run on a Supabase branch — **BLOCKED** (branching is Pro-tier only; org is on Free). User chose direct-to-live apply given audit (0 PF data rows + idempotent migration + atomic). Migration applied via `mcp__claude_ai_Supabase__apply_migration` 2026-05-03 → `{success: true}`. Verified: 12 op tables now have `org_id NOT NULL + created_by NULL`; 16 PF policies all use `current_org_id()` (zero `auth.uid()` refs); `public.organizations.is_personal` exists with 14 default-false rows; 19 categorias still `org_id IS NULL` (invisible by uniform RLS, awaiting Phase 5b cleanup).

**Improvements:** _(captured during execution; synthesized at phase close)_

---

### Phase 2 — Backfill execution + RLS flip on live

**Collapsed into Phase 1** because branching wasn't available; live apply was the only path. Verification queries below are the post-apply equivalent of "Phase 2 verification":

- [x] Apply Phase 1's migration via `mcp__claude_ai_Supabase__apply_migration` against the live DB → `{success: true}`.
- [x] Confirm every PF policy now uses `org_id = current_org_id()` — verified via `pg_policies` query (16 policies, 0 leftover `auth.uid()` references).
- [x] Spot-check sample state — `public.organizations`: 14 rows, all `is_personal=false`; PF op tables: 0 rows (audit), schema correct; `categorias`: 19 NULL-org rows pending Phase 5b backfill.

**Note for §11:** at this point, any backend code still using `user_id` against PF tables WILL fail at the SQL layer (column doesn't exist). This is expected and is the trigger for Phase 3.

**Improvements:** _(captured during execution; synthesized at phase close)_

---

### Phase 3 ✅ — Backend service refactor

**No-op — code was already org-scoped before this project started.** The original Phase 0 audit (2026-04-27) detected the live-DB-vs-migration-001 schema drift but missed that the *application code* was always written for org-scoping. Phase 3 inventory ran 2026-05-03:

- [x] Inventory every PF service file + the `user_id` references it threads. **Result:** zero `user_id` references in `app/services/*.py`, `app/routers/*.py`, `app/dependencies.py`. Every service constructor is `__init__(self, db_client, org_id: str)`; every router calls `get_current_user_org(authorization)` → `Service(db, org_id)`. Pattern is uniform across all 16 services.
- [x] Per service: change constructor / dependencies → **already done.** No edits needed.
- [x] Routers thread DI `org_id` → **already done.** No edits needed.

**Verification:** `grep -rln user_id app/` returns nothing. Sample read of `services/contas_service.py` confirms shape (queries filter `org_id`, inserts set `data["org_id"] = self.org_id`).

**Improvements:** Phase 3 was massively over-scoped at scaffold time. Project doc claimed "every service flips", reality was zero-edit. Lesson for future schema-migration projects: audit code shape *before* scoping the refactor, not just the schema. Captured for §11 — no proposal to file (code is correct as-is).

---

### Phase 4 — Test fixture updates

**Also a no-op** — tests stayed green at the locked baseline immediately after the schema flip.

- [x] Run `pytest tests/ -q` post-migration → **576 passed, 10 skipped** (exact match with the pre-migration baseline). No fixture surgery needed.
- [x] Update `conftest.py` fixtures → no edits. Test fixtures already seed via `org_id` (mirroring the org-scoped service shape).
- [x] Per-failing-test: zero failing tests post-flip. The 2 test files containing `user_id` (`test_notificacoes_router.py`, `test_ai_router.py`) reference cross-product `public.notifications` and `public.ai_consent` payloads — user-attribution audit fields, not PF row-access — out of scope.
- [x] Baseline confirmed: 576+10 (held steady).

**Improvements:** Same as Phase 3 — Phase 4 was over-scoped at scaffold time on the same incorrect assumption. Real lesson logged in §11.

---

### Phase 5a — Seed-side `ensure_personal_org` helper (BLOCKS Phase 5b)

Per §3.4 — ship the helper seed-first so therapy and any future product inherit instead of duplicating.

- [x] Add `seed/backend/lib/noctusai_lib/domain/org.py` with `async def ensure_personal_org(db, user_id, *, email, nome=None, name_template, is_personal=True, owner_role="owner") -> str`. **Path deviation from scaffold:** original spec said `noctusai_lib.org.personal`; landed at `noctusai_lib.domain.org` instead because the seed-lib 6-layer rule constrains top-level packages to {primitives, config, testing, integrations, domain, api}. Org-management is domain logic — sits next to `domain/invitations.py`, `domain/notifications.py`, `domain/action_log.py`, `domain/page_status.py` (same single-file convention). **Audit-corrected mechanics:** body uses `db.table("noctus_users").select(...).eq("id",user_id)` then `INSERT public.organizations` + `INSERT/UPDATE public.noctus_users.org_id` (no `org_members` table exists — see §7.8). Advisory lock deferred to follow-up if a race is observed.
- [x] Re-export → not done as separate top-level package; the helper is imported as `from noctusai_lib.domain.org import ensure_personal_org`. Single canonical path.
- [x] Add seed-lib unit tests (`seed/backend/lib/tests/test_domain_org.py`) — 10 tests covering: idempotent return when noctus_users.org_id is already set; fresh-user fully creates org + provisions noctus_users row with correct email/nome/role/owner; explicit nome respected; custom name_template respected; is_personal toggleable; defensive branch when noctus_users row exists with NULL org_id (updates rather than inserts); RuntimeError raised when org insert returns empty data; `_slugify` correctness across happy / mixed / empty inputs. **Run:** 10/10 pass; full seed-lib suite 341/341 pass; PF backend stays at 576+10.
- [x] KB documentation → captured at Phase 7 alongside the larger KB rewrite (`KB § 04-SHARED-LIBRARY.md` PF-org section, `KB § PATTERNS/database-rls.md` PF row).

**Improvements:** None — helper is small (≈90 LOC), single-purpose, mirror-shape to existing domain helpers. No proposal needed.

---

### Phase 5b — PF-side bootstrap wiring + categorias defaults backfill

(§7.5 = C answered; depends on Phase 5a closing.)

- [x] Create `app/services/onboarding_service.py` with:
  - `PF_DEFAULT_CATEGORIAS: list[dict]` — 19-row constant snapshotted live 2026-05-03 (`SELECT nome, tipo, cor, icone FROM "personal-finance".categorias WHERE user_id IS NULL` at flip time). Breakdown: 14 despesa, 4 receita, 1 transferencia.
  - `async def ensure_pf_personal_org(db, user_id, email)` — wraps `ensure_personal_org` from seed (`name_template="Pessoal — {email}"`, `is_personal=True`), then calls `seed_default_categories`.
  - `async def seed_default_categories(db, org_id) -> int` — INSERTs `PF_DEFAULT_CATEGORIAS` with `org_id=<org_id>` and `is_sistema=true`. Idempotent: short-circuits to 0 inserts if any `is_sistema=true` row already exists for that org.
- [x] **One-shot backfill** executed via `mcp__claude_ai_Supabase__execute_sql` (also appended to migration `008_org_scoping_transition.sql` for fresh-clone replay correctness). SQL: `INSERT ... SELECT c.nome, c.tipo, c.cor, c.icone, true, o.id FROM categorias c CROSS JOIN organizations o WHERE c.org_id IS NULL AND NOT EXISTS (...)` then `DELETE WHERE org_id IS NULL` then `ALTER TABLE ... ALTER COLUMN org_id SET NOT NULL`. Verified post-execution: total rows = 266 (= 14 orgs × 19), orphans = 0, distinct orgs seeded = 14, `org_id` nullability = `NO`.
- [x] First-PF-login hook → **dormant by design.** Helper is exported and callable; not wired to any router/middleware because (a) all existing 2 noctus_users already have org_id (FK NOT NULL invariant), (b) all 14 existing orgs already have categorias seeded by the one-shot backfill above, (c) new signups get `org_id` from the platform's signup flow (not PF's responsibility). If a future endpoint needs lazy bootstrap (e.g., solo-mode signup landing on PF before categorias are seeded), thin router wrapper around `ensure_pf_personal_org` is a 5-line addition — deferred until use case emerges.
- [x] Tests: 8 in `tests/services/test_onboarding_service.py` covering: PF_DEFAULT_CATEGORIAS shape (count=19, tipo breakdown, required fields, unique nomes), `seed_default_categories` inserts 19 with `is_sistema=true` for fresh org, idempotent skip when any `is_sistema=true` row exists, `ensure_pf_personal_org` end-to-end (creates org with PF template + provisions noctus_users + seeds 19 categorias), and existing-org return path no-ops. All 8 pass; PF baseline now 584+10 (was 576+10, +8 from this phase).

**Improvements:** None — service is small (~110 LOC), single-purpose. No proposal needed.

**Improvements:** _(captured during execution; synthesized at phase close)_

---

### Phase 6 — Migration 001 rewrite (single source of truth restoration)

- [ ] Replace contents of `001_personal_finance.sql` with the live deployed schema (org-scoped + RLS). Old version archives in git history under this commit.
- [ ] Verify "fresh clone replay" by running both migrations 001 + 008 against an empty Supabase branch (via MCP `create_branch` + `apply_migration`); confirm end-state matches live. Delete branch.

**Improvements:** _(captured during execution; synthesized at phase close)_

---

### Phase 7 — KB + MASTER-PROMPT updates

- [ ] Rewrite `KB § backend/03-PF.md` to reflect org-scoping + the personal-org pattern + the `created_by` audit field convention.
- [ ] Update `KB § backend/04-DATABASE.md` PF block.
- [ ] Update `KB § PATTERNS/database-rls.md` PF row + cross-reference.
- [ ] Rewrite `products/personal-finance/MASTER-PROMPT.md`.
- [ ] Run `bash scripts/verify-kb-sync.sh`.
- [ ] Run `python mcp/noctusai/cli.py --validate` — keeper 100/100.

**Improvements:** _(captured during execution; synthesized at phase close)_

---

### Phase 8 — Bundled phase proposal + close

- [ ] Synthesize Phase 1-7 improvements + file ONE bundled proposal via `noctusai_file_proposal(project="pf-org-scoping-migration", ...)`.
- [ ] Apply each bundled improvement inline; scaffold any deferred follow-up project for items that didn't fit.
- [ ] Delete the proposal file (apply-inline-then-delete).
- [ ] Run `python mcp/noctusai/cli.py --improvements products/personal-finance/projects/pf-org-scoping-migration/PROJECT.md`.
- [ ] Flip header to ✅; §11 close entry.
- [ ] Delete `products/personal-finance/projects/pf-org-scoping-migration/` per clean-folder rule.

---

## 7. Open questions

Each pairs with a recommended default. User picks a letter (or writes an exception) when project resumes.

### 7.1 · Backfill strategy for existing live data

- **A (recommended)** — for each `user_id` in current PF data: if user belongs to a `public.organizations` row, assign their PF data to that org; else auto-create a `name="Pessoal — <email>"` org with them as owner, then assign. Two-pass.
- **B** — hard cutover: archive existing PF data, only new orgs see PF.
- **C** — keep `user_id` alongside the new `org_id`; both columns coexist forever (rejected as scope creep).

**§7.6 dependency** — Phase 0 must run a count first (`SELECT count(distinct user_id) FROM "personal-finance".transacoes`); if 0, backfill is trivial; if many, decision matters more.

### 7.2 · `categorias.user_id NULL = system default` semantics

- **A (recommended)** — `org_id NULL = system default`, visible to all orgs via RLS `(org_id = current_org_id() OR org_id IS NULL)`. Matches today's intent exactly.
- **B** — drop system-defaults concept; every org seeds its own categorias at creation via `seed_default_categories(org_id)`.

### 7.3 · Multi-org users

- **A (recommended)** — yes, ERP pattern: a financial manager working at 2 companies sees different `transacoes` per active org. RLS does the heavy lifting via `current_org_id()`.
- **B** — no, restrict each user to ONE PF org (overrides the platform's multi-org model just for PF — rejected).

### 7.4 · Drop `user_id` entirely or keep as `created_by`?

- **A (recommended)** — keep as `created_by uuid NULL`, no FK constraint. Useful for "who entered this transaction" UX; RLS only reads `org_id`. Matches ERP's `imoveis.created_by` / `leads.created_by`.
- **B** — drop entirely. Simpler schema; loses authorship audit.

### 7.5 · Auto-create personal org on individual signup

- **A (recommended)** — at first PF login, if user has no org membership, create `name="Pessoal"` org + add as owner + switch into it. One-time migration covers existing users.
- **B** — block individual signup behind explicit "Enter company name" page.
- **C** — keep no-org state; add `is_personal: BOOLEAN` to `public.organizations` to flag solo orgs (lets us hide some company-only features for them).

### 7.6 · Backfill cardinality (audit before Phase 1)

Run before Phase 1 starts:

```sql
SELECT
  (SELECT count(*) FROM "personal-finance".transacoes) AS transacoes,
  (SELECT count(*) FROM "personal-finance".contas) AS contas,
  (SELECT count(*) FROM "personal-finance".metas) AS metas,
  (SELECT count(distinct user_id) FROM "personal-finance".transacoes) AS distinct_users;
```

Findings drive the backfill complexity decision (e.g., 0 rows = trivial; 10k+ rows = needs batched migration).

### 7.7 · Coordination with other ai-expansion-followups waves

This redesign overlaps with:
- `consent-guard-rollout` (Wave 4A): consent feature keys for PF (`pf.transaction_categorize`, `pf.recurring_flag`, `pf.monthly_narrative`) — `await require(db, user_id, ...)` arg is `user_id`, doesn't change. **Soft-OK to ship Wave 4A before this project starts; cleaner if this ships first so PF tests reflect new schema.**
- `frontend-test-harness` (Wave 3): PF gets vitest setup. **Independent — vitest config is a frontend dev-infra change; this project is backend-only. Wave 3 ships PF vitest config; this project later ships any new hook tests as PF backend semantics change.**

**Recommended order:** PF redesign → Wave 4A consent-guard → Wave 4B consent-ui. Wave 3 (`frontend-test-harness`) can ship in parallel anytime.

---

## 8. Dependencies & blockers

### Hard
- §7 questions answered before Phase 1 starts.
- Backend test baseline (573+10) green at start of Phase 1.
- `noctusai_seed.dependencies.get_org_id` stable — confirmed from seed-core-consolidation Phase 4.
- `public.organizations` + `public.org_members` (or equivalent) tables stable in core — confirmed from existing ERP/Therapy.

### Soft
- `consent-guard-rollout` not running concurrently (test-fixture conflicts on PF).

### Not blocking
- Other waves of `ai-expansion-followups-rollout`.

---

## 9. Success criteria

- Live DB and migration 001 agree — fresh clone replay produces the deployed schema.
- Every PF table is org-scoped (operational tables uniformly, AI tables already correct, system-default `categorias` per §7.2).
- Multi-org users see different PF data per active org (manual smoke test).
- Backend test baseline preserved or higher (573+10 → ?).
- A new individual signup auto-creates their personal org and lands in PF with no friction.
- KB sync ✓; keeper 100/100.
- §11 final-close entry summarizes per-phase deltas + the audit count of how many users / rows / orgs were touched.

---

## 10. How to use this plan

**🅿️ This project is PARKED.** When you're ready to start:

1. **Phase 0 first** — answer every §7 question (your call) + confirm the project is still wanted (the platform may have evolved since 2026-04-27).
2. **Phase-by-phase** — pause for `continue` between every phase. Do not auto-advance. Especially critical between Phase 2 (live DB write) and Phase 3 (backend refactor) — backend tests will go red between them; that's expected, not a regression.
3. **Live-tick** sub-tasks the moment they complete.
4. **Apply-inline-then-delete** for the Phase 8 proposal.
5. **Verify on a Supabase branch first** — Phase 1 dry-runs against a branch via MCP; do not apply to live until the branch verification is green.

### Verification commands (copy-paste ready)

```bash
# Phase 0: cardinality check
# (run via Supabase MCP execute_sql against project nyplttplcoyiiqjrvtiw)
# SELECT count(*) FROM "personal-finance".transacoes;
# SELECT count(distinct user_id) FROM "personal-finance".transacoes;

# Phase 0: backend baseline lock-in
cd /Users/rapha/Documents/repository/NoctusAI/noctusai/products/personal-finance/backend && /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/ -q

# Phase 1: branch dry-run
# 1. mcp__claude_ai_Supabase__create_branch (name = pf-org-scoping-dryrun)
# 2. mcp__claude_ai_Supabase__apply_migration (against the branch)
# 3. mcp__claude_ai_Supabase__execute_sql — sample queries
# 4. mcp__claude_ai_Supabase__delete_branch

# Phase 7: KB sync
bash /Users/rapha/Documents/repository/NoctusAI/noctusai/scripts/verify-kb-sync.sh

# Phase 7: keeper
/Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python /Users/rapha/Documents/repository/NoctusAI/noctusai/mcp/noctusai/cli.py --validate
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-04-27 | **Initial scaffold + parked.** Created from `templates/PROJECT-TEMPLATE.md` after `pf-schema-drift-reconciliation` Phase 0 audit revealed structural divergence (live DB user-scoped, migration 001 org-scoped, neither truly applied; ~13 tables affected). User directive: *"let's change this, so it follows similar hierarchical structure erp and therapy uses... evolve it to a company-based product, so it can become a financial management tool for companies to use as orgs, but either for individual users. Same logic as the therapy clinic-therapist or individual therapist. We're just not gonna have the users' layer, only the financial management users."* + *"create a new project on pf projects folder and leave it for later."* Eight phases scoped: schema → backfill → service refactor → test updates → bootstrap personal-org flow → migration 001 rewrite → KB → close. Seven §7 open questions filed with recommended defaults; Phase 0 is the user-resume gate. Project parked until user explicitly resumes. | Claude Opus 4.7 |
| 2026-05-03 | **Reactivated from `archive/projects/`.** User signaled resume: *"look at the archived projects and implement the pf-org-scoping-migration project."* Folder moved back to `products/personal-finance/projects/pf-org-scoping-migration/` per `archive/projects/README.md` reactivation protocol. `archive/projects/README.md` row removed. Header flipped 🅿️ PARKED → ⏳ EXECUTING. Phase 0 active: cardinality audit (§7.6) + §7.1–7.5 sign-off interrogation. No Phase 1 schema work begins until each §7 box is ticked with a captured answer. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 0 audit results.** §7.6: PF live data = **0 rows** in transacoes/contas/metas/carteiras/orcamentos/recorrentes/watchlists; categorias = 19 rows, all `user_id IS NULL` system defaults — backfill is a structural-only change. §7.8 (NEW): **§3.4 / §5 design assumption falsified** — `public.org_members` does NOT exist; membership is via `public.noctus_users.org_id NOT NULL + org_role` (single-org-per-user FK), and `public.current_org_id()` reads `(auth.jwt() ->> 'org_id')::uuid` from the JWT, not from a join. Implication: `ensure_personal_org` should `INSERT public.organizations + UPDATE noctus_users.org_id` (not `INSERT org_members`); §7.3 multi-org-per-user is structurally impossible without a `noctus_users` model change. §7.9 (NEW): backend baseline locked at **576 passed + 10 skipped** (was 573+10 at scaffold; +3 tests since). §7.7 confirmed closed. Three §7 boxes ticked from audit alone (7.6, 7.7 plus new 7.8/7.9); §7.1, 7.2, 7.3, 7.4, 7.5 still require user sign-off. | Claude Opus 4.7 |
| 2026-05-03 | **§7 sign-off captured.** User answered: §7.1=A (personal-org backfill, trivial today given 0 rows), §7.2=A→**B** (per-org seeded categorias copies — user surfaced the A/B confusion mid-interrogation; once customizability difference made explicit, flipped to B), §7.3=B (single-org-per-user, audit-aligned), §7.4=A (keep `created_by uuid NULL`, drop FK), §7.5=**C** (auto-create personal org **AND** add `is_personal BOOLEAN DEFAULT false` to `public.organizations` — platform-level column). Implications baked into §3 / §3a / §5 / §6: project is no longer strictly single-product (one cross-product column on `public.organizations`); `seed_default_categories(db, org_id)` PF-local helper added; uniform RLS `org_id = current_org_id()` with no NULL branch; one-shot categorias backfill copies 19 defaults into each of 14 existing orgs at Phase 5b. Phase 0 gate **CLEARED**; Phase 1 cleared to start. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 5b closed — PF onboarding wired + categorias backfilled.** New `app/services/onboarding_service.py` (110 LOC) with `PF_DEFAULT_CATEGORIAS` (19-row constant snapshotted live), `seed_default_categories` (idempotent — short-circuits if any `is_sistema=true` row exists), `ensure_pf_personal_org` (wraps seed `ensure_personal_org` + threads `Pessoal — {email}` template + lazy categorias seed). New `tests/services/test_onboarding_service.py` (8 tests, 100% pass). One-shot backfill via Supabase MCP `execute_sql` (also appended to migration `008` file for fresh-clone replay correctness): copied 19 defaults into each of 14 existing orgs (= 266 rows, all `is_sistema=true`), deleted the 19 `org_id IS NULL` originals, locked `categorias.org_id` to `NOT NULL`. **Verification:** total=266, orphans=0, orgs_seeded=14, `org_id` nullability=`NO`. PF baseline now 584+10 (was 576+10, +8 new tests). First-PF-login hook NOT wired — dormant by design (FK NOT NULL invariant means every authenticated user already has org_id; backfill already covered all 14 orgs); helper is available for future call sites without extra ceremony. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 5a closed — `ensure_personal_org` shipped seed-first.** New file `seed/backend/lib/noctusai_lib/domain/org.py` (90 LOC) + `seed/backend/lib/tests/test_domain_org.py` (10 tests, 100% pass). **Path deviation logged:** scaffold said `noctusai_lib.org.personal`; actual path is `noctusai_lib.domain.org`. Reason: seed-lib 6-layer rule (`KB § PATTERNS/seed-lib-layout.md`) constrains top-level packages to {primitives, config, testing, integrations, domain, api}; `org` as a top-level package would be a 7th layer. The helper is domain logic — landed next to `domain/invitations.py`, `domain/notifications.py`, `domain/action_log.py`, `domain/page_status.py` per existing convention. **Audit-corrected mechanics shipped:** SELECT `noctus_users.org_id` → return if set, else INSERT `public.organizations(is_personal=True, owner_id=user_id)` + INSERT/UPDATE `public.noctus_users` to attach (no `org_members` table — that assumption was falsified by §7.8 audit). Advisory-lock atomicity deferred to follow-up if races are observed. **Verification:** seed-lib 341/341 pass (was 331, +10 new); PF backend stays at 576+10. First test-run hit an `asyncio.get_event_loop()` interaction bug in pytest strict-asyncio mode; switched `_run` helper to `asyncio.run(coro)` for fresh-loop-per-test semantics. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 3+4 closed (no-op).** Audit invalidated original scoping. PF backend code was **already org-scoped before this project started** — every service constructor is `__init__(self, db_client, org_id: str)`, every router calls `get_current_user_org()` → `Service(db, org_id)`, and `dependencies.py` exports `get_current_user_org` that pulls `org_id` from `user.user_metadata`. Zero `user_id` references in `app/services/*.py`, `app/routers/*.py`, `app/dependencies.py`. The 2 test files mentioning `user_id` (`test_notificacoes_router.py`, `test_ai_router.py`) reference `public.notifications` + `public.ai_consent` payloads (cross-product user-attribution audit fields, not PF row access). Post-migration pytest run: **576 passed, 10 skipped** — exact match with pre-migration baseline. **Lesson:** original Phase 0 audit (2026-04-27) caught the live-DB-vs-migration-001 schema drift but didn't audit the *code* shape. The code was correct; the schema was the lagger. Phase 3 + Phase 4 sub-tasks ticked from Inventory + verification queries; no edits needed. Project size collapses from 8 phases → 5 effective phases (1+2, 3+4 no-op, 5a, 5b, 6, 7, 8). Moving directly to Phase 5a. | Claude Opus 4.7 |
| 2026-05-03 | **Phase 1+2 closed (collapsed).** Branching unavailable on Free-tier Supabase ($0.013/hr feature blocked); user chose direct-to-live apply given (a) 0 PF user-data rows in audit, (b) idempotent migration with `IF EXISTS` / `IF NOT EXISTS` guards everywhere, (c) atomic txn semantics from `apply_migration`. Drafted `products/personal-finance/backend/migrations/008_org_scoping_transition.sql` (390 lines) covering: `public.organizations.is_personal` addition, 12 PF op tables flipped (drop user_id FK + add org_id + backfill from `noctus_users.org_id` + SET NOT NULL + rename user_id → created_by + index swap + RLS rewrite), 4 child tables RLS-rewritten through parent, `invitations` policy normalized to `current_org_id()`. Applied → `{success:true}`. Post-apply verification: 16/16 PF policies use `current_org_id()`, 0 `auth.uid()` references survive, `is_personal` lives on 14 existing orgs (all defaulted to `false`), 19 categorias rows in `org_id IS NULL` orphan state (invisible by uniform RLS, scheduled for Phase 5b cleanup). Phase 2 sub-tasks ticked from same verification queries. **Backend code now broken against PF schema** — every `WHERE user_id=…` query will fail; that's the Phase 3 trigger. Pausing per PROJECT.md §10 directive: *"Especially critical between Phase 2 and Phase 3 — backend tests will go red between them; that's expected, not a regression."* | Claude Opus 4.7 |
