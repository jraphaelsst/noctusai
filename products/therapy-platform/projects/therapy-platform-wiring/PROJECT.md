# Therapy-Platform Wiring — Project Document

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project document evolves. Revise phases, fold in
> optimizations, update the Change Log. See
> `CLAUDE.md → Engineering Philosophy → Projects are living documents`.
>
> **Slug rationale (honest-scope check):** Originally discussed as
> `therapy-admin-console-gap` (intent=`gap`: narrow holes). Scope widened during
> interrogation to close every scaffolding gap across the whole `therapy-platform`
> product — admin **plus** therapist, patient, clinic, and public surfaces —
> which is an end-to-end *wiring* job, not a couple of gaps. Renamed per the
> naming convention in `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md §8`.

- **Created:** 2026-04-20
- **Last updated:** 2026-04-20
- **Status:** Design drafted — awaiting user sign-off before Phase 0 kicks off
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com) · Claude Opus 4.7
- **Related docs:**
  - `CLAUDE.md § Engineering Philosophy` — behavioral rules, loaded every session
  - `KNOWLEDGE-BASE/CONTEXT/02-LANDSCAPE.md` — product surface inventory
  - `KNOWLEDGE-BASE/CONTEXT/backend/06-THERAPY.md` — therapy backend spec
  - `KNOWLEDGE-BASE/CONTEXT/frontend/04-THERAPY.md` — therapy frontend spec
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/project-execution.md` — cadence, naming, tests-with-code
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/proposals-and-improvements.md` — phase-end protocol
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/database-rls.md` — migration discipline
  - `KNOWLEDGE-BASE/CONTEXT/PATTERNS/lgpd.md` — personal-data guardrails
  - `products/therapy-platform/MASTER-PROMPT.md` — the agent-facing product contract
- **Project slug:** `therapy-platform-wiring`

---

## 1. Context & Purpose

The `therapy-platform` product was shipped with a frontend that is substantially complete and a backend that is only partially wired. Multiple admin pages crash, 404, or 405. Several non-admin flows (therapist, patient, clinic) likely share the same class of defect: scaffolded UI hooks pointing at endpoints that are either missing, HTTP-method-mismatched, or returning raw DB rows instead of the DTO the frontend `types/` declares.

This was surfaced today (2026-04-20) by three admin-console reports from the user:

1. `/admin/terapeutas` crashed at `getInitials(t.nome)` because `nome` is undefined — backend returned raw `therapist_profiles` rows with no join to `auth.users`. *(Fixed ad-hoc in the same session — becomes Phase 1's reference pattern.)*
2. `/admin/agendamentos` toasts `[404] Not Found` — `GET /api/admin/appointments` is not defined in the backend router.
3. `/admin/financeiro` crashes with `A <Select.Item /> must have a value prop that is not an empty string` and toasts `[405] Method Not Allowed` — Radix Select misuse + `GET /api/admin/financials/commissions` is not routed (only the POST counterpart exists). *(Select fix applied ad-hoc — the 405 and sibling missing GETs fold into this project.)*

These three reports are symptoms of a product built with "frontend first, backend when needed" velocity — the common failure mode for a seed-inheriting product that grew faster than the platform around it. The purpose of this project is to **sweep every therapy-platform surface end-to-end, close every gap at the layer it belongs to (seed vs. product vs. schema), and land with tests and a clean build.** When this project finishes, any logged-in user of any role should be able to navigate any reachable page in the therapy-platform without a 4xx toast, a `TypeError` from a DTO mismatch, or a RLS surprise.

The win looks like: `vite build` clean, `pytest tests/` clean for backend, every `/admin/*` page loads real data in under one second with a 200, and the same goes for every `/therapist/*`, `/patient/*`, `/clinic/*`, and public route.

---

## 2. Confirmed constraints

User answers captured during interrogation (2026-04-20). **Future agents inherit the reasoning, not just the outcome.**

- **Scope breadth** — widest (A ⇒ B ⇒ C): fix known regressions, then sweep the admin console end-to-end, then close pre-existing scaffolding debt, then widen to the whole therapy-platform product (therapist/patient/clinic/public surfaces). *(Rules out a narrow "just appointments + financials" scope. Forces Phase 0 discovery to be rigorous — the rest of the project depends on a concrete gap inventory.)*
- **Display-name resolver** — absorb into seed (`noctusai_lib`), not inline per page. *(Rules out the per-row `get_user_by_id` pattern used in the ad-hoc therapists fix. Treat the ad-hoc fix as Phase 1's starting point and replace it once the shared helper ships.)*
- **Reject flow** — include the full wiring in this project (migration, service, list-endpoint status derivation, admin UI, test coverage). *(See §3 "Reject flow primer" for the current breakage and target state.)*
- **Tests** — always, per the three-layer discipline in `CONTEXT/PATTERNS/testing.md`. Not a per-phase decision. *(A phase without its tests is `⏳ (tests deferred)`, not `✅`.)*
- **Cadence** — phase-by-phase, pause after each, no auto-advance. The user will explicitly say "continue" / "do phase N" / "ram through 2-3" when bulk execution is wanted. *(Already documented in `project-execution.md §3`; verified during interrogation.)*
- **Seed sync** — patterns worth promoting mid-project (identity resolver, admin DTO-mapper helpers, reject-audit column scaffolding) land as **phase-end proposals** via `noctusai_file_proposal(project="therapy-platform-wiring", …)`. Reviewer triages separately; this project does not block waiting for seed promotion. *(Keeps this project shippable independently of seed maturation.)*
- **"The platform" in the widest-scope prompt** — interpreted as the `therapy-platform` product in full, not the whole NoctusAI multi-product repository. *(Other products are out of scope; seed touches are limited to the one identity-resolver capability and any other helpers discovered as genuinely generic.)*

---

## 3. Design principles

How we're approaching *this specific problem* on top of the platform-wide `CLAUDE.md` rules.

1. **Fix at the layer of the cause.** If two admin pages need `nome`/`email` from `auth.users`, the solution is a shared resolver — not two duplicated joins. Seed-absorption precedes duplication. The ad-hoc therapists fix applied this *inline*; Phase 1 consolidates.
2. **No band-aids.** We do not add `?? ''` guards to tolerate bad DTOs; we make the DTO correct at the backend boundary. The frontend consumes typed data or the endpoint is broken and Phase 0 catches it.
3. **LGPD-first on every personal-data endpoint.** Admin endpoints that aggregate patient/therapist data get a `noctusai_lgpd_flag` call the first time they touch identity/clinical/financial data in a new shape, per `CONTEXT/PATTERNS/lgpd.md`. The flag doesn't block — it puts the concern in the triage queue.
4. **Migrations and applied SQL stay in lockstep.** Every DDL we apply via `mcp__claude_ai_Supabase__apply_migration` lives first as `products/therapy-platform/backend/migrations/NNN_<name>.sql`. Schema drift is a rule violation, not a tradeoff.
5. **Tests land in the same phase as the code.** Three-layer discipline, no exceptions.
6. **Discovery is an artifact, not a vibe.** Phase 0 produces a checked-in gap table in this document. Phases 2-9 reference rows in that table — no phantom scope.

### Reject flow primer *(per constraint #3 — user asked for an explanation)*

**Current state today (2026-04-20):**

The therapy-platform models new therapists and new clinics as applications with a review lifecycle: `pendente → aprovado | rejeitado | suspenso`. The admin console's `/admin/terapeutas` and `/admin/clinicas` pages surface this as four tabs.

- `pendente`: user applied, no admin has acted.
- `aprovado`: admin clicked **Aprovar** → service sets `is_approved = true`. Works end-to-end.
- `rejeitado`: admin clicked **Rejeitar**, provided a reason → service is *supposed to* write the reason + actor + timestamp to the profile. **This is where the wiring is broken.**
- `suspenso`: previously approved, now deactivated → `is_active = false`. Works end-to-end.

**The break (caught during the admin-therapists fix earlier today):**

- `products/therapy-platform/backend/app/services/admin_service.py:84` writes `{"is_approved": False, "rejection_reason": reason}` to `therapist_profiles` / `clinics`.
- **No migration ever created the `rejection_reason` column.** Grep across `products/therapy-platform/backend/migrations/*.sql` returns zero hits.
- Therefore: clicking **Rejeitar** in the admin UI produces a Supabase error (undefined_column) → the request 500s. The UI never received a successful reject path.
- There is also no `rejected_at` / `rejected_by` — the audit trail (*who rejected this, and when?*) is missing entirely. LGPD and platform-admin accountability both want those fields.
- The admin list endpoint cannot derive `rejeitado` status because it has nothing to read from. The "Rejeitado" tab is empty in principle even if the above worked.
- The admin detail page has no "Rejection reason" surface — the admin clicking into a rejected profile cannot see the reason they (or a predecessor) gave.

**Target state after Phase 5:**

1. New migration `007_rejection_audit.sql`:
   - Adds `rejection_reason TEXT, rejected_at TIMESTAMPTZ, rejected_by UUID REFERENCES auth.users(id)` to `therapy.therapist_profiles` and `therapy.clinics`.
   - RLS policies unchanged (the existing `service_role_bypass` + `platform_admin` select policies already cover reading these columns).
   - Applied via `mcp__claude_ai_Supabase__apply_migration` **after** the file is committed, per the "MCP migrations mirror the file" rule.
2. `reject_entity()` service updates:
   - Writes `rejection_reason`, `rejected_at = now()`, `rejected_by = admin_id`.
   - Idempotent re-reject overwrites the reason (latest reject wins) — audit trail remains via `audit_logs` if/when that's a separate concern.
3. `approve_entity()` service update:
   - Re-approval *clears* `rejection_reason`/`rejected_at`/`rejected_by` — we decided (§7) the audit trail lives in application logs, not in the profile row. The profile reflects *current* state; history goes to logs.
4. `_derive_therapist_status()` / `_derive_clinic_status()`:
   - Return `rejeitado` when `rejection_reason IS NOT NULL AND is_approved = false`.
5. List endpoint filter:
   - `status=rejeitado` query resolves to `.eq("is_approved", False).not_.is_("rejection_reason", "null")` — the "empty fallback" hack from the ad-hoc fix goes away.
6. Admin detail view:
   - `/admin/terapeutas/:id` and `/admin/clinicas/:id` render `rejection_reason`, `rejected_at`, and (resolved through the new identity resolver from Phase 1) the *name* of the admin who rejected.
7. Tests:
   - `pytest tests/routers/test_admin_router.py` — cover pendente→rejeitado, rejeitado→aprovado (re-approval clears), aprovado→suspenso→aprovado.
   - `pytest tests/services/test_admin_service.py` — direct service-layer coverage for the three reject-audit columns being written and cleared correctly.
   - Migration idempotency test (re-applying the migration is a no-op).

**Why include it in this project instead of deferring:**
The admin UI already *shows* a Rejeitar button and a Rejeitado tab. Leaving the reject flow broken means the widest-scope sweep (closing *every* gap) has a visible unfinished corner. Per the "No incomplete commits" rule, the admin surface is not `✅` until reject works.

---

## 4. Scope

**In scope:**

- Every `therapy-platform` backend endpoint that a frontend hook calls. Includes: `/api/admin/*`, `/api/therapists/*`, `/api/patients/*`, `/api/clinics/*`, `/api/appointments/*`, `/api/invoices/*`, `/api/reviews/*`, `/api/conversations/*`, `/api/longitudinal/*`, `/api/matching/*`, `/api/sessions/*`, `/api/wallets/*`, and any others Phase 0 discovers.
- Every therapy-platform migration needed to support the above (notably the reject-audit migration; anything else Phase 0 discovers).
- The shared identity resolver in `seed/lib/backend/noctusai_lib/` (the one cross-product absorption this project is committing to).
- Frontend corrections required to consume corrected DTOs or fix pre-existing UI bugs uncovered during the sweep (Radix Select misuse, `Avatar` initial helpers, status-badge resolvers, etc.).
- Tests (unit + router + any integration paths) landing in the same phase as the code they cover.
- LGPD awareness: `noctusai_lgpd_flag` calls where new endpoints aggregate personal data in shapes not previously flagged.
- End-to-end verification: build + pytest + manual browser QA of the golden paths on every surface we touched.

**Out of scope (for now — with reason):**

- **Other products** (erp-imobiliario, core, adconnect, seed-the-template, etc.) — different projects, different slugs. *(This project is scoped to `therapy-platform`. Seed touches are limited to the identity-resolver helper per constraint #2.)*
- **UX redesigns** — if a page is ugly but works end-to-end, it stays. *(This is a wiring project, not a redesign.)*
- **New features** — no capability we aren't already carrying as scaffolded UI. If a hook points at `/api/admin/moderation-queue` and neither the backend nor a design exists, Phase 0 flags it and it becomes a separate future project. *(Avoid scope creep into fresh product work.)*
- **Payments / Stripe deep integration** beyond what's already scaffolded. Transactions, payouts, commissions exist — we wire the existing surface, not build new billing flows. *(Deeper billing work is a `-hardening` project on its own.)*
- **LiveKit / WebRTC depth** — we wire the session/video endpoints that exist. Real-time quality tuning, recording, or new RTC features are a separate project. *(Same reasoning.)*
- **Seed abstractions beyond the identity resolver** — if we spot another seed-worthy pattern (e.g., "admin DTO mapper"), we capture it in a phase-end proposal and let the reviewer schedule it as a separate seed project. *(Keeps this project shippable without waiting for seed maturation.)*
- **AI / transcription / clinical-summary pipelines** — only the wiring; model selection, prompt tuning, and pipeline restructuring are AI-expansion territory.

---

## 5. Architecture / Data Model

*Populated by Phase 0 in its entirety. This section starts with the shapes we already know from the interrogation; everything else lands as Phase 0's output.*

### 5.1 Shared identity resolver *(delivered by Phase 1)*

```
seed/lib/backend/noctusai_lib/identity/
├── __init__.py          # re-exports UserIdentity, fetch_user_identities
├── resolver.py          # implementation
└── types.py             # UserIdentity dataclass
```

```python
@dataclass(frozen=True)
class UserIdentity:
    user_id: str
    nome: str          # display name; falls back to email-local-part, then "Usuário"
    email: str         # empty string if auth lookup failed (never None — simpler downstream)
    foto_url: str | None = None

    @property
    def display_name(self) -> str:
        return self.nome or self.email.split("@")[0] or "Usuário"


async def fetch_user_identities(
    db: Any,                  # admin-scoped supabase client
    user_ids: Iterable[str],
) -> Dict[str, UserIdentity]:
    """Bulk resolve auth.users → UserIdentity, keyed by user_id.

    Implementation choice (Phase 1 decides based on benchmarking):
      (a) single list_users(per_page=N, page=...) walk, filter in memory
      (b) parallel asyncio.gather of get_user_by_id calls
      (c) direct `auth.users` SELECT via admin client (if RLS permits)

    Missing IDs return UserIdentity with blank nome/email — callers get a
    deterministic shape for every requested ID.
    """
```

### 5.2 Reject-audit migration *(delivered by Phase 5)*

`products/therapy-platform/backend/migrations/007_rejection_audit.sql`:

```sql
ALTER TABLE therapy.therapist_profiles
  ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
  ADD COLUMN IF NOT EXISTS rejected_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS rejected_by      UUID REFERENCES auth.users(id);

ALTER TABLE therapy.clinics
  ADD COLUMN IF NOT EXISTS rejection_reason TEXT,
  ADD COLUMN IF NOT EXISTS rejected_at      TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS rejected_by      UUID REFERENCES auth.users(id);

-- No RLS changes required: the existing platform_admin select policies cover
-- these columns, and the service_role_bypass policy covers writes from the
-- reject_entity service path.
```

### 5.3 Admin list DTO pattern

Every `/api/admin/<resource>` list endpoint returns `{ data: <Resource>[], pagination: { page, page_size, total, total_pages } }` where `<Resource>` exactly matches the frontend's `types/` declaration. No raw DB rows cross the HTTP boundary. Mappers live in `app/services/admin_service.py` (or a sibling file if they balloon).

### 5.4 Inventory *(populated by Phase 0)*

*Phase 0 deliverable: a table of every frontend → backend call, with status: `OK`, `404`, `405`, `DTO-mismatch`, `RLS-hole`, `missing-migration`, `missing-tests`. Used as the work list for Phases 2-9.*

---

## 6. Implementation phases

Phases are **suggestive, not strict.** Reorder, split, merge, or discover new phases as work progresses. Phases 6-9 in particular are placeholders whose shape is decided by Phase 0's output.

**Phase status-icon convention** (see `CONTEXT/PATTERNS/project-execution.md §1`):

| Icon | Meaning |
|---|---|
| _(none)_ | Pending — not started |
| ⏳ | In progress / partially done |
| ✅ | Complete — every sub-task ticked |
| ❌ | Blocked or failed — see Change Log |

**Improvement capture happens during steps. Proposal authoring happens at end of phase.** One bundled proposal per phase, filed via `noctusai_file_proposal(project="therapy-platform-wiring", …)` → lands in `products/therapy-platform/projects/therapy-platform-wiring/proposals/`.

---

### Phase 0 — Discovery & inventory

Produces the concrete gap table in §5.4. Every subsequent phase references rows from this table — no phantom scope.

- [ ] Enumerate every `api.get|post|put|patch|delete` call in `products/therapy-platform/frontend/src/hooks/` and `.../src/pages/`. Capture: URL, HTTP verb, caller hook/page, expected response shape (from `types/`).
- [ ] Enumerate every route decorator (`@router.get|post|put|patch|delete`) in `products/therapy-platform/backend/app/routers/*.py`. Capture: URL, HTTP verb, response shape (return value + `response_model` if set).
- [ ] Join the two lists → produce the gap table in §5.4 with one row per frontend call. Status values: `OK`, `404` (no backend route), `405` (verb mismatch), `DTO-mismatch` (shapes differ), `needs-audit` (shape unclear without running).
- [ ] Cross-reference every reference in services to a DB column against `products/therapy-platform/backend/migrations/*.sql`. Record every column that code writes/reads but no migration creates. (At minimum: `rejection_reason`, `rejected_at`, `rejected_by` — we already know. Phase 0 looks for more.)
- [ ] Run `python mcp/noctusai/cli.py --review products/therapy-platform` (keeper observation pass). Capture the proposal set it files into `products/therapy-platform/proposals/` as additional signal (not binding — reviewer triages separately).
- [ ] **Rewrite phases 2-9 in this file based on the gap table.** Phases 6-9 (non-admin) get concrete sub-tasks. If a row in the gap table turns out to be out-of-scope (e.g. references a page that itself should be deleted), log it in §7 Open questions and skip.
- [ ] Log Phase 0 completion in §11.

**Deliverable:** §5.4 is populated; phases 2-9 carry concrete work items instead of placeholders. Capture **Improvements** during the phase. File the phase-end proposal **before** flipping to ✅.

---

### Phase 1 — Shared identity resolver in `noctusai_lib`

Seed absorption for the "I need `nome`/`email` from `auth.users` given a list of UUIDs" pattern. The ad-hoc admin-therapists fix (landed earlier today in `products/therapy-platform/backend/app/services/admin_service.py::_fetch_user_identity`) is this phase's starting point — Phase 1 replaces it with the seed helper.

- [ ] Design the module layout per §5.1. Decide between list_users / get_user_by_id / direct `auth.users` select (benchmark page_size=100 on a realistic dataset via the Supabase MCP).
- [ ] Implement `UserIdentity` dataclass + `fetch_user_identities()` in `seed/lib/backend/noctusai_lib/identity/`.
- [ ] Unit tests in `seed/lib/backend/tests/test_identity_resolver.py` — happy path, missing IDs, empty input, mocked auth client.
- [ ] Update `CONTEXT/04-SHARED-LIBRARY.md` catalog section with the new helper.
- [ ] Replace `products/therapy-platform/backend/app/services/admin_service.py::_fetch_user_identity` with a call to the new helper. Keep the `_therapist_row_to_dto` mapper local to the service.
- [ ] Re-run `pytest products/therapy-platform/backend/tests/routers/test_admin_router.py` — must stay green.
- [ ] Run `python mcp/noctusai/cli.py --review seed` and `--review products/therapy-platform` after the change.
- [ ] Capture **Improvements** during the phase. File the phase-end proposal before flipping to ✅.

---

### Phase 2 — Admin Tier A: known regressions

Fix every `404` and `405` row in the gap table. At minimum we already know:

- `GET /api/admin/appointments` — missing entirely (Appointments page).
- `GET /api/admin/financials/summary` — missing.
- `GET /api/admin/financials/transactions` — missing.
- `GET /api/admin/financials/commissions` — wrong verb (only POST exists).
- `DELETE /api/admin/financials/commissions/{id}` — missing.
- Any other rows Phase 0 classified `404` or `405`.

- [ ] For each missing/wrong-verb endpoint: implement in `app/routers/*.py`, add a service-layer function in `app/services/*.py` (use the Phase 1 identity resolver for any display-name needs), return the DTO the frontend expects.
- [ ] For Appointments: the DTO needs `patient_name`, `therapist_name`, `clinic_name` — Phase 1 resolver handles the first two; `clinic_name` joins `therapy.clinics`.
- [ ] For Financials: decide whether `/summary` aggregates live or reads a materialized view (Phase 0 output will tell us what shape the frontend expects).
- [ ] Router tests for every new/updated endpoint — status code + shape + auth boundary (admin vs. therapist vs. patient vs. unauthed).
- [ ] Service unit tests for the non-trivial aggregation logic (`/summary` math, `/commissions` GET shape).
- [ ] Manual QA: navigate `/admin/agendamentos` and `/admin/financeiro` in the browser; confirm zero toasts, data renders.
- [ ] Run `python mcp/noctusai/cli.py --review products/therapy-platform`.
- [ ] Capture **Improvements**. File the phase-end proposal before flipping to ✅.

---

### Phase 3 — Admin Tier B: DTO normalization sweep

For every admin list endpoint the frontend calls, return the typed DTO. Raw DB rows do not cross the boundary.

At minimum: `/api/admin/clinics`, `/api/admin/patients`, `/api/admin/reports`, `/api/admin/reviews/flagged`, `/api/admin/blocks`, `/api/admin/support/conversations`. Phase 0 confirms the full list.

- [ ] For each endpoint: add/update a `_row_to_dto` mapper. Mirror the shape declared in `products/therapy-platform/frontend/src/types/`.
- [ ] Use Phase 1 identity resolver for every column where the DTO demands a display name/email that lives in `auth.users`.
- [ ] Accept the query filter the frontend already sends (status, busca, date ranges). Translate to DB predicates at the service layer.
- [ ] Add/update router tests per endpoint — auth boundary + happy path + one filter combination.
- [ ] Add/update service unit tests per mapper — covers the DTO contract directly without touching HTTP.
- [ ] Manual QA: walk each admin page, confirm data renders, tabs filter correctly.
- [ ] Run the keeper review pass.
- [ ] **Improvements** + phase proposal before ✅.

---

### Phase 4 — Admin Tier C: pre-existing scaffolding debt

Everything Phase 0 surfaced that Phases 2-3 didn't fold in. Likely candidates (confirmed by Phase 0):

- [ ] RLS hole audit across `therapy.*` admin-read paths. Compare the "who can select" policies against what the admin endpoints actually read.
- [ ] `search_path` hardening on any RPC that admin endpoints call.
- [ ] Migration drift: any column referenced in code but absent from `migrations/*.sql` that isn't the reject-audit set (that set is Phase 5).
- [ ] Missing admin-side tests — pages that had no router test at all before this project.
- [ ] Any admin endpoint that calls an N+1 pattern we didn't already collapse via Phase 1.
- [ ] `noctusai_lgpd_flag` calls on the new endpoints that aggregate personal data in novel shapes.
- [ ] Keeper review + **Improvements** + phase proposal before ✅.

---

### Phase 5 — Reject flow wiring

End-to-end reject. See §3 "Reject flow primer" for the target shape.

- [ ] Write `products/therapy-platform/backend/migrations/007_rejection_audit.sql` per §5.2. Commit with the migration file (do NOT apply yet).
- [ ] Apply via `mcp__claude_ai_Supabase__apply_migration` — migration file and applied state stay in lockstep.
- [ ] Update `reject_entity()` service: write `rejection_reason`, `rejected_at = now()`, `rejected_by = admin_id`. Idempotent re-reject.
- [ ] Update `approve_entity()` service: clear the three reject-audit columns on re-approval.
- [ ] Update `_derive_therapist_status()` / `_derive_clinic_status()` mappers (from Phase 1/2): return `rejeitado` when `rejection_reason IS NOT NULL AND is_approved = false`.
- [ ] Update admin list endpoints: `status=rejeitado` resolves to `.eq("is_approved", False).not_.is_("rejection_reason", "null")` — remove the "empty fallback" hack from the ad-hoc fix.
- [ ] Admin detail pages (`/admin/terapeutas/:id`, `/admin/clinicas/:id`): render `rejection_reason`, `rejected_at`, `rejected_by` (resolved to display name via Phase 1).
- [ ] Router tests: pendente→rejeitado with reason, rejeitado→aprovado clears audit columns, aprovado→suspenso→aprovado leaves audit columns clear.
- [ ] Service unit tests for `reject_entity` and `approve_entity` audit-column invariants.
- [ ] Migration idempotency test (re-applying is a no-op).
- [ ] `noctusai_lgpd_flag` call: rejection reasons may contain free-text about the applicant — acceptable under Art. 11 only with a retention policy. Flag for LGPD review even if the flag doesn't block.
- [ ] Manual QA: reject a pending therapist in the browser, verify the Rejeitado tab shows them with the reason, re-approve, verify they move back to Aprovado with audit columns cleared.
- [ ] Keeper review + **Improvements** + phase proposal before ✅.

---

### Phase 6 — Therapist portal wiring *(placeholder — shape set by Phase 0)*

Likely scope: `/therapist/pacientes`, `/therapist/agenda`, `/therapist/sessoes`, `/therapist/financeiro`, `/therapist/avaliacoes`, `/therapist/perfil`. Phase 0 produces the concrete task list.

- [ ] *(Populated by Phase 0.)*

---

### Phase 7 — Patient portal wiring *(placeholder)*

Likely scope: `/patient/home`, `/patient/matching`, `/patient/agenda`, `/patient/sessoes`, `/patient/diario`, `/patient/pagamentos`, `/patient/perfil`. Phase 0 produces the concrete task list.

- [ ] *(Populated by Phase 0.)*

---

### Phase 8 — Clinic portal wiring *(placeholder)*

Likely scope: `/clinic/terapeutas`, `/clinic/pacientes`, `/clinic/financeiro`, `/clinic/configuracoes`, `/clinic/branding`. Phase 0 produces the concrete task list.

- [ ] *(Populated by Phase 0.)*

---

### Phase 9 — Public surfaces + auth wiring *(placeholder)*

Likely scope: landing/marketing routes (if routed through the same Vite app), `/login`, `/signup`, password reset, email verification, OAuth callbacks, invitation-acceptance flows. Phase 0 produces the concrete task list.

- [ ] *(Populated by Phase 0.)*

---

### Phase 10 — End-to-end verification

- [ ] `cd products/therapy-platform/frontend && npx vite build` — clean.
- [ ] `cd products/therapy-platform/backend && python -m pytest tests/ -q` — full suite green.
- [ ] `cd seed/lib/backend && python -m pytest tests/` — seed tests green (identity resolver, anything else Phase 1 touched).
- [ ] `cd mcp/noctusai && python -m pytest tests/` — MCP toolkit tests green.
- [ ] `python mcp/noctusai/cli.py --review products/therapy-platform` — final keeper pass; triage any remaining proposals.
- [ ] Manual browser QA of the golden path per surface: admin, therapist, patient, clinic, public. Record any regressions in §11 and either fix inline or open a follow-up project.
- [ ] Update `products/therapy-platform/MASTER-PROMPT.md` with any contract changes (new shared helpers, new DTO conventions, reject-flow semantics).
- [ ] Update `KNOWLEDGE-BASE/CONTEXT/backend/06-THERAPY.md` and `frontend/04-THERAPY.md` to reflect current state.
- [ ] Run `python scripts/update-kb-counts.py` and `bash scripts/verify-kb-sync.sh`.
- [ ] Final **Improvements** block + phase proposal + Change Log entry before ✅.

---

## 7. Open questions

Unresolved items. Each tagged with *when it needs an answer* and *who answers*.

1. **Should `rejection_reason` be retained after re-approval?** *(Phase 5.)* — Current draft says no (cleared on re-approval; audit trail lives in logs). Confirm with user before Phase 5 ships. Decided by: user.
2. **`fetch_user_identities` implementation choice — list_users walk vs. parallel get_user_by_id vs. direct `auth.users` SELECT?** *(Phase 1.)* — Decide by benchmarking on a realistic page (100 IDs). Decided by: Claude during Phase 1, with the chosen implementation + benchmark numbers logged in the Phase 1 Improvements block.
3. **Does Phase 0 discover any admin page that should simply be deleted rather than wired?** *(Phase 0.)* — If yes, delete and log in §11. Decided by: user, with Claude's proposal.
4. **Are there therapy-platform surfaces that don't route through Vite at all?** *(Phase 0.)* — If there's e.g. a standalone marketing site, it's out of scope for this project. Decided by: Claude during Phase 0, flagged to user if ambiguous.
5. **LGPD stance on rejection reasons (free-text may contain applicant PII).** *(Phase 5.)* — Need a retention policy. Default: 90-day retention post-rejection, then null-out `rejection_reason` via a scheduled job. Decided by: user.
6. **Does the identity resolver belong under `noctusai_lib.identity/` or `noctusai_lib.auth/`?** *(Phase 1.)* — `identity` is more honest (it doesn't do auth, it resolves names); `auth` is where users look. Decided by: Claude during Phase 1.
7. **Avatar fallback chain** — today the Therapists page uses initials from `nome`. If `nome` comes out empty (e.g. user signed up with only an email), what do we show? Email-local-part? A generic silhouette? Decided by: Claude during Phase 2, design-logged in Improvements.

---

## 8. Dependencies & blockers

- **Supabase MCP access** — already granted via blanket approval (`feedback_supa_mcp_proactive`). Used for Phase 5 migration application and Phase 0 schema inspection.
- **`auth.admin` API access from the admin-client path** — Phase 1 depends on this. Already used elsewhere in the codebase (`auth_service.py`), no new access needed.
- **Baseline test stability** — every phase re-runs the prior phase's tests. A phase that destabilizes a previously-green test suite is a regression, not a normal revision.
- **Admin test fixtures may need updating** — once DTO shapes change, the mock `SAMPLE_*` fixtures in `tests/routers/test_admin_router.py` need to reflect the new shape. Track this inline per phase.

---

## 9. Success criteria

- **0 `404`s, 0 `405`s on every navigable URL** for a logged-in user with each role (admin, therapist, patient, clinic-admin) across the therapy-platform frontend. Verified manually in Phase 10.
- **Every admin list endpoint** returns the typed DTO declared in `products/therapy-platform/frontend/src/types/` (no raw DB rows cross the boundary).
- **Reject flow works end-to-end**: a pending therapist can be rejected with a reason, appears in the Rejeitado tab with the reason visible on the detail page, and can be re-approved back into Aprovado.
- **`pytest products/therapy-platform/backend/tests/` is green.**
- **`npx vite build` is green** for the therapy-platform frontend.
- **`improvements.md` populated** for every completed phase, regenerated by `noctusai_improvements` after each tick.
- **One phase-end proposal landed in `products/therapy-platform/projects/therapy-platform-wiring/proposals/`** for every phase with meaningful observations (or a one-line `**Improvements:** none identified.` when genuinely nothing was learned).
- **No new LGPD warnings opened without a planned resolution** — any `noctusai_lgpd_flag` call added during this project has either been resolved by the project's end or has a follow-up project named in `LGPD-WARNINGS.md`.
- **KB is in sync**: `bash scripts/verify-kb-sync.sh` and `python scripts/update-kb-counts.py --check` both pass after the project closes.

---

## 10. How to use this project

- **Single source of truth for progress.** Update as work progresses.
- **Live-tick tasks as they complete.** Flip `- [ ]` → `- [x]` immediately and save. Don't batch. The user watches this file as a live dashboard.
- **Phase-by-phase cadence.** Execute exactly one phase, then pause and wait for the user to say "continue" / "next phase" / "do phase N". Do **not** auto-advance. User overrides with explicit throughput instructions ("ram through 2-3", "run all admin phases").
- **Revise phases when reality diverges.** If Phase 0 discovers the gap set is smaller or larger than estimated, rewrite Phases 2-9 accordingly and log the revision in §11.
- **Commit project changes with the code.** The PROJECT.md evolves in the same commit as the phase's implementation.
- **Interrogate before designing revised phases.** If a phase needs a scope call, ask the user — don't assume.

### Verification commands *(run at end of every phase, not just Phase 10)*

```bash
# Frontend build (any phase that touches frontend)
cd products/therapy-platform/frontend && npx vite build

# Backend tests (every phase)
cd products/therapy-platform/backend && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/ -q

# Seed tests (Phase 1 and any phase that touches seed)
cd seed/lib/backend && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/

# MCP tests (only if the MCP toolkit was touched)
cd mcp/noctusai && \
  /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/

# Keeper review pass (after every phase)
python mcp/noctusai/cli.py --review products/therapy-platform

# Regenerate the retrospective (after every ticked phase header)
python mcp/noctusai/cli.py --improvements products/therapy-platform/projects/therapy-platform-wiring/PROJECT.md
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-04-20 | Initial project drafted from `templates/PROJECT-TEMPLATE.md` after interrogation of the user. Slug renamed `therapy-admin-console-gap` → `therapy-platform-wiring` to honor the scope widening captured in §2. Methodology docs updated with §8 slug-naming convention and §9 tests-land-with-implementation note. | Claude Opus 4.7 |
| 2026-04-20 | Project folder relocated from `projects/therapy-platform-wiring/` to `products/therapy-platform/projects/therapy-platform-wiring/` as part of the scope-scoped-projects architecture change (single-product scope lives under the product). Methodology docs updated to codify the two-location rule (`PATTERNS/project-execution.md §1`). MCP `proposals.py::_find_project_dir` resolver updated to search both locations. | Claude Opus 4.7 |
