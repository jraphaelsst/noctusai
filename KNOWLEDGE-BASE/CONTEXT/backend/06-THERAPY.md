# 06 — Therapy Platform Backend

> **39 routers · 38 services · 18 schema modules · 1,021 tests (62 files)**
> Port: 8003 · Schema: `therapy` · Auth: Direct Supabase Auth (NOT NoctusAI SSO)

---

## App Setup

- **Framework**: FastAPI with `configure_app()` from noctusai_shared
- **Database**: Supabase PostgreSQL, schema `therapy` via `ClientOptions(schema="therapy")`
- **Auth model**: Direct Supabase Auth (email/password + Google OAuth). Users log in directly — no NoctusAI SSO. Only the platform admin connects to NoctusAI core.
- **Role model**: 4 roles stored in `user_metadata` during registration: `platform_admin`, `clinic_admin`, `therapist`, `patient`
- **Multi-tenancy**: Via `clinic_id` (not `org_id`). Independent therapists have `clinic_id = NULL`.
- **Health check**: `GET /health` → `{"status": "ok", "version": "0.1.0", "product": "therapy-platform"}`

---

## Dependencies & Auth Helpers

| Function | Purpose |
|----------|---------|
| `get_current_user(authorization)` | Extracts and validates JWT, returns `(user, token)` |
| `get_user_role(user)` | Returns role from metadata: `platform_admin / clinic_admin / therapist / patient` |
| `require_role(*allowed_roles)` | Dependency factory — validates role, returns `(user, token, role)` or 403 |
| `get_clinic_id_for_user(user)` | Resolves `clinic_id` from metadata; `None` for independents |
| `get_user_client(token)` | Supabase client as user (respects RLS) |
| `get_admin_client()` | Supabase client with service role (bypasses RLS) |
| `log_action()` | Server-side audit logging (always service role) |

---

## Routers (39)

### Authentication & Admin
| Router | Prefix | Purpose |
|--------|--------|---------|
| auth | `/api/auth` | Registration, login, password recovery |
| admin | `/api/admin` | Platform administration and user management |
| admin_financials | `/api/admin/financials` | Platform-level financial reporting |
| lgpd | `/api/lgpd` | Data deletion per Brazilian data protection law |
| settings | `/api/settings` | User and clinic settings |
| support | `/api/support` | Customer support tickets |

### Clinic & Profiles
| Router | Prefix | Purpose |
|--------|--------|---------|
| clinics | `/api/clinics` | Clinic profiles and settings |
| therapists | `/api/therapists` | Therapist profiles and directory |
| patients | `/api/patients` | Patient profiles and listing |
| therapy_matching | `/api/matching` | Therapist-patient matching algorithm |
| reviews | `/api/reviews` | Therapist and clinic reviews |

### Scheduling & Sessions
| Router | Prefix | Purpose |
|--------|--------|---------|
| appointments | `/api/appointments` | Schedule, cancel, list therapy appointments |
| availability | `/api/availability` | Therapist availability slot management |
| recurring | `/api/recurring` | Recurring appointment management |
| sessions | `/api/sessions` | Video therapy session lifecycle (LiveKit) |
| rooms | `/api/salas` | Physical room and booking management |

### Clinical Features
| Router | Prefix | Purpose |
|--------|--------|---------|
| anamnese | `/api/anamnese` | Patient intake forms and history |
| treatment_plans | `/api/planos-tratamento` | Treatment planning and goals |
| evolution_notes | `/api/evolucao` | Clinical evolution note CRUD |
| observations | `/api/observations` | Session observations and notes |
| patient_notes | `/api/patient-notes` | Patient note management |
| crisis | `/api/alertas-crise` | Crisis detection and risk assessment alerts |
| longitudinal | `/api/longitudinal` | AI-generated cross-session analysis |

### Patient Self-Service
| Router | Prefix | Purpose |
|--------|--------|---------|
| mood | `/api/humor` | Patient mood/emotion tracking |
| homework | `/api/tarefas` | Assignment, submission, and review workflow |
| session_journal | `/api/journal` | Patient session journal entries |
| therapeutic_journal | `/api/diario` | Therapeutic journaling |

### Financial
| Router | Prefix | Purpose |
|--------|--------|---------|
| wallets | `/api/wallets` | Wallet balance and movements |
| transactions | `/api/transactions` | Financial transaction history |
| payments | `/api/payments` | Payment processing and status (Stripe) |
| invoices | `/api/recibos` | Invoice generation and management |
| refunds | `/api/refunds` | Refund request and processing |
| clinic_financials | `/api/clinic/financials` | Clinic-level financial reporting |

### Communication
| Router | Prefix | Purpose |
|--------|--------|---------|
| messaging | `/api/conversations` | Conversations, messages, blocks, reports |
| notificacoes | `/api/notificacoes` | Push and email notifications |
| whatsapp_therapy | `/api/whatsapp` | WhatsApp appointment reminders (WAHA) |
| attachments | `/api/attachments` | File upload and attachment management |

### Analytics
| Router | Prefix | Purpose |
|--------|--------|---------|
| dashboard_bi | `/api/bi` | Business intelligence and analytics dashboard |

---

## Services (38)

### Core Services
| Service | Purpose |
|---------|---------|
| auth_service | Registration, login, password recovery |
| admin_service | Approvals, commission overrides, patient assignments |
| clinic_service | Profile, settings, therapist management, directory |
| therapist_service | Profile management, directory listing, stats |
| patient_service | Profile management, patient listing |

### Scheduling & Sessions
| Service | Purpose |
|---------|---------|
| appointment_service | Create, cancel, list, no-show detection, price resolution |
| availability_service | Manage therapist availability slots, blocking, bookable windows |
| recurring_service | Create, approve, pause, resume, end, modify, skip, generate schedules |
| session_service | Video session lifecycle management |
| livekit_service | Room management, token generation, recording control |
| room_service | Physical room management and booking for clinics |
| no_show_service | Background detection and charging |

### Clinical & AI
| Service | Purpose |
|---------|---------|
| clinical_records_service | Anamnese, treatment plans, goals, evolution notes |
| ai_pipeline | Orchestrator for transcription, summary, and longitudinal analysis |
| summary_service | AI-powered session summary generation via OpenAI GPT |
| transcription_service | Audio-to-text via OpenAI Whisper |
| longitudinal_service | AI-generated longitudinal analyses across sessions |
| crisis_service | Risk keyword detection, alert creation, severity assessment |
| therapy_embedding_service | OpenAI embeddings for therapist and patient profiles |
| matching_service | Therapist-patient matching with composite scoring |

### Patient Self-Service
| Service | Purpose |
|---------|---------|
| journal_service | Patient journaling CRUD |
| homework_service | Assignment, submission, and review workflow |
| mood_service | Patient mood/emotion tracking and analytics |

### Financial
| Service | Purpose |
|---------|---------|
| wallet_service | Balance management, top-ups, debits, credits, movements |
| stripe_service | Payment processing, refunds, payouts |
| commission_engine | Financial calculation core |
| invoice_service | Generate and manage invoices from transactions |
| payout_service | Withdrawal requests, processing, and listing |
| refund_service | Request, review, and process refunds |

### Communication
| Service | Purpose |
|---------|---------|
| messaging_service | Conversations, messages, blocks, reports, read receipts |
| email_service | Notification emails via Resend API |
| whatsapp_therapy_service | Appointment reminders and messaging via WAHA |
| attachment_service | File upload and AI processing for message attachments |

### Other
| Service | Purpose |
|---------|---------|
| bi_service | Business intelligence and analytics for therapists |
| branding_service | Clinic-level and platform-level branding |
| lgpd_service | Data deletion per Brazilian data protection law |

---

## Key Integrations

| Integration | Purpose | Config |
|-------------|---------|--------|
| **LiveKit** | Video therapy sessions | `THERAPY_LIVEKIT_URL`, `THERAPY_LIVEKIT_API_KEY`, `THERAPY_LIVEKIT_API_SECRET` |
| **Stripe Connect** | Marketplace payments (patients pay, therapists receive) | `THERAPY_STRIPE_CONNECT_CLIENT_ID`, `stripe_secret_key` |
| **OpenAI GPT** | Session summaries, longitudinal analysis, crisis detection | `openai_api_key` (shared) |
| **OpenAI Whisper** | Session transcription (audio-to-text) | `openai_api_key` (shared) |
| **Google OAuth** | Google login + Calendar sync | `THERAPY_GOOGLE_CLIENT_ID`, `THERAPY_GOOGLE_CLIENT_SECRET` |
| **Resend** | Email notifications | `resend_api_key` (shared) |
| **WAHA** | WhatsApp appointment reminders | Shared WAHA instance |

---

## Database

All tables in `therapy` PostgreSQL schema. See `KNOWLEDGE-BASE/CONTEXT/backend/04-DATABASE.md` for full table listing.

### Migration Files (`products/therapy-platform/backend/migrations/`)

| File | Purpose |
|------|---------|
| `001_therapy_platform.sql` | Base schema: 39 tables (identity, scheduling, financials, messaging, notifications), 4-role RLS policies, helper functions, indexes, seed data, product seed |
| `002_clinical_features.sql` | Clinical features: anamnese, treatment plans, evolution notes, room management, pgvector extension for embeddings |
