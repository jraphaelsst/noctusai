# 04 — Therapy Platform Frontend

> Path: `products/therapy-platform/frontend/src/` · Port: 8095 · 50+ pages · 30 hooks · Auth: Direct Supabase Auth
> Standard frontend patterns: see `../PATTERNS/frontend/frontend.md`.
> Vite build: 596 KB main bundle (post-wiring close 2026-05-11).

## Architecture: Role-Based Routing

4 distinct layout wrappers with nested route groups:

| Role | Layout | Route Prefix | Pages |
|------|--------|-------------|-------|
| admin | AdminLayout | `/admin/*` | 15: Dashboard, Therapists, Clinics, Patients, Appointments, Financials, Refunds, Settings, AIPrompts, Support, Moderation, Reviews + TherapistDetail, ClinicDetail, PatientDetail |
| clinica | ClinicLayout | `/clinic/*` | 6: Dashboard, Therapists, Patients, Financials, Settings, LLMPreferences |
| terapeuta | TherapistLayout | `/therapist/*` | 15: Dashboard, Calendar, AvailabilitySettings, RecurringSchedules, Scheduling, Patients, PatientProfile, SessionDetail, Financials, Reviews, Settings, ClinicalRecords, HomeworkManager, BiDashboard, CrisisAlerts |
| paciente | PatientLayout | `/patient/*` | 14: Dashboard, Calendar, RecurringSchedules, SessionHistory, SessionDetail, Journey, Wallet, PaymentMethods, Reviews, Settings, MoodTracker, Diary, Homework, Invoices |

**Cross-role routes**: TherapistDirectory, ClinicDirectory, Messages, Session (full-screen video, no layout wrapper), TherapistProfile, ClinicProfile.
**Public**: Landing, Login, Register, ForgotPassword, AcceptInvite, PrivacyPolicy, TermsOfUse, NotFound.

Root logic: unauthenticated → public routes; authenticated → redirect to role-based dashboard.

## Components (49)

**UI Primitives**: 21 Radix-based components
**Layout**: Header, Sidebar, AdminLayout, ClinicLayout, TherapistLayout, PatientLayout, PublicLayout
**Calendar**: MonthView, WeekView, AgendaView, AppointmentCard, RecurringBadge, BookingFlow
**Session**: VideoPlaceholder, SessionControls, TextChat, ConsentPopup, PostSessionPopup, OvertimeAlerts
**Messaging**: ConversationList, ChatThread, MessageBubble, MessageInput, AttachmentPreview, NewConversation, ConversationActions

## Hooks (30) — Pattern-D consolidation closed

The wiring project closed Pattern-D (direct-fetch pages bypassing hooks) by replacing inline `useQuery({queryFn: api.get(...)})` calls with named hooks during Phases 6.a (therapist portal) + 8.a (clinic portal):

- **Scheduling**: useAppointments, useAvailability, useRecurring, useSessions, useScheduling
- **Financial**: useWallet, usePayments, useTransactions, useInvoices, useRefunds, useClinicFinancials, useAdminFinancials
- **Clinical**: useClinicalRecords, useMood, useDiary, useHomework, useJournal, useLongitudinal, useCrisis
- **Communication**: useConversations, useMessages, useConsents
- **Per-role lists** (new during wiring): **useTherapistPatients**, **useTherapistReviews**, **useClinicPatients**, **useClinicTherapists**, **usePatientReviews**
- **Other**: useAdmin, useSettings, useTherapyMatching, useBi

## Pattern A (backend route renames) — frontend already pre-aligned

Backend prefixes PT→EN closed in Phases 6.b/7.a/8.b. Frontend hooks already used the new EN paths (`useCrisis`, `useHomework`, `useMood`, `useDiary`, `useInvoices`). The single frontend bystander correction during the Pattern-A batch: `useClinicalRecords.ts` had been hitting `/api/clinical/anamnese|treatment-plans|evolution-notes` (silent 404 trio that pre-dated §7 Q9) — fixed to canonical EN prefixes inline.

## Known consumer-pending surfaces (filed as follow-ups)

| Surface | Status | Follow-up slug |
|---------|--------|----------------|
| `ClinicDirectory.tsx` + `TherapistDirectory.tsx` | Static placeholders (hardcoded empty states, non-functional search) | `therapy-public-directory-wiring` (+ `therapy-public-directory-auth-semantic` accept-with-rationale for JWT-vs-publicRoutes mismatch) |
| 7 `/api/auth/*` endpoints | Frontend bypasses via Supabase-direct + seed `LoginForm`/`ForgotPasswordPage`/`AcceptInvitePage` | `therapy-auth-router-orphan-cleanup` |
| Admin invitations management | Missing `pages/admin/Invitations.tsx` (admin list+cancel routes orphan) | `therapy-admin-invitations-management` |
| Clinic Settings.tsx | HIGH-PRIORITY silent-drop bug — bank/CNPJ/email/commission misroute to branding endpoint | `therapy-clinic-settings-misrouting` |
| Clinic rooms management | No `pages/clinic/Rooms.tsx` (5 orphan rooms routes) | `therapy-clinic-rooms-management-wiring` |
| Clinic therapist-config | Missing onClick on "Configurar" button (3 orphan routes) | `therapy-clinic-therapist-config-wiring` |
| `pages/clinic/Dashboard.tsx` | Fully-static placeholder; BI routes are therapist-only (`role != "therapist"` 403) | `therapy-clinic-dashboard-bi-wiring` |
| `useClinicTherapists` | Derives `clinic_id` client-side from `user.user_metadata.clinic_id` | `therapy-clinic-jwt-derived-clinic-id` (accept-with-rationale; N=1 today) |
| Patient LGPD portal | 3 unconsumed `lgpd.py` routes (data-subject-rights surface for Settings.tsx) | `therapy-lgpd-patient-portal-wiring` |
| Patient DTO enrichment | N=3 across admin/therapist/clinic — same shape needed | `therapy-patient-dto-enrichment-unified` |

## Supabase Client

Used **only for auth** (login/signup/session). All data goes through FastAPI backend via `createApiClient()` from `@noctusai/lib`. SSO callback for therapy is seed-provided (`SSOCallback` mounted at `/sso` by seed `app.tsx`) and calls **core** `POST /api/sso/session`. The product-owned `POST /api/auth/google` (in `auth.py`) is a separate in-product Google ID-token flow, currently orphan.
