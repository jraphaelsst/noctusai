# Therapy Platform -- Master Prompt

## Purpose

Online therapy platform connecting patients with therapists. Supports individual practitioners and multi-therapist clinics. Features video sessions (LiveKit), clinical AI (transcription, summaries, crisis detection via OpenAI), Stripe marketplace payments, scheduling, clinical records, patient self-service tools, and LGPD compliance.

## Architecture

- Schema: `therapy`
- Backend port: 8003 | Frontend port: 8095
- Tenant key: `clinic_id` (NOT `org_id` -- unique among products)
- Auth: Direct Supabase Auth (NOT NoctusAI SSO for end users; only platform admin connects to Core)
- Backend path: `products/therapy-platform/backend/app/`
- Frontend path: `products/therapy-platform/frontend/src/`

## Auth Model

Users log in directly -- no SSO flow for patients/therapists/clinic admins. 4 roles stored in `user_metadata`:

| Role | Scope |
|------|-------|
| `platform_admin` | Full platform access |
| `clinic_admin` | Manages one clinic |
| `therapist` | Own patients, sessions, schedule |
| `patient` | Own records, bookings, self-service tools |

Independent therapists have `clinic_id = NULL`.

### Auth Helpers

| Function | Purpose |
|----------|---------|
| `get_user_role(user)` | Returns role from metadata |
| `require_role(*allowed_roles)` | Dependency factory -- validates role, returns `(user, token, role)` or 403 |
| `get_clinic_id_for_user(user)` | Resolves `clinic_id` from metadata; `None` for independents |
| `log_action()` | Server-side audit logging (always service role) |

## Key Domains

### Auth and Admin
- **auth** -- registration, login, password flows
- **admin** -- platform admin operations
- **admin_financials** -- platform-level financial overview
- **lgpd** -- LGPD (Brazilian data protection) compliance: data export, deletion requests
- **settings** -- clinic and platform settings
- **support** -- support ticket system

### Profiles
- **clinics** -- clinic registration, profile, branding
- **therapists** -- therapist profiles, specializations, credentials
- **patients** -- patient profiles, intake data
- **therapy_matching** -- algorithm matching patients to therapists by specialty/availability/preference
- **reviews** -- patient reviews of therapists

### Scheduling
- **appointments** -- booking lifecycle (request, confirm, cancel, reschedule)
- **availability** -- therapist schedule configuration (weekly slots, exceptions)
- **recurring** -- recurring session patterns
- **sessions** -- session execution with LiveKit video integration
- **rooms** -- virtual room management for video sessions

### Clinical
- **anamnese** -- intake assessments
- **treatment_plans** -- structured treatment planning
- **evolution_notes** -- per-session clinical notes
- **observations** -- clinical observations
- **patient_notes** -- therapist private notes on patients
- **crisis** -- crisis detection and escalation protocols
- **longitudinal** -- long-term patient progress analysis (AI-powered, min 4 sessions)

### Patient Self-Service
- **mood** -- daily mood tracking
- **homework** -- therapeutic homework assignments
- **session_journal** -- patient session reflections
- **therapeutic_journal** -- ongoing therapeutic journaling

### Financial
- **wallets** (carteiras) -- therapist/clinic wallet balances
- **transactions** -- financial transaction history
- **payments** -- Stripe Connect marketplace payments (platform takes fee)
- **invoices** -- invoice generation
- **refunds** -- refund processing
- **clinic_financials** -- clinic-level financial reporting

### Communication
- **messaging** -- in-app messaging between therapist and patient
- **notificacoes** -- notification delivery (proxies to Core)
- **whatsapp_therapy** -- WhatsApp integration for appointment reminders
- **attachments** -- file attachments for messages and clinical records

### Analytics
- **dashboard_bi** -- clinic and therapist analytics dashboards

## AI Pipeline

Orchestrated by `ai_pipeline` service:

1. **Transcription** (OpenAI Whisper) -- session audio to text
2. **Summary** (GPT) -- session summary generation
3. **Longitudinal analysis** (GPT) -- cross-session progress tracking (requires min 4 sessions)
4. **Crisis detection** -- keyword analysis on session content for escalation

Prompt hierarchy: per-therapist > per-clinic > global default.

## Services (37)

admin, ai_pipeline, appointment, attachment, auth, availability, bi, branding, clinic, clinical_records, commission_engine, crisis, email, homework, invoice, journal, lgpd, livekit, longitudinal, matching, messaging, mood, no_show, patient, payout, recurring, refund, review, room, session, stripe, summary, therapist, therapy_embedding, transcription, wallet, whatsapp_therapy

## Frontend Structure

Role-based page directories:
- `pages/admin/` -- platform admin views
- `pages/clinic/` -- clinic admin views
- `pages/therapist/` -- therapist views
- `pages/patient/` -- patient views
- Shared pages: Dashboard, Landing, Login, Register, Session, Messages, ClinicDirectory, TherapistDirectory, ClinicProfile, TherapistProfile, ForgotPassword, AcceptInvite, PrivacyPolicy, TermsOfUse

## Development Guidelines

- Follow shared patterns from noctusai_shared (auth, roles, invitations, responses, exceptions)
- Router -> Service -> Schema pattern; routers are thin, business logic in services
- RLS policies use `(SELECT auth.uid())` pattern on all tables
- Portuguese for business domain names, English for technical/framework code
- Use `clinic_id` for tenant isolation (NOT `org_id`). Independent therapists have `clinic_id = NULL`
- Use `require_role()` dependency for role-based access control on every endpoint
- Use `log_action()` for audit logging on sensitive operations
- N+1 zero tolerance: batch all reads and writes
- Clinical data requires extra care: LGPD compliance, encryption at rest, data deletion support
- Stripe Connect: platform is the "connected account" facilitator; therapists/clinics onboard as connected accounts
- LiveKit room tokens are short-lived and scoped to specific session + participant

## Testing

```bash
cd products/therapy-platform/backend && pytest
```

1,080 tests across router and service test files.

## Dependencies

- Shared backend: `noctusai_shared`
- Shared frontend: `@noctusai/shared` + `@noctusai/shared/design-system`
- LiveKit: video therapy sessions (`THERAPY_LIVEKIT_URL`, `_API_KEY`, `_API_SECRET`)
- Stripe Connect: marketplace payments (`THERAPY_STRIPE_CONNECT_CLIENT_ID`)
- OpenAI GPT: session summaries, longitudinal analysis, crisis detection
- OpenAI Whisper: session transcription
- Google OAuth: login + calendar sync (`THERAPY_GOOGLE_CLIENT_ID`, `_SECRET`)
- Supabase: Auth, database, storage, RLS
