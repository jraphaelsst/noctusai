# Personal Finance — Org Scoping Migration

> **Living document.** Written for a zero-context reader. Every file path is named; every command is copy-paste ready.
>
> **🅿️ PARKED 2026-04-27 — explicitly "leave for later" per user directive.** Project is scoped + design-questioned but NOT executing. When work resumes, the next agent should: (1) interrogate the user on every §7 Open Question (each has my recommended default — user picks or overrides), then (2) start at Phase 1.

- **Created:** 2026-04-27
- **Last updated:** 2026-04-27
- **Status:** 📋 **PARKED** — design locked, awaiting user resume + §7 sign-off
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Project slug:** `pf-org-scoping-migration`
- **Project location:** `products/personal-finance/projects/pf-org-scoping-migration/` (single-product — schema + RLS + service refactor confined to PF).
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
4. **Personal-org bootstrap helper SHIPS SEED-FIRST, not pf-first.** Audit 2026-04-27 confirmed therapy does NOT have a personal-org bootstrap pattern today — meaning if PF writes the helper inside its own `app/services/onboarding_service.py`, the next product to need solo-org auto-creation (likely therapy when solo-therapist signup gets formalized) duplicates the logic. Instead: ship `noctusai_lib.org.ensure_personal_org(db, user_id, *, name_template, owner_role) -> org_id` (or similar) in seed lib FIRST as a Phase 0.5 (between user-resume gate and schema migration). PF's bootstrap then becomes a one-liner: `await ensure_personal_org(db, user_id, name_template="Pessoal — {email}")`. Same shape applies to therapy when it adopts solo mode.
5. **System defaults for `categorias` translate to `org_id IS NULL`.** Today's `user_id IS NULL = system default` becomes `org_id IS NULL = visible to all orgs`. RLS body: `(org_id = current_org_id() OR org_id IS NULL)` for read; system defaults are immutable for non-admin (admin-only `org_id IS NULL` writes — same pattern as ERP's `parametros_globais` if it exists, else a new convention).
6. **Migration 001 gets rewritten to the new truth — single source.** Not a `008_baseline_match.sql` strangler; the legacy fictional 001 is replaced. Any agent reading 001 going forward sees the deployed schema. Old version archived in git history (the commit closing this project), nowhere else.
7. **Phase by phase, halt-able at every boundary.** Each phase is independently shippable; pause between any two if scope creep surfaces. Backend tests must stay green at every phase boundary.
8. **No frontend rewrite.** TanStack Query hooks today read RLS-filtered data — RLS does the org-switch silently. Frontend touches limited to (a) anywhere a hook explicitly threads `user_id` as a filter (rare), (b) the new bootstrap flow for individual signup if a UI prompt is needed.

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

### RLS shape (uniform)

```sql
CREATE POLICY "transacoes_org_scoped" ON "personal-finance".transacoes
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id());

-- categorias: special case for system defaults
CREATE POLICY "categorias_org_scoped" ON "personal-finance".categorias
    FOR ALL TO authenticated
    USING (org_id = public.current_org_id() OR org_id IS NULL);
```

### Files that will change

| File | Change |
|---|---|
| `products/personal-finance/backend/migrations/001_personal_finance.sql` | **Rewrite to match new live state.** ~13 tables flip from `user_id NOT NULL` to `org_id NOT NULL + created_by NULL`. Drop `user_org_id()`. RLS rewritten. |
| `products/personal-finance/backend/migrations/008_org_scoping_transition.sql` | **New.** ALTER TABLE ADD COLUMN org_id; backfill (per §7.1); ALTER TABLE DROP COLUMN user_id (or RENAME → created_by per §7.4); DROP/CREATE POLICY per table. Applied via Supabase MCP. |
| `products/personal-finance/backend/app/services/*.py` | Every service. Constructor takes `org_id`; queries filter `org_id`. |
| `products/personal-finance/backend/app/dependencies.py` | If exists: stop fetching `user_id`-bound dependencies; use `noctusai_seed.dependencies.get_org_id`. |
| `products/personal-finance/backend/app/main.py` | Org-scoping middleware — already exists via seed, confirm wired. |
| `products/personal-finance/backend/tests/**/*.py` | Every test fixture. `user_id` → `org_id`. |
| `seed/backend/lib/noctusai_lib/org/personal.py` (new) | **Seed-side** `ensure_personal_org(db, user_id, *, name_template, owner_role) -> org_id` helper. Idempotent: returns existing org_id if user already has membership; otherwise atomically creates `public.organizations` row + adds user to `public.org_members` + returns new org_id. Tested in `seed/backend/lib/tests/test_org_personal.py`. |
| `products/personal-finance/backend/app/services/onboarding_service.py` (new or extended) | Thin per-product wrapper that calls `ensure_personal_org(...)` from the seed helper. The PF-specific concern (when to invoke + the `name_template="Pessoal — {email}"` choice) lives here; the org-creation mechanics live in seed. |
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

- [ ] User signals project resume.
- [ ] §7.1 — backfill strategy → answer captured.
- [ ] §7.2 — `categorias` system-default semantics → answer.
- [ ] §7.3 — multi-org users → answer.
- [ ] §7.4 — drop `user_id` or keep as `created_by` → answer.
- [ ] §7.5 — auto-create personal org for new signups → answer.
- [ ] §7.6 — backfill cardinality check → run `SELECT count(distinct user_id), count(*) FROM "personal-finance".transacoes` to set expectations on backfill scale.
- [ ] §7.7 — `pf-schema-drift-reconciliation` artifacts → confirm closed (already closed 2026-04-27 per pre-park).

**Improvements:** _(captured during execution; synthesized at phase close)_

---

### Phase 1 — Schema migration draft + dry-run

- [ ] Write `008_org_scoping_transition.sql` based on §7 answers. Cover: ADD COLUMN org_id; backfill (CTE join against existing org membership tables); ADD COLUMN created_by from old user_id (per §7.4); DROP COLUMN user_id; ALTER COLUMN org_id SET NOT NULL post-backfill; DROP/CREATE POLICY per table.
- [ ] Dry-run on a Supabase branch via `mcp__claude_ai_Supabase__create_branch` → `apply_migration` → run sample queries against the branch to confirm RLS behavior. Reset / delete branch after verification.

**Improvements:** _(captured during execution; synthesized at phase close)_

---

### Phase 2 — Backfill execution + RLS flip on live

- [ ] Apply Phase 1's migration via `mcp__claude_ai_Supabase__apply_migration` against the live DB. Confirm `{success: true}`.
- [ ] Re-run audit Q2 from `pf-schema-drift-reconciliation` Phase 0 — confirm every PF policy now uses `org_id = current_org_id()`.
- [ ] Spot-check sample row reads via `execute_sql`: pre-existing user data is reachable from their personal org context.

**Improvements:** _(captured during execution; synthesized at phase close)_

---

### Phase 3 — Backend service refactor

- [ ] Inventory every PF service file + the `user_id` references it threads. Produce delta list.
- [ ] Per service: change constructor / dependencies to take `org_id` instead of `user_id`. Update queries to filter `org_id`. Update inserts to set `org_id` from current context + `created_by` from `current_user.id`.
- [ ] Routers stay mostly unchanged — they thread the dependency-injected `org_id` to services.

**Improvements:** _(captured during execution; synthesized at phase close)_

---

### Phase 4 — Test fixture updates

- [ ] Run `pytest tests/ -q` — capture failure count + buckets.
- [ ] Update `conftest.py` fixtures: replace per-test `user_id` injection with `org_id` injection. Helper to seed a test org + add the test user as member if not already.
- [ ] Per-failing-test: rebind data setup from `{"user_id": user.id}` to `{"org_id": org.id, "created_by": user.id}`.
- [ ] Confirm baseline 573+10 returns to green (or higher if tests are added during refactor).

**Improvements:** _(captured during execution; synthesized at phase close)_

---

### Phase 5a — Seed-side `ensure_personal_org` helper (BLOCKS Phase 5b)

Per §3.4 — ship the helper seed-first so therapy and any future product inherit instead of duplicating.

- [ ] Add `seed/backend/lib/noctusai_lib/org/personal.py` with `async def ensure_personal_org(db, user_id, *, name_template, owner_role="owner") -> str`. Behavior: lookup `public.org_members` for user; if exists, return that org_id; else atomically `INSERT public.organizations` + `INSERT public.org_members` + return new org_id. Use Postgres advisory lock keyed on user_id to make concurrent first-logins safe.
- [ ] Re-export from `noctusai_lib.org` package init.
- [ ] Add seed-lib unit tests (`seed/backend/lib/tests/test_org_personal.py`): user-already-has-membership returns existing org_id; user-without-membership creates org + member row + returns new org_id; concurrent calls produce a single org (advisory lock holds); name_template substitution works.
- [ ] Update `KB § 04-SHARED-LIBRARY § auth/` (or new `org/` subsection) — document the helper.

**Improvements:** _(captured during execution; synthesized at phase close)_

---

### Phase 5b — PF-side bootstrap wiring

(Depends on §7.5 answer + Phase 5a closing.)

- [ ] If §7.5 = A: create `app/services/onboarding_service.py` — calls `await ensure_personal_org(db, user_id, name_template="Pessoal — {email}")` on first PF login. The PF-specific concerns (when to invoke + the name template) live here; the org-creation mechanics stay in seed.
- [ ] One-time backfill: for every existing PF user without an org, run the same helper as a one-shot (idempotent — already-has-org returns existing id).
- [ ] Tests: PF wrapper invokes the seed helper with the right name_template; backfill is idempotent.

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
