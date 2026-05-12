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
- Seed entry: `noctusai_seed.create_product_app(...)` with `standard_routers=["health", "notificacoes", "llm"]`, `consent_features="app.services.ai_consent_features"`, lifespan-managed APScheduler.

## Auth Model

Users log in directly -- no SSO flow for patients/therapists/clinic admins. 4 roles stored in `user_metadata`:

| Role | Scope |
|------|-------|
| `platform_admin` | Full platform access |
| `clinic_admin` | Manages one clinic |
| `therapist` | Own patients, sessions, schedule |
| `patient` | Own records, bookings, self-service tools |

Independent therapists have `clinic_id = NULL`.

### Auth Helpers (Pattern F — factory-bound in `app/dependencies.py`)

| Function | Purpose |
|----------|---------|
| `get_current_user` | Resolves authenticated user from JWT (re-exported from seed `create_dependencies`) |
| `get_user_role(user)` | Returns role from metadata; first consults `resolve_sso_role(user)` for SSO-derived admin access |
| `require_role(*allowed_roles)` | **Product-bound dependency factory**: `require_role = make_require_role(get_current_user, get_user_role)`. Use as `auth=Depends(require_role("platform_admin"))` — returns `(user, token, role)` or 403 |
| `get_clinic_id_for_user(user)` | Resolves `clinic_id` from metadata; `None` for independents |
| `log_action()` | Server-side audit logging (always service role) |

**Carve-out vs. cross-platform Pattern F:** therapy uses `clinic_id`, not `org_id`. The seed factory `noctusai_lib.api.auth.make_get_current_user_org` used by ERP/PF/etc. does NOT apply here. Pattern F in therapy materialized as `make_require_role` (formalized during `therapy-platform-wiring` Phase 1; seed-side `require_role` retired same phase).

## Shared identity resolver

Backend services bulk-resolve `auth.users` identity (name/email/photo) via the seed helper:

```python
from noctusai_lib.integrations.supabase_identity import (
    UserIdentity,
    fetch_user_identities,   # bulk
    fetch_user_identity,     # singular
)

identities = fetch_user_identities(db, user_ids)  # one query, N+1-free
identity = identities.get(uid, UserIdentity(user_id=uid))
```

Consumed by `admin_service.py` for therapist / patient / clinic / appointment / report / review / block / support list endpoints. N+1 zero-tolerance: pre-fetch identities before the DTO mapper loop.

## Key Domains

### Auth and Admin
- **auth** (`/api/auth`) -- registration, login, password flows. Several endpoints orphan post-Phase-9 (frontend bypasses via Supabase-direct + seed `LoginForm`/`ForgotPasswordPage`/`AcceptInvitePage`); see follow-up `therapy-auth-router-orphan-cleanup`.
- **admin** (`/api/admin`) -- platform admin operations. **Expanded during Phase 2-5 wiring**: appointments / dashboard / suspend / patients / clinics / reports / reviews / blocks / support / commissions all wired with typed DTOs via the identity resolver; reject-flow audit (rejection_reason + rejected_at + rejected_by) added via migration `013_rejection_audit.sql`.
- **admin_financials** (`/api/admin/financials`) -- platform-level financial overview: summary / transactions / commissions (GET/POST/DELETE) / payouts. `commission_overrides` table-name corrected to `platform_commission_overrides` (Phase 4).
- **invitations** (`/api/invitations`) -- accept-flow wired via seed `AcceptInvitePage`; admin list+cancel routes orphan.
- **lgpd** (`/api/lgpd`) -- LGPD (Brazilian data protection) compliance: data export, deletion requests. Patient-side consumer pending (follow-up `therapy-lgpd-patient-portal-wiring`).
- **settings** (`/api/settings`) -- clinic + therapist + patient + platform settings. All 11 endpoints migrated to `Depends(require_role(...))` Pattern F (Phase 1 bonus).
- **support** (`/api/support`) -- support ticket system.

### Profiles
- **clinics** (`/api/clinics`) -- clinic registration, profile, branding. Several settings endpoints consumer-pending; misroutes Settings.tsx bank/CNPJ/email/commission to branding endpoint (silent-drop bug filed as `therapy-clinic-settings-misrouting`).
- **therapists** (`/api/therapists`) -- therapist profiles, specializations, credentials.
- **patients** (`/api/patients`) -- patient profiles, intake data. Role-filtered server-side: clinic-admin branch via `get_clinic_id_for_user(user)`; therapist branch via `therapist_id` association.
- **therapy_matching** (`/api/matching`) -- algorithm matching patients to therapists. Unified `POST /api/matching/embed` with optional `{role}` body (split routes `embed-{terapeuta,paciente}` kept `deprecated=True` for backwards compat).
- **reviews** (`/api/reviews`) -- patient reviews of therapists. `GET /api/reviews/patient/{patient_id}` + `DELETE /api/reviews/{review_id}` added Phase 7; flagged-review moderation under admin.

### Scheduling
- **appointments** (`/api/appointments`) -- booking lifecycle (request, confirm, cancel, reschedule).
- **availability** (`/api/availability`) -- therapist schedule configuration (weekly slots, exceptions).
- **recurring** (`/api/recurring`) -- recurring session patterns.
- **scheduling** (`/api/scheduling`) -- alternative scheduling surface (seed scheduling primitive).
- **sessions** (`/api/sessions`) -- session execution with LiveKit video integration.
- **rooms** (`/api/rooms`, sub-paths `/bookings`) -- virtual + physical room management.

### Clinical
- **anamnese** (`/api/anamnese`) -- intake assessments (medical-PT term kept; Pattern A carve-out).
- **treatment_plans** (`/api/treatment-plans`) -- structured treatment planning (sub-path `/{plan_id}/metas` kept; `metas` is the seed-primitive name).
- **evolution_notes** (`/api/evolution-notes`) -- per-session clinical notes.
- **observations** (`/api/observations`) -- clinical observations.
- **patient_notes** (`/api/patient-notes`) -- therapist private notes on patients.
- **crisis** (`/api/crisis-alerts`) -- crisis detection and escalation protocols.
- **longitudinal** (`/api/longitudinal`) -- long-term patient progress analysis (AI-powered, min 4 sessions).
- **consents** (`/api/consents`) -- consent capture and audit.

### Patient Self-Service
- **mood** (`/api/mood`) -- daily mood tracking.
- **homework** (`/api/homework`) -- therapeutic homework assignments.
- **session_journal** (`/api/journal`) -- patient session reflections.
- **therapeutic_journal** (`/api/diary`) -- ongoing therapeutic journaling.

### Financial
- **wallets** (`/api/wallets`) -- therapist/clinic wallet balances.
- **transactions** (`/api/transactions`) -- financial transaction history.
- **payments** (`/api/payments`) -- Stripe Connect marketplace payments (platform takes fee).
- **invoices** (`/api/invoices`) -- invoice generation (Pattern-G `POST /api/invoices` replaces `POST /api/recibos/gerar`).
- **refunds** (`/api/refunds`) -- refund processing.
- **clinic_financials** (`/api/clinic/financials`) -- clinic-level financial reporting.

### Communication
- **messaging** (`/api/conversations`) -- in-app messaging between therapist and patient.
- **notificacoes** -- notification delivery (mounted by seed framework via `standard_routers=["notificacoes"]`; not a product-owned router file).
- **whatsapp_therapy** (`/api/whatsapp`) -- WhatsApp integration for appointment reminders. `send_via_waha` formalized to seed `noctusai_lib.integrations.whatsapp` 2026-05-10 (catalog: `send_via_waha exists in ERP and therapy`).
- **attachments** (`/api/attachments`) -- file attachments for messages and clinical records.

### Analytics
- **dashboard_bi** (`/api/bi`) -- clinic and therapist analytics dashboards.

## Backend Route Naming — Pattern A (PT → EN)

Closed-out during `therapy-platform-wiring` Phases 6.b/7.a/8.b. The 8 renames:

| Before | After |
|--------|-------|
| `/api/alertas-crise` | `/api/crisis-alerts` |
| `/api/tarefas` | `/api/homework` |
| `/api/humor` | `/api/mood` |
| `/api/salas` (sub-path `/reservas`) | `/api/rooms` (sub-path `/bookings`) |
| `/api/diario` | `/api/diary` |
| `/api/evolucao` | `/api/evolution-notes` |
| `/api/planos-tratamento` | `/api/treatment-plans` |
| `/api/recibos` (+ `POST /gerar`) | `/api/invoices` (+ `POST /api/invoices` Pattern-G) |

**Carve-outs preserved**: `anamnese` (medical-PT term), `treatment_plans/{plan_id}/metas` sub-path (seed-primitive name), `evolution-notes/paciente/{patient_id}` sub-path (Pattern-A is prefix-only).

## DTO Contract — Pattern E

193 routes have **no** `response_model=` declaration; DTO contract implicit via `success_response()` ∨ `paginated_response()` wrappers + per-service mapper functions (e.g. `_therapist_row_to_dto`, `_clinic_row_to_dto`, `_patient_row_to_dto`, `_appointment_row_to_dto`). Mappers carry the schema contract — cataloged as [A] during the wiring close.

## AI Pipeline

Orchestrated by `ai_pipeline` service. **All four steps call `noctusai_lib.llm` — ¬ the OpenAI SDK directly.** Clinical text passes `cache=False` to the lib, which short-circuits the response cache before any hashing (LGPD hard rule: Art. 11 sensitive data ¬ enters a cache key).

1. **Transcription** — `transcribe_audio(audio_bytes, ...)` (Whisper under the hood)
2. **Summary** — `chat_completion(messages, cache=False, ...)` for session summary
3. **Longitudinal analysis** — `chat_completion(messages, cache=False, ...)` for cross-session progress (requires min 4 sessions)
4. **Crisis detection** — keyword analysis + `chat_completion(cache=False)` for escalation signals
5. **Attachment analysis** — `analyze_image(...)` for vision, `transcribe_audio(...)` for audio uploads

Four LGPD concerns tracked in `LGPD-WARNINGS.md` (patient-clinical-text-in-llm-prompt, longitudinal-clinical-aggregation, patient-audio-to-whisper, patient-attachment-to-llm) — each requires a documented mitigation before the feature ≡ production-ready.

Prompt hierarchy: per-therapist > per-clinic > global default.

## Services (43)

`_bulk.py` (cross-cutting bulk-lookup helper used by admin list endpoints), admin, ai_consent_features, ai_pipeline, appointment, attachment, audio_retention, auth, availability, bi, branding, clinic, clinical_records, commission_engine, consent, crisis, email, homework, invoice, journal, lgpd, livekit, longitudinal, matching, messaging, mood, no_show, patient, payout, recurring, refund, review, room, scheduling (sub-package), session, stripe, summary, therapist, therapy_embedding, transcription, wallet, whatsapp_therapy.

## Frontend Structure

Role-based page directories:
- `pages/admin/` (15) -- Dashboard, Therapists, Clinics, Patients, Appointments, Financials, Refunds, Settings, AIPrompts, Support, Moderation, Reviews + TherapistDetail, ClinicDetail, PatientDetail
- `pages/clinic/` (6) -- Dashboard, Therapists, Patients, Financials, Settings, LLMPreferences
- `pages/therapist/` (15) -- Dashboard, Calendar, AvailabilitySettings, RecurringSchedules, Scheduling, Patients, PatientProfile, SessionDetail, Financials, Reviews, Settings, ClinicalRecords, HomeworkManager, BiDashboard, CrisisAlerts
- `pages/patient/` (14) -- Dashboard, Calendar, RecurringSchedules, SessionHistory, SessionDetail, Journey, Wallet, PaymentMethods, Reviews, Settings, MoodTracker, Diary, Homework, Invoices
- Cross-role: Messages, Session, TherapistProfile, ClinicProfile
- Public: Landing, Login, Register, ForgotPassword, AcceptInvite, ClinicDirectory, TherapistDirectory, PrivacyPolicy, TermsOfUse, NotFound

### Hooks (30)

Pattern-D consolidation: direct-fetch pages bypassing hooks were replaced by named hooks during Phases 6.a / 8.a:

- **Scheduling**: useAppointments, useAvailability, useRecurring, useSessions, useScheduling
- **Financial**: useWallet, usePayments, useTransactions, useInvoices, useRefunds, useClinicFinancials, useAdminFinancials
- **Clinical**: useClinicalRecords (corrected during Pattern-A batch: `/api/clinical/anamnese|treatment-plans|evolution-notes` → canonical prefixes), useMood, useDiary, useHomework, useJournal, useLongitudinal, useCrisis
- **Communication**: useConversations, useMessages, useConsents
- **Per-role lists** (new during wiring): useTherapistPatients, useTherapistReviews, useClinicPatients, useClinicTherapists, usePatientReviews
- **Other**: useAdmin, useSettings, useTherapyMatching, useBi

## Development Guidelines

- Follow shared patterns from noctusai_lib (auth, roles, invitations, responses, exceptions).
- Use `require_role()` (product-bound factory in `dependencies.py`) for every endpoint — ¬ re-introduce inline `_require_admin` / `_require_role` helpers.
- Bulk-resolve identities via `fetch_user_identities(db, user_ids)` before iterating DTO mapper loops — N+1 zero tolerance.
- Router → Service → Schema pattern; routers thin, business logic in services.
- RLS policies use `(SELECT auth.uid())` pattern on all tables.
- Portuguese for business domain names, English for technical/framework code; backend route prefixes use English per Pattern A (carve-outs documented above).
- Use `clinic_id` for tenant isolation (≠ `org_id`). Independent therapists have `clinic_id = NULL`.
- Use `log_action()` for audit logging on sensitive operations.
- Clinical data requires extra care: LGPD compliance, encryption at rest, data deletion support.
- Stripe Connect: platform is the "connected account" facilitator; therapists ∨ clinics onboard as connected accounts.
- LiveKit room tokens short-lived ∧ scoped to specific session + participant.

## Testing

```bash
cd products/therapy-platform/backend && pytest
```

**1336 ✅, 14 skipped** at `therapy-platform-wiring` close (2026-05-11). 64 test files across routers + services. Status-code-assertion rule enforced (every body-asserting test pins `.status_code` first).

### Test-suite hardening — 2026-05-11

Two engineer commits closed the OOS therapy test failures surfaced by the seed mock predicate refresh:

- **Engineer T (`ef01f57`)** — `test(therapy): close 10 OOS tenancy/predicate gaps surfaced by LATENT-FIX-THERAPY-2`. Four sub-causes:
  1. Tenancy-seed gap (clinic_id rows missing from fixture state).
  2. `is_("null")` literal-string predicate gap (closed structurally by Q's seed mock fix).
  3. `BackgroundTask` core_db resolution path (background side-effect ¬ resolve the right client in test).
  4. Tests asserting against OLD seed-mock predicate bug ≠ correct PostgREST IS-NULL semantics.
- **Engineer Y (`f5d386e`)** — `chore(therapy/tests): Phase 3 — replace "null" literal-string shims with None now that seed mock _eval_is handles IS-NULL`. Swept 6 `"null"` literal-string shims → `None` after Q's seed mock fix (`f3aabfd`, see *Methodology — 2026-05-11* below) made the workaround obsolete.

Net effect: the shim disappears, callers pass `None` (real PostgREST contract), ∧ the seed mock's `_eval_is` honours `IS NULL` natively. **¬ reintroduce the `"null"` literal shim** — it now silently misroutes (returns rows that should be excluded).

## Methodology — 2026-05-11

Live-methodology pieces that landed today ∧ bear on how you work in this product.

### 1. Codification pipeline (s1→s4)

New pattern doc — `KB § PATTERNS/methodology-codification-pipeline.md` — names the 4-stage path: **s1 emerges → s2 memory → s3 KB+CLAUDE.md → s4 `check_*` keeper detector with colocated test.** Promote when: deterministic predicate ∧ N≥3 ∧ remediation defined.

Keeper ≡ **codification layer** of the methodology — ¬ regulatory silo. Rules legitimately at s3 (judgment-dependent / context-dependent / methodology-in-pilot / aesthetic) explicitly documented. New rule emerges while inside therapy ⇒ route it deliberately through the stages — *¬ stall at memory*.

### 2. Doc-code coherence (NEW universal rule)

Three-way-sync (KB ↔ CLAUDE.md ↔ memory) extended one layer: **tool-code ↔ doc-prose stays coherent in the SAME commit.** Coding tool behavior Δ (new flag ∨ new mode ∨ renamed detector ∨ different severity) ⇒ every doc that references it MUST update with the code:

- KB pattern docs
- Situation→Tool maps (most-stale-prone surface)
- CLAUDE.md routing pointers describing behavior
- INDEX.md scope descriptions
- Inline `--help` text
- README ∨ MASTER-PROMPT references in product folders (**including this file**)

Discovery recipe: `grep -rn "<tool-name>" KNOWLEDGE-BASE/ CLAUDE.md CLAUDE/ projects/ products/*/README.md`. Pre-commit hook ¬ enforce this yet — agent-discipline at s3, with candidates `check_doc_tool_reference_drift` (already s4) + `check_mcp_tool_argument_drift` (tracked).

**Therapy implication:** therapy script `--help` Δ ∨ hook behavior Δ ∨ any tool the MASTER-PROMPT here cites Δ ⇒ update the prose in this file in the same commit.

### 3. Keeper detectors — 10 new checks (live registry)

Generated 2026-05-11 via `noctus.dev.outline_python mcp/noctusai/tools/noctus/dev/compliance.py`. These are the recently-added detectors most relevant when working in therapy:

| Detector | What it catches |
|----------|-----------------|
| `check_test_status_assertion` | Body-asserting tests (`.text` / `.json()` / `.content`) without a `.status_code` pin in the same method — defends against the false-green slip. |
| `check_unknown_table_references` | `<X>.table("name")` callsites where `name` is not declared by any `CREATE TABLE` in product migrations. |
| `check_function_search_path_pinned` | `CREATE FUNCTION` blocks in product migrations missing pinned `search_path` (Postgres security hygiene). |
| `check_admin_endpoint_service_role_bypass` | Admin-client `.table("T")` callsites where T lacks a `service_role_bypass` RLS policy. |
| `check_slowapi_with_pep563` | Files combining `@limiter.limit` (slowapi) with `from __future__ import annotations` — the runtime-resolution footgun. |
| `check_no_silent_ok_comment` | The literal `# silent-ok` annotation in production code (escape hatch retired platform-wide). |
| `check_auth_dep_anti_pattern` | `Depends(ProductDependencies.get_org_id/get_user_role/get_user_client)` — the positional-args → 422 query-param trap. **Therapy carve-out:** therapy uses `require_role()` (factory-bound), not `get_current_user_org` — this detector flags the cross-platform anti-shape; therapy's `make_require_role` is the correct surface here. |
| `check_mcp_path_via_settings` | `Path(__file__).parents[N]` in MCP tool modules — must import `REPO_ROOT, PRODUCTS_DIR` from `settings` instead. |
| `check_mcp_write_tool_worktree_arg` | MCP write tools (`create_*`, `update_*`, `delete_*`, `set_*`, …) missing the explicit `worktree_path` parameter. |
| `check_doc_tool_reference_drift` | KB doc references to `bash scripts/<name>.sh <mode>` where the referenced mode no longer exists in the script (the codification of the doc-code coherence rule). |

Adjacent detectors active in therapy: `check_archive_staleness`, `check_dispatcher_staleness`, `check_branch_orphan`, `check_gitignore_drift`, `check_pipefail_grep_q`, `check_section_7_placeholder_consistency`, `check_detector_has_regression_test`.

Run `noctus.dev.validate_product slug=therapy-platform` to surface any therapy-side hits.

### 4. Seed mock predicate fix — Q's commit `f3aabfd`

`fix(seed/mocks): _eval_is PostgREST IS-NULL + _FilterMixin.not_ negation (Option A soft compat)` landed at seed layer. Two predicate gaps closed:

- **`_eval_is`** — seed `MockSupabaseClient` correctly evaluates PostgREST `.is_("col", None)` as `IS NULL` (previously misrouted, requiring `"null"` literal-string shims in tests).
- **`_FilterMixin.not_`** — negation chain (`.not_.is_(...)`) flips correctly.

**Downstream impact in therapy:**
- Engineer Y's Phase 3 sweep (commit `f5d386e`) removed all 6 `"null"` literal-string shims from therapy tests.
- Engineer T's Phase 2 (commit `ef01f57`) tests asserting against OLD bug rewritten ↔ correct PostgREST contract.

**Anti-pattern alert:** ¬ reintroduce `is_("col", "null")` — pass `None`. Seed mock matches real PostgREST behavior; the workaround silently breaks results.

### 5. Canonical rate-limit policies — `DEFAULT_AUTH_RL` (therapy adopted)

Seed layer ships canonical policies in `noctusai_lib.api.rate_limit_policies`. **Therapy's `app/routers/auth.py` imports ∧ uses `DEFAULT_AUTH_RL`** at three endpoints (lines 82 / 95 / 119):

```python
from noctusai_lib.api.rate_limit_policies import DEFAULT_AUTH_RL

@router.post("/login")
@limiter.limit(DEFAULT_AUTH_RL)  # canonical seed policy
async def login(...): ...
```

**Convention:** ¬ hand-author per-product rate-limit strings on auth endpoints. Adopt the canonical seed policy. New auth-shape endpoints in therapy MUST pull from `noctusai_lib.api.rate_limit_policies`; deviation triages [F] ∨ [R] ∨ [A] per the recurrence rule.

### 6. Bootstrap auto-hydrate

`scripts/bootstrap-worktree.sh` ∧ `scripts/bootstrap-seed-workspace.sh` auto-hydrate the sibling workspace surface: stale-worktree cleanup runs **before** hydration; ensures the 8 noc surfaces (CLAUDE.md, CLAUDE/, KNOWLEDGE-BASE/, .claude/, mcp/, seed/, noctusai_lib/, templates/) symlink in cleanly without manual steps.

**Therapy implication:** isolated test workspace to debug a therapy issue ⇒ bootstrap script handles the noc surface inheritance — *¬ trim*. Per-product focus belongs here in MASTER-PROMPT.md, ¬ in pruning the inherited surface.

## Chatbot operational-readiness — N=2 inheritor candidate

Therapy chatbot (`whatsapp_therapy` router + `chatbot_*` services) is an **N=2 inheritor candidate** for `KB § PATTERNS/chatbot-operational-readiness.md` — production-hardening checklist first adopted by `imobi-scheduling`. The pattern bundles:

- Retries on transient external writes via `retry_call` composing seed `RetryPolicy`.
- Structured logs auto-wired by `create_product_app`.
- Health endpoint via `standard_routers=["health"]` (therapy already opted-in).
- `DEPLOYMENT.md` shape (per-product ops runbook).
- Supabase managed backups.
- Metrics-sink seam with `NoopCounter` default.

**Next touch of therapy chatbot wiring ⇒ evaluate checklist + file `therapy-chatbot-operational-readiness` follow-up** (∨ [A] individual items). N=2 ⇒ triage time per recurrence rule.

## Known Follow-ups (filed during wiring)

8 follow-up projects + 3 [A] entries surfaced during `therapy-platform-wiring` close:

| Slug | Surface |
|------|---------|
| `therapy-public-directory-wiring` | `ClinicDirectory.tsx` + `TherapistDirectory.tsx` static placeholders → wire to backend |
| `therapy-public-directory-auth-semantic` [A] | JWT-vs-publicRoutes mismatch on directory pages |
| `therapy-auth-router-orphan-cleanup` | 7 auth endpoints fully orphan; retire-vs-migrate decision |
| `therapy-admin-invitations-management` | Admin invitations list+cancel UX |
| `therapy-clinic-settings-misrouting` | HIGH-PRIORITY silent-drop bug: bank/CNPJ/email/commission → branding endpoint |
| `therapy-clinic-rooms-management-wiring` | 5 orphan rooms routes (no `pages/clinic/Rooms.tsx`) |
| `therapy-clinic-therapist-config-wiring` | 3 orphan clinic-admin therapist-config routes |
| `therapy-clinic-dashboard-bi-wiring` | Static `pages/clinic/Dashboard.tsx` + therapist-only BI gate |
| `therapy-clinic-jwt-derived-clinic-id` [A] | `useClinicTherapists` derives `clinic_id` client-side |
| `therapy-patient-dto-enrichment-unified` | Subsumes `therapist-patient-dto-enrichment`; N=3 across admin/therapist/clinic |
| `therapy-lgpd-patient-portal-wiring` | 3 unconsumed `lgpd.py` routes |
| `therapy-matching-embed-deprecation-removal` | Split-route removal after consumer migration |
| Pattern E DTO-contract-via-mappers [A] | 193 routes have no `response_model`; mappers carry the contract |

## Dependencies

- Shared backend: `noctusai_lib` (including `noctusai_lib.llm` for all AI access — GPT / Whisper / Vision / embeddings — with automatic `cache=False` on clinical flows) + `noctusai_lib.integrations.supabase_identity` (bulk identity resolver) + `noctusai_lib.api.auth.make_require_role` (factory) + `noctusai_lib.integrations.whatsapp` (WAHA transport).
- Shared frontend: `@noctusai/lib` + `@noctusai/lib/design-system`.
- Seed framework: `noctusai_seed.create_product_app` (FastAPI app factory; mounts `health` + `notificacoes` + `llm` standard routers).
- LiveKit: video therapy sessions (`THERAPY_LIVEKIT_URL`, `_API_KEY`, `_API_SECRET`).
- Stripe Connect: marketplace payments (`THERAPY_STRIPE_CONNECT_CLIENT_ID`).
- LLM access: via `noctusai_lib.llm` only — no direct `from openai import ...` in product services. `grep` invariant enforced.
- Google OAuth: login + calendar sync (`THERAPY_GOOGLE_CLIENT_ID`, `_SECRET`).
- Supabase: Auth, database, storage, RLS.
