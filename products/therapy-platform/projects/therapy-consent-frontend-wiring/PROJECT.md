# Therapy Consent Frontend Wiring — Project Document

> **Living document** — revise phases as work progresses.
> **Scaffolded 2026-04-22** from compliance-audit-reconciliation Phase 5 improvements bundle.
> **STATUS: PENDING USER INTERROGATION — blocks attachments feature go-live.**
> **Written for a zero-context reader.**

- **Created:** 2026-04-22
- **Last updated:** 2026-04-22
- **Status:** Filed pending interrogation. No phases designed yet.
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

_Interrogate the user before filling. Candidate questions:_
- Who registers consent — patient self-serves, or therapist attests verbally?
- Do other scopes (`transcription`, `ai_summary`, `longitudinal`) get their own UI, or recording-only for v1?
- Do revoked consents render in the session list / history?

---

## 3. Design principles

_TBD after interrogation._

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

_Designed after §2 interrogation. Placeholder only._

- [ ] Phase 0 — Map the existing session-start UI surface; identify where the consent gate must land.
- [ ] Phase 1 — Build the consent modal + wire to `POST /grant`.
- [ ] Phase 2 — Revoke + history UI.
- [ ] Phase 3 — Tests + E2E build.

---

## 7. Open questions

See §2 — all answered at interrogation time.

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
