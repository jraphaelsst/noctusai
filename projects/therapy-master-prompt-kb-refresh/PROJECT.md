# Therapy MASTER-PROMPT + KB Refresh — Project Document

> **Status: ✅ CLOSED 2026-05-11.** Documentation-only follow-up to the closed
> `therapy-platform-wiring` project (10 phases over 21 days; closed at commit
> `d72af2b`). Engineer THE-P10's worktree was destroyed mid-Phase-10 by the
> `mole` cleanup-stale-worktrees `rm -rf` fallback (fix shipped same session at
> commit `c4a90ce`) before they could author the MASTER-PROMPT.md update and KB
> §06/§04-THERAPY refresh that the wiring project deferred to orchestrator
> follow-up. Filed as this standalone project per orchestrator §17.6.1 fallback.

- **Created:** 2026-05-11
- **Closed:** 2026-05-11
- **Status:** ✅ CLOSED — MASTER-PROMPT.md + KB §06-THERAPY + KB §04-THERAPY refreshed against the 10-phase post-wiring surface.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com) · Claude Opus 4.7
- **Related docs:**
  - `products/therapy-platform/projects/therapy-platform-wiring/PROJECT.md` — closed parent project; §11 close summary is the authoritative source-of-truth for what changed.
  - `products/therapy-platform/MASTER-PROMPT.md` — the agent-facing therapy product contract.
  - `KNOWLEDGE-BASE/CONTEXT/backend/06-THERAPY.md` — therapy backend KB section.
  - `KNOWLEDGE-BASE/CONTEXT/frontend/04-THERAPY.md` — therapy frontend KB section.
- **Project slug:** `therapy-master-prompt-kb-refresh`
- **Branch:** `therapy-master-prompt-kb-refresh-2026-05-11`

---

## 1. Context & Purpose

Closing `therapy-platform-wiring` shifted the therapy-platform surface
substantially over 10 phases (2026-04-20 → 2026-05-11):

- **8 backend route renames** (Pattern A PT→EN): `/api/alertas-crise` →
  `/api/crisis-alerts`, `/api/tarefas` → `/api/homework`, `/api/humor` →
  `/api/mood`, `/api/salas` → `/api/rooms` (sub-paths `/reservas` →
  `/bookings`), `/api/diario` → `/api/diary`, `/api/evolucao` →
  `/api/evolution-notes`, `/api/planos-tratamento` → `/api/treatment-plans`,
  `/api/recibos` → `/api/invoices` (+ Pattern-G `POST /api/recibos/gerar` →
  `POST /api/invoices`).
- **5 new admin endpoints** (Phase 2): `/api/admin/appointments`,
  `/api/admin/dashboard`, `/api/admin/suspend/{type}/{id}`,
  `/api/admin/financials/{summary,transactions,commissions,commissions/{id}}`.
- **5 list-endpoint DTO normalizations** (Phase 3): `/api/admin/clinics`,
  `/api/admin/patients`, `/api/admin/reports`, `/api/admin/reviews/flagged`,
  `/api/admin/blocks`, `/api/admin/support/conversations` — typed mappers
  replace raw-row passthrough.
- **3 new patient/reject service surfaces** (Phases 5 + 7): reject-flow audit
  triplet (`rejection_reason`/`rejected_at`/`rejected_by` via migration
  `013_rejection_audit.sql`); `GET /api/reviews/patient/{patient_id}` +
  `DELETE /api/reviews/{review_id}` + `usePatientReviews` hook; unified
  `POST /api/matching/embed` with role inference.
- **1 production-broken table-name corrected**: `commission_overrides` →
  `platform_commission_overrides` (Phase 4, `admin_service.set_commission_override`).
- **Pattern F (require_role factory) adoption**: `app/dependencies.py` exposes
  product-bound `require_role = make_require_role(get_current_user, get_user_role)`
  via the seed factory; 11 endpoints in `settings.py` migrated to
  `Depends(require_role(...))` (Phase 1 bonus delivery). N.b. therapy uses
  `clinic_id` not `org_id`, so the cross-platform `make_get_current_user_org`
  factory does NOT apply here — therapy's Pattern F is `make_require_role`.
- **Shared identity resolver shipped**: `noctusai_lib.integrations.supabase_identity`
  with `UserIdentity` + `fetch_user_identities()` (bulk) + `fetch_user_identity()`
  (singular); consumed by `admin_service.py` for therapist / patient / clinic
  list endpoints (N+1 → bulk pre-fetch).
- **Seed-lib bug fixed bonus**: `noctusai_lib.api.auth.require_role` retired
  during Phase 1, replaced with `make_require_role` factory matching the
  `make_get_current_user` pattern.
- **8 follow-up projects filed**: `therapy-public-directory-wiring`,
  `therapy-auth-router-orphan-cleanup`, `therapy-admin-invitations-management`,
  `therapy-clinic-settings-misrouting`, `therapy-clinic-rooms-management-wiring`,
  `therapy-clinic-therapist-config-wiring`, `therapy-clinic-dashboard-bi-wiring`,
  `therapy-patient-dto-enrichment-unified`.
- **3 accept-with-rationale entries**: `therapy-public-directory-auth-semantic`
  (JWT-vs-publicRoutes mismatch), `therapy-clinic-jwt-derived-clinic-id`
  (Phase 8 `useClinicTherapists`), Pattern E DTO-contract-via-mappers (193
  routes have no `response_model`; mappers carry the contract).

The therapy-platform `MASTER-PROMPT.md` and KB sections `06-THERAPY` (backend)
+ `04-THERAPY` (frontend) were drafted before this evolution and reference the
pre-wiring surface. A NEW engineer joining therapy-platform today would read
stale docs. This project refreshes the three artifacts so the agent-facing
contract reflects the closed-wiring state.

---

## 2. Confirmed constraints

- **Documentation-only.** No code edits. No new tests. No backend or frontend
  behavioral changes.
- **Preserve existing valid content.** Only refresh what is stale or
  contradicted by the closed-wiring state. Don't rewrite for stylistic taste.
- **Three artifacts in scope**:
  `products/therapy-platform/MASTER-PROMPT.md`,
  `KNOWLEDGE-BASE/CONTEXT/backend/06-THERAPY.md`,
  `KNOWLEDGE-BASE/CONTEXT/frontend/04-THERAPY.md`.
- **`verify-kb-sync.sh` GREEN** at close.
- **No `--no-verify`** at commit.
- **Branch rename per KB §20**: `therapy-master-prompt-kb-refresh-2026-05-11`.

---

## 3. Design principles

1. **PROJECT.md §11 is the source-of-truth.** Cross-reference every refreshed
   bullet against the closed `therapy-platform-wiring` §11 narrative — no
   invention, no speculation.
2. **What would a NEW engineer joining therapy-platform need to know
   post-wiring?** That is the editorial target for MASTER-PROMPT.md.
3. **KB §06-THERAPY = backend contract surface** (routes, schemas, auth shape,
   DTO conventions). KB §04-THERAPY = frontend page-to-API contract (pages,
   hooks, role-based layouts).
4. **Counts come from the live tree, not memory.** `ls routers/ | wc -l`,
   `ls services/ | wc -l`, `ls hooks/ | wc -l` — never trust the stale doc.
5. **Note carve-outs honestly**: therapy uses `clinic_id` not `org_id`; the
   cross-platform `make_get_current_user_org` factory does NOT apply.

---

## 3a. Seed-first analysis (REQUIRED)

Documentation-only project — no seed surface touched. The artifacts edited
(MASTER-PROMPT + KB) are themselves the seed-first analysis surface for
therapy-platform: the refresh records that the product consumes the seed via
`create_product_app(...)`, `noctusai_lib.integrations.supabase_identity`,
`noctusai_lib.api.auth.make_require_role`, `noctusai_lib.llm.*`, etc.

---

## 4. Scope

**In scope:**
- Refresh `products/therapy-platform/MASTER-PROMPT.md` to reflect post-wiring
  surface (route names, new admin endpoints, Pattern F factory, seed identity
  resolver, follow-up project pointers).
- Refresh `KNOWLEDGE-BASE/CONTEXT/backend/06-THERAPY.md` with current router
  count, route prefixes, auth helpers, and seed-imports.
- Refresh `KNOWLEDGE-BASE/CONTEXT/frontend/04-THERAPY.md` with current page
  count per role, hook inventory (incl. the 4 new hooks shipped by the wiring
  project: `useClinicPatients`, `useClinicTherapists`, `useTherapistPatients`,
  `useTherapistReviews`, `usePatientReviews`), and known consumer-pending
  surfaces.
- Verify `bash scripts/verify-kb-sync.sh` GREEN.

**Out of scope:**
- Code edits (any backend or frontend file).
- New tests.
- 8 follow-up projects (each lives in its own slug — refresh just *points* to
  them).
- 3 accept-with-rationale catalog entries (the project's responsibility;
  cataloging them is a separate task per the "promote to catalog before folder
  deletion" rule — surfaced as follow-up).

---

## 5. Architecture / Data Model

N/A — documentation refresh.

---

## 6. Implementation phases

### Phase 0 — Read inputs ✅

**Improvements:** none identified — single-engineer documentation refresh against PROJECT.md §11 source of truth, no behavioral surface touched.

- Read `products/therapy-platform/projects/therapy-platform-wiring/PROJECT.md`
  §11 (closed-project change log, 10 phases).
- Read current `products/therapy-platform/MASTER-PROMPT.md`.
- Read current `KNOWLEDGE-BASE/CONTEXT/backend/06-THERAPY.md`.
- Read current `KNOWLEDGE-BASE/CONTEXT/frontend/04-THERAPY.md`.
- Sanity-check counts: `ls products/therapy-platform/backend/app/routers/`
  (40 router files + `__init__.py`), services (42 + `__init__.py`), frontend
  hooks (30 hook files + `__tests__/`), pages (admin: 15, clinic: 6, patient:
  14, therapist: 15, shared: 14).

### Phase 1 — MASTER-PROMPT.md refresh ✅

**Improvements:** none identified — single-engineer documentation refresh against PROJECT.md §11 source of truth, no behavioral surface touched.

- Update route prefixes (Pattern A renames: `/api/crisis-alerts`,
  `/api/homework`, `/api/mood`, `/api/rooms`, `/api/diary`,
  `/api/evolution-notes`, `/api/treatment-plans`, `/api/invoices`).
- Document Pattern F adoption: `require_role = make_require_role(...)` in
  `dependencies.py`; note `clinic_id`-not-`org_id` carve-out.
- Document seed identity resolver consumption
  (`noctusai_lib.integrations.supabase_identity`).
- Update services count (43 services in `app/services/` incl. `_bulk.py`).
- Update auth-helpers table to point at the factory-bound `require_role`.
- Note 5 new admin endpoints + 5 DTO-normalized list endpoints + reject-flow
  triplet.
- Note `commission_overrides` → `platform_commission_overrides` correction.
- Cross-link the 8 follow-up projects + 3 accept-with-rationale entries.

### Phase 2 — KB §06-THERAPY refresh ✅

**Improvements:** none identified — single-engineer documentation refresh against PROJECT.md §11 source of truth, no behavioral surface touched.

- Update header counts: 41 routers → 40 + invitations, 43 services.
- Update router-groups list to reflect Pattern A renames + new admin endpoints.
- Add a "Recent (2026-05-11 post-wiring)" subsection noting what changed.
- Tighten auth-helpers row to point at `make_require_role` factory.

### Phase 3 — KB §04-THERAPY refresh ✅

**Improvements:** none identified — single-engineer documentation refresh against PROJECT.md §11 source of truth, no behavioral surface touched.

- Update per-role page counts (admin: 15, clinic: 6, therapist: 15, patient:
  14).
- Update hooks count from 24 → 30 + list the new wave (clinic/therapist/patient
  enrichments).
- Note Pattern A consumer-side path renames (frontend already pre-aligned;
  `useClinicalRecords.ts` was bystander-fixed Phase 6.b/7.a/8.b).
- Note consumer-pending surfaces: `ClinicDirectory.tsx` + `TherapistDirectory.tsx`
  + `lgpd.py` patient routes + 5 clinic-portal orphans.

### Phase 4 — Verification ✅

**Improvements:** none identified — single-engineer documentation refresh against PROJECT.md §11 source of truth, no behavioral surface touched.

- `bash scripts/verify-kb-sync.sh` GREEN.
- Manual diff review.
- Commit with HEREDOC + Co-Authored-By trailer.

---

## 7. Open questions

None — documentation-only scope; PROJECT.md §11 of the closed parent is
unambiguous.

---

## 8. Dependencies & blockers

None.

---

## 9. Success criteria

- All three artifacts refreshed against the post-wiring surface.
- `bash scripts/verify-kb-sync.sh` GREEN at close.
- `findings.md` 5-category content returned as text (per §17.6.1 fallback).
- Commit + push from this worktree's branch (no merge to main — that is the
  orchestrator's responsibility, last step of project close).

---

## 10. How to use this plan

Documentation-only follow-up. Execute Phases 0-4 sequentially; commit at close.
The parent `therapy-platform-wiring` project is already closed and merged; this
project does not gate any open work.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Project created + executed + closed. Engineer THERAPY-MP-KB-REFRESH refreshed MASTER-PROMPT.md (route prefixes per Pattern A; Pattern F `make_require_role` factory; seed identity resolver consumption; new admin endpoints + DTO-normalized lists + reject-flow triplet; 8 follow-ups + 3 accept-with-rationale entries cross-linked); KB §06-THERAPY (router counts, auth helpers, post-wiring changes subsection); KB §04-THERAPY (per-role page counts, hooks expansion 24→30, consumer-pending surfaces). Verification: `bash scripts/verify-kb-sync.sh` GREEN. Findings returned as text per §17.6.1 fallback. | engineer-subagent THERAPY-MP-KB-REFRESH |
