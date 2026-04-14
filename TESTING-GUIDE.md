# NoctusAI Platform — Manual Testing Guide

## Pre-requisites

1. Run `bash scripts/setup.sh` (if not done already)
2. Ensure `.env` has all required keys (especially `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `RESEND_API_KEY`)
3. Start all services: `bash start.sh`

---

## 1. Supabase Configuration (one-time)

### 1.1 Add "seed" to Exposed Schemas

1. Open Supabase Dashboard → your project
2. Go to **Project Settings** → **API** (left sidebar)
3. Scroll to **"Exposed schemas"**
4. Current list should show: `public, erp, personal-finance, therapy`
5. Add `seed` to the list
6. Click **Save**
7. Wait ~30 seconds for PostgREST to reload

**Verify:** Open `https://YOUR-PROJECT.supabase.co/rest/v1/` with header `Accept-Profile: seed` — should not return an error.

### 1.2 Register Seed Product

Run this in Supabase SQL Editor or via MCP:

```sql
INSERT INTO public.products (nome, slug, descricao, icone, url_base, cor, ativo)
VALUES ('Seed Product', 'seed', 'Reference implementation', '🌱', 'http://localhost:8100', '#22c55e', true)
ON CONFLICT (slug) DO NOTHING;
```

---

## 2. SSO Flow Testing

### 2.1 Core → ERP via SSO

- [ ] **Step 1:** Open `http://localhost:5173` (Core)
- [ ] **Step 2:** Log in as org owner
- [ ] **Step 3:** Dashboard shows products with "Acessar" button
- [ ] **Step 4:** Click ERP product card
- [ ] **Step 5:** New tab opens at `http://localhost:8080/sso?token=...`
- [ ] **Step 6:** SSO callback processes, redirects to `/dashboard`
- [ ] **Step 7:** Sidebar shows org name as subtitle
- [ ] **Step 8:** Sidebar shows "Back to NoctusAI" link at bottom
- [ ] **Step 9:** Header shows "Administrador" role (if org owner)

**Expected:** Smooth redirect, no errors, admin access in ERP.

### 2.2 Core → PF via SSO

- [ ] Repeat steps above for PF (`http://localhost:8090`)
- [ ] Verify org name in sidebar subtitle
- [ ] Verify admin role in header

### 2.3 Core → Therapy via SSO

- [ ] Repeat for Therapy (`http://localhost:8095`)
- [ ] Should see admin dashboard (if org_role=owner/admin or noctus_role=admin)

### 2.4 Core → Seed via SSO

- [ ] Repeat for Seed (`http://localhost:8100`)
- [ ] Dashboard should show "Stack Status" card with user/org info

### 2.5 SSO Logout Redirect

- [ ] In any product (entered via SSO), click logout
- [ ] **Expected:** Redirects to NoctusAI Core (`http://localhost:5173`), NOT to product login

---

## 3. Direct Login Testing

### 3.1 ERP Direct Login

- [ ] Open `http://localhost:8080` (not via SSO)
- [ ] Should see Landing page with "Entrar" button
- [ ] Click "Entrar" → Login page
- [ ] Log in with Supabase credentials
- [ ] **Expected:** Redirects to `/dashboard`, no "Back to NoctusAI" link (not SSO)

### 3.2 PF Direct Login

- [ ] Open `http://localhost:8090`
- [ ] Landing page → Login → Dashboard
- [ ] No "Back to NoctusAI" (direct login, not SSO)

### 3.3 Therapy Direct Login

- [ ] Open `http://localhost:8095`
- [ ] Landing page → Login → Role-based dashboard

### 3.4 Direct Logout Redirect

- [ ] Log in directly (not via SSO) to any product
- [ ] Click logout
- [ ] **Expected:** Redirects to `/login` (product's own login page), NOT to Core

---

## 4. Invitation Flow Testing

### 4.1 ERP: Invite Employee

- [ ] **Step 1:** Log in to ERP as admin
- [ ] **Step 2:** Navigate to "Equipe" page (sidebar → Painel de Controle → Equipe)
- [ ] **Step 3:** Click "Convidar" button
- [ ] **Step 4:** Enter email + select role (e.g. "Corretor")
- [ ] **Step 5:** Click submit
- [ ] **Step 6:** Invitation appears in "Convites Pendentes" section
- [ ] **Step 7:** Check email inbox — invitation email should arrive from NoctusAI

**If RESEND_API_KEY is set:** Real email arrives with "Aceitar Convite" button.
**If not set:** Check server logs for `Email (not sent — no provider): to=...`

### 4.2 Accept Invitation

- [ ] **Step 1:** Open the invitation link (or manually go to `http://localhost:8080/accept-invite/TOKEN`)
- [ ] **Step 2:** Form shows: email (read-only), nome, password fields
- [ ] **Step 3:** Fill in nome + password (min 6 chars)
- [ ] **Step 4:** Click "Aceitar e Criar Conta"
- [ ] **Step 5:** Success screen: "Convite aceito!"
- [ ] **Step 6:** Click "Ir para o login"
- [ ] **Step 7:** Log in with the email + password just set
- [ ] **Step 8:** Should see corretor-level dashboard (limited nav)

### 4.3 Cancel Invitation

- [ ] Create a new invitation
- [ ] Click the cancel button (X) on the pending invitation
- [ ] **Expected:** Invitation disappears from pending list

### 4.4 Duplicate Email

- [ ] Try inviting an email that's already a member
- [ ] **Expected:** Error "Este email ja e membro da organizacao" (409)

### 4.5 PF Invitation

- [ ] Repeat invite flow in PF (admin → invite member → accept → login)
- [ ] PF roles: admin / member

### 4.6 Therapy Invitation (Admin → Clinic)

- [ ] Log in to Therapy as platform_admin
- [ ] (Note: invite UI is in backend only for now — test via API)
- [ ] `POST /api/invitations` with `{ email, role: "clinic_admin", invite_type: "platform_to_clinic" }`
- [ ] Verify invitation created

### 4.7 Therapy: Therapist → Patient (Bound)

- [ ] Log in as therapist
- [ ] `POST /api/invitations` with `{ email, role: "patient", invite_type: "therapist_to_patient" }`
- [ ] Accept invitation
- [ ] Verify patient profile has `therapist_id` binding

---

## 5. Password Recovery Testing

### 5.1 Forgot Password Flow

- [ ] **Step 1:** Go to any product's login page
- [ ] **Step 2:** Click "Esqueceu a senha?"
- [ ] **Step 3:** Enter email
- [ ] **Step 4:** Click "Enviar Link"
- [ ] **Step 5:** Success screen: "Email enviado!"
- [ ] **Step 6:** Check inbox for Supabase password reset email
- [ ] **Step 7:** Click reset link → set new password
- [ ] **Step 8:** Log in with new password

**Note:** Supabase sends the reset email directly (not via Resend). The email comes from Supabase's configured sender.

---

## 6. Role & Access Control Testing

### 6.1 Dev Role — Page Visibility

- [ ] Assign a user the "dev" org_role (via Core admin panel → Users)
- [ ] Set a page to "desenvolvimento" status in the product's `status_pagina` table:
  ```sql
  UPDATE erp.status_pagina SET status = 'desenvolvimento' WHERE nome_pagina = 'matching';
  ```
- [ ] Log in as dev user → should see the page with "DEV" badge
- [ ] Log in as regular member → page should be HIDDEN from sidebar
- [ ] Log in as owner → should see it (owners see everything)

### 6.2 Admin Cannot Remove Owner

- [ ] As admin, try to remove the org owner from the team
- [ ] **Expected:** Error 400/403 "Cannot remove owner"

### 6.3 Member Cannot Invite

- [ ] Log in as a regular member (not admin/owner)
- [ ] Try to access team management or call invite API
- [ ] **Expected:** 403 "Acesso restrito a administradores"

---

## 7. Context Awareness Testing

### 7.1 Trial Subscription Banner

- [ ] Set a subscription to "trial" with `expires_at` within 7 days:
  ```sql
  UPDATE public.subscriptions SET status = 'trial', expires_at = now() + interval '3 days' WHERE org_id = 'YOUR_ORG_ID';
  ```
- [ ] SSO into any product
- [ ] **Expected:** Yellow banner at top: "Periodo de teste expira em 3 dias."

### 7.2 License Expiry Warning

- [ ] Set a license `fim` within 7 days:
  ```sql
  UPDATE public.licenses SET fim = now() + interval '5 days' WHERE org_id = 'YOUR_ORG_ID' AND product_id = 'PRODUCT_ID';
  ```
- [ ] SSO into that product
- [ ] **Expected:** Red banner: "Licenca expira em 5 dias."

### 7.3 Org Name in Sidebar

- [ ] SSO into any product
- [ ] **Expected:** Sidebar subtitle shows org name (not hardcoded product name)

---

## 8. Health Check Verification

All backends should respond to health checks:

```bash
curl http://localhost:8000/api/health   # Core
curl http://localhost:8001/api/health   # ERP
curl http://localhost:8002/api/health   # PF
curl http://localhost:8003/api/health   # Therapy
curl http://localhost:8004/api/health   # Seed
```

**Expected response format:**
```json
{"status": "ok", "product": "Product Name", "version": "0.x.0"}
```

---

## Test Results Log

_Record results here as you test._

| # | Test | Date | Result | Notes |
|---|------|------|--------|-------|
| 1.1 | Seed exposed schema | | | |
| 2.1 | Core → ERP SSO | | | |
| 2.2 | Core → PF SSO | | | |
| 2.3 | Core → Therapy SSO | | | |
| 2.4 | Core → Seed SSO | | | |
| 2.5 | SSO logout redirect | | | |
| 3.1 | ERP direct login | | | |
| 3.2 | PF direct login | | | |
| 3.3 | Therapy direct login | | | |
| 3.4 | Direct logout redirect | | | |
| 4.1 | ERP invite employee | | | |
| 4.2 | Accept invitation | | | |
| 4.3 | Cancel invitation | | | |
| 4.4 | Duplicate email | | | |
| 4.5 | PF invitation | | | |
| 4.6 | Therapy admin→clinic | | | |
| 4.7 | Therapist→patient bound | | | |
| 5.1 | Forgot password | | | |
| 6.1 | Dev role visibility | | | |
| 6.2 | Cannot remove owner | | | |
| 6.3 | Member cannot invite | | | |
| 7.1 | Trial banner | | | |
| 7.2 | License expiry warning | | | |
| 7.3 | Org name in sidebar | | | |
| 8 | Health checks (5 products) | | | |
