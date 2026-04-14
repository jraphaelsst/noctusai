# NoctusAI Platform — Manual Testing Guide

> Test everything through the UI. If it can't be done through the UI, it's a missing feature.

## Pre-requisites

- [ ] `bash scripts/setup.sh` completed
- [ ] `.env` file configured with all keys
- [ ] `bash start.sh` running (all 5 backends + 5 frontends)
- [ ] Supabase Dashboard: `seed` added to "Exposed schemas" (Project Settings → API)

Services running:
- Core: http://localhost:5173 (frontend) / http://localhost:8000 (API)
- ERP: http://localhost:8080 / http://localhost:8001
- PF: http://localhost:8090 / http://localhost:8002
- Therapy: http://localhost:8095 / http://localhost:8003
- Seed: http://localhost:8100 / http://localhost:8004

---

## 1. Core Platform — Registration & Org Setup

### 1.1 Landing / Login Page

- [ ] Open http://localhost:5173
- [ ] Page loads without errors (no white screen, no console errors)
- [ ] "NoctusAI" branding visible
- [ ] Login form shows: email field, password field, submit button
- [ ] Signup toggle exists ("Criar conta" or similar)
- [ ] Form validates: try submitting empty → error messages appear
- [ ] Form validates: try invalid email format → error message
- [ ] Form validates: try password less than 6 chars → error message

### 1.2 New User Registration

- [ ] Toggle to signup mode
- [ ] Fill in: Nome, Email (use a real email you can check), Empresa, Password
- [ ] Submit → should succeed, redirect to dashboard
- [ ] Check email inbox: welcome email received (if Resend configured)
- [ ] If no email: check server logs for `Email (not sent — no provider)`

### 1.3 Core Dashboard (first login)

- [ ] Dashboard loads with "Bem-vindo, [Name]!" greeting
- [ ] Header shows: user name, email, role badge, theme toggle, logout button
- [ ] User card (hover/click on avatar): shows name, email, role
- [ ] Products grid visible (may show "Solicitar acesso" since no licenses yet)
- [ ] If org is new/free: upgrade banner or trial info visible
- [ ] Theme toggle works: click → switches dark/light, persists on reload

### 1.4 Profile Edit

- [ ] Click on user avatar/name in header → profile card opens
- [ ] Click "Editar" → edit form appears
- [ ] Change name → save → name updates in header immediately
- [ ] Change password → save → logout → login with new password works
- [ ] Cancel edit → form closes, no changes applied

### 1.5 Admin Panel (if admin user)

- [ ] "Admin Panel" button visible in header (only for admins)
- [ ] Click → navigates to /admin
- [ ] Admin sidebar shows: Dashboard, Organizacoes, Usuarios, Subscriptions, API Keys, Plans, Products, Webhooks, Settings
- [ ] Each admin page loads without errors
- [ ] Admin → Usuarios: shows user list with role badges
- [ ] Admin → Usuarios → Edit: can change org_role (dropdown shows all 7 roles: Proprietario, Administrador, Gerente, Membro, Visualizador, Desenvolvedor, Teste)
- [ ] Save role change → role updates in list

---

## 2. Core — Team Management

### 2.1 Team Page

- [ ] Navigate to Team Management page
- [ ] Shows "Membros" section with current org members
- [ ] Shows "Convites Pendentes" section (empty initially)
- [ ] "Convidar" button visible

### 2.2 Invite a Member

- [ ] Click "Convidar"
- [ ] Modal/form appears: email field, role dropdown
- [ ] Role dropdown shows available roles
- [ ] Enter a real email address you can check
- [ ] Select role (e.g. "Membro")
- [ ] Submit → success message
- [ ] New invitation appears in "Convites Pendentes" with: email, role, expiry date
- [ ] Check inbox: invitation email arrives with "Aceitar Convite" button

### 2.3 Duplicate Invite

- [ ] Try inviting the same email again
- [ ] Expected: error message "Ja existe um convite pendente para este email"

### 2.4 Cancel Invite

- [ ] Click cancel/X on a pending invitation
- [ ] Invitation disappears from pending list
- [ ] If you try the old invitation link: should show error "Convite ja foi utilizado ou cancelado"

### 2.5 Accept Invite (open in incognito/different browser)

- [ ] Open the invitation link from the email
- [ ] AcceptInvite page loads: shows org name, role
- [ ] Form shows: email (read-only), nome field, password field
- [ ] Submit with empty fields → validation errors
- [ ] Submit with password < 6 chars → validation error
- [ ] Fill in correctly → submit → "Convite aceito!" success screen
- [ ] Click "Ir para o login" → redirects to login
- [ ] Log in with the new credentials → Core dashboard loads
- [ ] New member visible in team list (back in admin's browser)

---

## 3. SSO — Core to Products

### 3.1 License Setup

- [ ] In Core admin panel: go to Products → verify ERP/PF/Therapy/Seed are listed
- [ ] Go to Licenses (or the mechanism to grant access) → grant your org a license for each product
- [ ] Return to Dashboard → products should now show "Acessar" (green dot)

### 3.2 SSO into ERP

- [ ] On Core Dashboard, click ERP product card
- [ ] New tab opens at http://localhost:8080/sso?token=...
- [ ] Loading spinner: "Autenticando via NoctusAI..."
- [ ] Redirects to ERP dashboard
- [ ] **Sidebar checks:**
  - [ ] Brand icon + title visible at top
  - [ ] Org name visible as subtitle (not hardcoded)
  - [ ] Navigation groups visible (Principal, Comercial, Financeiro, etc.)
  - [ ] "Voltar ao NoctusAI" link at bottom of sidebar
  - [ ] Sidebar is collapsible (hamburger on mobile)
- [ ] **Header checks:**
  - [ ] User name + email visible
  - [ ] Role badge shows "Administrador" (if org owner/admin)
  - [ ] Theme toggle works
  - [ ] Notification bell visible (with badge count if notifications exist)
  - [ ] Profile edit works (change name → saves)
- [ ] **Admin features visible:** Equipe, Usuarios, Admin pages in sidebar

### 3.3 SSO into PF

- [ ] Click PF product card on Core Dashboard
- [ ] Same SSO flow → PF dashboard
- [ ] Sidebar: "Financas Pessoais" brand, org name subtitle, nav groups (Principal, Planejamento, Investimentos, Relatorios)
- [ ] "Voltar ao NoctusAI" visible
- [ ] "Equipe" nav item visible (if admin)

### 3.4 SSO into Therapy

- [ ] Click Therapy product card
- [ ] SSO → Therapy admin dashboard
- [ ] Role-based nav: should see Admin nav groups (Principal, Operacional, Sistema)
- [ ] "Voltar ao NoctusAI" visible

### 3.5 SSO into Seed

- [ ] Click Seed product card
- [ ] SSO → Seed dashboard
- [ ] Dashboard shows "Stack Status" card with user info, org info, SSO context
- [ ] This validates the entire shared stack is wired correctly

### 3.6 SSO Logout

- [ ] In any product (entered via SSO), click Logout
- [ ] Expected: redirects to Core (http://localhost:5173), NOT to product login
- [ ] Core dashboard loads (you're still logged in on Core)

---

## 4. Direct Login — Product Landing Pages

### 4.1 ERP Landing Page

- [ ] Open http://localhost:8080 in a fresh browser (not logged in)
- [ ] Landing page loads: hero section, feature cards, "Entrar" CTA
- [ ] **Visual checks:**
  - [ ] Responsive: resize to mobile (375px) → single column, no overflow
  - [ ] Resize to tablet (768px) → 2-column grid
  - [ ] Resize to desktop (1440px) → 3-column grid
- [ ] "Entrar" button → navigates to /login
- [ ] Navbar is sticky on scroll

### 4.2 ERP Login Page

- [ ] Login page loads with Building2 icon, "ERP Imobiliario" title
- [ ] "Esqueceu a senha?" link visible
- [ ] "Acesse pelo NoctusAI" link at bottom
- [ ] Submit empty form → validation errors
- [ ] Submit invalid email → error
- [ ] Submit wrong password → toast error "Erro ao entrar"
- [ ] Submit correct credentials → redirects to /dashboard
- [ ] No "Voltar ao NoctusAI" in sidebar (direct login, not SSO)

### 4.3 PF Landing Page

- [ ] Open http://localhost:8090
- [ ] Landing page: hero, feature cards, "Por que usar?" section
- [ ] Responsive layout works at 375px / 768px / 1440px
- [ ] "Entrar" → login page
- [ ] Login with DollarSign icon, "Financas Pessoais" title
- [ ] Same validation tests as ERP

### 4.4 Therapy Landing Page

- [ ] Open http://localhost:8095
- [ ] Full landing page: hero, features, how-it-works, FAQ
- [ ] "Entrar" → login, "Criar conta" → register
- [ ] Login works, redirects to role-based dashboard

### 4.5 Seed Landing Page

- [ ] Open http://localhost:8100
- [ ] Minimal landing: "Seed Product" hero, login CTA
- [ ] Login works with Sprout icon branding

### 4.6 Direct Login Logout

- [ ] Log in directly to any product (not via SSO)
- [ ] Click logout
- [ ] Expected: redirects to /login (product's own), NOT to Core

---

## 5. ERP — Team Invitations (Product-Level)

### 5.1 Navigate to Equipe

- [ ] Log in to ERP as admin (via SSO or direct)
- [ ] Sidebar → Painel de Controle → "Equipe"
- [ ] Page loads: "Membros" section + "Convites Pendentes"
- [ ] Current user visible in members list with "Admin" badge

### 5.2 Invite a Corretor

- [ ] Click "Convidar"
- [ ] Dialog appears: email field, role dropdown
- [ ] Role dropdown shows: Administrador, Coordenador, Desenvolvedor, Corretor
- [ ] Enter a real email, select "Corretor"
- [ ] Submit → toast "Convite enviado" (or similar)
- [ ] Invitation appears in pending list with: email, "Corretor" badge, expiry

### 5.3 Accept ERP Invitation (different browser/incognito)

- [ ] Open invitation link from email
- [ ] Page loads: ERP branding (Building2 icon), form with email + nome + password
- [ ] Fill in nome and password → submit
- [ ] Success: "Convite aceito!"
- [ ] Navigate to login → log in with new credentials
- [ ] Dashboard loads with corretor-level nav (limited menu — no admin pages)
- [ ] Sidebar does NOT show "Painel de Controle" (corretor can't see admin pages)

### 5.4 Verify Corretor Restrictions

- [ ] As corretor: try navigating to /equipe directly → should be redirected or see access denied
- [ ] As corretor: sidebar shows only corretor-visible pages
- [ ] As corretor: no "Voltar ao NoctusAI" (they logged in directly, not SSO)

### 5.5 Admin Removes Corretor

- [ ] Switch back to admin browser
- [ ] Equipe page → find the corretor in members list
- [ ] Click remove button → confirmation dialog
- [ ] Confirm → member removed from list
- [ ] Corretor's next page load should fail (session invalidated or data gone)

### 5.6 Admin Changes Role

- [ ] Invite another user → they accept → appear as member
- [ ] On Equipe page, find the member
- [ ] Click role dropdown/edit → change to "Coordenador"
- [ ] Save → role badge updates
- [ ] The user's sidebar should update on next load to show coordenador-level pages

---

## 6. PF — Team Invitations

### 6.1 PF Team Management

- [ ] Log in to PF as admin
- [ ] Navigate to "Equipe" page
- [ ] Invite a member (email + "Membro" role)
- [ ] Invitation appears in pending list
- [ ] Accept in incognito → new user can log in
- [ ] New user sees member-level nav

### 6.2 PF Remove Member

- [ ] Admin removes the member from Equipe page
- [ ] Member disappears from list

---

## 7. Therapy — Multi-Type Invitations

> Note: Therapy invite UI is currently backend-only for some flows. Test via the AcceptInvite page for acceptance, and via API for creation where no UI exists yet.

### 7.1 AcceptInvite Page

- [ ] Navigate to http://localhost:8095/accept-invite/FAKE-TOKEN
- [ ] Should show error: "Convite nao encontrado"
- [ ] Navigate to a valid token URL (if you have one from API testing)
- [ ] Form loads: Heart icon, "Plataforma de Terapia", email + nome + password
- [ ] Submit → success

### 7.2 Therapy Login + Role-Based Nav

- [ ] Log in as different roles and verify nav:
  - [ ] **platform_admin**: sees Admin nav (Dashboard, Terapeutas, Clinicas, Pacientes, etc.)
  - [ ] **clinic_admin**: sees Clinic nav (Dashboard, Terapeutas, Pacientes, Financeiro)
  - [ ] **therapist**: sees Therapist nav (Dashboard, Agenda, Pacientes, Sessoes, etc.)
  - [ ] **patient**: sees Patient nav (Dashboard, Encontrar Terapeuta, Minha Agenda, etc.)

---

## 8. Password Recovery

### 8.1 ERP Forgot Password

- [ ] Go to http://localhost:8080/login
- [ ] Click "Esqueceu a senha?"
- [ ] Forgot password page loads: Building2 icon, email field
- [ ] Submit empty → validation error
- [ ] Submit valid email → success screen: "Email enviado!" with checkmark
- [ ] "Voltar ao login" link → goes back to /login
- [ ] Check inbox: Supabase sends password reset email
- [ ] Click reset link → opens Supabase password reset form
- [ ] Set new password → log in with new password

### 8.2 PF Forgot Password

- [ ] Same flow at http://localhost:8090/forgot-password
- [ ] DollarSign icon branding
- [ ] Reset works

### 8.3 Therapy Forgot Password

- [ ] Same flow at http://localhost:8095/forgot-password
- [ ] Heart icon branding
- [ ] Reset works

---

## 9. Notification System

### 9.1 Notification Bell

- [ ] In any product, check the header for notification bell icon
- [ ] Click bell → dropdown/popover opens
- [ ] If no notifications: shows "Nenhuma notificacao" or empty state
- [ ] Bell shows badge count if unread notifications exist

### 9.2 Create a Notification (via Core)

- [ ] In Core, perform an action that generates a notification (e.g. team invite)
- [ ] Switch to a product → bell should show updated count
- [ ] Click bell → notification visible in list
- [ ] Click "Marcar como lida" → notification marked, count decreases
- [ ] "Marcar todas como lidas" → all cleared

---

## 10. Theme & Responsiveness

### 10.1 Dark Mode

- [ ] In any product, click theme toggle in header
- [ ] Entire UI switches to dark mode: sidebar, content, cards, forms
- [ ] Reload page → dark mode persists (stored in localStorage)
- [ ] Toggle back → light mode, persists

### 10.2 Mobile Responsiveness

For each product (ERP, PF, Therapy, Seed):

- [ ] Resize browser to 375px width (or use DevTools mobile simulation)
- [ ] Sidebar collapses to hamburger menu
- [ ] Click hamburger → sidebar slides in as overlay
- [ ] Click outside sidebar → closes
- [ ] All content is single-column, no horizontal overflow
- [ ] Buttons/inputs are at least 44px tall (tap-friendly)
- [ ] Forms are usable on mobile

### 10.3 Tablet

- [ ] Resize to 768px
- [ ] Layout adjusts: 2-column grids where applicable
- [ ] Sidebar may be visible or collapsible depending on product

---

## 11. Error States & Edge Cases

### 11.1 404 Page

For each product:
- [ ] Navigate to a non-existent URL (e.g. /this-page-does-not-exist)
- [ ] 404 page loads: "Pagina nao encontrada" message
- [ ] "Voltar" and "Ir ao Inicio" buttons work

### 11.2 Expired Session

- [ ] Log in to a product
- [ ] Wait for token to expire (~1 hour) OR manually clear localStorage
- [ ] Try to navigate → should auto-refresh token OR redirect to login
- [ ] No infinite error loops

### 11.3 Invalid SSO Token

- [ ] Navigate to http://localhost:8080/sso?token=INVALID
- [ ] Error screen: "Erro no login SSO" with retry button and "Voltar ao NoctusAI" link

### 11.4 Network Error

- [ ] Stop a backend (kill the uvicorn process)
- [ ] Try to use the product → error toasts appear (not white screen)
- [ ] Restart backend → product recovers on next request

---

## 12. Health Checks

Open each URL in browser or curl:

- [ ] http://localhost:8000/api/health → `{"status": "ok", "product": "NoctusAI Core", "version": "..."}`
- [ ] http://localhost:8001/api/health → `{"status": "ok", "product": "ERP Imobiliario", "version": "..."}`
- [ ] http://localhost:8002/api/health → `{"status": "ok", "product": "Personal Finance", "version": "..."}`
- [ ] http://localhost:8003/api/health → `{"status": "ok", "product": "Therapy Platform", "version": "..."}`
- [ ] http://localhost:8004/api/health → `{"status": "ok", "product": "Seed Product", "version": "..."}`
- [ ] http://localhost:8005/api/health → `{"status": "ok", "product": "NoctusAI Daily Life", "version": "..."}`

---

## 13. Daily Life — Feature Pages

### 13.1 Tarefas (Tasks)

- [ ] Navigate to /tarefas
- [ ] Stats cards visible at top (total, pendentes, em progresso, concluidas)
- [ ] Click "Nova Tarefa" → modal opens
- [ ] Create task: fill titulo, descricao, select prioridade "Alta", add categoria, set data_vencimento
- [ ] Submit → task appears in list with red "Alta" badge
- [ ] Create another task with "Baixa" prioridade → green badge
- [ ] Filter by status: select "Pendente" → only pending tasks shown
- [ ] Filter by prioridade: select "Alta" → only high priority shown
- [ ] Click a task → edit modal opens with current values
- [ ] Change status to "Concluida" → save → task shows strikethrough or completed badge
- [ ] Delete a task → confirm dialog → task removed
- [ ] Verify stats update after changes
- [ ] Overdue tasks: set data_vencimento to yesterday → date shows in red

### 13.2 Metas (Goals & Habits)

- [ ] Navigate to /metas
- [ ] Click "Nova Meta" → modal opens
- [ ] Create a goal: titulo, tipo="Meta", meta_valor=100, unidade="km", data_limite
- [ ] Submit → goal card shows with progress bar at 0%
- [ ] Create a habit: titulo, tipo="Habito", frequencia="Diario"
- [ ] Submit → habit card shows with purple badge and frequency indicator
- [ ] Filter by tipo: select "Habito" → only habits shown
- [ ] On a habit card: click "Registrar" → check-in modal opens
- [ ] Fill valor=10, nota="Morning run" → submit
- [ ] Progress bar updates (10/100 = 10%)
- [ ] Register another check-in: valor=15 → progress updates to 25%
- [ ] Expand check-in history → shows both entries with dates and values
- [ ] Edit goal: change meta_valor → save → progress % recalculates
- [ ] Delete goal → confirm → removed

### 13.3 Agenda (Schedule)

- [ ] Navigate to /agenda
- [ ] Month navigation: click prev/next → month label changes
- [ ] Click "Novo Evento" → modal opens
- [ ] Create event: titulo, data_inicio, data_fim, local, select a color
- [ ] Submit → event appears with colored dot
- [ ] Create all-day event: toggle dia_inteiro on → datetime inputs become date-only
- [ ] Submit → shows "Dia inteiro" badge
- [ ] Create recurring event: select recorrencia="Semanal", set recorrencia_fim 1 month out
- [ ] Submit → recurring event shows 🔄 badge
- [ ] Set lembrete_minutos=15 → event shows reminder badge
- [ ] Click an event → edit modal with current values
- [ ] Change color → save → dot color updates
- [ ] Delete event → confirm → removed
- [ ] Click "Hoje" → navigates back to current month

### 13.4 Notas (Notes)

- [ ] Navigate to /notas
- [ ] Click "Nova Nota" → modal opens
- [ ] Create note: titulo, conteudo (multiline text), tags "trabalho, importante"
- [ ] Submit → note card shows with truncated content preview and tag chips
- [ ] Create another note with fixada=true → pinned note shows pin icon and appears first
- [ ] Type in search box → results filter as you type (debounced)
- [ ] Search a word only in conteudo (not titulo) → note still found
- [ ] Click pin icon on unpinned note → becomes pinned, moves to top
- [ ] Click pin icon on pinned note → unpinned, moves down
- [ ] Edit note: change content → save → content updates
- [ ] Delete note → confirm → removed
- [ ] Tags display as colored chips with consistent colors

---

## 14. Resend Email Verification

- [ ] Start all services
- [ ] In ERP, go to Equipe → invite a real email address
- [ ] Check server logs: confirm email sending attempted (not "not sent — no provider")
- [ ] Check email inbox: invitation email arrives from NoctusAI
- [ ] Email shows: product name, org name, role, inviter name, "Aceitar Convite" button
- [ ] Click the button → opens AcceptInvite page in browser
- [ ] Complete acceptance → verify full flow works end-to-end
- [ ] Repeat for PF: invite → email → accept
- [ ] Test forgot password: go to /forgot-password → enter email → Supabase sends reset email

---

## 15. Therapy Admin Invite UI (backend-only for now)

> Note: Therapy invitation creation has no frontend UI yet. Test via API.

- [ ] Start Therapy backend
- [ ] Using curl or Postman, as platform_admin:
  - `POST /api/invitations` with `{ "email": "clinic@test.com", "role": "clinic_admin", "invite_type": "platform_to_clinic" }`
  - Verify 200 response with invitation record
- [ ] Validate the token: `GET /api/invitations/accept/validate?token=TOKEN`
- [ ] Accept: `POST /api/invitations/accept` with `{ "token": "TOKEN", "nome": "Test Clinic", "password": "123456" }`
- [ ] As therapist, invite a patient:
  - `POST /api/invitations` with `{ "email": "patient@test.com", "role": "patient", "invite_type": "therapist_to_patient" }`
- [ ] As patient, try to invite → 403

---

## 16. Daily Life — Focus & Metrics (desenvolvimento)

> These pages are flagged as "desenvolvimento" in status_pagina. Only dev/owner roles can see them.

- [ ] Log in as a user with "dev" org_role → sidebar shows "Foco" and "Metricas" with DEV badge
- [ ] Log in as regular member → "Foco" and "Metricas" NOT visible in sidebar
- [ ] As dev user, test via API:
  - `POST /api/foco` with `{ "tipo": "pomodoro", "duracao_minutos": 25 }`
  - `GET /api/foco` → returns session list
  - `GET /api/foco/stats` → returns totals
  - `POST /api/metricas` with `{ "data": "2026-04-14", "score": 85 }`
  - `GET /api/metricas/resumo` → returns averages and streaks

---

## Test Results Log

| Section | Test | Date | Pass/Fail | Notes |
|---------|------|------|-----------|-------|
| 1.1 | Core login page loads | | | |
| 1.2 | New user registration | | | |
| 1.3 | Dashboard loads correctly | | | |
| 1.4 | Profile edit works | | | |
| 1.5 | Admin panel accessible | | | |
| 2.1 | Team page loads | | | |
| 2.2 | Invite member | | | |
| 2.3 | Duplicate invite blocked | | | |
| 2.4 | Cancel invite | | | |
| 2.5 | Accept invite | | | |
| 3.1 | Licenses granted | | | |
| 3.2 | SSO → ERP | | | |
| 3.3 | SSO → PF | | | |
| 3.4 | SSO → Therapy | | | |
| 3.5 | SSO → Seed | | | |
| 3.6 | SSO logout → Core | | | |
| 4.1 | ERP landing page | | | |
| 4.2 | ERP direct login | | | |
| 4.3 | PF landing + login | | | |
| 4.4 | Therapy landing + login | | | |
| 4.5 | Seed landing + login | | | |
| 4.6 | Direct logout → /login | | | |
| 5.1 | ERP Equipe page | | | |
| 5.2 | ERP invite corretor | | | |
| 5.3 | Accept ERP invite | | | |
| 5.4 | Corretor restrictions | | | |
| 5.5 | Admin removes member | | | |
| 5.6 | Admin changes role | | | |
| 6.1 | PF team management | | | |
| 6.2 | PF remove member | | | |
| 7.1 | Therapy AcceptInvite | | | |
| 7.2 | Therapy role-based nav | | | |
| 8.1 | ERP forgot password | | | |
| 8.2 | PF forgot password | | | |
| 8.3 | Therapy forgot password | | | |
| 9.1 | Notification bell | | | |
| 9.2 | Notification lifecycle | | | |
| 10.1 | Dark mode toggle | | | |
| 10.2 | Mobile responsiveness | | | |
| 10.3 | Tablet layout | | | |
| 11.1 | 404 pages | | | |
| 11.2 | Expired session | | | |
| 11.3 | Invalid SSO token | | | |
| 11.4 | Network error recovery | | | |
| 12 | Health checks (6 products) | | | |
| 13.1 | Daily Life Tarefas | | | |
| 13.2 | Daily Life Metas | | | |
| 13.3 | Daily Life Agenda | | | |
| 13.4 | Daily Life Notas | | | |
| 14 | Resend email verification | | | |
| 15 | Therapy admin invite (API) | | | |
| 16 | Daily Life Focus + Metrics (dev) | | | |
