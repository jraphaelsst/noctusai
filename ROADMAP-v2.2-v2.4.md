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

### 2.3.1 — Core Role System Expansion

Current: `noctus_users.role` is just "admin" or "user". `org_role` is "owner"/"admin"/"member"/"viewer".

Target roles for `org_role`:
- `owner` — org creator, full control, billing
- `admin` — manage team, settings, billing
- `manager` — manage team, no billing access
- `member` — access licensed products
- `viewer` — read-only dashboards, can't launch products
- `dev` — same as member + sees "in development" pages
- `test` — same as viewer (reserved for QA testing)

Steps:
- [ ] Update Core migration/seed: expand `org_role` allowed values
- [ ] Update Core `noctus_users` table constraints (if any CHECK constraint exists)
- [ ] Update Core admin panel `AdminUsers.tsx`: add new role options to dropdown
- [ ] Update Core `team.py` router: support new roles in invitations
- [ ] Update Core frontend `auth-context.tsx`: expose role for UI gating
- [ ] Update SSO token: `org_role` already carried — no change needed
- [ ] Add tests for new role values in SSO flow

### 2.3.2 — Shared Page Status System

Currently ERP-only: `erp.status_pagina` table + sidebar badge filtering. Extract to shared pattern consumed by all products.

**Backend:**
- [ ] Create shared migration template: `status_pagina` table per product schema
  - Fields: `id`, `nome_pagina` (route key), `status` (enum: producao/desenvolvimento/desativado), `created_at`
  - RLS: org-scoped or role-scoped depending on product
- [ ] Create `noctusai_shared/page_status.py` — helpers for status queries
- [ ] Apply migration to Core schema (public.status_pagina)
- [ ] Apply migration to PF schema (personal-finance.status_pagina)
- [ ] Apply migration to Therapy schema (therapy.status_pagina)
- [ ] ERP already has it — verify compatibility with shared pattern
- [ ] Seed status_pagina in each product's migration with all current routes

**Frontend:**
- [ ] Extract ERP's nav filtering logic to shared utility
  - `filterNavByPageStatus(groups, statusPaginas, isDevOrOwner)` → filtered NavGroup[]
  - Badge rendering: "DEV" badge on desenvolvimento pages (visible to dev/owner only)
- [ ] Create shared hook: `usePageStatus(supabase)` → returns status list
- [ ] Update ERP Layout to use shared filter (already has the pattern — refactor to shared)
- [ ] Update Therapy Layout to use shared page status filtering
- [ ] Update PF Layout to use shared page status filtering
- [ ] Update Core Layout (if applicable — Core may not need it)
- [ ] Update Seed Layout template with page status integration
- [ ] Dev/owner role check: `isDevOrOwner(ssoCtx, productRoles)` shared helper

**Dev role visibility rules:**
- Pages with status `producao` → visible to all users
- Pages with status `desenvolvimento` → visible ONLY to dev + owner roles
- Pages with status `desativado` → hidden from everyone
- Dev/owner see "DEV" badge on desenvolvimento pages in sidebar

### 2.3.3 — Shared Invitation System

Extract Core's `team.py` + `invitations` table into a shared pattern.

**Backend (shared):**
- [ ] Create `noctusai_shared/invitations.py`:
  - `generate_invite_token()` — secure random token
  - `create_invitation(db, org_id, email, role, invited_by, expires_days=7)` → invitation record
  - `validate_invitation(db, token)` → invitation record or raise
  - `accept_invitation(db, token, user_id)` → updates status
  - `cancel_invitation(db, invitation_id)` → updates status
  - `list_pending_invitations(db, org_id)` → list
  - `expire_old_invitations(db)` — cleanup expired
- [ ] Create shared email templates:
  - `send_product_invitation_email(to, product_name, org_name, role, invite_token, base_url)`
  - Configurable product branding (name, color, icon)

**Database:**
- [ ] Core: `invitations` table already exists — verify schema matches shared pattern
- [ ] ERP: Create `erp.invitations` table (same schema as Core's)
- [ ] PF: Create `personal-finance.invitations` table
- [ ] Therapy: Create `therapy.invitations` table (extended with `invite_type` field)
- [ ] Seed: Create migration template for invitations table
- [ ] All tables: RLS policies scoped to org_id (or clinic_id for therapy)

**Core invitation endpoints (already exist — refactor to use shared):**
- [ ] `POST /api/team/invite` — refactor to use shared `create_invitation()`
- [ ] `POST /api/team/accept-invite` — refactor to use shared `accept_invitation()`
- [ ] `GET /api/team/invitations` — refactor to use shared `list_pending_invitations()`
- [ ] `DELETE /api/team/invitations/{id}` — refactor to use shared `cancel_invitation()`

**ERP invitation endpoints (new):**
- [ ] Create `routers/team.py`:
  - `POST /api/team/invite` — admin invites employee with role (admin/coordenador/dev/corretor)
  - `POST /api/team/accept-invite` — employee accepts, sets password, creates erp.profiles record
  - `GET /api/team` — list team members
  - `GET /api/team/invitations` — list pending invitations
  - `DELETE /api/team/invitations/{id}` — cancel invitation
  - `DELETE /api/team/{user_id}` — remove employee
  - `PATCH /api/team/{user_id}/role` — change employee role

**ERP frontend (new):**
- [ ] Create `pages/Team.tsx` — team management page (list members, invite, manage roles)
- [ ] Create `pages/AcceptInvite.tsx` — public page: token validation + set password form
- [ ] Add "Equipe" nav item to sidebar (admin-only, under Painel de Controle)
- [ ] Add team route to App.tsx

**PF invitation endpoints (new):**
- [ ] Create `routers/team.py` (simpler: admin + member roles only)
- [ ] Create `pages/Team.tsx`
- [ ] Create `pages/AcceptInvite.tsx`

**Therapy invitation system (extended):**
- [ ] Extend therapy.invitations with `invite_type` enum:
  - `platform_to_clinic` — admin invites a clinic
  - `platform_to_user` — admin invites a user (any role)
  - `clinic_to_therapist` — clinic admin invites therapist
  - `clinic_to_patient` — clinic admin invites patient
  - `therapist_to_patient` — therapist invites patient (creates bound relationship)
  - `therapist_to_therapist` — therapist invites colleague (no binding)
- [ ] Create/update `routers/invitations.py`:
  - `POST /api/invitations` — invite with type + role
  - `POST /api/invitations/accept` — accept with password setup
  - `GET /api/invitations` — list (filtered by role permissions)
  - `DELETE /api/invitations/{id}` — cancel
- [ ] Therapist-patient binding: on acceptance, create relationship record
- [ ] Frontend: invite UI in admin dashboard, clinic settings, therapist patient list

### 2.3.4 — Password Reset & Recovery

- [ ] Verify Supabase password reset flow works for all products
- [ ] Shared `<ForgotPasswordForm />` component (if not already shared)
- [ ] Each product's login page links to forgot password
- [ ] Password reset email uses product-specific branding
- [ ] Test: reset → email → new password → login

### 2.3.5 — "Technology by NoctusAI" Footer

**Shared component:**
- [ ] Create `shared/frontend/src/design-system/components/PoweredByFooter.tsx`
  - Sidebar version: small text "Technology by NoctusAI" with subtle link
  - Landing page version: full footer bar with NoctusAI branding + contact info
  - Props: `variant: "sidebar" | "landing"`, optional contact info override
- [ ] Export from design system index

**Apply to all products:**
- [ ] Sidebar: add `PoweredByFooter variant="sidebar"` above BackToCore in all layouts
- [ ] Landing/login pages: add `PoweredByFooter variant="landing"` to public pages
- [ ] Core: add to login page and public pages
- [ ] Seed template: add to Layout + Login

### 2.3.6 — Resend Integration

- [x] Resend API key configured in .env
- [ ] Verify email delivery works: send test invitation from Core
- [ ] Update `send_invitation_email()` to support product-specific branding
- [ ] Create product-specific email templates (ERP, PF, Therapy branding)
- [ ] Test: invite → email received → link works → password set → login

### 2.3.7 — Tests for v2.3

- [ ] Core: role expansion tests (new org_role values)
- [ ] Shared: invitation utility tests (create, validate, accept, expire)
- [ ] ERP: team router tests (invite, accept, list, remove, role change)
- [ ] PF: team router tests
- [ ] Therapy: invitation router tests (all invite types)
- [ ] Shared: page status filtering tests
- [ ] Integration: end-to-end invite → accept → login flow

### 2.3.8 — Documentation

- [ ] Update CLAUDE.md: role system, page status, invitation pattern
- [ ] Update KNOWLEDGE-BASE/07-SHARED-LIBRARY.md: new shared modules
- [ ] Update KNOWLEDGE-BASE per product backend docs
- [ ] Update seed template docs

---

## v2.4 — Product Login, Landing Pages, Polish

### 2.4.1 — ERP Direct Login & Landing

- [ ] Create `pages/Landing.tsx` — public product presentation
  - Hero section with ERP value proposition
  - Feature highlights (CRM, sales funnel, AI matching, etc.)
  - Login/register CTA buttons
  - Responsive: mobile-first
- [ ] Update `pages/Login.tsx` — use shared `<LoginForm />` with ERP branding
  - Building2 icon, "ERP Imobiliario" title
  - Link to forgot password
  - "Acesse pelo NoctusAI" fallback link for SSO users
- [ ] Update `App.tsx` routing: public routes (landing, login, accept-invite)
- [ ] Update auth flow: support both SSO and direct Supabase login

### 2.4.2 — PF Direct Login & Landing

- [ ] Create `pages/Landing.tsx` — personal finance presentation
- [ ] Update `pages/Login.tsx` — use shared `<LoginForm />` with PF branding
  - DollarSign icon, "Financas Pessoais" title
- [ ] Update `App.tsx` routing
- [ ] Update auth flow

### 2.4.3 — Therapy Landing Page (already has login)

- [ ] Review existing `pages/Landing.tsx` — update if needed
- [ ] Ensure invitation accept flow works with therapy branding
- [ ] Test all invite types end-to-end

### 2.4.4 — Core Landing/Public Pages

- [ ] Review Core login page — ensure role selection works
- [ ] Review Core onboarding — ensure org creation works with new roles
- [ ] Test: signup → create org → buy license → enter product

### 2.4.5 — End-to-End Testing

- [ ] Flow 1: New user → Core signup → buy ERP license → enter ERP via SSO → invite employee → employee accepts → employee logs in directly
- [ ] Flow 2: Therapy admin → invite clinic → clinic accepts → clinic invites therapist → therapist invites patient
- [ ] Flow 3: PF user → invite family member → member accepts → member logs in
- [ ] Flow 4: Dev role → sees "in development" pages → member doesn't
- [ ] Flow 5: Password reset → email → new password → login

### 2.4.6 — Final Documentation

- [ ] Update all KNOWLEDGE-BASE docs
- [ ] Update CLAUDE.md with final patterns
- [ ] Update seed template to reflect all new patterns
- [ ] Final test count update

---

## Notes

_Use this section for decisions, context, and observations along the way._

- Resend API key: configured in .env (2026-04-13)
- LGPD: cross-product data sharing deferred until encryption is in place
- Core's auth-context.tsx uses React Context (not Zustand) — intentional, Core is different
- Core's login uses REST API (not Supabase) — intentional, Core manages auth differently
- Therapy uses clinic_id not org_id for multi-tenancy — architecturally different from ERP/PF
- ERP already has status_pagina + user_roles tables — extract pattern, don't rebuild
