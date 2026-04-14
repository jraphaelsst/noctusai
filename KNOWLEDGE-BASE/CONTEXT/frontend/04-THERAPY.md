# 04 — Therapy Platform Frontend

> Path: `products/therapy-platform/frontend/src/` · Port: 8095 · Auth: Direct Supabase Auth
> Standard frontend patterns: see CLAUDE.md

## Architecture: Role-Based Routing

4 distinct layout wrappers with nested route groups:

| Role | Layout | Route Prefix | Pages |
|------|--------|-------------|-------|
| admin | AdminLayout | `/admin/*` | 15: Dashboard, Therapists, Clinics, Patients, Appointments, Financials, Refunds, Settings, AIPrompts, Support, Moderation, Reviews + detail pages |
| clinica | ClinicLayout | `/clinic/*` | 5: Dashboard, Therapists, Patients, Financials, Settings |
| terapeuta | TherapistLayout | `/therapist/*` | 14: Dashboard, Calendar, Availability, Recurring, Patients, PatientProfile, SessionDetail, Financials, Reviews, Settings, ClinicalRecords, Homework, BI, CrisisAlerts |
| paciente | PatientLayout | `/patient/*` | 14: Dashboard, Calendar, Recurring, SessionHistory, SessionDetail, Journey, Wallet, PaymentMethods, Reviews, Settings, MoodTracker, Diary, Homework, Invoices |

**Cross-role routes**: TherapistDirectory, ClinicDirectory, Messages, Session (full-screen video, no layout wrapper).
**Public**: Landing, Login, Register, ForgotPassword, TermsOfUse, PrivacyPolicy.

Root logic: unauthenticated → public routes; authenticated → redirect to role-based dashboard.

## Components (49)

**UI Primitives**: 21 Radix-based components
**Layout**: Header, Sidebar, AdminLayout, ClinicLayout, TherapistLayout, PatientLayout, PublicLayout
**Calendar**: MonthView, WeekView, AgendaView, AppointmentCard, RecurringBadge, BookingFlow
**Session**: VideoPlaceholder, SessionControls, TextChat, ConsentPopup, PostSessionPopup, OvertimeAlerts
**Messaging**: ConversationList, ChatThread, MessageBubble, MessageInput, AttachmentPreview, NewConversation, ConversationActions

## Hooks (24)

**Scheduling**: useAppointments, useAvailability, useRecurring, useSessions
**Financial**: useWallet, usePayments, useTransactions, useInvoices, useRefunds, useClinicFinancials
**Clinical**: useClinicalRecords, useMood, useDiary, useHomework, useJournal, useLongitudinal
**Communication**: useConversations, useMessages, useNotificacoes
**Other**: useCrisis, useAdmin, useSettings, useTherapyMatching, useBi

## Supabase Client

Used **only for auth** (login/signup/session). All data goes through FastAPI backend via `createApiClient()`.
