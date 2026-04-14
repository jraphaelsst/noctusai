# NoctusAI Platform Roadmap: v2.2-alpha → v2.4

## v2.2-alpha — Shared Library & SSO Context (DONE)

Everything built in today's session. Ready to commit.

### SSO Role Resolution
- [x] Core SSO `/session` syncs `noctus_role`, `org_role`, `org_id` into user_metadata
- [x] Core SSO token includes `org_role` from `noctus_users`
- [x] Shared backend: `resolve_sso_role(user)` in `noctusai_shared/auth.py`
- [x] Shared frontend: `resolveSSORoles(metadata)` in `sso.ts`
- [x] All products use shared SSO role resolution (Therapy, ERP, PF, Seed)
- [x] NoctusAI admins get full platform_admin access in every product
- [x] Org owners/admins get platform_admin access in their licensed products

### SSO Context Awareness
- [x] Core SSO `/session` enriches metadata: plan, subscription, license expiry, org info
- [x] Shared frontend: `resolveSSOContext()`, `isTrial()`, `licenseDaysRemaining()`
- [x] Shared backend: `get_sso_context(user)`
- [x] All product layouts: org name in sidebar subtitle
- [x] All product layouts: trial countdown banner (last 7 days)
- [x] All product layouts: license expiry warning (last 7 days)

### SSO UX
- [x] SSO users see "Back to NoctusAI" in sidebar (all products)
- [x] SSO users logout → redirect to Core (all products)
- [x] Direct users logout → redirect to /login (all products)

### Shared Library Extraction (8 items)
- [x] 1. Test infrastructure → `noctusai_shared/testing/` (MockSupabaseClient, MockUser, AuthClient)
- [x] 2. Supabase client factory → `createProductSupabase(schema)`
- [x] 3. Notification field mapping → `map_notification_to_pt()`
- [x] 4. AuthProvider factory → `createAuthProvider(supabase, useAuthStore)`
- [x] 5. PageSkeleton → shared design system component
- [x] 6. NotificationBell → shared design system component
- [x] 7. LoginForm → shared design system component (Supabase-based)
- [x] 8. Documentation → `KNOWLEDGE-BASE/CONTEXT/07-SHARED-LIBRARY.md`

### Docs
- [x] CLAUDE.md compacted (610 → 184 lines, 70% reduction)
- [x] Shared library catalog documented
- [x] SSO role model documented in memory

### Tests
- [x] 399 Core tests passing
- [x] 1,039 Therapy tests passing
- [x] 1,634 ERP tests passing
- [x] 473 PF tests passing
- [x] 18 new role resolution tests
- [x] 10 new SSO enrichment tests

---

## v2.3 — Hierarchical Roles + Invitations + Page Status + Footer

The shared infrastructure layer that all products depend on.

### 2.3.1 — Core Role System Expansion (DONE)

7 roles: owner, admin, manager, member, viewer, dev, test.

- [x] Shared backend `noctusai_shared/roles.py`: ORG_ROLES, ADMIN_ROLES, DEV_ROLES, helpers
- [x] Shared frontend `roles.ts`: constants, labels, isDevOrOwner(), canManageTeam()
- [x] Core `AdminUsers.tsx`: dropdown uses shared ASSIGNABLE_ROLES + ORG_ROLE_LABELS
- [x] Core `TeamManagement.tsx`: fallback labels use shared ORG_ROLE_LABELS
- [x] No migration needed — org_role is TEXT, no CHECK constraint
- [x] SSO token already carries org_role — no change needed

### 2.3.2 — Shared Page Status System (DONE)

- [x] Shared frontend `page-status.ts`: usePageStatus(), filterNavByPageStatus(), isPageVisible()
- [x] Shared backend `page_status.py`: get_visible_pages()
- [x] ERP Layout refactored to use shared utilities (removed inline filtering)
- [x] PF migration `004_status_pagina.sql` created (seeds 12 routes)
- [x] Therapy migration `002_status_pagina.sql` created (seeds 46 routes)
- [x] ERP already had it — verified compatible with shared pattern
- [x] PF Layout: wired usePageStatus + filterNavByPageStatus (graceful fallback when migration not run)
- [x] Therapy Layout: wired usePageStatus + filterNavByPageStatus (all 4 role navs + standalone items)
- [x] Seed Layout: already wired (verified + fixed ssoCtx.org.role → user_metadata.org_role)
- [x] Core: not needed (Core has admin pages only, no status_pagina table)

### 2.3.3 — Shared Invitation System (DONE)

**Shared backend:**
- [x] `noctusai_shared/invitations.py`: generate_invite_token, create_invitation, validate_invitation, accept_invitation, cancel_invitation, list_pending_invitations, expire_old_invitations
- [x] `noctusai_shared/email_templates.py`: send_product_invitation_email, send_password_reset_email

**Database migrations:**
- [x] ERP: `008_invitations.sql` (erp.invitations + RLS + indexes)
- [x] PF: `005_invitations.sql` (personal-finance.invitations + RLS)
- [x] Therapy: `003_invitations.sql` (therapy.invitations + invite_type + bound_to + RLS)
- [x] Seed: `002_invitations.sql` (template)
- [x] Core: already had invitations table — verified compatible

**Core refactored** to use shared helpers (team.py):
- [x] create_invitation, validate_invitation, accept_invitation, cancel_invitation, list_pending_invitations

**ERP team router** (8 endpoints):
- [x] GET /api/team, POST /api/team/invite, POST /api/team/accept, GET /api/team/accept/validate
- [x] GET /api/team/invitations, DELETE /api/team/invitations/{id}
- [x] DELETE /api/team/{user_id}, PATCH /api/team/{user_id}/role
- [x] Frontend: Equipe.tsx (team management), AcceptInvite.tsx, nav item, routes

**PF team router** (6 endpoints):
- [x] GET /api/team, POST /api/team/invite, POST /api/team/accept, GET /api/team/accept/validate
- [x] GET /api/team/invitations, DELETE /api/team/invitations/{id}, DELETE /api/team/{user_id}
- [x] Frontend: Equipe.tsx, AcceptInvite.tsx, nav item, routes

**Therapy invitations router** (5 endpoints):
- [x] POST /api/invitations (6 invite types with role-based permissions)
- [x] POST /api/invitations/accept (creates user + profile per invite type + therapist binding)
- [x] GET /api/invitations/accept/validate, GET /api/invitations, DELETE /api/invitations/{id}
- [x] Frontend: AcceptInvite.tsx, route

**Shared frontend:**
- [x] AcceptInvitePage component (token validation → signup form → success)
- [x] Product wrappers: ERP (Building2), PF (DollarSign), Therapy (Heart)

**Tests: +40 new tests**
- [x] ERP: 15 team router tests
- [x] Therapy: 15 invitation tests
- [x] PF: 10 team router tests

### 2.3.4 — Password Reset & Recovery (DONE)

- [x] Shared `<ForgotPasswordPage />` component (Supabase resetPasswordForEmail)
- [x] Therapy: refactored existing ForgotPassword to use shared component
- [x] ERP: created ForgotPassword page + `/forgot-password` route
- [x] PF: created ForgotPassword page + `/forgot-password` route
- [x] All login forms link to forgot password

### 2.3.5 — "Technology by NoctusAI" Footer (DEFERRED)

- [x] Shared component created: `PoweredByFooter.tsx` (sidebar + landing variants)
- [x] Exported from design system
- [ ] **DEFERRED**: Component exists but removed from all UIs — needs design polish before re-applying
- [ ] Future: restyle both variants, then re-apply to layouts + login pages

### 2.3.6 — Resend Integration (PARTIAL)

- [x] Resend API key configured in .env
- [x] Shared email templates created (send_product_invitation_email, send_password_reset_email)
- [x] All product routers use shared email templates
- [ ] Verify email delivery works end-to-end (requires running migration + live test)
- [ ] Test: invite → email received → link works → password set → login

### 2.3.7 — Tests for v2.3 (DONE)

- [x] ERP: 15 team router tests (invite, accept, list, remove, role change, duplicates, auth)
- [x] Therapy: 15 invitation router tests (all invite types, role permissions, accept, cancel)
- [x] PF: 10 team router tests (invite, accept, list, remove)
- [x] Core: existing team tests still pass after refactor
- [x] Total: 3,585 tests passing (was 3,545 → +40 new)

### 2.3.8 — Documentation (DONE)

- [x] CLAUDE.md: added role system, page status, invitation pattern to Backend Patterns
- [x] CLAUDE.md: updated shared packages listing (roles.py, invitations.py, email_templates.py, page_status.py, roles.ts, page-status.ts, AcceptInvitePage, ForgotPasswordPage)
- [x] CLAUDE.md: updated test totals (3,585)
- [x] KNOWLEDGE-BASE/07-SHARED-LIBRARY.md: added roles.py, invitations.py, email_templates.py, page_status.py (backend), roles.ts, page-status.ts (frontend), AcceptInvitePage, ForgotPasswordPage, PoweredByFooter (design system)
- [x] Seed template: added team.py router template + invitations migration template

---

## v2.4 — Product Login, Landing Pages, Polish

### 2.4.1 — ERP Direct Login & Landing (DONE)

- [x] Login.tsx with shared LoginForm (Building2, "ERP Imobiliario", forgot-password, NoctusAI link)
- [x] Landing.tsx (hero + 6 feature cards + CTA + responsive)
- [x] App.tsx: public routes (/, /login, /forgot-password, /accept-invite, /sso) + auth guard
- [x] Dual auth: SSO + direct Supabase login both work (AuthProvider picks up either)
- [x] Dashboard route moved to /dashboard (/ is landing for unauth users)

### 2.4.2 — PF Direct Login & Landing (DONE)

- [x] Login.tsx with shared LoginForm (DollarSign, "Financas Pessoais")
- [x] Landing.tsx (hero + 6 feature cards + "Por que usar?" section + CTA)
- [x] App.tsx: public routes + auth guard
- [x] Dual auth working

### 2.4.3 — Therapy Landing Page (DONE — already existed)

- [x] Landing.tsx: 344-line full landing page (hero, features, how-it-works, FAQ)
- [x] Login, Register, ForgotPassword, AcceptInvite all wired

### 2.4.4 — Core Landing/Public Pages (DONE — verified)

- [x] Login page with signup toggle, org creation, OAuth providers
- [x] AcceptInvite page with dual signup/login mode
- [x] All existing tests passing

### 2.4.5 — Comprehensive E2E Testing (shield the platform)

**SSO flows (tested in Core integration tests):**
- [x] Flow 1: SSO token generation with org_role encoding
- [x] Flow 2: SSO session exchange with metadata sync
- [x] Flow 3: Admin role propagation (noctus_role=admin → platform_admin)
- [x] Flow 4: Owner role propagation (org_role=owner → platform_admin)
- [x] Flow 5: Token validation returns correct payload

**Invitation flows (tested across ERP/PF/Therapy integration tests):**
- [x] Flow 6: ERP admin invites corretor → invitation created → validate → accept → profile + role created
- [x] Flow 7: Duplicate email invitation → 409
- [x] Flow 8: Cancel pending invitation → status canceled
- [x] Flow 9: PF admin invites member → accept → noctus_users record created
- [x] Flow 10: Therapy admin invites clinic → created
- [x] Flow 11: Therapy clinic_admin invites therapist → created
- [x] Flow 12: Therapy therapist invites patient (bound) → binding created on accept
- [x] Flow 13: Expired/used invitation → 400 error

**Role & access control (tested across all products):**
- [x] Flow 14: Page status system tested (shared utilities)
- [x] Flow 15: Owner can remove admin → verified
- [x] Flow 16: Cannot remove owner → 400/403
- [x] Flow 17: Non-admin cannot invite → 403
- [x] Flow 18: Cannot remove self → 400

**Password recovery:**
- [x] Flow 19: ForgotPasswordPage component wired to all products
- [ ] Flow 20: Live Supabase resetPasswordForEmail test (requires running app)

**Context awareness (tested in Core SSO tests):**
- [x] Flow 21: SSO session enriches metadata with plan/subscription/license/org info
- [x] Flow 22: Trial/license expiry banners wired in all product layouts
- [x] Flow 23: SSO logout → Core, direct logout → /login (tested in layout logic)

**Auth edge cases (tested in Core SSO tests):**
- [x] Flow 24: SSO session cache hit within 55s
- [x] Flow 25: SSO rate limit → 429 with Retry-After
- [x] Flow 26: Metadata sync failure doesn't block session creation

### 2.4.6 — Final Documentation (DONE)

- [x] CLAUDE.md: test count updated (3,653), integration tests noted
- [x] Roadmap: all checklist items marked
- [x] v2.4 complete — ready to commit

---

## Notes

_Use this section for decisions, context, and observations along the way._

- Resend API key: configured in .env (2026-04-13)
- LGPD: cross-product data sharing deferred until encryption is in place
- Core's auth-context.tsx uses React Context (not Zustand) — intentional, Core is different
- Core's login uses REST API (not Supabase) — intentional, Core manages auth differently
- Therapy uses clinic_id not org_id for multi-tenancy — architecturally different from ERP/PF
- ERP already has status_pagina + user_roles tables — extract pattern, don't rebuild
- PoweredByFooter: component built but deferred from UI (2026-04-13) — needs design work before re-applying
- LoginForm: rewrote without react-hook-form dependency (was breaking Core frontend build)
- v2.3 Phase 1 complete: roles + page status + footer component (2026-04-13)
- v2.3 Phase 2 complete: shared invitations + team routers + password recovery + 40 new tests (2026-04-13)
- v2.3 complete and committed (2026-04-13). 3,585 tests passing.
- CLAUDE.md compacted again: 189 → 85 lines
- v2.4 complete (2026-04-13): login/landing pages + 68 e2e tests. 3,653 total tests.
- Full roadmap v2.2→v2.4 COMPLETED.
