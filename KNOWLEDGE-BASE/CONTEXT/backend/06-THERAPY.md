# 06 — Therapy Platform Backend

> Path: `products/therapy-platform/backend/app/` · Port: 8003 · 39 routers · 38 services · 1,021 tests
> Schema: `therapy` · Auth: Direct Supabase Auth (NOT NoctusAI SSO)

## Auth Model

Users log in directly to the therapy platform — no SSO. Only the platform admin connects to NoctusAI core. 4 roles stored in `user_metadata`: `platform_admin`, `clinic_admin`, `therapist`, `patient`. Multi-tenancy via `clinic_id` (not `org_id`). Independent therapists have `clinic_id = NULL`.

## Dependencies & Auth Helpers

| Function | Purpose |
|----------|---------|
| `get_user_role(user)` | Returns role from metadata |
| `require_role(*allowed_roles)` | Dependency factory — validates role, returns `(user, token, role)` or 403 |
| `get_clinic_id_for_user(user)` | Resolves `clinic_id` from metadata; `None` for independents |
| `log_action()` | Server-side audit logging (always service role) |

## Router Groups (39)

- **Auth & Admin**: auth, admin, admin_financials, lgpd, settings, support
- **Profiles**: clinics, therapists, patients, therapy_matching, reviews
- **Scheduling**: appointments, availability, recurring, sessions (LiveKit), rooms
- **Clinical**: anamnese, treatment_plans, evolution_notes, observations, patient_notes, crisis, longitudinal
- **Patient Self-Service**: mood, homework, session_journal, therapeutic_journal
- **Financial**: wallets, transactions, payments (Stripe Connect), invoices, refunds, clinic_financials
- **Communication**: messaging, notificacoes, whatsapp_therapy, attachments
- **Analytics**: dashboard_bi

## Key Integrations

| Integration | Purpose | Config |
|-------------|---------|--------|
| LiveKit | Video therapy sessions | `THERAPY_LIVEKIT_URL`, `_API_KEY`, `_API_SECRET` |
| Stripe Connect | Marketplace payments | `THERAPY_STRIPE_CONNECT_CLIENT_ID` |
| OpenAI GPT | Session summaries, longitudinal, crisis detection | Shared `openai_api_key` |
| OpenAI Whisper | Session transcription | Shared `openai_api_key` |
| Google OAuth | Login + Calendar sync | `THERAPY_GOOGLE_CLIENT_ID`, `_SECRET` |

## AI Pipeline

Orchestrated by `ai_pipeline` service: transcription (Whisper) → summary (GPT) → longitudinal analysis (GPT, min 4 sessions). Crisis detection runs keyword analysis on session content. Prompt hierarchy: per-therapist > per-clinic > global default.
