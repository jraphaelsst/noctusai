# Therapy Consent Frontend Wiring — Project Document

> **Living document** — revise phases as work progresses.
> **Scaffolded 2026-04-22** from compliance-audit-reconciliation Phase 5 improvements bundle.
> **STATUS: PENDING USER INTERROGATION — blocks attachments feature go-live.**
> **Written for a zero-context reader.**

- **Created:** 2026-04-22
- **Last updated:** 2026-05-03
- **Status:** ⏳ Interrogation closed 2026-05-03 (Tier 1 round of `projects/side-projects-batch/`). Q6=both paths (patient self-serve + therapist-attest), Q7=recording-only v1, Q8=render revoked with badge. §2 + §3 + §6 filled. Phase 0 ready.
- **Owner / stakeholders:** Raphael (joaoraphaelsst@gmail.com)
- **Related docs:**
  - `projects/compliance-audit-reconciliation/PROJECT.md` § Phase 5 — backend `/api/consents/*` endpoints + `sessions.py` consent-gate.
  - `products/therapy-platform/backend/app/routers/consents.py` — endpoints the frontend must call.
  - `products/therapy-platform/backend/migrations/008_consent_retention.sql` — consent_records schema + RLS.
- **Project slug:** `therapy-consent-frontend-wiring`
- **Project location:** `products/therapy-platform/projects/therapy-consent-frontend-wiring/` (single-product scope)

---

## 1. Context & Purpose

compliance-audit-reconciliation Phase 5 (2026-04-22) replaced the ephemeral `consent_given: bool` flag on session-start with a persisted, per-scope consent (`therapy.consent_records`). The backend now REQUIRES a `recording` consent record before `POST /api/sessions/:id/start` succeeds.

**Impact:** the frontend `/session/:id` page still sends only `{consent_given: true}` — every session-start will return 400 with "Consentimento de gravação não registrado" until the UI calls `POST /api/consents/grant` first.

This project wires the UI. Scope covers: pre-session consent modal, revoke UI, consent-history view.

---

## 2. Confirmed constraints

Answers locked 2026-05-03 in the Tier-1 §7 round of `projects/side-projects-batch/` Phase 1.a.

- **Who registers consent** — **both paths.** Patient self-serves via the patient app (LGPD-clean primary path), therapist-attest is the in-clinic fallback when the patient isn't on a device. Both paths write to the same `therapy.consent_records` row; the audit trail captures `granted_by_user_id` so the actor is reconstructable. *(Q6 answered: don't force one shape; LGPD principle is "documented consent," not "mode of capture.")*
- **Scope coverage v1** — **recording only.** The other three scopes (`transcription`, `ai_summary`, `longitudinal`) ship as separate UI sections in v2 once `recording` is field-validated. Backend already supports all four; the gate is UI surface area + UX clarity. *(Q7 answered: matches `sessions.py` consent-gate which only enforces `recording`; widens scope cleanly later without rework.)*
- **Revoked consents in history** — **render with a "Revogado em <date>" badge.** LGPD audit-trail visibility wins over UI cleanliness. Revoked rows appear in the consent-history view with strike-through styling and an explicit revoke timestamp. *(Q8 answered: LGPD principle is "transparent record"; hiding revoked rows would mask the audit trail from the user themselves.)*

---

## 4. Scope

**In scope:**
- Pre-session consent modal / flow.
- Revoke button on active consents.
- `GET /consents/:appointment_id` listing view.

**Out of scope:**
- Backend work (already shipped by compliance-audit Phase 5).
- LGPD-wide consent unification (other products).

---

## 5. Architecture / Data Model

Reuses the existing `/api/consents/*` surface:
- `POST /api/consents/grant` → 200 with consent row.
- `POST /api/consents/revoke` → 200.
- `GET /api/consents/:appointment_id` → list of scopes + granted/revoked timestamps.

### Files likely in scope

- Therapy frontend: session/appointment pages (paths to be discovered during interrogation).

---

## 6. Implementation phases

_Designed 2026-05-03 from §2 answers + child §1 context._

### Phase 0 — Map session-start UI surface + consent gate location

- [ ] Read therapy frontend session/appointment pages — outline only first (narrow-read), then bodies for the actual session-start trigger. Likely paths: `products/therapy-platform/frontend/src/pages/Session*.tsx`, `products/therapy-platform/frontend/src/components/Session*.tsx`.
- [ ] Identify the exact button/flow that calls `POST /api/sessions/:id/start`. Note the React Query mutation hook involved.
- [ ] Confirm `/api/consents/grant`, `/api/consents/revoke`, `/api/consents/:appointment_id` shapes are reachable via existing axios client setup — read the typed API client.
- [ ] Decide the patient-self-serve vs. therapist-attest entry point: do both routes pass through the same modal UI with an actor toggle, or two separate components? *(Default: same modal, role-aware; therapist sees an additional checkbox "Atesto verbalmente o consentimento do paciente" that flips a server-side `granted_by_actor=therapist` flag.)*
- [ ] Run `noctusai_scan_cross_product_helpers` on therapy `frontend/src/components/`: is there a similar consent/disclosure component pattern in another product? (PF/ERP have LGPD modals — verify for absorption opportunity.)
- [ ] Inventory result documented in this §6 + §11.

### Phase 1 — Consent modal + grant flow (patient self-serve + therapist-attest)

- [ ] Build `ConsentRecordingModal.tsx` with role-aware UI (patient view shows the LGPD purposes + grant button; therapist view shows the same + the "atesto verbalmente" checkbox).
- [ ] Wire to `POST /api/consents/grant` via a `useGrantConsent` React Query mutation hook. Invalidate `['consents', appointmentId]` on success.
- [ ] Hook the modal into the session-start path discovered in Phase 0: `Iniciar Sessão` button checks `useConsents(appointmentId)` for an active `recording` consent; if none, opens the modal. Modal `onSuccess` re-invokes session-start.
- [ ] No silent error path — surface `POST /grant` failure as a toast + keep the modal open.
- [ ] AST-first edits (ts-morph) for any wiring of the existing session-start hook.

### Phase 2 — Revoke + history UI

- [ ] Build `ConsentHistoryView.tsx` consuming `GET /api/consents/:appointmentId` — table of scopes with status (Concedido / Revogado em ...).
- [ ] "Revogar" button per active row → `POST /api/consents/revoke` mutation. Confirm dialog before firing (irreversible side effect).
- [ ] Revoked rows render with strike-through styling + "Revogado em <date>" badge (Q8 design).
- [ ] Add `ConsentHistoryView` as a tab/section on the session detail page — exact placement decided by Phase 0 inventory.

### Phase 3 — Tests + E2E + verification

- [ ] Component tests for `ConsentRecordingModal` (Vitest + React Testing Library): renders patient view, renders therapist view, fires correct mutation payload, surfaces error toast, closes on success.
- [ ] Component tests for `ConsentHistoryView`: lists scopes, renders revoked badge, fires revoke mutation, confirm dialog flow.
- [ ] E2E (Playwright if therapy frontend has one; otherwise manual smoke with `npx vite preview`): patient logs in → session-start → modal appears → grant → session starts. Then revoke → history shows revoked row.
- [ ] Backend regression: `pytest tests/routers/test_consents_router.py tests/routers/test_sessions_router.py -q` — confirm gate still works.
- [ ] `cd products/therapy-platform/frontend && npx vite build` — green.
- [ ] Phase-end keeper review: `python mcp/noctusai/cli.py --review`.

---

## 7. Open questions

All §7 questions resolved 2026-05-03 (Tier 1 round of `projects/side-projects-batch/` Phase 1.a). See §2 for answers + reasoning.

- Q6 (consent registration actor) — ✅ ANSWERED: both paths.
- Q7 (scope coverage v1) — ✅ ANSWERED: recording only.
- Q8 (revoked consents in UI) — ✅ ANSWERED: render with revoked badge.

Phase 0 may surface follow-up sub-questions (e.g. exact session-start hook location, modal placement on session-detail page) — those resolve during inventory, not via user round.

---

## 8. Dependencies & blockers

- User interrogation (§2 questions).
- Blocks attachment feature enabling in production.

---

## 9. Success criteria

- `POST /api/sessions/:id/start` never returns "consentimento não registrado" from the frontend happy path.
- `vite build` green on therapy.

---

## 10. How to use this project

Interrogate, then phase-by-phase.

### Verification commands

```bash
cd products/therapy-platform/frontend && npx vite build
cd products/therapy-platform/backend && /Users/rapha/Documents/repository/NoctusAI/noctusai/venv/bin/python -m pytest tests/routers/test_consents_router.py tests/routers/test_sessions_router.py -q
```

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-04-22 | **Initial scaffold** — filed as Phase 5 follow-up from compliance-audit-reconciliation. Pending interrogation. | Claude Opus 4.7 |
| 2026-05-03 | **§7 round closed.** Q6=both paths (patient self-serve + therapist-attest), Q7=recording-only v1, Q8=render revoked with badge. §2 + §6 phase plan filled (3 phases). Phase 0 ready to execute as part of `projects/side-projects-batch/` Phase 1.e. | Claude Opus 4.7 |
