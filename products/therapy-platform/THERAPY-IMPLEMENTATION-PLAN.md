# Therapy Platform — Full Implementation Plan

> **This document is the single source of truth for the therapy platform implementation.**
> Every phase, step, and detail is listed here so nothing is lost across context windows.
> Mark items as [x] when completed.

---

## Phase 1 — Foundation (Scaffold)

### 1.1 Directory Structure
- [x] Create `products/therapy-platform/backend/app/`
- [x] Create `products/therapy-platform/backend/app/routers/`
- [x] Create `products/therapy-platform/backend/app/services/`
- [x] Create `products/therapy-platform/backend/app/schemas/`
- [x] Create `products/therapy-platform/backend/tests/`
- [x] Create `products/therapy-platform/backend/tests/routers/`
- [x] Create `products/therapy-platform/backend/tests/services/`
- [x] Create `products/therapy-platform/backend/migrations/`
- [x] Create `products/therapy-platform/frontend/src/`
- [x] Create `products/therapy-platform/frontend/src/pages/`
- [x] Create `products/therapy-platform/frontend/src/components/`
- [x] Create `products/therapy-platform/frontend/src/components/auth/`
- [x] Create `products/therapy-platform/frontend/src/components/layout/`
- [x] Create `products/therapy-platform/frontend/src/components/ui/`
- [x] Create `products/therapy-platform/frontend/src/hooks/`
- [x] Create `products/therapy-platform/frontend/src/store/`
- [x] Create `products/therapy-platform/frontend/src/lib/`
- [x] Create `products/therapy-platform/frontend/src/types/`
- [x] Create `products/therapy-platform/frontend/src/integrations/supabase/`
- [x] Create `products/therapy-platform/frontend/public/`

### 1.2 Backend Scaffold
- [x] `app/__init__.py` — empty
- [x] `app/config.py` — extends BaseAppSettings with THERAPY_* env vars (livekit, google, stripe connect), port 8095 CORS, jwt_secret validator
- [x] `app/database.py` — `get_supabase_client()` with schema="therapy", `get_core_client()` for public schema, `supabase_admin` singleton
- [x] `app/dependencies.py` — `get_current_user()`, `get_user_role()` (checks therapist_profiles/patient_profiles/clinics), `require_role()` factory, `get_clinic_id_for_user()`, `get_user_client()`, `get_admin_client()`, `log_action()`
- [x] `app/rate_limit.py` — `create_limiter(redis_url=settings.redis_url)`
- [x] `app/logging_config.py` — re-export from shared + suppress livekit/stripe loggers
- [x] `app/responses.py` — `from noctusai_shared.responses import *`
- [x] `app/exceptions.py` — `from noctusai_shared.exceptions import *`
- [x] `app/middleware.py` — `from noctusai_shared.middleware import *`
- [x] `app/main.py` — FastAPI app with title "NoctusAI Therapy Platform API", `configure_app()`, `/health` endpoint, no routers
- [x] `app/routers/__init__.py` — empty

### 1.3 Backend Tests
- [ ] `tests/__init__.py` — empty
- [ ] `tests/conftest.py` — MockSupabaseClient (no org_id), MockUser with role support, AuthClient fixture, role-specific test helpers

### 1.4 Backend Requirements
- [x] `requirements.txt` — product-specific deps: `-e shared/backend`, fastapi, uvicorn, supabase, pydantic, httpx, PyJWT, slowapi, livekit-api, stripe, google-api-python-client, google-auth-oauthlib, openai, resend, APScheduler, sentry-sdk, redis, pytest-asyncio

### 1.5 Database Migration
- [ ] `migrations/001_therapy_platform.sql` — complete schema with ALL tables:

#### Section 0: Schema + Permissions
- [x] `CREATE SCHEMA IF NOT EXISTS therapy` + GRANT USAGE + DEFAULT PRIVILEGES (same pattern as ERP/PF)

#### Section 1: Helper Functions
- [x] `therapy.get_user_role()` — returns role by checking profile tables
- [x] `therapy.get_user_clinic_id()` — returns clinic_id for auth.uid()

#### Section 2: Tables — Identity (3)
- [x] `therapy.clinics` — id, name, cnpj, responsible_person, contact_email, phone, logo_url, description, tagline, specialties_offered[], is_approved, approved_at, approved_by, created_at, updated_at, is_active
- [x] `therapy.therapist_profiles` — user_id PK (FK auth.users), clinic_id nullable, crp, bio, specialties[], approaches[], photo_url, default_session_price, session_duration_minutes(50), is_approved, approved_at, approved_by, created_at, updated_at, is_active
- [x] `therapy.patient_profiles` — user_id PK (FK auth.users), current_therapist_id nullable, origin(platform|platform_assigned|clinic|therapist), clinic_id nullable, assigned_by_admin_id nullable, assigned_at, phone, photo_url, created_at, updated_at, is_active

#### Section 2: Tables — Clinic Config (3)
- [x] `therapy.clinic_settings` — clinic_id PK, bank_name, bank_agency, bank_account, pix_key, notification_email_to, default_commission_pct_clinic_sourced, default_commission_pct_therapist_sourced
- [x] `therapy.clinic_therapist_config` — id, clinic_id, therapist_id, pricing_policy(clinic_controls|therapist_controls), commission_override_clinic_sourced nullable, commission_override_therapist_sourced nullable, clinic_set_default_price nullable, UNIQUE(clinic_id, therapist_id)
- [x] `therapy.clinic_branding` — clinic_id PK, primary_color, secondary_color, logo_url, favicon_url

#### Section 2: Tables — Commission + Pricing (2)
- [x] `therapy.platform_commission_overrides` — id, target_type(clinic|therapist), target_id, custom_commission_pct, set_by_admin_id, created_at, updated_at
- [x] `therapy.patient_pricing` — id, therapist_id, patient_id, clinic_id nullable, custom_price, set_by(therapist|clinic_admin|platform_admin), created_at, updated_at

#### Section 2: Tables — Therapist Config (1)
- [x] `therapy.therapist_settings` — therapist_id PK, bank_name, bank_agency, bank_account, pix_key, openai_api_key nullable, google_connected, google_refresh_token nullable, notification_email_to nullable

#### Section 2: Tables — Scheduling (3)
- [x] `therapy.availability_slots` — id, therapist_id, clinic_id nullable, day_of_week, start_time, end_time, is_recurring, specific_date nullable, is_blocked, created_at
- [x] `therapy.recurring_schedules` — id, therapist_id, patient_id, clinic_id nullable, frequency(weekly|biweekly|monthly|custom), custom_interval_weeks nullable, day_of_week, start_time, duration_minutes, start_date, end_condition(indefinite|after_n_occurrences|on_date), end_after_n nullable, end_on_date nullable, status(active|paused|ended), created_by_type, created_by_user_id, approved_by_user_id nullable, paused_at, resumed_at, ended_at, created_at, updated_at
- [x] `therapy.appointments` — id, therapist_id, patient_id, clinic_id nullable, recurring_schedule_id nullable, patient_origin(clinic_sourced|therapist_sourced|independent|platform_assigned), session_price_applied, platform_fee_pct_applied, clinic_commission_pct_applied nullable, scheduled_start, scheduled_end, status(waiting|in_progress|paused|completed|cancelled|late_cancelled|no_show|payment_pending|payment_failed), video_room_id nullable, meeting_link, google_event_id nullable, payment_id nullable, is_auto_generated, started_at, ended_at, patient_attended, therapist_attended, created_at, updated_at

#### Section 2: Tables — Video/Session (5)
- [x] `therapy.video_rooms` — id, appointment_id UNIQUE, livekit_room_name, room_token nullable, meeting_url, accessible_from, accessible_until, reopen_until nullable, reopen_count, reopen_button_visible_until nullable, status(pending|waiting|active|paused|closed|auto_finalized|reopened), total_pauses, therapist_joined_at, patient_joined_at, session_started_at, session_ended_at, last_paused_at, last_resumed_at, last_reopened_at, auto_finalized_at
- [x] `therapy.session_audio_segments` — id, video_room_id, segment_number, segment_type(initial|resumed|reopened), audio_file_url, started_at, ended_at nullable, transcription_text nullable, is_transcribed, download_expires_at nullable, created_at
- [x] `therapy.session_interruptions` — id, video_room_id, event_type(pause|resume|disconnect|reconnect|reopen|end), participant_type(therapist|patient|system), participant_user_id nullable, reason nullable, timestamp, interruption_duration_seconds nullable
- [x] `therapy.session_records` — id, appointment_id UNIQUE, combined_transcript_text, therapist_notes_private nullable, total_segments, ai_generated_at nullable, audio_deleted_at nullable, created_at
- [x] `therapy.session_observations` — id, session_record_id, observation_text, is_initial, created_at, updated_at, deleted_at nullable

#### Section 2: Tables — Clinical/AI (5)
- [x] `therapy.session_summary_versions` — id, session_record_id, track(base|clinical), version_number, summary, key_points[], tags[], source(ai_generated|ai_auto_fallback|manual_edit), observation_snapshot_ids[] nullable, created_at
- [x] `therapy.patient_session_notes` — id, session_record_id, patient_id, note_text, created_at, updated_at
- [x] `therapy.clinical_longitudinal_analyses` — id, patient_id, therapist_id, clinic_id nullable, version_number, narrative_summary, recurring_themes[], progress_timeline[], unresolved_topics[], observation_insights nullable, session_count_at_generation, clinical_summary_version_ids[] nullable, created_at
- [x] `therapy.patient_longitudinal_analyses` — id, patient_id, therapist_id, version_number, narrative_summary, recurring_themes[], progress_reflection[], ongoing_topics[], session_count_at_generation, base_summary_version_ids[] nullable, patient_note_ids[] nullable, created_at
- [x] `therapy.patient_longitudinal_notes` — id, patient_id, therapist_id, longitudinal_analysis_id nullable, note_text, created_at, updated_at

#### Section 2: Tables — Financial (6)
- [x] `therapy.wallets` — id, owner_id, owner_type(patient|therapist|clinic), balance, last_updated
- [x] `therapy.wallet_movements` — id, wallet_id, type(credit|debit), amount, reference_type(session_commission|voluntary_transfer|withdrawal|refund|top_up|no_show_fee), reference_id nullable, description nullable, created_at
- [x] `therapy.transactions` — id, appointment_id, patient_id, therapist_id, clinic_id nullable, patient_origin, gross_amount, platform_fee_pct, platform_fee_amount, clinic_commission_pct nullable, clinic_share_amount nullable, therapist_share_amount, status(pre_authorized|captured|refunded|failed|released), gateway_ref nullable, pre_authorized_at, captured_at nullable, refunded_at nullable, created_at
- [x] `therapy.clinic_transfers` — id, clinic_id, therapist_id, amount, reason, initiated_by_user_id, created_at
- [x] `therapy.payouts` — id, recipient_id, recipient_type(patient|therapist|clinic), amount, fee_pct, fee_amount, net_amount, status(pending|processing|completed|failed), bank_details_snapshot JSONB, requested_at, processed_at nullable
- [x] `therapy.refund_requests` — id, transaction_id, appointment_id, patient_id, therapist_id, clinic_id nullable, reason, status(pending|approved|denied), reviewed_by_admin_id nullable, review_response nullable, refund_amount, resolved_at nullable, created_at, updated_at

#### Section 2: Tables — Reviews (3)
- [x] `therapy.reviews` — id, patient_id, therapist_id, clinic_id nullable, star_rating(1-5), review_text nullable, tags[] nullable, is_flagged, flagged_by_therapist_id nullable, flagged_reason nullable, is_hidden, hidden_by_admin_id nullable, created_at, updated_at, UNIQUE(patient_id, therapist_id)
- [x] `therapy.clinic_reviews` — id, patient_id, clinic_id, star_rating(1-5), review_text nullable, tags[] nullable, is_flagged, flagged_by_clinic_admin_id nullable, flagged_reason nullable, is_hidden, hidden_by_admin_id nullable, created_at, updated_at, UNIQUE(patient_id, clinic_id)
- [x] `therapy.review_responses` — id, review_id nullable, clinic_review_id nullable, responder_id, response_text, created_at, updated_at

#### Section 2: Tables — Messaging (5)
- [x] `therapy.conversations` — id, mode(human|ai_managed|hybrid) DEFAULT 'human', created_at, updated_at, last_message_at nullable, is_archived
- [x] `therapy.conversation_participants` — id, conversation_id, participant_type(user|clinic|platform_support), participant_id nullable, clinic_id nullable, last_read_message_id nullable, is_muted, is_deleted, is_blocked, created_at, UNIQUE(conversation_id, participant_id, participant_type)
- [x] `therapy.messages` — id, conversation_id, sender_type(user|clinic_entity|platform_support|ai_agent), sender_user_id nullable, sender_clinic_id nullable, message_type(text|system|ai|image|audio) DEFAULT 'text', content, file_url nullable, file_type nullable, file_size nullable, ai_processed_content nullable, created_at, updated_at, deleted_at nullable
- [x] `therapy.message_reports` — id, conversation_id, message_id nullable, reported_by_user_id, reason, status(pending|reviewed|resolved), reviewed_by_admin_id nullable, resolution nullable, created_at, resolved_at nullable
- [x] `therapy.user_blocks` — id, blocker_user_id, blocked_user_id, created_at, UNIQUE(blocker_user_id, blocked_user_id)

#### Section 2: Tables — Config (2)
- [x] `therapy.platform_settings` — key TEXT PK, value TEXT, updated_at
- [x] `therapy.platform_settings_history` — id, setting_key, old_value nullable, new_value, changed_by_admin_id, changed_at

#### Section 3: Indexes
- [x] All FK columns indexed
- [x] `appointments(therapist_id, scheduled_start)`, `appointments(patient_id)`, `appointments(status)`
- [x] `messages(conversation_id, created_at)`, `messages(deleted_at)` partial
- [x] `session_summary_versions(session_record_id, track)`
- [x] `reviews(therapist_id)`, `clinic_reviews(clinic_id)`
- [x] `wallet_movements(wallet_id, created_at)`
- [x] `recurring_schedules(therapist_id, status)`

#### Section 4: RLS Policies
- [x] Enable RLS on ALL tables
- [x] `therapist_profiles` — own (user_id=auth.uid()) + clinic admin reads affiliated + admin reads all
- [x] `patient_profiles` — own (user_id=auth.uid()) + therapist reads own patients + clinic admin reads clinic patients
- [x] `appointments` — therapist/patient read own + clinic admin reads clinic + admin reads all
- [x] `patient_session_notes` — STRICTLY patient only (patient_id=auth.uid())
- [x] `session_observations` — therapist + clinic admin + admin only (NEVER patient)
- [x] `clinical_longitudinal_analyses` — therapist + clinic admin + admin only
- [x] `patient_longitudinal_analyses` — STRICTLY patient only (patient_id=auth.uid())
- [x] `wallets` — owner reads own + admin reads all
- [x] `conversations/messages` — participant-based visibility rules
- [x] Service role bypass on ALL tables

#### Section 5: Seed Data
- [x] `platform_settings` defaults: global_commission_rate=10.00, app_name, session timings, refund_enabled=false, cancellation_cutoff_hours=24, AI prompt defaults, withdrawal_min_amount=10.00, withdrawal_fee_pct=2.00, audio_retention_hours=24, longitudinal_min_sessions=4, message_notification_delay_minutes=5
- [x] Seed product into `public.products` table

#### Section 6: Final Grants
- [x] GRANT ALL/SELECT/INSERT/UPDATE/DELETE on all therapy tables to appropriate roles

### 1.6 Frontend Scaffold
- [x] `package.json` — name "noctusai-therapy-platform", same deps as PF (radix, tanstack, zustand, sonner, react-router-dom, shadcn, tailwindcss)
- [x] `vite.config.ts` — port 8095, `@/` alias, `@noctusai/shared` alias
- [x] `tsconfig.json` — base config with `@/*` and `@noctusai/shared/*` paths
- [x] `tsconfig.app.json` — app-specific TS config
- [x] `tsconfig.node.json` — build tool TS config
- [x] `tailwind.config.ts` — therapy theme, purple/violet primary (hsl 262 80% 50%)
- [x] `postcss.config.js` — tailwindcss + autoprefixer
- [x] `index.html` — therapy platform title, lang="pt-BR", dark mode script
- [x] `.env` — VITE_SUPABASE_URL, VITE_SUPABASE_PUBLISHABLE_KEY, VITE_BACKEND_API_URL=http://localhost:8003
- [x] `src/main.tsx` — createRoot, render App
- [x] `src/index.css` — Tailwind directives + shadcn CSS variables with therapy palette
- [x] `src/App.tsx` — QueryClientProvider + BrowserRouter + AuthProvider + Sonner. Routes: /login, /register, / (Dashboard)
- [x] `src/integrations/supabase/client.ts` — createClient with db.schema="therapy"
- [x] `src/lib/api-client.ts` — createApiClient pointing to port 8003
- [x] `src/lib/utils.ts` — re-export cn from shared
- [x] `src/store/authStore.ts` — createAuthStore from shared
- [x] `src/components/auth/AuthProvider.tsx` — useSupabaseAuthInit from shared
- [x] `src/pages/Login.tsx` — placeholder
- [x] `src/pages/Register.tsx` — placeholder
- [x] `src/pages/Dashboard.tsx` — placeholder
- [x] `src/types/index.ts` — empty

### 1.7 Infrastructure Updates
- [ ] `start.sh` — add THERAPY_BACKEND (port 8003) + THERAPY_FRONTEND (port 8095), add 8003/8095 to PORTS array, update echo block
- [ ] Root `requirements.txt` — add `# Therapy-only` section: livekit-api, google-api-python-client, google-auth-oauthlib, openai (if not already present)
- [ ] `CLAUDE.md` — add therapy product to Architecture section, add port 8003/8095

### 1.8 Verification
- [x] Backend starts: `uvicorn app.main:app --port 8003` → health endpoint responds
- [x] Frontend builds: `npm install && npm run build` → no errors
- [x] TypeScript: `npx tsc --noEmit` → no errors
- [x] Migration SQL: syntactically valid (manual execution in Supabase SQL Editor)

---

## Phase 2 — Profiles, Clinics & Discovery

### 2.1 Backend — Auth & Profiles
- [x] `routers/auth.py` — direct registration (email+password, Google OAuth), login, password recovery, role assignment at registration. Endpoints: POST /api/auth/register, POST /api/auth/login, POST /api/auth/google, POST /api/auth/forgot-password
- [x] `routers/therapists.py` — therapist profile CRUD + directory listing. Endpoints: GET /api/therapists (directory, filters: specialty, approach, price, availability, rating, clinic affiliation, sort), GET /api/therapists/:id (profile), POST /api/therapists (register), PATCH /api/therapists/:id, DELETE /api/therapists/:id
- [x] `routers/patients.py` — patient profile CRUD. Endpoints: GET /api/patients (admin/therapist), GET /api/patients/:id, POST /api/patients (register), PATCH /api/patients/:id
- [x] `routers/clinics.py` — clinic CRUD + directory. Endpoints: GET /api/clinics (directory, filters), GET /api/clinics/:id (profile + therapist roster), POST /api/clinics (register), PATCH /api/clinics/:id, POST /api/clinics/:id/invite-therapist
- [x] `routers/admin.py` — platform admin: approve/reject therapists+clinics, user management. Endpoints: POST /api/admin/approve/:type/:id, POST /api/admin/reject/:type/:id, GET /api/admin/pending-approvals
- [x] `services/auth_service.py` — registration logic, profile creation, role assignment
- [x] `services/therapist_service.py` — profile management, directory queries with filters+sort
- [x] `services/patient_service.py` — profile management
- [x] `services/clinic_service.py` — clinic management, therapist invitation, commission config
- [x] `schemas/auth.py` — registration/login request models
- [x] `schemas/therapist.py` — profile models
- [x] `schemas/patient.py` — profile models
- [x] `schemas/clinic.py` — clinic models

### 2.2 Backend — Reviews
- [x] `routers/reviews.py` — therapist reviews + clinic reviews. Endpoints: POST /api/reviews (therapist review), PATCH /api/reviews/:id, GET /api/reviews/therapist/:id, POST /api/clinic-reviews, GET /api/clinic-reviews/:id, POST /api/reviews/:id/flag, POST /api/reviews/:id/respond
- [x] `services/review_service.py` — review logic, rating aggregation, flag management

### 2.3 Backend — Clinic Config
- [x] `routers/clinic_settings.py` — commission config, pricing policy, branding. Endpoints: GET/PATCH /api/clinic/settings, GET/PATCH /api/clinic/commissions, GET/PATCH /api/clinic/therapists/:id/config
- [x] `services/commission_service.py` — commission calculation engine (platform % → clinic % → therapist share)

### 2.4 Frontend — Auth Pages
- [x] `pages/Login.tsx` — email+password login form, Google OAuth button, redirect to register
- [x] `pages/Register.tsx` — role selection (patient/therapist/clinic), multi-step form per role
- [x] `pages/ForgotPassword.tsx` — password recovery form
- [x] `components/auth/GoogleAuthButton.tsx` — Google OAuth component
- [x] `components/auth/RoleGuard.tsx` — route protection by role
- [x] Role-based routing in App.tsx: `/admin/*`, `/clinic/*`, `/therapist/*`, `/patient/*`

### 2.5 Frontend — Directory & Profiles
- [x] `pages/TherapistDirectory.tsx` — card listing with filters, sort, pagination
- [x] `pages/TherapistProfile.tsx` — full profile with availability calendar, reviews, book button
- [x] `pages/ClinicDirectory.tsx` — clinic cards with dual ratings, filters
- [x] `pages/ClinicProfile.tsx` — clinic info + therapist roster + clinic reviews
- [x] `components/therapists/TherapistCard.tsx` — listing card
- [x] `components/clinics/ClinicCard.tsx` — listing card
- [x] `components/reviews/ReviewsList.tsx` — paginated reviews with star display
- [x] `components/reviews/ReviewForm.tsx` — star rating + text + tags
- [x] `components/reviews/ReviewResponse.tsx` — therapist/clinic reply
- [x] `hooks/useTherapists.ts` — directory queries
- [x] `hooks/useClinics.ts` — directory queries
- [x] `hooks/useReviews.ts` — review CRUD

### 2.6 Frontend — Layout Shells
- [x] `components/layout/AdminLayout.tsx` — platform admin sidebar + nav
- [x] `components/layout/ClinicLayout.tsx` — clinic admin sidebar + nav
- [x] `components/layout/TherapistLayout.tsx` — therapist sidebar + nav
- [x] `components/layout/PatientLayout.tsx` — patient sidebar + nav (with NotificationBell)
- [x] `pages/admin/Dashboard.tsx` — admin metrics
- [x] `pages/clinic/Dashboard.tsx` — clinic metrics
- [x] `pages/therapist/Dashboard.tsx` — therapist metrics
- [x] `pages/patient/Dashboard.tsx` — patient welcome + upcoming session

### 2.7 Notifications Integration
- [x] `hooks/useNotificacoes.ts` — createNotificationHooks from shared
- [x] `components/NotificationBell.tsx` — notification bell in all layouts
- [x] `routers/notificacoes.py` — same pattern as ERP/PF (proxy to public.notifications)

### 2.8 Tests — Phase 2
- [x] Router tests: auth, therapists, patients, clinics, admin, reviews, clinic_settings
- [x] Service tests: auth_service, therapist_service, patient_service, clinic_service, commission_service, review_service

---

## Phase 3 — Calendar & Scheduling

### 3.1 Backend — Calendar
- [x] `routers/availability.py` — therapist availability CRUD. Endpoints: GET/POST/PATCH/DELETE /api/availability/slots, POST /api/availability/block-dates
- [x] `routers/appointments.py` — booking flow. Endpoints: POST /api/appointments (book), PATCH /api/appointments/:id (cancel/reschedule), GET /api/appointments (list with filters), GET /api/appointments/:id
- [x] `routers/recurring.py` — recurring schedule CRUD. Endpoints: POST /api/recurring (create), PATCH /api/recurring/:id (modify/pause/resume/end), POST /api/recurring/:id/approve, POST /api/recurring/:id/skip/:occurrence, GET /api/recurring (list)
- [x] `services/availability_service.py` — slot management, conflict detection
- [x] `services/appointment_service.py` — booking logic, cancellation (24h policy), no-show detection (50% charge), meeting link generation
- [x] `services/recurring_service.py` — auto-generation job (start of month + mid-month), conflict handling, patient absence tracking, payment failure handling (pause after N failures)
- [x] `services/google_calendar_service.py` — bidirectional sync: outbound (create events with platform link, NO Google Meet), inbound (read external events as busy time), conflict detection across both calendars

### 3.2 Backend — Scheduling Jobs
- [x] `scheduler.py` — APScheduler setup: recurring appointment auto-generation (monthly), no-show detection, Google Calendar sync polling
- [x] Cancellation policy enforcement: free >24h, 50% no-show fee, late cancellation charge

### 3.3 Frontend — Calendar
- [x] Install FullCalendar.js
- [x] `pages/therapist/Calendar.tsx` — therapist calendar (FullCalendar) with availability slots, appointments, Google Calendar busy times. View configurable (weekly/monthly/agenda)
- [x] `pages/therapist/AvailabilitySettings.tsx` — recurring slots, blocked dates, session duration
- [x] `pages/patient/Calendar.tsx` — patient calendar with appointments (one-off + recurring), Google Calendar overlay, view configurable
- [x] `pages/patient/RecurringSchedules.tsx` — "Meus Agendamentos Recorrentes" with skip/end/request changes
- [x] `pages/therapist/RecurringSchedules.tsx` — manage all recurring schedules, approve requests
- [x] `components/calendar/BookingFlow.tsx` — slot selection → confirm → payment
- [x] `components/calendar/RecurringBadge.tsx` — visual indicator for recurring appointments
- [x] `hooks/useAppointments.ts` — appointment CRUD + calendar queries
- [x] `hooks/useAvailability.ts` — slot management
- [x] `hooks/useRecurring.ts` — recurring schedule CRUD
- [x] `hooks/useGoogleCalendar.ts` — sync status, connect/disconnect

### 3.4 Backend — Google Calendar Integration
- [x] `services/google_auth_service.py` — OAuth flow for Google, token storage, refresh
- [x] `routers/google_auth.py` — OAuth callback endpoint
- [x] Google Calendar event creation with platform meeting link (NOT Google Meet link)
- [x] Inbound sync: read therapist's external events, display as busy time
- [x] Patient Google Calendar sync: outbound appointments + inbound busy time

### 3.5 Tests — Phase 3
- [x] Router tests: availability, appointments, recurring, google_auth
- [x] Service tests: availability_service, appointment_service, recurring_service, google_calendar_service
- [x] Test scenarios: conflict detection, 24h cancellation policy, no-show 50% charge, recurring auto-generation, Google Calendar sync

---

## Phase 4 — Video Calls + AI Pipeline

### 4.1 Backend — LiveKit Integration
- [x] `services/livekit_service.py` — room creation, token generation, room management (close, participant events)
- [x] `routers/sessions.py` — session lifecycle endpoints: POST /api/sessions/:id/start, POST /api/sessions/:id/pause, POST /api/sessions/:id/resume, POST /api/sessions/:id/end, POST /api/sessions/:id/reopen, GET /api/sessions/:id/status
- [x] Server-side audio recording via LiveKit recording API (audio only, NOT video)
- [x] Multi-segment recording: one segment per Start→Pause/End cycle
- [x] Audio storage in Supabase Storage (temporary, 24h retention for download, auto-delete)
- [x] Consent recording endpoint (both parties must consent before recording starts)

### 4.2 Backend — Session Lifecycle
- [x] `services/session_service.py` — full lifecycle: waiting → active → paused → resumed → ended/auto-finalized → reopened
- [x] Access window enforcement: accessible_from (scheduled_start - 15min), accessible_until (scheduled_end + 45min)
- [x] Auto-pause on disconnect (either party)
- [x] Overtime alerts data: 30, 15, 10, 5, 2, 1 min before window closes
- [x] Auto-finalization when window expires while paused
- [x] Reopen session: 50min independent timer, available only after auto-finalization
- [x] Reopen button visibility: configurable window (default 60min after auto-finalization)
- [x] Session interruption logging (all events in session_interruptions table)

### 4.3 Backend — AI Pipeline
- [x] `services/transcription_service.py` — Whisper API: transcribe each audio segment, concatenate with pause/resume/reopen markers
- [x] `services/summary_service.py` — GPT dual-track summaries: Track 1 (base, patient-facing, transcript only), Track 2 (clinical, therapist-facing, transcript + observations)
- [x] `services/longitudinal_service.py` — dual-track longitudinal analysis: clinical (Track 2 summaries + observations), patient personal (Track 1 summaries + patient notes)
- [x] Summary versioning: never overwrite, auto-increment version per track per session
- [x] Observation change triggers clinical summary regeneration (debounce 30s)
- [x] Patient note change triggers patient longitudinal regeneration (debounce 60s)
- [x] AI prompt injection from platform_settings (admin-configurable prompts)
- [x] Prompt hierarchy: per-therapist > per-clinic > global default
- [x] Tag generation (thematic tags from transcripts/summaries)

### 4.4 Backend — Post-Session
- [x] `routers/observations.py` — CRUD for session observations (therapist only). Auto-triggers clinical summary regeneration
- [x] `routers/patient_notes.py` — CRUD for patient session notes (patient only, private). Triggers patient longitudinal regeneration
- [x] `routers/session_journal.py` — session history endpoints (role-filtered: patient sees Track 1, therapist sees Track 2)
- [x] `routers/longitudinal.py` — longitudinal analysis endpoints: GET /api/longitudinal/clinical/:patient_id (therapist/clinic), GET /api/longitudinal/personal (patient, "Minha Jornada")
- [x] Audio download endpoint (available 24h after session end)

### 4.5 Frontend — Video Call
- [x] Install LiveKit React SDK
- [x] `pages/Session.tsx` — video call page accessed via meeting link (/session/:uuid)
- [x] `components/session/VideoRoom.tsx` — LiveKit video+audio with controls (mute, camera, screen share)
- [x] `components/session/TextChat.tsx` — in-call text chat panel
- [x] `components/session/SessionControls.tsx` — Start/Resume/End buttons (therapist only)
- [x] `components/session/ConsentPopup.tsx` — recording consent (both parties)
- [x] `components/session/WaitingScreen.tsx` — patient waiting for therapist to start
- [x] `components/session/PauseScreen.tsx` — "waiting for reconnection" with countdown
- [x] `components/session/OvertimeAlerts.tsx` — countdown alerts (30/15/10/5/2/1 min)
- [x] `components/session/PostSessionPopup.tsx` — therapist observation + patient notes (shown after End Session)
- [x] `components/session/ReopenButton.tsx` — "Reabrir Sessão" (visible only after auto-finalization)

### 4.6 Frontend — Session Journal
- [x] `pages/therapist/PatientProfile.tsx` — tabbed: Profile | Session Journal (Track 2) | Clinical Longitudinal | Recurring | Pricing | "Patient View" toggle
- [x] `pages/therapist/SessionDetail.tsx` — clinical summary + version history + observation CRUD + private notes + interruption log + reopen button
- [x] `pages/patient/SessionHistory.tsx` — chronological list of sessions with base summary preview
- [x] `pages/patient/SessionDetail.tsx` — base summary (Track 1) + personal notes (editable)
- [x] `pages/patient/Journey.tsx` — "Minha Jornada" personal longitudinal analysis + version browser
- [x] `components/session/SummaryVersionHistory.tsx` — expandable version list
- [x] `components/session/ObservationHistory.tsx` — chronological observation CRUD
- [x] `hooks/useSessions.ts` — session data, summaries, observations
- [x] `hooks/useLongitudinal.ts` — longitudinal analysis versions

### 4.7 LiveKit Self-Hosted Setup Guide
- [x] Document LiveKit server setup on VPS
- [x] TURN/STUN server configuration
- [x] SSL/TLS setup for WebRTC
- [x] Firewall rules (UDP ports for WebRTC media)
- [x] Environment variable configuration (THERAPY_LIVEKIT_*)

### 4.8 Tests — Phase 4
- [x] Session lifecycle tests (start, pause, resume, end, auto-finalize, reopen)
- [x] AI pipeline tests (transcription, summary generation, versioning, debounce)
- [x] Observation trigger tests
- [x] Audio retention/deletion tests
- [x] Access window enforcement tests

---

## Phase 5 — Financial System

### 5.1 Backend — Wallet & Payments
- [x] `routers/wallets.py` — wallet management. Endpoints: GET /api/wallets/me (own wallet), POST /api/wallets/top-up (patient loads credits via Stripe), POST /api/wallets/withdraw (request withdrawal)
- [x] `routers/payments.py` — payment processing. Endpoints: POST /api/payments/validate-card (phantom charge for card validation), GET /api/payments/methods (saved payment methods), POST /api/payments/methods (add), DELETE /api/payments/methods/:id
- [x] `routers/transactions.py` — transaction history. Endpoints: GET /api/transactions (filterable list), GET /api/transactions/:id (detail with full breakdown)
- [x] `routers/clinic_financials.py` — clinic financial management. Endpoints: GET /api/clinic/financials (dashboard), POST /api/clinic/transfers (voluntary transfer to therapist), GET /api/clinic/transfers (history)
- [x] `routers/admin_financials.py` — platform admin financial overview. Endpoints: GET /api/admin/financials (global dashboard), GET /api/admin/wallets (all wallets), PATCH /api/admin/commissions (global rate, per-clinic/per-therapist overrides)
- [x] `routers/refunds.py` — refund system (feature-flag controlled). Endpoints: POST /api/refunds (patient request), GET /api/admin/refunds (admin dashboard), PATCH /api/admin/refunds/:id (approve/deny)

### 5.2 Backend — Financial Services
- [x] `services/wallet_service.py` — wallet CRUD, top-up (credit from Stripe), debit (session end), withdrawal request, balance validation
- [x] `services/payment_service.py` — Stripe Connect Standard integration, card validation (phantom charge), payment method management, session-end capture (wallet debit + card fallback)
- [x] `services/commission_engine.py` — atomic commission calculation: gross → platform fee → clinic share → therapist share. Handles all precedence rules (per-therapist > per-clinic > global for platform fee; per-therapist > clinic default for clinic commission, differentiated by patient_origin)
- [x] `services/payout_service.py` — withdrawal processing, fee calculation (configurable %), bank transfer via Stripe
- [x] `services/refund_service.py` — refund workflow (admin-only), wallet reversal, Stripe refund
- [x] `services/no_show_service.py` — auto-detect no-shows (neither party joined), apply 50% charge to patient wallet

### 5.3 Frontend — Financial Pages
- [x] `pages/patient/Wallet.tsx` — balance, top-up (card/PIX), transaction history, withdrawal
- [x] `pages/patient/PaymentMethods.tsx` — saved cards, add/remove, default for recurring
- [x] `pages/therapist/Financials.tsx` — balance, revenue, paid sessions, active recurring count, statement
- [x] `pages/therapist/Withdraw.tsx` — withdrawal request form
- [x] `pages/clinic/Financials.tsx` — clinic revenue, per-therapist breakdown, wallet, transfers
- [x] `pages/clinic/TransferForm.tsx` — voluntary transfer to therapist
- [x] `pages/admin/Financials.tsx` — global dashboard, ledger, commission management
- [x] `pages/admin/Refunds.tsx` — refund dashboard (pending/approved/denied)
- [x] `hooks/useWallet.ts` — wallet queries, top-up, withdrawal
- [x] `hooks/useTransactions.ts` — transaction history
- [x] `hooks/usePaymentMethods.ts` — card CRUD

### 5.4 Tests — Phase 5
- [x] Commission engine tests (all precedence scenarios, all patient origins)
- [x] Wallet top-up/debit/withdrawal tests
- [x] No-show detection + 50% fee tests
- [x] Card validation (phantom charge) tests
- [x] Session-end payment flow (wallet debit → card fallback → payment_failed)
- [x] Refund feature flag tests (API blocks when disabled)

---

## Phase 6 — Messaging System

### 6.1 Backend — Messaging
- [x] `routers/messaging.py` — conversation + message CRUD. Endpoints: GET /api/conversations (list with filters), POST /api/conversations (start new), GET /api/conversations/:id/messages (with pagination), POST /api/conversations/:id/messages (send), PATCH /api/conversations/:id/read (mark read), POST /api/conversations/:id/archive, POST /api/conversations/:id/mute, DELETE /api/messages/:id (hard delete), POST /api/messages/:id/report
- [x] `routers/support.py` — platform support channel. Endpoints: GET /api/support/conversations (admin inbox), POST /api/support/conversations/:id/messages (admin reply)
- [x] `services/messaging_service.py` — conversation creation (any user → any user), message delivery, read receipts, archive/mute/delete/block logic, report handling
- [x] `services/attachment_service.py` — file/image/audio upload (max 50MB), OpenAI processing (image description, audio transcription), storage in Supabase Storage
- [x] Supabase Realtime integration for live message delivery + presence
- [x] System message generation on key events (session scheduled, completed, summary available, payment received)
- [x] Email notification for unread messages (5min delay default, configurable per user)

### 6.2 Frontend — Messaging UI
- [x] `pages/Messages.tsx` — WhatsApp-like layout: conversation list (left) + active chat (right)
- [x] `components/messaging/ConversationList.tsx` — sorted by recent, pinned support, unread badges, search, filters (All/Unread/Patients/Therapists/Clinics/Support)
- [x] `components/messaging/ChatThread.tsx` — message area with infinite scroll upward
- [x] `components/messaging/MessageInput.tsx` — text field + send button + file/image/audio attachment buttons (Enter sends, Shift+Enter newline)
- [x] `components/messaging/MessageBubble.tsx` — text content, timestamp, sent/delivered/read indicators
- [x] `components/messaging/NewConversation.tsx` — user search to start conversation
- [x] `components/messaging/ConversationActions.tsx` — archive, mute, delete, block, report
- [x] `components/messaging/AttachmentPreview.tsx` — image/audio/file preview with AI-processed content
- [x] Persistent chat icon in all layouts with unread badge
- [x] Mobile responsive: full-screen chat on mobile, side-by-side on desktop
- [x] `hooks/useConversations.ts` — conversation list, realtime subscription
- [x] `hooks/useMessages.ts` — message CRUD, realtime subscription, read receipts

### 6.3 Tests — Phase 6
- [x] Conversation creation tests (all user combinations)
- [x] Privacy/visibility tests (patient can't see other patients' conversations, clinic can't see therapist messages)
- [x] Message hard delete tests
- [x] Block/report tests
- [x] File attachment + OpenAI processing tests
- [x] System message generation tests

---

## Phase 7 — Platform Views & Polish

### 7.1 Platform Admin View
- [x] `pages/admin/Dashboard.tsx` — key metrics (users, revenue, sessions, pending approvals, support tickets)
- [x] `pages/admin/Therapists.tsx` — list with approve/reject
- [x] `pages/admin/TherapistDetail.tsx` — full profile, commission override, sessions, financials
- [x] `pages/admin/Clinics.tsx` — list with approve/reject
- [x] `pages/admin/ClinicDetail.tsx` — profile, affiliated therapists, financials, commission override
- [x] `pages/admin/Patients.tsx` — list, assign to therapist/clinic, set per-patient price
- [x] `pages/admin/PatientDetail.tsx` — profile, current therapist, sessions, transactions
- [x] `pages/admin/Appointments.tsx` — all appointments with filters
- [x] `pages/admin/Wallets.tsx` — all wallets overview
- [x] `pages/admin/Payouts.tsx` — payout management
- [x] `pages/admin/Settings.tsx` — APP_NAME, commission rates, access window timing, reopen settings, AI prompts, refund toggle, email config
- [x] `pages/admin/AIPrompts.tsx` — all configurable prompts with version history
- [x] `pages/admin/Support.tsx` — support inbox
- [x] `pages/admin/Moderation.tsx` — reported messages, user blocks
- [x] `pages/admin/Reviews.tsx` — flagged reviews moderation

### 7.2 Clinic Admin View
- [x] All `/clinic/*` pages fully functional (dashboard, therapist roster, patient directory, financials, wallet+transfers, commission config, pricing, profile, settings, reviews, messaging)

### 7.3 Therapist View
- [x] All `/therapist/*` pages fully functional (dashboard, calendar+availability, patient list, patient profiles, session journal, session detail, financials, recurring schedules, profile, settings, reviews, messaging)

### 7.4 Patient View
- [x] All `/patient/*` pages fully functional (dashboard, calendar, session history, session detail, "Minha Jornada", wallet, payment methods, recurring schedules, profile, settings, reviews, messaging)
- [x] Therapist directory + clinic directory (authenticated)
- [x] Booking flow

### 7.5 Clinic White-labeling
- [x] `services/branding_service.py` — load clinic branding (logo, colors)
- [x] Dynamic theme injection for clinic-affiliated views

### 7.6 Landing Page
- [x] `pages/Landing.tsx` — hero section, how it works, benefits, testimonials, FAQ, CTAs (Encontrar Terapeuta, Explorar Clínicas, Sou Terapeuta, Sou uma Clínica)
- [x] Auth-gate: CTAs redirect to /register with redirect_to parameter
- [x] Footer with institutional links, terms, privacy
- [x] Responsive mobile-first

### 7.7 Legal Pages
- [x] `pages/TermsOfUse.tsx` — terms of use template (PT-BR)
- [x] `pages/PrivacyPolicy.tsx` — privacy policy template (PT-BR, LGPD compliant)

### 7.8 LGPD Compliance
- [x] Patient data deletion flow: delete all patient-side data, keep therapist-side data
- [x] Therapist can delete their own data individually
- [x] Audit trail for data deletion requests

### 7.9 Email Notifications
- [x] `services/email_service.py` — Resend integration for all notification types listed in spec Section 4.9
- [x] Email templates (PT-BR): registration, approval, booking, reminders (48h/24h/1h), cancellation, recurring events, refund, summary available, session lifecycle (paused/resumed/reopened/auto-finalized), payment, reviews, messages

### 7.10 Polish
- [x] Responsive design (mobile-first) across all views
- [x] Loading states (skeleton loaders) on all pages
- [x] Empty states with appropriate messages and CTAs
- [x] Error boundaries
- [x] Toast notifications (sonner)
- [x] Status badges (color-coded per spec Section 4.13.1)
- [x] Keyboard navigation + accessibility

### 7.11 Tests — Phase 7
- [x] Full test coverage for all remaining routers/services
- [x] Integration tests for multi-role scenarios
- [x] RLS policy verification tests
- [x] E2E critical flows: registration → booking → session → payment → review

---

## Cross-Phase Considerations

### Environment Variables (root .env additions)
```
# Therapy Platform (product-specific, THERAPY_ prefix)
THERAPY_LIVEKIT_URL=ws://localhost:7880
THERAPY_LIVEKIT_API_KEY=...
THERAPY_LIVEKIT_API_SECRET=...
THERAPY_GOOGLE_CLIENT_ID=...
THERAPY_GOOGLE_CLIENT_SECRET=...
THERAPY_STRIPE_CONNECT_CLIENT_ID=...
```
Global vars (SUPABASE_*, JWT_SECRET, OPENAI_API_KEY, STRIPE_SECRET_KEY, RESEND_API_KEY) are already in root .env.

### LiveKit Self-Hosted Setup (Phase 4 prerequisite)
1. Install LiveKit server on VPS
2. Configure TURN/STUN (coturn)
3. SSL certificates for WebRTC
4. Open UDP ports (3478, 5349, 7880-7881, 50000-60000)
5. Set THERAPY_LIVEKIT_* env vars

### Stripe Connect Setup (Phase 5 prerequisite)
1. Stripe account with Connect enabled (Standard mode)
2. Create Connect application in Stripe Dashboard
3. Set THERAPY_STRIPE_CONNECT_CLIENT_ID
4. Configure webhook endpoints for payment events

### Google OAuth + Calendar Setup (Phase 2+3 prerequisite)
1. Google Cloud project with Calendar API enabled
2. OAuth 2.0 credentials (web application type)
3. Set THERAPY_GOOGLE_CLIENT_ID and THERAPY_GOOGLE_CLIENT_SECRET
4. Configure authorized redirect URIs

### Supabase Schema Setup (Phase 1) [DONE]
1. Open Supabase SQL Editor
2. Run `001_therapy_platform.sql`
3. Go to Project Settings → API → "Exposed schemas" → Add `therapy`
4. Verify RLS policies are active

---

## Phase 8 — Infrastructure & Deployment

### 8.1 LiveKit Self-Hosted Setup
- [ ] Install LiveKit server on VPS (`curl -sSL https://get.livekit.io | bash`)
- [ ] Generate API key pair (`livekit-server generate-keys`)
- [ ] Create config file `/etc/livekit.yaml` with:
  - Port 7880 (HTTP), 7881 (RTC)
  - TURN server config (ports 3478, 5349)
  - Redis connection (optional, for multi-node)
- [ ] Set up SSL certificates (Let's Encrypt via certbot)
- [ ] Configure TURN/STUN with coturn:
  - Install coturn: `apt install coturn`
  - Configure `/etc/turnserver.conf` with realm + credentials
  - Open UDP ports: 3478, 5349, 50000-60000
- [ ] Open firewall ports: TCP 7880-7881, UDP 3478, 5349, 50000-60000
- [ ] Start LiveKit as systemd service
- [ ] Set env vars in root `.env`:
  ```
  THERAPY_LIVEKIT_URL=wss://your-domain:7880
  THERAPY_LIVEKIT_API_KEY=generated-key
  THERAPY_LIVEKIT_API_SECRET=generated-secret
  ```
- [ ] Test: connect to room via LiveKit CLI or test page

### 8.2 Stripe Connect Setup
- [ ] Create Stripe account (or use existing)
- [ ] Enable Stripe Connect (Dashboard → Connect → Get started)
- [ ] Select Standard mode
- [ ] Create Connect application (Dashboard → Settings → Connect → Platform settings)
- [ ] Copy Client ID
- [ ] Set up webhook endpoint: `https://your-domain/api/webhooks/stripe`
- [ ] Set env vars:
  ```
  STRIPE_SECRET_KEY=sk_test_...  (already exists in root .env if shared with core)
  THERAPY_STRIPE_CONNECT_CLIENT_ID=ca_...
  ```
- [ ] Test: create test payment in Stripe test mode

### 8.3 Google OAuth + Calendar Setup
- [ ] Go to Google Cloud Console → Create project (or use existing)
- [ ] Enable APIs: Google Calendar API, Google People API
- [ ] Create OAuth 2.0 credentials:
  - Application type: Web application
  - Authorized redirect URIs: `http://localhost:8095/auth/google/callback`, `https://your-domain/auth/google/callback`
- [ ] Set env vars:
  ```
  THERAPY_GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
  THERAPY_GOOGLE_CLIENT_SECRET=GOCSPX-...
  ```
- [ ] Test: Google login flow in dev

### 8.4 Seed Platform Admin
- [ ] Create admin user via Supabase Dashboard or seed script
- [ ] Set user_metadata: `{"role": "platform_admin"}`
- [ ] Verify admin can login and access /admin/*

### 8.5 Frontend Environment
- [x] Configure `products/therapy-platform/frontend/.env` with real Supabase keys

### 8.6 Manual QA Pass
- [ ] See `THERAPY-QA-CHECKLIST.md` for full checklist
- [ ] Fix any issues found during QA

### 8.7 Domain & Deployment
- [ ] Choose final product name (replace "Psicomatch" placeholder)
- [ ] Update `APP_NAME` in therapy.platform_settings
- [ ] Set up production domain + SSL
- [ ] Deploy backend to VPS (same pattern as ERP/PF)
- [ ] Deploy frontend (Vercel or VPS + nginx)
- [ ] Update `CORS_ORIGINS` with production domain
- [ ] Update Supabase redirect URLs for production
- [ ] Update Google OAuth redirect URIs for production

### 8.8 Content & Legal
- [ ] Customize Terms of Use template with real company data
- [ ] Customize Privacy Policy template with DPO contact
- [ ] Write/refine default AI prompts in platform_settings
- [ ] Add real testimonials to landing page
- [ ] Design and upload logo
- [ ] Configure sender email (Resend domain verification)
