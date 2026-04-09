# Therapy Platform — Manual QA Checklist

> **Purpose**: Walk through every user flow to verify frontend↔backend integration.
> Run `bash start.sh` and open `http://localhost:8095` before starting.
>
> Mark each item as you test. Note any issues in the "Issues" column.

---

## Prerequisites
- [ ] Backend running on port 8003 (`curl localhost:8003/health` returns OK)
- [ ] Frontend running on port 8095
- [ ] Supabase schema `therapy` exposed in API settings
- [ ] Platform admin user seeded (see Phase 8.4 in implementation plan)
- [ ] `.env` files configured (root + frontend)

---

## 1. Landing Page & Public Routes

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 1.1 | Open `http://localhost:8095` | Landing page loads with hero, features, FAQ | [ ] | |
| 1.2 | Click "Encontrar Terapeuta" (not logged in) | Redirect to /login or /register | [ ] | |
| 1.3 | Click "Sou Terapeuta" | Redirect to /register | [ ] | |
| 1.4 | Click "Sou uma Clinica" | Redirect to /register | [ ] | |
| 1.5 | Navigate to /termos | Terms of Use page loads | [ ] | |
| 1.6 | Navigate to /privacidade | Privacy Policy page loads | [ ] | |
| 1.7 | Navigate to /invalid-page | 404 page with back button | [ ] | |

---

## 2. Registration

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 2.1 | Register as Patient | Step 1: role cards shown. Select "Sou Paciente". Step 2: form (nome, email, senha, telefone). Step 3: "Conta Criada!" | [ ] | |
| 2.2 | Register as Therapist | Step 2: form includes CRP, bio. Step 3: "Aguardando aprovacao" | [ ] | |
| 2.3 | Register as Clinic | Step 2: form includes nome clinica, CNPJ, responsavel, telefone. Step 3: "Aguardando aprovacao" | [ ] | |
| 2.4 | Register with existing email | Error toast: email already exists | [ ] | |
| 2.5 | Register with short password (<8 chars) | Inline validation error | [ ] | |
| 2.6 | Register with invalid email | Inline validation error | [ ] | |
| 2.7 | Navigate to /login from register | Link works | [ ] | |

---

## 3. Login

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 3.1 | Login as Patient | Redirect to /patient dashboard | [ ] | |
| 3.2 | Login as Therapist | Redirect to /therapist dashboard | [ ] | |
| 3.3 | Login as Clinic Admin | Redirect to /clinic dashboard | [ ] | |
| 3.4 | Login as Platform Admin | Redirect to /admin dashboard | [ ] | |
| 3.5 | Login with wrong password | Error toast | [ ] | |
| 3.6 | Login with nonexistent email | Error toast | [ ] | |
| 3.7 | "Esqueceu a senha?" link | Navigate to /forgot-password | [ ] | |
| 3.8 | Forgot password form | Submit email → success message | [ ] | |

---

## 4. Platform Admin — Approval Flow

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 4.1 | Admin dashboard loads | Shows metrics cards (may be zero) | [ ] | |
| 4.2 | Admin → Terapeutas page | List of therapists with status tabs | [ ] | |
| 4.3 | Filter "Pendentes" tab | Shows only pending therapists | [ ] | |
| 4.4 | Approve a therapist | Status changes to "Aprovado", toast success | [ ] | |
| 4.5 | Reject a therapist | Reason dialog → status changes to "Rejeitado" | [ ] | |
| 4.6 | Admin → Clinicas page | List of clinics with status tabs | [ ] | |
| 4.7 | Approve a clinic | Same flow as therapist approval | [ ] | |
| 4.8 | Admin → Pacientes page | List of patients | [ ] | |
| 4.9 | Admin → Configuracoes | Settings page with editable fields | [ ] | |
| 4.10 | Admin → Prompts IA | 6 prompt cards, editable, save works | [ ] | |

---

## 5. Therapist Directory & Discovery

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 5.1 | Patient → "Encontrar Terapeuta" | Directory page loads with search + filters | [ ] | |
| 5.2 | Search by name | Results filter in real-time | [ ] | |
| 5.3 | Filter by specialty | Results filter | [ ] | |
| 5.4 | Click therapist card | Navigate to therapist profile | [ ] | |
| 5.5 | Therapist profile page | Bio, specialties, rating, availability tab | [ ] | |
| 5.6 | "Explorar Clinicas" | Clinic directory loads | [ ] | |
| 5.7 | Click clinic card | Navigate to clinic profile | [ ] | |
| 5.8 | Clinic profile | Description, therapist roster, reviews tab | [ ] | |

---

## 6. Booking Flow

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 6.1 | On therapist profile → "Agenda" tab | Shows booking flow component | [ ] | |
| 6.2 | Select a date | Available time slots shown | [ ] | |
| 6.3 | Select a time slot | Confirmation step with price | [ ] | |
| 6.4 | Confirm booking | Appointment created, toast success | [ ] | |
| 6.5 | Check patient calendar | New appointment visible | [ ] | |
| 6.6 | Check therapist calendar | New appointment visible | [ ] | |

---

## 7. Calendar Views

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 7.1 | Therapist → Agenda | Calendar loads (week view default) | [ ] | |
| 7.2 | Switch to month view | Month grid renders | [ ] | |
| 7.3 | Switch to list view | Agenda/list renders | [ ] | |
| 7.4 | Navigate dates (< >) | Calendar updates | [ ] | |
| 7.5 | Click appointment block | Detail dialog opens | [ ] | |
| 7.6 | Patient → Minha Agenda | Patient calendar loads | [ ] | |
| 7.7 | Therapist → Configurar Disponibilidade | Availability settings page | [ ] | |
| 7.8 | Add availability slot | Slot appears on calendar | [ ] | |
| 7.9 | Block date range | Blocked dates shown | [ ] | |

---

## 8. Session (Video Call) — requires LiveKit

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 8.1 | Navigate to meeting link (/session/:id) | Session page loads | [ ] | |
| 8.2 | Before access window | "Sessao abre em [time]" message | [ ] | |
| 8.3 | Within access window (therapist) | "Iniciar Sessao" button visible | [ ] | |
| 8.4 | Within access window (patient) | Waiting screen shown | [ ] | |
| 8.5 | Consent popup | Recording consent dialog appears | [ ] | |
| 8.6 | Accept consent → Start | Video placeholders appear, recording indicator | [ ] | |
| 8.7 | Session controls | Mute/camera/chat buttons work | [ ] | |
| 8.8 | Text chat | Side panel opens, can send messages | [ ] | |
| 8.9 | End session | Post-session popup appears | [ ] | |
| 8.10 | Post-session observation (therapist) | Textarea → submit/skip | [ ] | |
| 8.11 | Post-session notes (patient) | Textarea → submit/skip | [ ] | |
| 8.12 | Processing indicator | "Processando resumo..." spinner | [ ] | |
| 8.13 | After processing | Redirect to session detail | [ ] | |

---

## 9. Session Journal & AI Summaries — requires OpenAI

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 9.1 | Therapist → session detail | Track 2 clinical summary visible | [ ] | |
| 9.2 | Observation tab | Can add/edit/delete observations | [ ] | |
| 9.3 | Add observation | Clinical summary regenerates (toast) | [ ] | |
| 9.4 | Version history tab | Previous versions listed | [ ] | |
| 9.5 | "Visao do Paciente" tab | Shows Track 1 (read-only) | [ ] | |
| 9.6 | Patient → session detail | Track 1 base summary only | [ ] | |
| 9.7 | Patient → "Minhas Anotacoes" | Can add/edit personal notes | [ ] | |
| 9.8 | Patient does NOT see Track 2 | No clinical data visible | [ ] | |
| 9.9 | Patient → "Minha Jornada" | Longitudinal analysis (or placeholder if <4 sessions) | [ ] | |
| 9.10 | Therapist → patient profile → Longitudinal | Clinical longitudinal visible | [ ] | |

---

## 10. Financial System — requires Stripe

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 10.1 | Patient → Minha Carteira | Wallet page with balance (R$0,00) | [ ] | |
| 10.2 | "Adicionar Creditos" → top up | Payment dialog → Stripe flow | [ ] | |
| 10.3 | After top-up | Balance updated, movement recorded | [ ] | |
| 10.4 | "Sacar" → withdrawal | Amount input → fee preview → confirm | [ ] | |
| 10.5 | Withdrawal below minimum (R$10) | Error: below minimum | [ ] | |
| 10.6 | Movement history | Shows top-up and withdrawal entries | [ ] | |
| 10.7 | Therapist → Financeiro | Balance, revenue, statement visible | [ ] | |
| 10.8 | Clinic → Financeiro | Clinic revenue, per-therapist breakdown | [ ] | |
| 10.9 | Clinic → Transfer to therapist | Dialog → amount + reason → success | [ ] | |
| 10.10 | Admin → Financeiro | Global dashboard, all wallets, payouts | [ ] | |
| 10.11 | Patient → Metodos de Pagamento | Card list (empty initially) | [ ] | |

---

## 11. Messaging System

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 11.1 | Navigate to /[role]/mensagens | WhatsApp-like layout loads | [ ] | |
| 11.2 | "Nova conversa" button | User search dialog opens | [ ] | |
| 11.3 | Search for user | Results appear | [ ] | |
| 11.4 | Start conversation | Chat thread opens, first message sent | [ ] | |
| 11.5 | Send text message | Message appears in thread | [ ] | |
| 11.6 | Enter sends, Shift+Enter newline | Correct behavior | [ ] | |
| 11.7 | Conversation list updates | New message shown in preview | [ ] | |
| 11.8 | Unread badge | Badge count visible on nav item | [ ] | |
| 11.9 | Archive conversation | Disappears from list | [ ] | |
| 11.10 | Mute conversation | Mute icon appears | [ ] | |
| 11.11 | Delete own message | Message removed (hard delete) | [ ] | |
| 11.12 | Block user | Conversation hidden | [ ] | |
| 11.13 | Support conversation | Always pinned at top | [ ] | |
| 11.14 | Mobile responsive | Full-screen chat on small screen | [ ] | |

---

## 12. Reviews

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 12.1 | Patient → therapist profile → reviews tab | Reviews listed (or empty) | [ ] | |
| 12.2 | Leave a review (after completed session) | Star rating + text + tags → submit | [ ] | |
| 12.3 | Edit own review | Updated review visible | [ ] | |
| 12.4 | Therapist → Avaliacoes | All received reviews listed | [ ] | |
| 12.5 | Therapist responds to review | Response visible below review | [ ] | |
| 12.6 | Flag a review | Flag icon → reason → submitted | [ ] | |
| 12.7 | Admin → Avaliacoes | Flagged reviews shown | [ ] | |
| 12.8 | Clinic reviews | Separate from therapist reviews | [ ] | |

---

## 13. Recurring Schedules

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 13.1 | Therapist → Recorrentes | Schedule list page | [ ] | |
| 13.2 | Create recurring schedule | Form with frequency, day, time → submit | [ ] | |
| 13.3 | Patient → Recorrentes | Own schedules listed | [ ] | |
| 13.4 | Patient skips occurrence | Skip confirmed, slot freed | [ ] | |
| 13.5 | Patient ends schedule | All future cancelled, toast | [ ] | |
| 13.6 | Patient requests change | Dialog → reason → sent to therapist | [ ] | |
| 13.7 | Therapist approves change | Schedule updated | [ ] | |
| 13.8 | Pause/resume schedule | Status toggles correctly | [ ] | |

---

## 14. Settings Pages

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 14.1 | Therapist → Configuracoes | Profile, bank, integrations, price sections | [ ] | |
| 14.2 | Edit therapist bio | Saved, toast success | [ ] | |
| 14.3 | Edit bank details | Saved | [ ] | |
| 14.4 | Patient → Configuracoes | Personal data, calendar, payments, notifications | [ ] | |
| 14.5 | Clinic → Configuracoes | Profile, bank, commissions, branding | [ ] | |
| 14.6 | Clinic branding | Color pickers, logo upload | [ ] | |
| 14.7 | Admin → Configuracoes | All platform settings editable | [ ] | |
| 14.8 | Change global commission rate | Saved with version history | [ ] | |

---

## 15. LGPD Data Deletion

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 15.1 | Patient → request data deletion | Confirmation dialog ("CONFIRMAR EXCLUSAO") | [ ] | |
| 15.2 | Wrong confirmation text | Rejected | [ ] | |
| 15.3 | Correct confirmation | Data deleted, logged out | [ ] | |
| 15.4 | Therapist → delete specific session | Session data removed | [ ] | |

---

## 16. Cross-Cutting

| # | Test | Expected | Status | Issues |
|---|---|---|---|---|
| 16.1 | Mobile responsive (320px) | All pages usable | [ ] | |
| 16.2 | Dark mode toggle (if implemented) | Themes switch | [ ] | |
| 16.3 | Notification bell | Shows unread count, popover with notifications | [ ] | |
| 16.4 | Session timeout / 401 | Redirected to login | [ ] | |
| 16.5 | Empty states | Friendly messages with CTAs on empty pages | [ ] | |
| 16.6 | Loading states | Skeleton loaders while fetching | [ ] | |
| 16.7 | Error boundaries | Errors caught, friendly message shown | [ ] | |
| 16.8 | Breadcrumb / back navigation | Works on detail pages | [ ] | |

---

## Issue Log

| # | Page/Feature | Issue Description | Severity | Fixed? |
|---|---|---|---|---|
| | | | | |
| | | | | |
| | | | | |
