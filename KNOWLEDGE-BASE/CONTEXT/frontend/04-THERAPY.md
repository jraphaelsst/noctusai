# 04 — Therapy Platform Frontend

> **63 pages · 49 components · 24 hooks · 1 Zustand store · 5 type modules**
> Port: 8095 · Auth: Direct Supabase Auth · 4 role-based layouts

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Framework | React 18 + TypeScript |
| Build | Vite + SWC |
| Routing | React Router v6 |
| Server State | TanStack React Query v5 |
| Client State | Zustand v5 (auth only) |
| UI | Radix UI primitives + Tailwind CSS |
| Forms | React Hook Form + Zod |
| Charts | Recharts |
| Icons | Lucide React |
| Dates | date-fns |
| Toasts | sonner |

---

## Architecture

### Role-Based Routing

4 distinct layout wrappers with nested route groups:

| Role | Layout | Route Prefix | Dashboard |
|------|--------|-------------|-----------|
| `admin` | `AdminLayout` | `/admin/*` | Platform overview |
| `clinica` | `ClinicLayout` | `/clinic/*` | Clinic overview |
| `terapeuta` | `TherapistLayout` | `/therapist/*` | Therapist overview |
| `paciente` | `PatientLayout` | `/patient/*` | Patient overview |

Root logic: unauthenticated → public routes; authenticated → redirects to role-based dashboard.

### Cross-Role Routes
- `/therapists`, `/therapists/:id` — Therapist directory (public + authenticated)
- `/clinics`, `/clinics/:id` — Clinic directory (public + authenticated)
- `/session/:appointmentId` — Full-screen video session (no layout wrapper)
- `/messages` — Messaging (all authenticated roles)

---

## Pages (63)

### Public / Authentication (8)
Landing, Login, Register, ForgotPassword, TermsOfUse, PrivacyPolicy, NotFound, SSOCallback

### Role-Neutral (7)
Dashboard (redirector), Messages, TherapistDirectory, TherapistProfile, ClinicDirectory, ClinicProfile, Session (video)

### Admin Panel (15)
Dashboard, Therapists, TherapistDetail, Clinics, ClinicDetail, Patients, PatientDetail, Appointments, Financials, Refunds, Settings, AIPrompts, Support, Moderation, Reviews

### Clinic (5)
Dashboard, Therapists, Patients, Financials, Settings

### Therapist (14)
Dashboard, Calendar, AvailabilitySettings, RecurringSchedules, Patients, PatientProfile, SessionDetail, Financials, Reviews, Settings, ClinicalRecords, HomeworkManager, BiDashboard, CrisisAlerts

### Patient (14)
Dashboard, Calendar, RecurringSchedules, SessionHistory, SessionDetail, Journey, Wallet, PaymentMethods, Reviews, Settings, MoodTracker, Diary, Homework, Invoices

---

## Components (49)

### UI Primitives (21 — Radix-based)
alert-dialog, avatar, badge, button, card, collapsible, dialog, dropdown-menu, input, label, page-skeleton, popover, progress, scroll-area, select, separator, skeleton, switch, tabs, textarea, tooltip

### Layout (7)
Header, Sidebar, AdminLayout, ClinicLayout, TherapistLayout, PatientLayout, PublicLayout

### Calendar (6)
MonthView, WeekView, AgendaView, AppointmentCard, RecurringBadge, BookingFlow

### Session (6)
VideoPlaceholder, SessionControls, TextChat, ConsentPopup, PostSessionPopup, OvertimeAlerts

### Messaging (7)
ConversationList, ChatThread, MessageBubble, MessageInput, AttachmentPreview, NewConversation, ConversationActions

### Auth (1)
AuthProvider

### Other (1)
NotificationBell

---

## Hooks (24)

### Scheduling & Appointments
useAppointments, useAvailability, useRecurring, useSessions

### Financial & Payments
useWallet, usePayments, useTransactions, useInvoices, useRefunds, useClinicFinancials

### Clinical & Patient Data
useClinicalRecords, useMood, useDiary, useHomework, useJournal, useLongitudinal

### Messaging & Communication
useConversations, useMessages, useNotificacoes

### Crisis & Monitoring
useCrisis

### Admin, Settings & Analytics
useAdmin, useSettings, useTherapyMatching, useBi

---

## Stores

### `authStore.ts`
Single Zustand store created from shared `createAuthStore()` factory (`@noctusai/shared/stores`). Manages current user, auth status, and role information.

---

## Types (5 modules)

| Module | Content |
|--------|---------|
| `index.ts` | Core entities (Terapeuta, Clinica, Paciente, Sessao, Agendamento, Avaliacao, Pagamento), clinical types (Anamnese, TreatmentPlan, EvolutionNote), patient features (MoodEntry, JournalEntry, HomeworkAssignment), crisis, matching, BI |
| `scheduling.ts` | Appointment & scheduling data types |
| `session.ts` | Session state & video room types |
| `financial.ts` | Wallet, transaction, payment types |
| `messaging.ts` | Conversation, message, attachment types |

---

## API Client

Uses `createApiClient()` from `@noctusai/shared/api`:
- Backend URL: `VITE_BACKEND_API_URL` (defaults to `http://localhost:8003`)
- Auth: JWT from Supabase session
- Token refresh: Auto-refreshes expired tokens via `onTokenExpired`
- All data operations go through FastAPI backend, not direct Supabase queries

Supabase client is used **only for auth** (login/signup/session management).

---

## Patterns

Same patterns as ERP/PF frontends:
- **Toasts**: sonner (`toast.success()`, `toast.error()`)
- **Query hooks**: `enabled: !!user` guard, appropriate `staleTime`, correct `invalidateQueries`
- **Code splitting**: All pages lazy-loaded via `lazy()` + `Suspense` with `PageSkeleton`
- **Forms**: React Hook Form + Zod schemas
- **Dates**: date-fns for manipulation
