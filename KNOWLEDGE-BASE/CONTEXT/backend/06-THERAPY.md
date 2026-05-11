# 06 — Therapy Platform Backend

> Path: `products/therapy-platform/backend/app/` · Port: 8003 · 40 routers · 43 services · 1336 backend tests passing (2026-05-11 post-wiring)
> Schema: `therapy` · Auth: Direct Supabase Auth (NOT NoctusAI SSO)
> Seed entry: `noctusai_seed.create_product_app(..., standard_routers=["health", "notificacoes", "llm"], consent_features="app.services.ai_consent_features")`.

## Auth Model

Users log in directly to the therapy platform — no SSO. Only the platform admin connects to NoctusAI core. 4 roles stored in `user_metadata`: `platform_admin`, `clinic_admin`, `therapist`, `patient`. Multi-tenancy via `clinic_id` (not `org_id`). Independent therapists have `clinic_id = NULL`.

## Dependencies & Auth Helpers (Pattern F — factory-bound)

| Function | Purpose |
|----------|---------|
| `get_current_user` | Resolves authenticated user from JWT (re-exported from seed `create_dependencies`) |
| `get_user_role(user)` | Returns role from metadata; first consults `resolve_sso_role(user)` for SSO-derived admin access |
| `require_role(*allowed_roles)` | **Product-bound factory** in `app/dependencies.py`: `require_role = make_require_role(get_current_user, get_user_role)`. Use as `auth=Depends(require_role("platform_admin"))` — returns `(user, token, role)` or 403 |
| `get_clinic_id_for_user(user)` | Resolves `clinic_id` from metadata; `None` for independents |
| `log_action()` | Server-side audit logging via `noctusai_lib.domain.action_log.log_action` (always service role) |

**Carve-out vs. cross-platform Pattern F:** therapy uses `clinic_id`, not `org_id`. The cross-platform `noctusai_lib.api.auth.make_get_current_user_org` used by ERP/PF/etc. does NOT apply. Therapy's Pattern F materialized as `make_require_role` — formalized during `therapy-platform-wiring` Phase 1; seed-side `require_role` retired same phase.

## Shared identity resolver

```python
from noctusai_lib.integrations.supabase_identity import (
    UserIdentity, fetch_user_identities, fetch_user_identity,
)
identities = fetch_user_identities(db, user_ids)
identity = identities.get(uid, UserIdentity(user_id=uid))
```

Consumed by `admin_service.py` (therapist/patient/clinic/appointment/report/review/block/support list endpoints). N+1 zero-tolerance: pre-fetch identities before the DTO mapper loop.

## Router Groups (40 product routers + 3 seed standard_routers)

- **Auth & Admin**: auth, admin, admin_financials, invitations, lgpd, settings, support
- **Profiles**: clinics, therapists, patients, therapy_matching, reviews
- **Scheduling**: appointments, availability, recurring, scheduling, sessions (LiveKit), rooms
- **Clinical**: anamnese, treatment_plans, evolution_notes, observations, patient_notes, crisis, longitudinal, consents
- **Patient Self-Service**: mood, homework, session_journal, therapeutic_journal
- **Financial**: wallets, transactions, payments (Stripe Connect), invoices, refunds, clinic_financials
- **Communication**: messaging, whatsapp_therapy, attachments  *(notificacoes is mounted by seed `standard_routers`, not a product file)*
- **Analytics**: dashboard_bi

## Route prefixes (post-wiring, Pattern A PT→EN closed)

| Router | Prefix |
|--------|--------|
| `crisis.py` | `/api/crisis-alerts` |
| `homework.py` | `/api/homework` |
| `mood.py` | `/api/mood` |
| `rooms.py` | `/api/rooms` (sub-path `/bookings`) |
| `therapeutic_journal.py` | `/api/diary` |
| `evolution_notes.py` | `/api/evolution-notes` |
| `treatment_plans.py` | `/api/treatment-plans` |
| `invoices.py` | `/api/invoices` (Pattern-G `POST /api/invoices` replaces `POST /api/recibos/gerar`) |
| `messaging.py` | `/api/conversations` |
| `session_journal.py` | `/api/journal` |
| `therapy_matching.py` | `/api/matching` |
| `whatsapp_therapy.py` | `/api/whatsapp` |
| `clinic_financials.py` | `/api/clinic/financials` |
| `dashboard_bi.py` | `/api/bi` |

**Carve-outs preserved**: `anamnese` (medical-PT), `treatment_plans/{plan_id}/metas` sub-path (seed-primitive `noctusai_lib.domain.metas`), `evolution-notes/paciente/{patient_id}` sub-path (Pattern-A is prefix-only).

## DTO Contract — Pattern E

193 routes have **no** `response_model=` declaration; the DTO contract is implicit via `success_response()` / `paginated_response()` wrappers + per-service mapper functions (e.g. `_therapist_row_to_dto`, `_clinic_row_to_dto`, `_patient_row_to_dto`, `_appointment_row_to_dto`). Mappers carry the contract — accept-with-rationale at close.

## Post-wiring surface (2026-05-11 close summary)

`therapy-platform-wiring` (10 phases, 2026-04-20 → 2026-05-11) landed:

- **5 new admin endpoints** (Phase 2): `/api/admin/appointments`, `/api/admin/dashboard`, `/api/admin/suspend/{type}/{id}`, `/api/admin/financials/{summary,transactions,commissions,commissions/{id}}`.
- **5 list-endpoint DTO normalizations** (Phase 3): clinics, patients, reports, reviews/flagged, blocks, support/conversations — typed mappers replace raw-row passthrough; identity resolver bulk-pre-fetch.
- **Reject-flow triplet** (Phase 5): migration `013_rejection_audit.sql` adds `rejection_reason` + `rejected_at` + `rejected_by` to `therapist_profiles` + `clinics`; `reject_entity` writes audit; `approve_entity` clears it.
- **Patient reviews** (Phase 7): `GET /api/reviews/patient/{patient_id}`, `DELETE /api/reviews/{review_id}` added; `useUpdateReview` rewired to canonical `PATCH /api/reviews/{review_id}`.
- **Matching unified** (Phase 7): `POST /api/matching/embed` with optional `{role}` body; split routes `embed-{terapeuta,paciente}` kept `deprecated=True`.
- **Pattern F migration** (Phase 1 bonus): `app/routers/settings.py` 11 endpoints migrated from inline `_require_admin` / `_require_role` to `Depends(require_role(...))`.
- **Table-name corrected** (Phase 4): `commission_overrides` → `platform_commission_overrides`.

8 follow-up projects + 3 accept-with-rationale entries filed at close. `MASTER-PROMPT.md` carries the cross-link table.

## Key Integrations

| Integration | Purpose | Config |
|-------------|---------|--------|
| LiveKit | Video therapy sessions | `THERAPY_LIVEKIT_URL`, `_API_KEY`, `_API_SECRET` |
| Stripe Connect | Marketplace payments | `THERAPY_STRIPE_CONNECT_CLIENT_ID` |
| OpenAI GPT | Session summaries, longitudinal, crisis detection | Shared `openai_api_key` via `noctusai_lib.llm` |
| OpenAI Whisper | Session transcription | Shared `openai_api_key` via `noctusai_lib.llm` |
| Google OAuth | Login + Calendar sync | `THERAPY_GOOGLE_CLIENT_ID`, `_SECRET` |
| WAHA (WhatsApp) | Appointment reminders | seed `noctusai_lib.integrations.whatsapp.WahaClient` (formalized 2026-05-10) |
| Supabase | Auth, database, storage, RLS | shared |

## AI Pipeline

Orchestrated by `ai_pipeline` service. **All four steps call `noctusai_lib.llm` — never the OpenAI SDK directly.** Clinical text passes `cache=False` to the lib (LGPD hard rule: Art. 11 sensitive data never enters a cache key).

1. Transcription (Whisper) → 2. Summary (GPT) → 3. Longitudinal analysis (GPT, min 4 sessions) → 4. Crisis detection (keyword + GPT) → 5. Attachment analysis (vision/audio).

Prompt hierarchy: per-therapist > per-clinic > global default. 4 LGPD concerns tracked in `LGPD-WARNINGS.md`.
