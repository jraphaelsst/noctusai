# PROMPT — Online Therapy Platform (codename: "Psicomatch")

> **WARNING:** "Psicomatch" is a placeholder name. Do NOT hardcode it anywhere that would require refactoring later (domains, env vars, DB names, UI copy). Use a single central config constant (e.g., `APP_NAME`) so the name can be changed in one place.

> **LANGUAGE:** This prompt is written in English for clarity and compatibility with AI tooling. However, **the platform itself must be entirely in Brazilian Portuguese (pt-BR).** All user-facing text — UI labels, buttons, placeholders, error messages, email templates, notifications, landing page copy, CTAs, tooltips, and any other text the user sees — must be in Portuguese. Code-level artifacts (variable names, comments, commit messages, API documentation) can remain in English. **Note:** throughout this spec, UI element labels are written in English for readability (e.g., "Start Session", "End Session", "Book a Session"). When implementing, translate these to their Portuguese equivalents (e.g., "Iniciar Sessão", "Encerrar Sessão", "Agendar Sessão"). Use a centralized translation file/system so all labels are in one place.

---

## 0. GOLDEN RULE — ASK BEFORE YOU CODE

**You MUST NOT begin any implementation until the specification phase is complete.**

Your mandatory workflow is:

1. **Read** every section of this spec carefully.
2. **Identify gaps, ambiguities, or technical decisions** that need my input.
3. **Ask ALL necessary questions** in an organized way — grouped by domain (architecture, business logic, UX, integrations, infrastructure).
4. **Wait for my answers.** If needed, run additional rounds of questions until we both agree the specs are complete.
5. **Present an implementation plan** (phases, execution order, folder structure, confirmed stack) for my approval.
6. **Only then begin implementing**, phase by phase, validating with me at each delivery.

If at any point during implementation a decision arises that is not covered by the specs, **stop and ask** — do not assume.

---

## 1. PRODUCT OVERVIEW

A web SaaS platform connecting psychoanalysts/psychologists with patients, providing:

> **The platform is 100% online.** All sessions happen via video call. There are no in-person sessions, physical addresses, or location-based features.

- **Discovery:** Patients find therapists by profile, specialty, and availability.
- **Scheduling:** Internal calendar system with bidirectional Google Calendar sync.
- **Video sessions:** Native video calls with AI-powered transcription and summaries.
- **Clinical management:** Session journal, notes, history, automatic summaries, dual-track AI-powered longitudinal analysis (clinical for therapists, personal for patients).
- **Financial management:** In-app payments, configurable-fee payouts, digital wallet.
- **Messaging:** WhatsApp-like messaging system — any user can message any user. Platform support channel. Clinic oversight of therapist conversations. AI-ready architecture.
- **Admin panel:** Multi-tenant user management, global and per-therapist financials, support inbox.
- **Clinic support:** Clinics can onboard and manage their own therapists, with scoped data isolation via RLS and independent commission structures.

---

## 2. ROLES AND ACCESS LEVELS

### 2.1 Platform Administrator (top-level — "control panel")
- Full CRUD on all users (clinics, therapists, patients, admins).
- Approve/reject therapists (independent) and clinics for directory listing.
- Global financial management: view balances, transactions, commissions, payouts.
- **Platform commission (tax) configuration:**
  - Set the **global platform commission rate** (% of session price) — the default applied to all transactions.
  - Set a **per-clinic commission override** — a custom % that applies to all sessions within that clinic (unless a per-therapist override also exists).
  - Set a **per-therapist commission override** — a custom % for a specific therapist (highest priority, overrides both global and per-clinic rates).
- **Patient management and pricing:**
  - The platform admin can **assign platform-sourced patients** (independently registered) to a specific therapist or clinic. This is useful when the platform acts as a matchmaker/referral source.
  - When assigning a patient, the platform admin can **set a custom session price** for that specific patient-therapist pair. This platform-set per-patient price takes highest precedence in the price resolution chain.
  - The platform admin can also set per-patient prices for any platform-sourced patient without necessarily assigning them — e.g., subsidized rates, promotional pricing, social programs.
- Grant and revoke access periods for therapists and clinics.
- Analytics dashboard: usage metrics, revenue, sessions completed, etc.
- Platform-wide settings (APP_NAME, sender email address for all platform notifications, global API keys).
- **AI prompt configuration (core infrastructure level):** Define and version-control the system prompts that instruct all AI processing on the platform (transcription, base summaries, clinical summaries, longitudinal analyses, tag generation). This is a core-admin infrastructure setting, not exposed to product-level users.
- **Support inbox:** View and respond to all user and clinic support conversations from a centralized dashboard.
- **Messaging oversight:** Full access to ALL conversations across the platform for audit, moderation, and dispute resolution. Moderation inbox for message reports and user blocks.

### 2.2 Clinic (organizational account)
- A clinic is an organization that manages multiple therapists under its umbrella.
- **The clinic has its own dedicated view of the platform** — a self-contained dashboard that functions like a sub-platform. The clinic admin sees and manages only their own organization's data: their therapists, their patients, their financials, their settings. This is NOT just a filtered view of the platform admin panel — it is a purpose-built clinic workspace.
- Registration with business data (company name, CNPJ, responsible person, contact info).
- **Immediate access** to the clinic dashboard after registration, but the clinic and its therapists remain **invisible in the directory** until platform admin approval.
- Clinic admin can invite/register therapists who belong to that clinic.
- Full CRUD on their own therapists and patients — **scoped via Row-Level Security (RLS) policies** so a clinic can only see and manage its own data.
- **Clinic dashboard includes:**
  - Overview/home with key metrics (active therapists, total patients, upcoming sessions, revenue).
  - Therapist management: invite, view profiles, activate/deactivate, configure commission rates, set pricing policy and per-patient prices (when clinic controls pricing).
  - Patient management: view all clinic patients, assign to therapists, **access each patient's clinical longitudinal analysis** (Track 2 — AI-generated clinical overview, see Section 4.7.1). The clinic does NOT see the patient's personal longitudinal analysis (Track 1).
  - Financial management: revenue overview, per-therapist breakdowns, commission configuration, **voluntary transfers to therapists** (bonuses, advances, etc.), withdrawal requests.
  - Settings: branding, bank details, commission rates, pricing policies, notification email (receiving address).
- **Clinic-level financial management (platform-automated commissions):**
  - The clinic **defines the rules** but the **platform executes all payments.** The platform pays both the clinic and the therapist directly.
  1. Patient pays the full session amount to the platform.
  2. Platform deducts its commission fee (global or per-clinic override) from the gross amount.
  3. Platform uses the **clinic-defined commission** to calculate the clinic's share and the therapist's share from the remaining amount.
  4. Platform credits the **clinic's wallet** with the clinic's share AND the **therapist's wallet** with the therapist's share — simultaneously, in a single atomic transaction.
  5. **The clinic does NOT process session-based payouts to therapists** — the platform automates that entirely based on the commission rules. However, the clinic **can hold money** in its wallet and **voluntarily transfer funds** to its therapists' wallets at any time (e.g., bonuses, advances, expense reimbursements, or any discretionary payment).
- **Clinic money movement capabilities:**
  - Transfer funds from the clinic wallet to any affiliated therapist's wallet (with amount, reason/description, and optional reference).
  - View transfer history (outgoing transfers to therapists).
  - Withdraw funds to the clinic's registered bank account / PIX.
  - All clinic-initiated transfers are logged in `wallet_movements` and visible to the platform admin for audit.
  6. When either party requests a withdrawal (or on an automatic schedule), the platform processes the payout directly to each recipient's registered bank account / PIX.
- **Clinic commission on therapists (mirrors the platform's commission model):**
  - Just as the platform sets a commission % on clinics/therapists, the clinic sets a commission % on its therapists — determining how much of the post-platform-fee amount the clinic retains.
  - The clinic admin configures:
    - **Default clinic commission rate for `clinic_sourced` patients** — applies to all therapists unless overridden (e.g., clinic keeps 30% by default for patients the clinic brought in).
    - **Default clinic commission rate for `therapist_sourced` patients** — typically lower, since the therapist brought the patient (e.g., clinic keeps 10% by default).
    - **Per-therapist overrides for `clinic_sourced` patients** — a custom rate for a specific therapist that takes precedence over the clinic-sourced default (e.g., senior therapist negotiated a lower clinic take of 20%).
    - **Per-therapist overrides for `therapist_sourced` patients** — a custom rate for a specific therapist that takes precedence over the therapist-sourced default.
  - **Precedence (highest to lowest):** per-therapist override → clinic default rate (for the applicable patient origin).
  - Each `appointment` or patient-therapist relationship must track the **patient origin** (`clinic_sourced` | `therapist_sourced`) to apply the correct commission.
- **Session pricing model (clinic-level config):**
  - The clinic admin has a **pricing policy toggle** per therapist: `clinic_controls_pricing` or `therapist_controls_pricing`.
  - **If `clinic_controls_pricing`:** the clinic admin sets the session price for each therapist, and can further customize it **per patient** (e.g., therapist A charges R$200 by default, but patient X pays R$150 due to a negotiated rate). The therapist cannot override these prices.
  - **If `therapist_controls_pricing`:** the therapist sets their own default session price and can customize it **per patient** individually. The clinic can see the prices but does not control them.
  - In both modes, **per-patient pricing is supported.** There is always a therapist-level default price, and optional per-patient overrides. The per-patient price takes precedence when set.
  - The price displayed in the therapist directory and profile is the therapist's **default** price. If a per-patient price exists for the logged-in patient, it is shown instead once they access the booking flow.
- **Messaging** (as a business entity — clinic name + logo, not individual admin identity):
  - Message any user on the platform (therapists, patients, other clinics).
  - Platform support conversation for bug reports, inquiries, and feedback.
  - Shared organizational inbox — any clinic admin user can read and respond to all clinic conversations.
  - **Oversight:** Can view affiliated therapists' conversations (therapist ↔ patients, therapist ↔ others) for professional supervision. Cannot view patients' private conversations.
- Clinic has its own settings page: bank details / PIX for receiving the clinic's share of platform payouts, clinic commission rates (default + per-therapist overrides, differentiated by patient origin), per-therapist pricing policy, notification email (where the clinic receives platform notifications), branding.

### 2.3 Therapist (psychoanalyst or psychologist)
- A therapist can be **independent** (self-managed) or **clinic-affiliated** (managed by a clinic).
- **Regardless of affiliation, every therapist sees the same full-featured therapist workspace.** A clinic-affiliated therapist's dashboard looks and works exactly like an independent therapist's — same calendar, same session journal, same patient management, same settings. The difference is purely in data scope and financial flow, not in UI or capabilities.
  - **Independent therapist:** their workspace is their own. They manage everything directly with the platform.
  - **Clinic-affiliated therapist:** their workspace is scoped to the clinic's context. Their patients, sessions, and financials are visible to their clinic admin (via the clinic dashboard), but the therapist's day-to-day experience feels like their own standalone workspace — they are NOT navigating the clinic admin panel. They log in, see their dashboard, and work as if they were independent.
- Registration with professional data (CRP license number, therapeutic approach, specialties, bio, photo).
- **Independent therapists:** register directly on the platform. Immediate access to the therapist dashboard, but invisible in the directory until platform admin approval.
- **Clinic-affiliated therapists:** registered/invited by their clinic admin. Visibility depends on the clinic's approval status. Upon accepting the invite, they land in their own therapist workspace (not the clinic's admin panel).
- Internal calendar interface to define availability (recurring and one-off slots), with optional bidirectional Google Calendar sync for external event awareness and appointment mirroring.
- View and manage active patients.
- Per-patient session journal: **clinical summaries** (Track 2 — enriched with observations, versioned), observation history (chronological, ongoing), private notes. The therapist can also toggle to see the patient's base summary (Track 1) to understand the patient's perspective.
- **Per-patient clinical longitudinal analysis:** AI-generated comprehensive overview that synthesizes ALL clinical summaries (Track 2) and observation histories over time into a cohesive clinical narrative — accessible from the patient's profile page (see Section 4.7.1, Track 2). The patient does NOT see this — the patient has their own separate personal longitudinal analysis built from their own data.
- Personal financial management: paid session history, receivable balance, payout statements.
  - **Independent therapists:** balance = gross amount minus platform fee.
  - **Clinic-affiliated therapists:** balance = their share as calculated by the platform using the clinic-defined commission rates (which vary depending on patient origin — see 2.2). The therapist sees their net amount and the commission breakdown, but does NOT see the clinic's share, the clinic's total revenue, or other therapists' data. Payouts go directly from the platform to the therapist — not through the clinic.
- Settings page: bank details / PIX key for receiving payouts.
- Integration settings: OpenAI API key, Google connection (Calendar, etc.), notification email (where the therapist receives platform notifications).
- **Messaging:** Message any user on the platform (patients, other therapists, clinics) and platform support. WhatsApp-like interface with conversation management (archive, mute, block, report). If clinic-affiliated, the clinic admin can view the therapist's conversations for oversight.
- **Session pricing:**
  - **Independent therapists:** set their own default session price, and can customize it **per patient** (e.g., a standard rate of R$250 but a specific patient pays R$180).
  - **Clinic-affiliated therapists:** pricing depends on the clinic's policy for that therapist:
    - If `clinic_controls_pricing` → the therapist sees the prices set by the clinic (default + per-patient) but cannot change them.
    - If `therapist_controls_pricing` → the therapist sets their own default price and per-patient overrides, same as an independent therapist.
  - Per-patient pricing takes precedence over the default when set.

### 2.4 Patient (user who has booked/had a session)
- Registration with basic personal data. **No approval required** — patients gain immediate, full access upon registration (unlike therapists and clinics, which require platform admin approval).
- A patient can be **platform-sourced** (registered independently), **platform-assigned** (registered independently but assigned to a therapist/clinic by the platform admin), **clinic-sourced** (registered/assigned by a clinic), or **therapist-sourced** (brought in directly by a clinic-affiliated therapist).
- Browse and view available therapist profiles via the **therapist directory**, or browse **clinics** and explore their affiliated therapists via the **clinic directory** (filters: specialty, approach, price range, available times).
- Book sessions during therapist's available slots.
- **Personal calendar view:** Visual overview of all upcoming and past appointments (one-off and recurring), with optional Google Calendar sync to see external events alongside therapy sessions (see Section 4.7.2).
- Manage recurring schedules: cancel individual occurrences, skip sessions, end entire schedules directly (no approval needed). Request edits to day/time/frequency (requires therapist/clinic approval — schedule unchanged until approved).
- Access session history: **base summaries only** (Track 1 — transcript-derived, no therapist observations), key points (transcript-derived), and **personal session notes** (private journal entries — visible only to the patient). The patient does NOT see: clinical summaries (Track 2), therapist observations, therapist private notes, clinical longitudinal analysis, or any data enriched by therapist input.
- **Personal longitudinal analysis ("Minha Jornada"):** AI-generated overview of the patient's therapeutic journey built exclusively from their own data — base summaries (Track 1) + personal session notes. No clinical data included. See Section 4.7.1, Track 1.
- **Each user develops their own timeline independently.**
- Pay for sessions through the platform. The price shown at booking reflects the resolved per-patient price (which may be set by the platform admin, clinic admin, or therapist depending on context).
- **Leave a rating and review** for their therapist after completing at least one session (see Section 4.3.3).
- **Messaging:** Message any user on the platform (therapists, other patients, clinics) and platform support. WhatsApp-like interface with conversation management. Patient conversations are strictly private — only the patient can see their own conversations (therapists, clinics, and admins cannot view patient-to-patient or patient-to-non-affiliated-user conversations).
- **Constraint:** a patient can only have ONE active therapist at a time. To switch, they must end the current relationship first.

### 2.5 Visitor / Non-patient user
- Accesses the landing page and institutional info only.
- **Cannot browse the therapist or clinic directories** — these are private, available only to registered users.
- Clicking "Encontrar Terapeuta" or "Explorar Clínicas" on the landing page redirects to the **registration/login page**. After registering or logging in, the user is redirected to the intended directory.
- Can register (as patient, therapist, or clinic).

---

## 3. CORE FLOWS

### 3.1 Therapist registration and onboarding
> **Approval rule:** Only therapists and clinics require platform admin approval. Patients register freely with no verification step.

1. **Independent therapist:** visits landing page → clicks "Sou Terapeuta" → registration form (personal + professional data + documentation). Account created → access to therapist dashboard (functional but not visible in the directory). Platform admin receives notification → reviews → approves or rejects.
2. **Clinic-affiliated therapist:** clinic admin invites or registers the therapist from the clinic dashboard. Therapist receives invite → completes profile. Visibility follows the clinic's approval status.
3. If approved → therapist appears in the directory listing and can receive bookings.
4. If rejected → notified with reason and can resubmit.

### 3.2 Clinic registration and onboarding
1. Clinic admin visits landing page → clicks "Sou uma Clínica" → registration form (business data + documentation).
2. Account created → access to clinic dashboard (functional but not visible in the directory).
3. Clinic admin fills in profile info for the directory (description, tagline, specialties, logo).
4. Platform admin reviews → approves or rejects.
5. If approved → clinic appears in the **clinic directory** (visible to all registered users), and approved therapists within the clinic appear in both the clinic's page and the general therapist directory.
6. Clinic admin configures: default clinic commission rates (by patient origin), per-therapist commission overrides (if needed), per-therapist pricing policy (`clinic_controls` or `therapist_controls`), bank/PIX details.

### 3.3 Patient registration and booking
1. Patient registers → **immediately** accesses both the therapist directory and clinic directory (no approval step).
2. **Path A (therapist-first):** Browses the therapist directory → filters by criteria → views therapist profile → sees availability calendar → books.
3. **Path B (clinic-first):** Browses the clinic directory → selects a clinic → browses the clinic's therapists → selects a therapist → views profile → sees availability calendar → books.
4. Regardless of path, selects time slot → confirms booking → makes payment.
   - **Recurring option:** At booking time, the patient can **request a recurring schedule** (e.g., "same day and time every week"). This sends a request to the therapist (or clinic admin if clinic-controlled), who must approve it before it takes effect. The patient pays only for the first session at booking — recurring sessions are charged automatically as they occur (see Section 4.4.3).
5. System creates a video room with a **platform-generated meeting link** (e.g., `https://{APP_DOMAIN}/session/{uuid}`) → notifies both parties by email with link and instructions. If Google Calendar is connected, a calendar event is also created with the meeting link in the description (no Google Meet link).
6. **Video room rules (access window):**
   - Room becomes accessible **N minutes before** the scheduled start time (default: 15 min — configurable by platform admin).
   - Room remains active until **M minutes after** the scheduled end time (default: 45 min — configurable by platform admin). **This is also the hard boundary for pause/resume** — if the session is paused and nobody returns before this time, the session auto-finalizes.
   - Both parties are informed of these rules at the time of booking.

### 3.4 Video session (therapist-controlled lifecycle with pause/resume)
1. Within the access window, the **therapist** enters the room first and sees a **"Start Session" button**. The room is in a "waiting" state.
2. The **patient** can access the room URL within the access window, but lands on a **waiting screen** ("Your therapist will start the session shortly") until the therapist clicks "Start Session".
3. Once the therapist clicks **"Start Session":**
   - The patient is admitted into the video call.
   - Audio recording begins server-side (after mandatory consent prompt to both parties).
   - A **temporary audio segment** is created — this will NOT be permanently stored.
4. Video call (via LiveKit). **Only audio is recorded, NOT video** (privacy requirement — confirmed).

5. **Session interruption → automatic PAUSE (not end):**
   - If either party **disconnects** (browser closed, internet drops, tab closed, device crash), the session is **automatically paused**, NOT ended.
   - **On pause:**
     - The current audio recording segment is stopped and saved server-side as a completed segment.
     - The remaining connected party sees a **"waiting for reconnection"** screen with a countdown showing the remaining time in the session's access window.
     - The system logs an **interruption event**: who disconnected, timestamp, reason (if detectable — e.g., network error vs. browser close).
   - **The session stays in `paused` state** — no AI pipeline is triggered, no summary is generated, no payment is captured. The session is NOT over.
   - **The session's resumability is bounded by the access window.** The room remains available for resuming until `scheduled_end + 45 minutes` (configurable) — the same hard boundary that governs the room's overall lifecycle. There is no separate pause timer; the access window IS the boundary.
   - **Example:** if a session is scheduled for 15:00–16:00, the room is accessible from 14:45 to 16:45. If the session pauses at 15:30, the therapist has until 16:45 to resume. The remaining access window time is the resume window.
   - **Waiting screen shows:** "Sessão pausada. Você tem até [16:45] para retomar a sessão." with a live countdown.

6. **Resume session (therapist-controlled):**
   - The **therapist** can return to the room at any time before the access window closes (`scheduled_end + 45 min`) and click **"Resume Session"**. This:
     - Reactivates the video call in the same room (same meeting link).
     - Starts a **new audio recording segment** (server-side).
     - If the patient is already in the room (reconnected and waiting), they're admitted immediately.
     - If the patient hasn't returned yet, the therapist sees a waiting screen. The patient receives a **notification** (in-app + email): "Your therapist has resumed the session. Click here to rejoin."
   - The system logs a **resume event**: who returned first, who was already present, timestamp.
   - **Multiple pause/resume cycles** are allowed within the access window. Each cycle creates a new audio segment. The session accumulates segments over time.
   - The **patient can also return** to the room during a pause, but lands on a waiting screen until the therapist clicks "Resume Session" — consistent with the therapist-controlled model.

7. **End Session (intentional — final and irreversible):**
   - The therapist clicks **"End Session"** to intentionally conclude the session. This is the ONLY action that triggers the AI pipeline and payment capture. Pauses and disconnections do NOT trigger it.
   - **An intentionally ended session CANNOT be reopened.** The therapist made a deliberate choice to end. The reopen feature is reserved exclusively for problem cases (auto-finalized sessions — see step 8b).
   - **When the therapist clicks "End Session":**
     - The video call is terminated for both parties immediately.
     - **Both parties see a post-session popup simultaneously:**
       - The **patient** sees a **post-session notes popup** — personal reflections/journal entry. Optional. Private to the patient. NOT fed into AI.
       - The **therapist** sees a **post-session observation popup** — clinical observation. Optional but encouraged. First entry in the observation history.
     - **The AI processing pipeline is triggered after the therapist submits or dismisses their popup:**
       1. All audio segments from the session are transcribed (each segment separately via Whisper API). Segments are concatenated chronologically with `[Sessão pausada às HH:MM]` and `[Sessão retomada às HH:MM]` markers between them, forming the full combined transcript.
       2. Combined transcript + first therapist observation (if provided) → GPT generates both summary tracks (see Section 4.6).
       3. All data saved to database.
       4. **Once transcription and summaries are confirmed saved, ALL temporary audio segments are permanently deleted.** No reopen is possible — audio is gone.
     - Payment is captured at this point (pre-authorization → capture).
     - Both parties are notified (in-app + email) when the summary is ready.

8. **Automatic session finalization (fallback — timer expired while paused due to problems):**
   - If the session is paused (due to disconnection, internet drop, etc.) and **neither party returns** before the governing timer expires, the system **automatically finalizes the session.** The governing timer is:
     - The **access window** (`scheduled_end + 45 min`) — for the initial session.
     - The **reopen timer** (`last_reopened_at + 50 min`) — for a reopened session (see step 8b).
   - Auto-finalization process:
     - All accumulated audio segments are transcribed and concatenated (same as step 7).
     - AI pipeline runs with transcript only (no therapist observation — popup was never shown).
     - Summaries generated as `source: ai_auto_fallback`.
     - Payment is captured.
     - The therapist receives a notification: "Sua sessão foi finalizada automaticamente devido a problemas de conexão. Um resumo foi gerado a partir da gravação disponível. Adicione observações para enriquecer o resumo clínico."
     - The patient receives the standard "summary available" notification.
   - **If only the therapist returned but the patient didn't:** the therapist can still click "End Session" to intentionally finalize with their observation, even if the patient never rejoined — as long as the governing timer hasn't expired.
   - **If only the patient returned but the therapist didn't:** the patient sees a waiting screen. If the therapist never returns before the timer expires, the auto-finalization fallback kicks in.
   - **After auto-finalization, the "Reabrir Sessão" button becomes available** — see step 8b.

8b. **Reopen Session (recovery after problems only — 50-minute extension):**
   - The "Reabrir Sessão" button is available **ONLY after a session was auto-finalized** (step 8) — meaning the session ended because of a problem (disconnection, internet drop, technical failure) and neither party returned before the timer expired. **It is NEVER available after an intentional "End Session" click** (step 7).
   - **Purpose:** To recover from technical failures. If a therapist's or patient's internet dropped and the session was auto-finalized before they could return, the therapist can reopen the same room to finish the conversation — without creating a new appointment, losing existing data, or paying again.
   - **Reopen window: 50 minutes from the moment of reopening.** This is an independent timer that starts when the therapist clicks "Reabrir Sessão" — it does NOT depend on the original access window. If the access window has already closed (or is about to close), the reopen timer **overrides** it.
     - **Example:** Session scheduled 15:00–16:00. Access window closes at 16:45. Internet drops at 16:20, session auto-finalizes at 16:45. At 16:50, therapist clicks "Reabrir Sessão." The reopen timer gives 50 minutes from 16:50 → session can continue until 17:40, even though the original access window closed at 16:45.
   - **How long is the "Reabrir Sessão" button available?** The button appears on the session detail page immediately after auto-finalization and remains visible for a configurable period (default: 60 minutes after auto-finalization — configurable by platform admin). After this visibility window passes, the button disappears and the session is considered permanently finalized.
   - **When the therapist clicks "Reabrir Sessão":**
     1. The same video room (same meeting link) is reactivated with a new access boundary: `now() + 50 minutes`.
     2. The patient receives a **notification** (in-app + email): "Seu terapeuta reabriu a sessão após o problema de conexão. Clique aqui para retornar."
     3. A **new audio recording segment** begins server-side when both rejoin.
     4. The therapist can end the reopened session via "End Session" (intentional — this time it IS final, no further reopens after an intentional end) or it auto-finalizes when the 50-minute reopen timer expires (which would make it eligible for another reopen).
   - **AI processing for reopened sessions:**
     - When the reopened portion ends ("End Session" or reopen timer expiry), the new audio segment is transcribed.
     - The new transcript is **appended** to the original session's combined transcript in `session_records`, with a `[Sessão reaberta às HH:MM]` marker.
     - The AI pipeline **re-generates both summary tracks** using the full combined transcript (original segments + reopened segment) + any existing observations. This produces new summary versions that cover the entire session including the reopened portion.
     - Previous summary versions (generated before the reopen) are preserved as earlier versions — never overwritten.
   - **Audio lifecycle for reopened sessions:**
     - After auto-finalization, audio segments are retained (NOT deleted) until the reopen visibility window expires — in case the therapist reopens.
     - After a reopened session ends and new combined summaries are confirmed saved, ALL audio segments (original + reopened) are permanently deleted.
     - If the therapist never reopens and the visibility window expires, the audio from the auto-finalized session is deleted at that point.
   - **Constraints:**
     - Only the **therapist** can reopen the session — not the patient, clinic admin, or platform admin.
     - A session can be reopened **multiple times** if each reopening also ends via auto-finalization (problem persists). Each reopening resets the 50-minute timer. But once the therapist intentionally clicks "End Session" on a reopened session, it's final — no further reopens.
     - **No additional payment is charged** for the reopened time — it is included in the original session price. The reopen feature is for session recovery, not for extending sessions.
     - **The 50-minute reopen duration is configurable** by the platform admin.
   - **Pause/resume still works during a reopened session.** If a disconnection happens during the reopened portion, the session pauses as normal. The therapist can resume within the remaining reopen timer. If the reopen timer expires while paused, auto-finalization kicks in — and the reopen button becomes available again.

9. **Session interruption tracking:**
   - Every pause, resume, disconnection, and reconnection event is logged in `session_interruptions` with: event type, which participant, timestamp, duration of interruption.
   - This data is available to the therapist (in the session detail) and the platform admin (for support/audit).
   - The AI summary pipeline receives this metadata so it can annotate the transcript appropriately (e.g., noting interruptions in the summary context).

10. **Observation history (ongoing, post-session — therapist only):**
    - After the session is finalized, the therapist can **add new observations** or **edit/update existing observations** at any time. This creates a **chronological observation history** per session.
    - **Every time an observation is added, modified, or deleted, the AI automatically generates a new version of the clinical summary (Track 2).** Base summary (Track 1) is unaffected.
    - The previous summary version is preserved in a version history — no summary is ever overwritten or lost.

11. **Patient session notes (ongoing, post-session — patient only):**
    - After the initial popup, the patient can also **add or edit their personal notes** at any time from their session history.
    - Private therapeutic journal — visible only to the patient. NOT fed into AI.

12. Therapist can also add/edit private notes at any time (invisible to the patient). Separate from observations — not fed into AI.

### 3.5 Financial flow (fully platform-automated)

> **Core principle: the platform is the sole payment processor.** All money flows through the platform. The platform calculates every commission, credits every wallet, and disburses every payout. Clinics define the commission rules but never process session-based payments.

1. Patient books a session → for one-off sessions, payment is **pre-authorized** (held) at booking time. For recurring sessions, pre-authorization happens when the appointment enters the rolling window. In both cases, the **actual charge is captured when the session ends** (therapist clicks "End Session" or automatic fallback triggers). The charged amount is the **resolved session price** (see price resolution below).
2. **For independent therapists:**
   - Platform deducts its commission → credits the therapist's wallet with the net amount.
3. **For clinic-affiliated therapists (single atomic transaction):**
   - Platform deducts its commission (per-therapist override → per-clinic override → global rate, in precedence order) from the gross amount.
   - Platform applies the **clinic's commission** (based on patient origin, with per-therapist override if set) to the post-commission remainder:
     - `clinic_sourced` patient → per-therapist override for clinic_sourced (if set) → clinic default rate for clinic_sourced.
     - `therapist_sourced` patient → per-therapist override for therapist_sourced (if set) → clinic default rate for therapist_sourced.
     - `platform_assigned` patient → commission rate follows the patient origin tracking set at assignment time (**ask me if platform-assigned patients should have their own commission category or map to one of the existing ones**).
   - Platform credits the **clinic's wallet** with the clinic's share AND the **therapist's wallet** with the therapist's share — in the same transaction. Session-based payments never route through the clinic.
4. **Payouts (platform → bank accounts):**
   - All session-based payouts are processed directly by the platform to each recipient's registered bank account / PIX.
   - Therapists (independent or affiliated) can view their balance and request withdrawal — the platform pays them directly.
   - Clinics can view their balance and request withdrawal — the platform pays them directly.
   - Clinics do NOT process session-based payouts to their therapists — the platform does this automatically.
   - **However,** clinics can make **voluntary transfers** from their wallet to any affiliated therapist's wallet at any time (bonuses, advances, reimbursements, etc.). These are discretionary, not part of the automated session commission flow.
5. Platform admin can view all transactions globally, adjust fees, and manage all payouts.
6. **Platform commission (tax) precedence — highest to lowest:**
   1. Per-therapist override (set by platform admin for a specific therapist) → highest priority.
   2. Per-clinic override (set by platform admin for a specific clinic) → applies to all therapists in that clinic unless #1 exists.
   3. Global platform rate → fallback default.
7. **Clinic commission (on therapists) precedence — highest to lowest, per patient origin:**
   1. Per-therapist override for that patient origin (set by clinic admin) → highest priority.
   2. Clinic default rate for that patient origin → fallback.
   - Example: Clinic default for `clinic_sourced` = 30%. Therapist A has an override of 20% for `clinic_sourced`. When therapist A sees a clinic_sourced patient, the clinic takes 20% (override). All other therapists → clinic takes 30% (default).
   - This mirrors the platform's own hierarchical commission model, giving clinics the same flexibility at their level.
8. **Session price resolution — highest to lowest:**
   1. Platform-admin-set per-patient price (for platform-sourced/assigned patients) → highest priority.
   2. Clinic-admin-set or therapist-set per-patient price (from `patient_pricing`) → next.
   3. Clinic-set default price (if `clinic_controls_pricing` for that therapist) → next.
   4. Therapist's own default price (`therapist_profiles.default_session_price`) → fallback.
9. **"Digital wallet" model:**
   - Every entity that receives money has its own wallet on the platform: independent therapists, clinic-affiliated therapists, and clinics.
   - **All session-based wallet credits come directly from the platform** — including clinic-affiliated therapists' wallets. However, **clinics can also voluntarily transfer funds** from their wallet to their therapists' wallets for discretionary payments (bonuses, advances, etc.).
   - Payouts from wallets to bank accounts can be manual (recipient requests) or automatic on a schedule (configurable by platform admin).
   - Integrate with **Stripe Connect** for automatic payment splitting, marketplace model, and compliance. Alternatives for the Brazilian market (Asaas, Mercado Pago) can be considered later if Stripe's BR coverage is insufficient.
   - **Ask me about whether I want automatic or manual payouts.**
10. **Refund system (platform-exclusive, disabled by default):**
    - **The refund system is a platform-level feature** — only the platform admin controls refund decisions. Therapists and clinics do NOT participate in the refund workflow (they don't approve, deny, or process refunds). The platform is the sole monetary authority.
    - **Feature flag: refund system is DISABLED by default at launch.** The platform admin can enable/disable it at any time from the admin settings panel (see Section 4.10). When disabled:
      - The "Solicitar Reembolso" button is visible on the patient's transaction detail but **grayed out / disabled** with a tooltip: "Reembolsos não estão disponíveis no momento."
      - No refund requests can be submitted by patients.
      - The refund management dashboard is still visible to the platform admin (showing empty state) so they can enable the feature when ready.
    - **When ENABLED by the platform admin:**
      - After a session is completed and charged, the patient can **request a refund within N days** of the session date (N is configurable by platform admin, default: 7 days).
      - Refund requests are submitted by the patient through their session history or the "Solicitar Reembolso" button on the transaction detail, with a mandatory reason/explanation.
      - **Refund workflow (platform-only):**
        1. Patient submits refund request → request goes **directly to the platform admin** (NOT to the therapist or clinic).
        2. Platform admin reviews the request from the refund management dashboard → **approves or denies** with a reason.
        3. If **approved:** the full session amount is refunded to the patient's original payment method. The corresponding wallet credits are **reversed** — the therapist's wallet (and clinic's wallet, if applicable) is debited by the amounts they received. A `refund` entry is created in `wallet_movements` and `transactions`.
        4. If **denied:** the patient is notified with the reason. No further escalation — the platform admin's decision is final.
      - **After the configured refund window (default 7 days):** no refund is possible. The "Solicitar Reembolso" button is hidden/disabled for sessions older than the window.
      - **Late-cancellation charges** (less than 24h before session) are also eligible for refund requests when the feature is enabled, following the same platform-only workflow.
    - **Platform admin controls:**
      - Enable/disable refund feature (global toggle).
      - Configure refund window duration (days).
      - Refund management dashboard: all pending, approved, and denied requests with full transaction details.

---

## 4. DETAILED FEATURES

### 4.1 Landing page
- Hero section with value proposition.
- Sections: how it works, benefits, testimonials, FAQ.
- CTAs: "Encontrar Terapeuta" (→ if logged in: `/therapists` directory; if not: `/register` then redirect) / "Explorar Clínicas" (→ if logged in: `/clinics` directory; if not: `/register` then redirect) / "Sou Terapeuta" (→ therapist registration) / "Sou uma Clínica" (→ clinic registration).
- **Redirect logic:** all directory CTAs check authentication status. Unauthenticated users are sent to `/register` (or `/login`) with a `redirect_to` parameter so they land on the intended page after authentication.
- Footer with institutional links, contact, terms of use, privacy policy.
- Responsive design (mobile-first).
- **Do not use the name "Psicomatch" in decorative/hardcoded ways; use `APP_NAME` via config.**

### 4.2 Authentication
- Registration with email + password. **One account per email — UNIQUE constraint enforced at the database level.** If a user tries to register with an email that already exists, they are directed to login (not allowed to create a second account).
- Login with email + password.
- Google login (OAuth 2.0) — beyond authentication, links the Google account for:
  - Google Calendar integration (therapists: bidirectional sync for availability + appointment mirroring; patients: read external events on platform calendar + receive platform appointments on Google Calendar).
  - (Future) Google Sheets, Gmail.
- **Google ID is also UNIQUE** — one Google account can only be linked to one platform user.
- Password recovery via email.
- Session management with JWT + refresh token.
- Role assignment at registration (therapist, patient, clinic admin). Platform admin created via seed or internal tooling.
- Route protection by access level (platform_admin / clinic_admin / therapist / patient). **All routes except landing page, login, and registration require authentication.** Therapist and clinic directories are accessible to any authenticated user (any role), but booking requires patient role.
- **Identity guarantee:** Whether a user registers via email or Google OAuth, they get exactly ONE `users.id`. This ID is the FK anchor across every table in the system. There is no scenario where the same person has two different IDs.

### 4.3 Discovery (therapists and clinics — authenticated users only)

The platform has **two directories** — one for therapists and one for clinics. **Both require authentication** — only registered and logged-in users can browse them. Non-authenticated visitors who click on directory CTAs are redirected to the registration/login page, then forwarded to the intended directory after authentication. Clinic-affiliated therapists appear in **both** the general therapist directory AND their clinic's dedicated page.

#### 4.3.1 Therapist directory (`/therapists`)
- **All approved therapists** are listed here — independent AND clinic-affiliated. This is the main discovery page.
- Listing card shows:
  - Photo, name, CRP number, approaches, specialties, **default price per session** (shown as "starting at" if per-patient pricing may differ).
  - Clinic badge/name (if affiliated — clickable, navigates to the clinic's profile page). Independent therapists show an "Independente" label or no badge.
  - **Average rating** (star rating, e.g., 4.7/5) and **total number of reviews**.
- Filters: specialty, approach, price range, available times, name search, clinic affiliation (dropdown: "All", "Independent only", or specific clinic name), **minimum rating**.
- **Sort options:** relevance (default), highest rated, most reviewed, lowest price, nearest availability.
- Individual therapist profile page (`/therapists/:id`) with:
  - Full bio, education, approach.
  - Clinic affiliation info (if applicable — with link to clinic's profile page).
  - Interactive availability calendar (internal calendar UI showing available slots — patient cannot see Google Calendar details or busy labels, only open vs. unavailable).
  - **Ratings and reviews section** (see 4.3.3).
  - "Book a Session" button.

#### 4.3.2 Clinic directory (`/clinics`)
- **All approved clinics** are listed here. This is a separate discovery entry point for patients who prefer to choose a clinic first, then browse its therapists.
- Listing card shows:
  - Clinic logo/photo, clinic name, description/tagline, specialties offered (aggregated from their therapists), number of active therapists.
  - **Two distinct ratings:**
    - **Clinic rating** — from clinic-specific reviews (patients reviewing the clinic as an organization). Shown as e.g., "4.5/5 (23 avaliações da clínica)".
    - **Therapist aggregate rating** — average of all affiliated therapists' individual ratings. Shown as e.g., "4.7/5 média entre 8 profissionais".
- Filters: specialties available, price range (min/max across therapists), minimum aggregate rating, name search.
- **Sort options:** relevance (default), highest rated, most therapists, name A-Z.
- **Clinic profile page** (`/clinics/:id`):
  - Clinic name, logo, full description/about, mission statement, specialties offered.
  - **Therapist roster** — a filtered version of the therapist directory showing ONLY therapists affiliated with this clinic. Same card format as the main therapist directory (photo, name, CRP, specialties, price, rating). Each card links to the therapist's individual profile page.
  - Filters within the clinic page: specialty, approach, price range, available times, minimum rating (same filters as the main directory, but pre-scoped to this clinic).
  - Aggregate clinic stats: total therapists, clinic review count + average rating, therapist aggregate average rating.
  - **Clinic reviews section** — paginated list of reviews specifically about the clinic (separate from individual therapist reviews).
  - **No direct booking on the clinic page** — the patient clicks a therapist card to go to the therapist's profile page, then books from there. The clinic page is for discovery/browsing and clinic-level reviews.

#### Cross-linking (all behind authentication):
- Therapist profile → clinic badge links to `/clinics/:id` (if affiliated).
- Clinic profile → each therapist card links to `/therapists/:id`.
- Therapist directory filter "clinic affiliation" → selecting a clinic redirects to `/clinics/:id`.
- Landing page CTAs "Encontrar Terapeuta" and "Explorar Clínicas" → check auth, redirect to login/register if needed, then to the directory.

#### 4.3.3 Ratings and reviews system

The platform supports reviews for **both therapists and clinics** — as separate review types.

##### Therapist reviews:
- **Who can review:** Only patients who have completed at least one session with the therapist. The system verifies this — no review without a completed `appointment` record.
- **When to prompt:** After a session is completed and the AI summary is available, the patient receives a gentle prompt (in-app + optional email) to leave a review. The prompt is non-intrusive and can be dismissed. The patient can also leave or edit a review at any time from the session history or therapist profile.
- **Review structure:**
  - **Star rating** (1–5 stars, required).
  - **Written review** (free text, optional, with a reasonable character limit — e.g., 1000 chars).
  - **Tags** (optional, from a predefined list): e.g., "Bom ouvinte", "Pontual", "Empático(a)", "Profissional", "Me ajudou a crescer", "Comunicação clara". These allow structured filtering without requiring long written reviews.
- **One review per patient-therapist pair.** The patient can update their review at any time (the previous version is overwritten — reviews are NOT versioned like summaries). The review reflects the overall relationship, not individual sessions.
- **Display:**
  - Therapist profile shows: average star rating, total review count, and a paginated list of reviews (newest first).
  - Each review shows: star rating, tags (if any), written text (if any), date, and the **patient's first name**. All reviews are attributed — there is no anonymous option.
  - Therapist directory listing shows: average rating and review count as a compact badge.

##### Clinic reviews:
- **Who can review:** Only patients who have completed at least one session with **any therapist affiliated with that clinic.** The review is about the clinic as an organization, not about a specific therapist.
- **No post-session prompt for clinic reviews.** Unlike therapist reviews, clinic reviews are NOT prompted after a session. Patients leave clinic reviews **only from the clinic's profile page** — voluntarily, when they feel ready to evaluate the clinic as a whole.
- **Review structure:** Same as therapist reviews — star rating (1–5, required), written review (optional, 1000 chars), tags (from a clinic-specific predefined list, e.g., "Bem organizada", "Bom atendimento", "Variedade de profissionais", "Recomendo").
- **One review per patient-clinic pair.** Updatable at any time. A patient who has seen multiple therapists within the same clinic still leaves only one clinic review.
- **Display:**
  - Clinic profile page shows: average star rating, total review count, paginated list of clinic reviews (newest first). This is separate from the individual therapist ratings also shown on the clinic page.
  - Clinic directory listing shows: clinic's own average rating and review count as a compact badge (distinct from the aggregate therapist rating).
  - **Two ratings visible on clinic cards:** "Clinic rating: 4.5/5 (23 reviews)" AND "Therapists: 4.7/5 avg across 8 professionals" — so patients can distinguish the organizational experience from individual therapist quality.

##### Moderation (applies to both therapist and clinic reviews):
- Reviews are published immediately (no pre-approval by therapist, clinic, or admin).
- Therapists can **flag** therapist reviews; clinic admins can **flag** clinic reviews. Flagged reviews remain visible until the platform admin takes action.
- Platform admin can: view flagged reviews, hide/remove reviews that violate guidelines, and see review analytics across both review types.
- Reviews cannot be edited or deleted by the therapist or clinic admin.

##### Visibility (applies to both therapist and clinic reviews):
- Visible to all registered users (accessible to any logged-in user).
- Therapist: sees all their own reviews with full patient name and details.
- Clinic admin: sees all clinic reviews + all reviews for affiliated therapists.
- Platform admin: sees all reviews across the platform.

### 4.4 Scheduling system (dual-channel: internal + Google Calendar sync)

The platform has its **own internal calendar and scheduling system** as the primary channel. Google Calendar is a **sync channel** — not the source of truth.

#### 4.4.1 Internal calendar (primary — source of truth)
- The platform has a built-in calendar UI (e.g., FullCalendar.js or similar) embedded in the therapist's workspace.
- **This is where all scheduling logic lives:** availability configuration, slot booking, conflict detection, appointment management, and **recurring appointment automation** (see 4.4.3).
- Therapist configures availability:
  - Recurring availability slots (e.g., every Tuesday, 2 PM–6 PM) — these define **when the therapist is generally available**, not specific patient appointments. Think of them as "office hours."
  - Block specific dates (vacations, holidays).
  - Default session duration (configurable, default 50 min).
- **Note:** Recurring availability slots (4.4.1) and recurring appointments (4.4.3) are different concepts. Availability slots define open windows. Recurring appointments lock a specific slot for a specific patient on a regular cadence.
- Patient sees only available (unbooked) slots on the therapist's profile.
- On booking:
  - Slot is blocked immediately in the internal system.
  - The platform generates a **unique meeting link** (e.g., `https://{APP_DOMAIN}/session/{uuid}`) — this is the video call room URL created by the platform, NOT a Google Meet link.
  - Confirmation email sent to both parties with the platform-generated meeting link + access rules.
- Cancellation / rescheduling:
  - **Free cancellation:** If cancelled **more than 24 hours before** the scheduled start time, the session is cancelled at no charge.
  - **Late cancellation (less than 24h before):** The patient is **charged the full session price** as a no-show/late-cancellation fee. The payment flow runs as if the session had occurred (platform commission + clinic commission deducted, wallets credited).
  - Email notification on cancellation (with charge/no-charge status clearly stated).
  - Cancelled appointments free the slot in both the internal calendar and Google Calendar.

#### 4.4.2 Google Calendar sync (secondary — two-way sync)
- If the therapist has connected their Google account (OAuth), the internal calendar **syncs bidirectionally** with Google Calendar:
- **Internal → Google Calendar (outbound):**
  - When an appointment is created on the platform, the system creates a corresponding Google Calendar event for both the therapist and the patient (if the patient also has Google connected).
  - The Google Calendar event includes: session title, date/time, participants (therapist + patient emails), and the **platform-generated meeting link in the event description** (NOT as a Google Meet conference link — the event must NOT auto-generate a Google Meet link).
  - When an appointment is cancelled/rescheduled on the platform, the Google Calendar event is updated/deleted accordingly.
- **Google Calendar → Internal (inbound):**
  - The internal calendar **reads** the therapist's Google Calendar to display external events (non-platform appointments, personal events) as **blocked/busy time** on the internal calendar UI. This prevents double-booking.
  - External Google Calendar events are displayed in a different color/style (e.g., grayed out) to distinguish them from platform appointments.
  - The platform does NOT modify or manage external Google Calendar events — it only reads them for availability awareness.
- **Conflict detection:** When a patient tries to book a slot, the system checks both the internal appointments AND the synced Google Calendar busy times to ensure no conflicts.
- **Graceful degradation:** If the therapist has NOT connected Google Calendar, the internal calendar works fully on its own — Google sync is optional, not required.
- **Patient-side Google Calendar sync:** covered in Section 4.7.2. The same bidirectional principles apply — outbound (platform appointments → patient's Google Calendar) and inbound (patient's external events → platform calendar as read-only busy time). The patient's sync is independent of the therapist's — each party connects their own Google account.

#### 4.4.3 Recurring appointments

Recurring appointments allow a therapist-patient pair to lock in a regular schedule (e.g., every Thursday at 3 PM) without rebooking each week. The system automates appointment creation, payment, and calendar sync for the entire recurrence.

##### Who can create recurring schedules:
- **Therapist** can create a recurring schedule for any active patient directly from their calendar or the patient's profile.
- **Clinic admin** can create a recurring schedule for any therapist-patient pair within the clinic.
- **Patient** can **request** a recurring schedule when booking a session (see Section 3.3). The request must be **approved by the therapist** (or clinic admin, if the clinic controls scheduling for that therapist) before it takes effect. The patient cannot unilaterally create a recurrence — only request one.

##### Recurrence configuration:
- **Frequency:** weekly (default), biweekly, or custom interval (e.g., every 3 weeks). **Ask me if monthly should also be supported.**
- **Day and time:** e.g., every Thursday at 15:00.
- **Duration:** inherits the therapist's default session duration (or per-patient override if set).
- **Start date:** the date from which the recurrence begins (can be immediate or future).
- **End condition (one of):**
  - No end date — continues indefinitely until manually stopped.
  - End after N occurrences (e.g., "8 sessions").
  - End on a specific date.
- **Exceptions:** individual occurrences can be skipped, rescheduled, or cancelled without affecting the rest of the series. Skipped sessions are not charged.

##### Automated appointment generation:
- The system **auto-generates individual appointments** for the next N upcoming occurrences on a rolling basis (e.g., always keep the next 4 weeks of appointments pre-created). This avoids generating hundreds of future appointments at once while ensuring upcoming sessions are always ready.
- Each auto-generated appointment follows the exact same flow as a manually booked appointment: video room pre-created, meeting link generated, Google Calendar event synced (if connected), and the resolved session price snapshot recorded at generation time.
- **Auto-generation runs as a background job** (e.g., daily cron) that checks all active recurring schedules and creates appointments for any uncovered upcoming slots within the rolling window.

##### Automated payment:
- **Payment is NOT charged in advance.** It is charged **when the session ends** — triggered by the therapist clicking "End Session" or by the automatic fallback (see Section 3.4). This applies to both one-off and recurring appointments.
- For recurring appointments, the patient must have a **saved payment method** on file. The system pre-authorizes (holds) the amount when the appointment enters the rolling window, but the actual capture happens at session end.
- **Cancellation policy for recurring appointments follows the same rules as one-off sessions:**
  - Cancelled **more than 24h before** → no charge, pre-authorization released.
  - Cancelled **less than 24h before** (or no-show) → full session price charged as a late-cancellation/no-show fee.
- If the saved payment method fails at capture time:
  - The transaction is marked `payment_failed`.
  - The patient receives a notification to update their payment method and settle the balance.
  - The therapist/clinic still receives the session summary and all clinical data — payment failure does NOT block the AI pipeline.
  - After N consecutive payment failures (configurable, e.g., 3), the recurring schedule is **automatically paused** and both parties are notified.

##### Conflict handling:
- Before auto-generating each appointment, the system checks for conflicts (internal calendar + Google Calendar busy times).
- If a conflict is detected:
  - The conflicting occurrence is **skipped** (not created).
  - Both parties are notified: "Your recurring session on [date] could not be scheduled due to a conflict. The next session on [future date] is unaffected."
  - The therapist can manually reschedule the skipped occurrence or let it pass.

##### Management UI:

**Therapist view:**
- In the calendar, recurring appointments are displayed with a **recurring icon/badge** (e.g., a loop/repeat symbol) to distinguish them from one-off appointments.
- Clicking a recurring appointment shows options: "Edit this occurrence only" / "Edit all future occurrences" / "Cancel this occurrence" / "Cancel all future occurrences" / "End recurring schedule."
- **Recurring schedules manager** — a dedicated section (accessible from calendar settings or patient profile) listing all active, paused, and ended recurring schedules with: patient name, day/time, frequency, start date, end condition, status, next upcoming session, total sessions completed.
- Therapist can **pause** a schedule (e.g., during vacation — no new appointments generated until unpaused) or **resume** it.
- Therapist can **modify** the schedule (change day, time, or frequency) — changes apply to all future occurrences only, past appointments are unaffected.

**Clinic admin view:**
- Same management capabilities as the therapist, but scoped to all therapist-patient pairs within the clinic.
- Can create, modify, pause, resume, or end recurring schedules for any affiliated therapist.
- Overview dashboard showing all active recurring schedules across the clinic.

**Patient view:**
- Patient can see their active recurring schedule(s) in their dashboard and calendar.
- **Patient CAN directly (cancellation only — no approval needed):**
  - **Cancel a single occurrence** — follows the standard cancellation policy (free if >24h before, charged if <24h).
  - **End the entire recurring schedule** — all future auto-generated appointments are cancelled (free if >24h before each), and no new appointments are generated. The therapist/clinic is notified immediately.
  - **Skip an occurrence** — marks a specific upcoming session as skipped (not charged, slot freed). The rest of the series continues normally. Must be done >24h before to avoid charge.
- **Patient CANNOT directly (edits require therapist/clinic approval):**
  - Change the day, time, frequency, or any other parameter of the recurrence. The patient can **request** these changes, which are sent to the therapist (or clinic admin) for review and approval. The schedule continues unchanged until the change is approved.
  - **Edit flow:** Patient submits a change request (e.g., "move from Thursday 3 PM to Friday 2 PM") → therapist/clinic receives notification → approves (schedule updated for all future occurrences) or denies (schedule remains unchanged, patient is notified with reason).
- **Summary: patients cancel, therapists/clinics edit.** This ensures patients have autonomy to stop sessions but cannot unilaterally disrupt the therapist's schedule.
  - Change the day, time, or frequency of the recurrence — these changes must be **requested** and approved by the therapist/clinic.
- Patient can see upcoming auto-generated appointments, their payment status (pre-authorized, captured, etc.), and recurring schedule details (frequency, next session, total sessions completed).
- Patient can manage their **saved payment method** for automatic recurring charges from Settings (see Section 4.10).

##### Google Calendar sync for recurring:
- Each individual auto-generated appointment creates its own Google Calendar event (NOT a Google Calendar recurring event). This keeps the platform as the source of truth and avoids sync complexity with Google's recurrence model.
- If an occurrence is skipped or cancelled, the corresponding Google Calendar event is removed.

### 4.5 Video call (platform-native)
- **Technology: LiveKit** (recommended) — an open-source, self-hostable WebRTC SFU (Selective Forwarding Unit) that supports video, audio, screen sharing, and **server-side audio recording** out of the box. Alternatives: Daily.co (managed, easier setup but vendor-locked) or 100ms (managed). **Ask me which one I prefer, but LiveKit is the recommended default because:**
  - Open-source and self-hostable (can run on the existing VPS or a dedicated server).
  - Built-in server-side recording (critical for the audio capture → transcription pipeline).
  - SDKs for React (frontend) and Node.js/Python (backend).
  - Room management API for creating/closing rooms programmatically.
  - SFU architecture handles poor network conditions better than pure P2P.
- **Room lifecycle:**
  - When an appointment is created, the platform **pre-creates a LiveKit room** (or equivalent) with a unique ID tied to the appointment.
  - The meeting link (`https://{APP_DOMAIN}/session/{uuid}`) resolves to the platform's video call interface, which connects to the LiveKit room.
  - **Access window (single hard boundary for the entire session lifecycle):**
    - Opens: `scheduled_start - N minutes` (default: 15 min, configurable by platform admin via `session_pre_access_minutes`).
    - Closes: `scheduled_end + M minutes` (default: 45 min, configurable by platform admin via `session_post_access_minutes`).
    - **This window governs everything:** initial entry, session start, pauses, resumes, and auto-finalization. If the session is still active or paused when the window closes, the system auto-finalizes.
    - Outside this window: page shows session info with a message indicating when the room will/was available.
- **Session lifecycle (pause/resume model — therapist-controlled):**
  - Therapist enters first → sees "Start Session" button.
  - Patient enters → sees waiting screen until therapist starts.
  - Therapist clicks "Start Session" → patient admitted, **server-side audio recording begins** (after consent).
  - **Disconnection = PAUSE (not end).** If either party disconnects, the session pauses automatically. Audio segment is saved. Remaining party sees "waiting for reconnection" with countdown to access window end. No AI pipeline triggers. No payment captured.
  - **Therapist clicks "Resume Session"** → room reactivates, new audio segment begins, patient notified/admitted. Must happen before access window closes.
  - Multiple pause/resume cycles allowed within the access window (`scheduled_end + 45 min`). Each cycle creates a new audio segment.
  - **Therapist clicks "End Session"** (the ONLY intentional way to end — **final and irreversible**, no reopen possible) → call terminated → both see post-session popups → all audio segments transcribed and concatenated → AI pipeline runs → payment captured → audio deleted.
  - **Fallback auto-finalization:** if paused and nobody returns before the access window closes (`scheduled_end + 45 min`), session auto-finalizes with AI pipeline on accumulated segments. **"Reabrir Sessão" button becomes available** — see Section 3.4, step 8b.
  - **"Reabrir Sessão"** (only after auto-finalization due to problems) → reopens the same room with a 50-minute independent timer (overrides access window). New audio segment recorded, appended to transcript, AI re-generates summaries.
- **Recording:**
  - **Only audio is recorded, NOT video** (privacy requirement — confirmed).
  - Recording is **server-side** (via LiveKit's recording API or equivalent), not client-side — this ensures reliability, avoids browser limitations, and simplifies the pipeline.
  - Audio is recorded per-segment (each Start→Pause and Resume→Pause/End cycle is a separate segment). Segments are concatenated during transcription.
  - All audio segments are temporary. After intentional "End Session": deleted immediately after summaries confirmed saved. After auto-finalization: retained until reopen visibility window expires (in case therapist reopens). See Section 4.6.
- Call interface:
  - Video + audio for both participants.
  - Controls: mute mic, toggle camera, share screen (optional), **"Start Session" (therapist only, pre-call)**, **"Resume Session" (therapist only, during pause)**, **"End Session" (therapist only, during active call)**. Either party can leave the call at any time — this triggers a pause, not an end.
  - Recording indicator (visible to both when audio is being recorded). Shows paused state during interruptions.
  - Side text chat (optional — **ask me**).
- Audio capture for transcription (mandatory consent from both parties before recording starts).

### 4.6 AI transcription, observations, and summary

#### 4.6.1 Initial summary generation (triggered by "End Session" or auto-finalization)
- **Primary trigger:** The therapist clicks "End Session" and then submits or dismisses the observation popup.
- **Fallback trigger (auto-finalization):** If the session is in `paused` state and neither party returns before the governing timer expires (access window for initial session, or reopen timer for reopened session), the system automatically finalizes and triggers the pipeline. The summary is generated from the accumulated transcript segments alone (no therapist observation). The therapist is notified and can add observations later. **After auto-finalization, the "Reabrir Sessão" button becomes available** (see Section 3.4, step 8b) — audio segments are retained until the reopen visibility window expires.
- **Guard:** The pipeline must check if a summary has already been generated for this session before running. If version 1 already exists (e.g., therapist clicked "End Session" and the fallback also fires due to a race condition), the duplicate run is skipped.
- **Inputs to the initial AI pipeline:**
  1. All audio segments from the session → transcription via Whisper API (or alternative — **ask which model I prefer**). Each segment is transcribed separately, then concatenated chronologically with `[Sessão pausada às HH:MM]` and `[Sessão retomada às HH:MM]` markers.
  2. Therapist's initial observation (optional text submitted via the popup — becomes the first entry in the observation history).
- **AI processing (GPT):**
  - The AI receives the full combined transcript (including any pause/resume segments) AND the current observation history (which at this point is either empty or contains one entry) as separate inputs.
  - **Deduplication rule:** The AI does NOT simply append or repeat observation content. It assesses whether each observation contains information, clinical insight, or context that is NOT already present in the transcript. If an observation adds new value (e.g., clinical impressions, non-verbal cues, contextual background the audio wouldn't capture), the AI weaves it into the summary naturally. If an observation is redundant with the transcript content, it is acknowledged but not duplicated.
  - The AI generates **two summary tracks simultaneously:**
    - **Track 1 (base — patient-facing):** Concise session summary from transcript only. No therapist observations included. Factual recap.
    - **Track 2 (clinical — therapist/clinic/admin-facing):** Enriched session summary from transcript + therapist observations (if any). Includes clinical interpretation and observation-derived insights. For sessions with pause/resume cycles, both tracks seamlessly cover the entire session including interruptions.
    - Both tracks include: key points and automatic thematic tags. Track 1 tags are transcript-derived only; Track 2 tags may include observation-derived themes.
- Results saved as **version 1 of each track** in the `session_summary_versions` table. The transcript (assembled from all audio segments with pause/resume markers) is saved in `session_records`.
- **The new clinical summary (Track 2) version triggers a new version of the clinical longitudinal analysis** (see 4.7.1, Track 2). **The new base summary (Track 1) version triggers a new version of the patient's personal longitudinal analysis** (see 4.7.1, Track 1). Each track's longitudinal is triggered independently by its own summary track.
- **Audio file lifecycle:**
  - Audio is captured **server-side** via LiveKit's recording API (or equivalent) as **multiple segments** — one per active call period (Start→Pause, Resume→Pause, Resume→End). Segments are stored temporarily in object storage (S3 / Supabase Storage).
  - **During a paused session:** all accumulated audio segments are retained. No deletion occurs while the session is paused and the access window is still open.
  - **After intentional "End Session":** once transcription and summaries are **confirmed persisted in the database**, ALL temporary audio segments are **permanently deleted**. No reopen is possible after an intentional end — audio retention is not needed.
  - **After auto-finalization (problem case):** audio segments are retained (NOT deleted) until the reopen visibility window expires (default: 60 minutes after auto-finalization). If the therapist reopens, new segments are added and all audio is retained until the reopened session ends and summaries are confirmed saved. If the therapist never reopens, audio is deleted when the visibility window expires.
  - No audio recordings are retained long-term. Only the text transcript (with pause/resume markers), observation history, summary versions, key points, and tags persist.

#### 4.6.2 Observation history (ongoing, post-session — strictly therapist/clinic/admin)
- The therapist can **add new observations, edit existing ones, or delete observations** at any time after the session — immediately after, or days/weeks/months later.
- Observations are stored as a **chronological history** (a list of timestamped entries), not a single text field. Each entry records:
  - The observation text.
  - Timestamp of creation.
  - Timestamp of last edit (if modified).
  - Whether it was the initial post-session observation or a later addition.
- The observation history serves as the therapist's evolving clinical record for that session — capturing insights that emerge over time as the therapist reflects, reviews notes, or learns new context from subsequent sessions.
- **Observation history is strictly private to the responsible therapist.** Only the therapist-of-session can see observations. **Clinic admins and platform admins do NOT see observations** (narrowed 2026-04-22 per `GRAVACAO_SESSOES_LEGAL.md` + `projects/compliance-audit-reconciliation/` Phase 3 — RLS migration 007 dropped both roles from clinical-content policies). **The patient NEVER sees observations — not the raw text, not any data derived from or enriched by observations.** This is a core privacy boundary.

#### 4.6.3 Dual-track summary system (base vs. clinical)

> **Core principle: each user builds their own timeline.** The patient sees only data derived from the session transcript and their own personal notes. The therapist sees data enriched by their clinical observations and private notes. Each party develops their perspective independently, with the AI serving each track separately.

The platform generates **two separate summary tracks** per session:

##### Track 1 — Base summary (patient-facing)
- Generated from the **transcript only** — no therapist observations are ever included.
- Created when the session ends (via "End Session" or auto-finalization). If the session had multiple pause/resume cycles, the base summary covers all segments.
- **The patient sees ONLY this track.** It provides a factual recap of what was discussed, without any clinical interpretation or therapist-added context.
- Versioned (never overwritten) — version 1 is generated at session end. Additional versions are NOT expected for Track 1 under normal circumstances (since it's transcript-only and the transcript is assembled once at session end). Observation changes do NOT trigger base summary regeneration.
- **Manual edits by the therapist on this track are NOT allowed** — the base summary is a neutral, transcript-derived record. If the therapist wants to add clinical interpretation, that belongs in Track 2.

##### Track 2 — Clinical summary (therapist/clinic/admin-facing)
- Generated from the **transcript + all therapist observations** — the enriched, clinically interpreted version.
- Created when the session ends (using transcript + initial observation if provided). Updated (new version) every time the observation history changes.
- **The patient NEVER sees this track.** It is a clinical tool for the therapist, clinic admin, and platform admin only.
- Versioned (never overwritten) — same rules as before (see below). Observation changes trigger new clinical summary versions.
- The therapist can manually edit clinical summary versions. Manual edits create a new version tagged as `source: manual_edit`.
- **This is the track that feeds into the clinical longitudinal analysis** (Section 4.7.1, Track 2).

##### Versioning rules (apply to both tracks independently):
- **Summaries are NEVER overwritten.** Every AI generation or manual edit creates a new version. Previous versions are permanently preserved.
- **Base summary (Track 1)** new version triggers: initial generation at session end (version 1 — covers all audio segments from the session, including pause/resume cycles). If the session is reopened, a new version is generated from the expanded combined transcript (original + reopened segments).
- **Clinical summary (Track 2)** new version triggers: initial generation at session end, observation added/edited/deleted, session reopened (re-generated from expanded transcript + observations).
- **Debounce / rate-limiting:** If the therapist makes multiple rapid observation edits, the system debounces clinical summary generation (30-second inactivity window). Base summary is unaffected by observation changes.
- **Display logic:**
  - **Patient** always sees the latest version of Track 1 (base summary). A "Resumo atualizado em [data]" indicator is visible. Patient has no awareness that Track 2 exists.
  - **Therapist** sees the latest version of Track 2 (clinical summary) by default, with the ability to browse the full clinical version history. The therapist can also view Track 1 (base summary) to see what the patient sees, but cannot edit it.
  - **Clinic admin** sees Track 2 for all affiliated therapists' sessions.
  - **Platform admin** can see both tracks for any session.

### 4.7 Session journal / history

> **Each user builds their own timeline.** The session journal is the same feature for all users, but each role sees a fundamentally different layer of data. No user can see another user's private layer.

- Chronological timeline of all sessions between a therapist and patient.

- **Therapist view per session (clinical layer):**
  - **Clinical summary** (Track 2) — latest AI-generated enriched summary and key points (editable — edits create a new version). This is the therapist's primary working document.
  - **Clinical summary version history** — expandable list of all past versions with timestamps, version numbers, and source labels (`ai_generated`, `ai_auto_fallback`, `manual_edit`). Therapist can compare versions to track how the clinical picture evolved as observations were added.
  - **Observation history** — chronological list of all observations with timestamps. Therapist can add new observations, edit or delete existing ones. Each change triggers a new clinical summary version (see 4.6.3).
  - **Private notes** (separate from observations — not fed into AI, not versioned). The therapist's personal scratch space.
  - **"Patient view" toggle** — the therapist can switch to see what the patient sees (Track 1 base summary + patient has no enriched data), to understand the patient's perspective. Read-only from this toggle.
  - Date, duration, tags.

- **Patient view per session (personal layer):**
  - **Base summary** (Track 1) — AI-generated summary from transcript only (read-only). A factual recap of the session without clinical interpretation.
  - "Resumo atualizado em [data]" indicator.
  - **Personal session notes** — the patient's own private reflections/journal entry for this session. Editable at any time. **Only the patient can see these.** NOT visible to therapist, clinic admin, or platform admin. This is the patient's private therapeutic journal.
  - Does NOT see: clinical summary (Track 2), observation history, clinical summary version history, therapist private notes, or any data enriched by therapist observations.
  - Date, duration, tags (same tags as Track 1 — transcript-derived only).

- **Clinic admin view per session:** Same as therapist view (clinical layer) for any session within the clinic. Can see Track 2 clinical summary, observation history, and version history for oversight purposes. Cannot see therapist private notes.

- **Platform admin view per session:** Can see both Track 1 and Track 2 for any session (for audit/support). Can see observation history and version histories. Cannot see therapist private notes unless required for dispute resolution.

- Search history by text, tags, or date — searches within the user's visible layer (patient searches Track 1 + personal notes; therapist searches Track 2 + observations + private notes).

### 4.7.1 Longitudinal analysis (dual-track — mirrors session summaries)

> **Same principle as session summaries: each user builds their own longitudinal timeline.** The therapist gets a clinical longitudinal analysis built from clinical data. The patient gets their own personal longitudinal analysis built from their own data. Neither sees the other's.

This is a **meta-level AI feature** that operates above individual session summaries, synthesizing the full history of a patient-therapist relationship into an evolving narrative. There are **two independent longitudinal analyses**, one per track.

#### Track 1 — Patient longitudinal analysis (patient-facing)

##### What it is:
- An AI-generated **personal therapeutic journey overview** built exclusively from the patient's own data — NO clinical input from the therapist.
- Displayed in the patient's session history / dashboard as a dedicated section: "Minha Jornada Terapêutica" (or similar).
- It answers the patient's questions: What themes keep coming up in my sessions? How have I progressed? What topics do I keep returning to? What breakthroughs have I had?
- Think of it as a **personal journal summary** — a reflection of the patient's experience over time, in their own perspective.

##### Inputs (patient data only — no clinical data):
- All **base summaries (Track 1)** for the patient-therapist pair: latest versions of transcript-derived summaries, key points, tags.
- All **patient session notes** (`patient_session_notes`) — the patient's private journal entries across sessions.
- Session metadata: dates, frequency, gaps between sessions.
- **Strictly excluded:** clinical summaries (Track 2), therapist observations, therapist private notes, any therapist-generated or therapist-enriched data.

##### AI processing:
- The AI synthesizes all patient inputs into a structured personal report with:
  - **Personal journey summary** — a cohesive narrative of the patient's therapeutic journey from their perspective.
  - **Recurring personal themes** — topics, emotions, or patterns that appear across the patient's base summaries and personal notes.
  - **Progress reflection** — milestones or shifts the patient may recognize from their own timeline.
  - **Ongoing topics** — themes that remain open or keep surfacing in sessions.
- The tone is **personal and reflective** (not clinical). The AI writes as if addressing the patient, helping them see their own growth and patterns.

##### Auto-regeneration (versioned):
- A new patient longitudinal version is generated whenever:
  - A new **base summary (Track 1)** version is created (i.e., after a completed session).
  - The patient adds or edits a **personal session note** (patient_session_notes).
- **Clinical summary (Track 2) changes do NOT trigger patient longitudinal regeneration.**
- Versioned — never overwritten. Patient can browse past versions.
- **Debounce:** 60-second inactivity window for note edits.

##### Access:
- **Patient:** Full access. This is their personal therapeutic journey document. Read-only (AI-generated). Visible in their dashboard / session history.
- **Therapist, clinic admin, platform admin:** Do NOT see the patient's longitudinal analysis. This is private to the patient — it contains their personal notes which are strictly patient-only.

##### UX:
- Displayed in the patient's dashboard as a prominent section or tab: "Minha Jornada" — separate from the session-by-session list.
- Shows latest version by default with "Versão N — gerado em [data] — baseado em N sessões" indicator.
- Version history browser available.
- If fewer than 2 completed sessions: placeholder message.

---

#### Track 2 — Clinical longitudinal analysis (therapist/clinic/admin-facing)

##### What it is:
- An AI-generated **comprehensive clinical case analysis** built from the therapist's clinical data — enriched summaries + observations.
- Displayed on the patient's profile page within the therapist's workspace.
- It answers clinical questions: What themes recur across sessions? How has the patient progressed over time? What patterns has the therapist observed? Are there unresolved topics that keep surfacing? What milestones or breakthroughs have occurred?
- Think of it as a **living clinical case study** that updates itself as new sessions happen and new observations are recorded.

##### Inputs (clinical track data only):
- All **clinical summaries (Track 2)** for the patient-therapist pair: latest versions of enriched summaries, key points, tags.
- All `session_observations` across all sessions (the full observation history, chronologically ordered).
- Session metadata: dates, frequency, gaps between sessions.
- Session interruption data (pause/resume events — for context).
- **Strictly excluded:** base summaries (Track 1), patient session notes, any patient-private data.

##### AI processing:
- The AI synthesizes all clinical inputs into a structured longitudinal report with:
  - **Overall clinical narrative** — a cohesive analysis of the patient's therapeutic journey from the therapist's clinical perspective.
  - **Recurring themes and patterns** — topics, emotions, or behavioral patterns that appear across multiple sessions.
  - **Progress timeline** — key milestones, breakthroughs, or shifts identified from the clinical history.
  - **Unresolved / ongoing topics** — themes that remain open or keep resurfacing.
  - **Observation-derived insights** — clinical patterns that emerge from the therapist's observation history that may not be visible in individual session summaries alone.
- **Deduplication and synthesis:** The AI does NOT simply concatenate clinical summaries. It synthesizes, identifies cross-session patterns, and produces a narrative that is more than the sum of its parts.

##### Auto-regeneration (versioned):
- A new clinical longitudinal version is generated whenever:
  - A new **clinical summary (Track 2)** version is created (i.e., after a completed session or observation change).
  - **Base summary (Track 1) and patient note changes do NOT trigger clinical longitudinal regeneration.**
- **Trigger chain example:** Session #5 completed → clinical summary (Track 2, v1) generated → new clinical longitudinal version. Later, therapist adds observation to session #3 → session #3 clinical summary (Track 2, v2) → another clinical longitudinal version. Meanwhile, the patient adds a personal note to session #3 → patient longitudinal gets a new version, but clinical longitudinal is unaffected.
- Versioned — never overwritten. Therapist and clinic admin can browse all past versions.
- **Debounce:** 60-second inactivity window.

##### Access:
- **Therapist:** Full access from the patient's profile page. Read-only (AI-generated), but can add a **longitudinal private note** — a free-form annotation NOT fed back into the AI.
- **Clinic admin:** Full access for affiliated therapists' patients — for clinical oversight.
- **Patient:** Does NOT see the clinical longitudinal analysis. **Period.** There is no simplified version, no filtered view, no future plan to expose it. The patient has their own longitudinal analysis (Track 1) for their own perspective.
- **Platform admin:** Can access for support/audit only.

##### UX:
- The patient's profile page (therapist view) has a prominent section/tab for the clinical longitudinal analysis, separate from the session journal.
- Shows latest version by default with "Versão N — gerado em [data] — baseado em N sessões" indicator.
- **Version history browser:** expandable list of all past versions.
- If fewer than 2 completed sessions: placeholder message.

### 4.7.2 Patient calendar view

Patients have their own **calendar overview** — a visual, read-friendly view of their therapy schedule that consolidates platform appointments and (optionally) their Google Calendar events.

#### Internal appointments (always shown):
- All upcoming appointments (one-off and recurring) are displayed on a calendar UI (monthly/weekly/agenda views).
- Recurring appointments are visually distinguished with a **recurring badge/icon**.
- Each appointment shows: therapist name, date/time, duration, meeting link, status (confirmed, payment pending, etc.).
- **Actions from the calendar:**
  - Click an appointment → view details (therapist, meeting link, price, cancellation policy).
  - Cancel a single appointment (follows 24h cancellation policy).
  - Skip a recurring occurrence (>24h before to avoid charge).
  - End an entire recurring schedule.
- Past appointments appear in a different style (grayed out / past color) with a link to the session journal entry (summary, key points, personal notes).

#### Google Calendar sync (optional — if patient connects Google):
- If the patient has connected their Google account (OAuth), their **external Google Calendar events** are displayed on the platform calendar as **busy/blocked time** (read-only, different color/style).
- This helps the patient see their full schedule in one place — therapy sessions alongside personal/work events — without leaving the platform.
- The platform does NOT create, modify, or delete the patient's external Google Calendar events.
- **Platform appointments are synced TO the patient's Google Calendar** (outbound): when the patient books a session (or a recurring appointment is auto-generated), a Google Calendar event is created with the platform meeting link in the description (no Google Meet link).
- **Graceful degradation:** If the patient has NOT connected Google Calendar, the platform calendar shows only platform appointments — no Google events. Google sync is optional.

#### Recurring schedule management (from calendar):
- The calendar provides a **"Meus Agendamentos Recorrentes"** section (or a dedicated tab/filter) showing all active, paused, and ended recurring schedules.
- Each schedule shows: therapist name, frequency, day/time, next session, total sessions completed, status.
- Actions: skip next occurrence, end schedule, **request changes** (day/time/frequency — sent to therapist/clinic for approval; schedule unchanged until approved).

### 4.8 Financial management

#### For therapists (independent or clinic-affiliated):
- Personal financial dashboard: available balance, total revenue, paid sessions, **active recurring schedules count**.
- Detailed statement: each transaction with date, patient, gross amount, platform fee, clinic commission (if applicable), net amount received. Recurring-generated transactions show a **recurring badge** and link to the parent schedule.
- For clinic-affiliated therapists: statement shows the full breakdown clearly — platform tax deducted, clinic commission deducted (with patient origin label and rate applied), resulting amount credited to the therapist's wallet. **Session-based payments come directly from the platform.** Additionally, the statement shows any **voluntary transfers received from the clinic** (bonuses, advances, etc.) as separate line items.
- Payout config: bank details (routing/account) or PIX key.
- Withdrawal request (or automatic payout on schedule).
- **Refund visibility (read-only):** If a refund is processed by the platform admin, the therapist sees it in their statement as a debit with the reason. Therapists do NOT approve, deny, or process refunds — the platform handles all refund decisions.

#### For clinic admins:
- Clinic financial dashboard: total revenue generated by the clinic's therapists, platform fee deducted, clinic's share of each transaction, total clinic balance.
- Per-therapist breakdown with patient origin tracking (clinic-sourced vs. therapist-sourced) and the corresponding commission rates applied.
- **Clinic commission configuration (mirrors the platform's commission model):**
  - Set default clinic commission rate for `clinic_sourced` patients (applies to all therapists unless overridden).
  - Set default clinic commission rate for `therapist_sourced` patients (applies to all therapists unless overridden).
  - Set per-therapist overrides for either patient origin — giving specific therapists a different rate than the clinic default (e.g., senior therapist, special agreement).
  - View a summary of all commission rates in effect: which therapists use the default, which have overrides.
- Clinic wallet balance and statements. **Note:** the clinic admin does NOT process session-based payouts to therapists — the platform handles those. But the clinic **can:**
  - **Transfer funds** from the clinic wallet to any affiliated therapist's wallet — for bonuses, advances, expense reimbursements, or any other discretionary reason. Each transfer requires an amount and a description/reason.
  - **View transfer history** — all outgoing transfers to therapists, with dates, amounts, recipients, and reasons.
  - **Request withdrawal** for the clinic's balance to the clinic's registered bank account / PIX (or automatic payout on schedule).
- **Refund visibility (read-only):** If a refund is processed by the platform admin for a session involving a clinic-affiliated therapist, the clinic sees it in their statement as a debit. Clinics do NOT approve, deny, or process refunds.

#### For platform admins:
- Global financial dashboard: total revenue, commissions collected, payouts to therapists (completed and pending), payouts to clinics (completed and pending).
- General ledger with filters by therapist, clinic, period, status, patient origin.
- **Commission (tax) management:**
  - Global commission rate configuration (default %).
  - Per-clinic commission overrides.
  - Per-therapist commission overrides.
- **Patient pricing management:**
  - Set per-patient session prices for platform-sourced and platform-assigned patients.
  - Assign platform-sourced patients to a specific therapist or clinic, with optional custom price at assignment time.
  - View and audit all per-patient price overrides across the platform.
- **Payout management:** The platform admin oversees all session-based payouts — to independent therapists, clinic-affiliated therapists, and clinics. All are direct platform-to-recipient disbursements. The admin can also **audit clinic-initiated voluntary transfers** (clinic→therapist wallet movements) for transparency.
- **Refund management (platform-exclusive):**
  - **Feature toggle:** Enable/disable the refund system globally. When disabled, patients see a grayed-out button; when enabled, patients can submit requests.
  - **Refund dashboard:** All pending, approved, and denied requests with full transaction details (patient, therapist, clinic, session date, amount, reason). Platform admin is the sole decision-maker — approve or deny with reason.
  - **Approved refunds** automatically reverse wallet credits for the therapist (and clinic if applicable), and process the refund to the patient's original payment method.
  - **Configuration:** Refund window duration (default: 7 days), feature enabled/disabled toggle.
- **"Digital wallet" model:** every entity that receives money (independent therapists, clinic-affiliated therapists, clinics) has a wallet. The platform funds all wallets directly based on commission calculations. Platform admin can view and audit all wallets.

#### For patients:
- Payment history: all transactions with date, therapist, amount, status (pre-authorized, captured, refunded, etc.).
- Saved payment methods management (add, remove, set default for recurring).
- **Refund requests (feature-flag controlled):**
  - **When refund feature is ENABLED:** "Solicitar Reembolso" button active on completed transactions within the refund window. Submit reason, track status (pending, approved, denied). Platform admin makes all decisions — no therapist/clinic involvement.
  - **When refund feature is DISABLED (default at launch):** "Solicitar Reembolso" button visible but **grayed out / disabled** with tooltip: "Reembolsos não estão disponíveis no momento." Patient sees the button exists but cannot interact with it.
- Upcoming recurring charges (pre-authorized amounts with session dates).

#### Payment gateway (Stripe Connect — default):
- **Stripe Connect** is the default payment gateway. It supports pre-authorization + capture, payment splitting (marketplace model), multi-party payouts, and refunds — all required by this platform.
- **Alternatives** (if Stripe's coverage for the Brazilian market proves insufficient): Asaas (BR-native), Mercado Pago, PagSeguro. The payment layer should be abstracted behind an interface so the gateway can be swapped without refactoring business logic.
- **Payment lifecycle:**
  1. **Pre-authorization (hold):** At booking time (one-off) or when the recurring appointment enters the rolling window — the amount is held on the patient's payment method but NOT charged yet.
  2. **Capture:** Triggered when the session ends (therapist clicks "End Session" or fallback auto-trigger). The held amount is captured and the platform calculates all commissions in a single atomic operation, crediting the appropriate wallets.
  3. **Late-cancellation charge:** If the patient cancels less than 24h before the session, the pre-authorized amount is captured as a late-cancellation fee and distributed normally.
  4. **Free cancellation release:** If cancelled more than 24h before, the pre-authorization is released (no charge).
  5. **Refund (when feature is enabled):** Within the configured window (default 7 days) of session completion, the platform admin can approve a refund to the patient's original payment method (see Section 3.5, item 10). When the feature is disabled, this step is blocked at the API level.
- Patient pays via credit/debit card, PIX, or bank slip (boleto). **Note:** pre-authorization may not be supported by all payment methods (e.g., PIX). For methods that don't support pre-auth, charge at session end directly — **ask me how to handle PIX-specific flow.**

### 4.9 Notifications
- **Email** (MVP priority):
  - Registration confirmation.
  - Therapist / clinic approval/rejection.
  - Booking confirmation (with room link + access rules).
  - **Session reminders (three-tier):**
    - **48 hours before:** Reminder with session details + explicit cancellation policy notice: "Cancelamento gratuito até 24h antes da sessão. Após esse prazo, o valor integral será cobrado."
    - **24 hours before:** Final free-cancellation window reminder: "Última chance para cancelar sem cobrança. A partir de agora, o cancelamento será cobrado integralmente."
    - **1 hour before:** Session starting soon reminder with meeting link + access rules.
  - Cancellation / reschedule (with charge/no-charge status clearly stated).
  - Recurring schedule approved (patient notification when therapist/clinic approves their recurrence request).
  - Recurring schedule paused / resumed / ended (both parties notified — including when patient ends the schedule directly).
  - Recurring occurrence skipped by patient (therapist notified — with reason if provided).
  - Recurring occurrence cancelled by patient (therapist notified — with charge/no-charge status based on 24h rule).
  - Recurring appointment auto-generated (both parties — upcoming session confirmation).
  - Recurring payment failed (patient — with instructions to update payment method).
  - Recurring schedule auto-paused (both parties — after N consecutive payment failures).
  - Recurring session skipped due to conflict (both parties — with next session date).
  - Refund request submitted (platform admin — patient submitted a refund request, review required).
  - Refund approved (patient — refund is being processed to original payment method).
  - Refund approved — wallet debit (therapist and/or clinic — notification that a refund was processed and the amount was debited from their wallet, with session details and reason).
  - Refund denied (patient — with reason. Platform admin's decision is final).
  - Session summary available (triggered after AI processing completes and audio is deleted).
  - Session summary auto-generated (therapist-only — triggered when auto-finalization generated a summary because the therapist didn't click "End Session" before the governing timer expired; includes a prompt to add observations to enrich the clinical summary).
  - Session paused — connection issue (both parties — notifies that the session was interrupted and can be resumed by the therapist).
  - Session resumed (patient notification — therapist has resumed the session, with rejoin link).
  - Session reopened (patient notification — therapist has reopened a finished session, with rejoin link and remaining time indication).
  - Session auto-finalized (therapist notification — access window or reopen timer closed while session was paused; summary generated from available segments).
  - Session summary updated (triggered after observation-driven re-generation — notify patient that an updated summary is available).
  - Payout processed.
  - Voluntary transfer received (for clinic-affiliated therapists — when the clinic sends a bonus/advance).
  - New review received (for therapists — when a patient leaves or updates a review).
  - Review prompt (for patients — after a completed session, gentle nudge to leave a review).
  - New message received (in-app badge immediately; email after configurable delay if still unread — e.g., 10 minutes).
- **Sender address:** All email notifications are sent FROM a single platform-level email address configured by the core platform admin (e.g., `noreply@{APP_DOMAIN}`). Clinics, therapists, and patients do NOT have their own sender addresses — all communication comes from the platform's identity. This is a core infrastructure setting (see Section 4.10, Platform Admin).
- (Future) push notifications, WhatsApp — **do not include in MVP unless I ask.**

### 4.10 Settings page

#### Platform Admin:
- APP_NAME and basic branding.
- **Platform commission (tax):**
  - Global commission rate (default %).
  - Per-clinic overrides (custom % per clinic).
  - Per-therapist overrides (custom % per therapist — highest priority).
- **Platform-level patient pricing:**
  - Per-patient price overrides for platform-sourced / platform-assigned patients.
  - Patient-to-therapist/clinic assignment interface with optional price setting.
- Global API keys (OpenAI, Google, Stripe).
- **Email infrastructure (core platform-level):**
  - Sender address (FROM email for all platform notifications, e.g., `noreply@{APP_DOMAIN}`).
  - Email service config (SMTP credentials OR API key for Resend / SendGrid).
  - All emails across the entire platform — to patients, therapists, clinics — are sent from this single sender identity. No user or organization has their own sender address.
- Cancellation policy: free cancellation cutoff (default: 24h before session — configurable). Refund request window (default: 7 days — configurable).
- **Refund feature management:**
  - **Global toggle:** Enable/disable the refund system across the entire platform. **Default: DISABLED.** When disabled, the "Solicitar Reembolso" button appears grayed out to patients. When enabled, patients can submit refund requests within the configured window.
  - **Refund window duration** (days — default: 7). Only configurable when the feature is enabled.
  - This toggle is an admin-level feature flag — changing it takes effect immediately across the platform.
- **Session access window timing:**
  - Pre-session access (default: 15 minutes before scheduled start — configurable).
  - Post-session access (default: 45 minutes after scheduled end — configurable). This is also the hard boundary for pause/resume — if a session is paused and nobody resumes before this time, the session auto-finalizes.
- **Session reopen settings (available only after auto-finalization due to problems):**
  - Reopen timer duration (default: 50 minutes from moment of reopen — configurable). This is the independent timer that overrides the access window when a therapist reopens an auto-finalized session.
  - Reopen button visibility window (default: 60 minutes after auto-finalization — configurable). After this period, the "Reabrir Sessão" button disappears and the session is permanently final. Audio segments are also deleted at this point.
- **AI prompt configuration (core-admin level — infrastructure, not product):**
  - This is a **core infrastructure setting** accessible ONLY to platform administrators. It is NOT exposed to therapists, clinics, or patients. It does NOT appear in any product-level settings page.
  - **Purpose:** The platform admin defines the system-level prompts/instructions that control how the AI processes session data. All AI-generated content on the platform (session summaries, longitudinal analyses, tag generation, etc.) follows these instructions.
  - **Configurable prompt fields:**
    - **Transcription instructions** — instructions passed to the Whisper API (or alternative) for transcription behavior (e.g., language hints, speaker diarization preferences, vocabulary biases for clinical terms).
    - **Base summary prompt (Track 1)** — the system prompt/instructions that tell GPT how to generate the patient-facing base summary from a transcript. Defines tone, structure, length, what to include/exclude.
    - **Clinical summary prompt (Track 2)** — the system prompt/instructions for generating the therapist-facing clinical summary from transcript + observations. Defines clinical depth, deduplication rules, how to weave observations, structure.
    - **Longitudinal analysis prompt (clinical — Track 2)** — the system prompt for generating the clinical cross-session longitudinal analysis from accumulated clinical summaries + observations.
    - **Longitudinal analysis prompt (patient — Track 1)** — the system prompt for generating the patient's personal journey longitudinal analysis from base summaries + patient session notes. Should use a reflective, personal tone (not clinical).
    - **Tag generation prompt** — instructions for generating thematic tags from transcripts and summaries.
  - **All prompts are stored in `platform_settings`** as key-value pairs (e.g., `ai_prompt_base_summary`, `ai_prompt_clinical_summary`, etc.) and injected into the AI pipeline at runtime.
  - **Version control:** When a prompt is updated, the previous version is preserved (timestamped). This allows the platform admin to see what prompt was active when a specific summary was generated, and to roll back if a prompt change produces poor results.
  - **This is a power-user feature.** The platform ships with sensible default prompts. The admin can customize them to adjust AI behavior (e.g., make summaries shorter, change clinical depth, add domain-specific instructions) without touching code.

#### Clinic Admin:
- Clinic profile (name, CNPJ, contact).
- Bank details / PIX key for receiving the clinic's share of platform-automated payouts.
- **Clinic commission rates (mirrors platform's model):**
  - Default rate for `clinic_sourced` patients.
  - Default rate for `therapist_sourced` patients.
  - Per-therapist overrides (for either patient origin) — takes precedence over defaults.
- **Per-therapist pricing policy toggle:** `clinic_controls_pricing` or `therapist_controls_pricing`.
- **If clinic controls pricing:** interface to set each therapist's default session price + per-patient price overrides.
- Notification email (the email address WHERE the clinic receives platform notifications — not a sender address).
- Therapist management (invite, activate, deactivate).

#### Therapist:
- Personal and professional data.
- Bank details / PIX key.
- Google Calendar connection (OAuth) — enables bidirectional sync: platform appointments appear on Google Calendar (with platform meeting link, no Google Meet), and external Google Calendar events show as busy time on the internal calendar.
- Personal OpenAI API key (if per-therapist model) **OR** use admin's global key.
- Notification email (the email address WHERE the therapist receives platform notifications — not a sender address).
- **Default session price** (editable if independent or if clinic policy is `therapist_controls_pricing`; read-only otherwise).
- **Per-patient price overrides** (same editability rules as default price).
- Default session duration.

#### Patient:
- Personal data (name, email, phone, profile photo).
- Google Calendar connection (OAuth) — enables: platform appointments synced to patient's Google Calendar (with platform meeting link), and external Google Calendar events displayed as busy time on the patient's platform calendar (see Section 4.7.2).
- Saved payment methods management (add, remove, set default for recurring appointments).
- Notification preferences.

### 4.11 Multi-tenant UX architecture (platform views)

The platform has **four distinct views**, each a self-contained experience tailored to the user's role. These are NOT just permission-filtered versions of a single panel — each is a purpose-built interface.

#### 1. Platform Admin view
- The god-mode control panel. Sees everything: all clinics, all therapists (independent + affiliated), all patients, all transactions.
- Manages approvals, global settings, commission overrides, platform-level payouts.
- **Support inbox:** Centralized view of all support conversations from users and clinics. Admins can respond, assign, and manage conversations.
- **Messaging oversight:** Can access ALL conversations across the platform for audit, moderation, and dispute resolution. Moderation inbox for reported messages and user blocks.
- This is the only view that can see cross-clinic and cross-therapist data simultaneously.

#### 2. Clinic Admin view
- A self-contained organizational workspace. The clinic admin sees ONLY their clinic's data.
- Feels like its own sub-platform: the clinic admin manages their therapists, their patients, their financials, their settings — as if the platform were built exclusively for their clinic.
- Cannot see other clinics' data, independent therapists' data, or platform-level financials.
- **Messaging inbox:** All clinic-entity conversations (shared organizational inbox) + **oversight access** to affiliated therapists' conversations. Messages sent as the clinic's business identity.
- **Platform support conversation** accessible from the messaging panel.
- Key sections: therapist roster (with commission rates, pricing policy, and per-patient pricing management), patient directory (with access to each patient's **clinical longitudinal analysis** — Track 2 only), financial dashboard (with per-therapist commission breakdowns and voluntary transfer management), messaging inbox, appointment overview, settings.

#### 3. Therapist view
- A personal workspace that is **identical in structure and features** whether the therapist is independent or clinic-affiliated.
- Independent therapist: data flows directly between them and the platform.
- Clinic-affiliated therapist: data is scoped to their clinic context, but the **UI is the same**. They do NOT see the clinic admin panel, other therapists' data, or clinic-level financials. They see their own patients, their own calendar, their own session history, their own earnings.
- Each patient has a **profile page** within the therapist's workspace containing: session journal (clinical track — Track 2 summaries, observation histories, version history), the **clinical longitudinal analysis** (Track 2), and a **"patient view" toggle** to see what the patient sees (Track 1 base summaries only). The therapist-of-session can also read the **patient's own session notes** — a product decision locked 2026-04-22 (Q1 of `projects/compliance-audit-reconciliation/`); encoded in RLS migration 007. The patient's personal longitudinal analyses remain patient-scoped (therapist access only if therapist_id matches the authoring therapist).
- **Messaging:** WhatsApp-like interface with all personal conversations (patients, other therapists, clinics, support). Conversation management (archive, mute, block, report). Accessible via persistent nav icon with unread badge.
- The therapist should never feel like they are "inside" the clinic's admin interface. They are in their own professional workspace that happens to be organizationally connected to a clinic.

#### 4. Patient view
- A consumer-facing experience: browse therapists (via therapist directory or clinic directory), book sessions, attend video calls, view session history, manage payments, leave ratings and reviews.
- **"Minha Jornada" (personal longitudinal analysis):** AI-generated overview of the patient's therapeutic journey built from their own data (base summaries + personal notes). No clinical data. Private to the patient.
- **Personal calendar:** Visual overview of upcoming therapy sessions (one-off + recurring) with optional Google Calendar overlay. Manage recurring schedules, cancel/skip sessions, see past appointments linked to session journal.
- **Messaging:** WhatsApp-like interface with all personal conversations (therapists, other patients, clinics, support). Strictly private — nobody else can see the patient's conversations. Accessible via persistent nav icon with unread badge.
- No awareness of the organizational layer or the therapist's clinical data — the patient sees only their own timeline.

**Implementation note:** These four views should be implemented as distinct layout shells / route groups (e.g., `/admin/*`, `/clinic/*`, `/therapist/*`, `/patient/*`), each with their own navigation, sidebar, and dashboard. Directory routes (`/therapists`, `/therapists/:id`, `/clinics`, `/clinics/:id`) **require authentication** — unauthenticated access redirects to `/register` or `/login` with a `redirect_to` parameter. The **only unauthenticated routes** are the landing page (`/`), registration (`/register`), and login (`/login`). Shared components (calendar, video call, session journal, **messaging panel**) are reused across views but wrapped in the appropriate layout context. RLS ensures data isolation at the database level, and middleware enforces route-level access control.

---

### 4.12 Messaging system (WhatsApp-like)

The platform has a **general-purpose messaging system** — a WhatsApp-like chat interface where any user can message any other user on the platform. This is NOT limited to therapist-patient relationships. It's a full communication layer for the entire platform.

The system is designed with **AI-controlled conversations in mind for the near future** — the architecture must support injecting an AI participant into any conversation thread without refactoring.

#### 4.12.1 Who can message whom

**Any authenticated user can start a conversation with any other authenticated user or entity.** The system supports the following participant combinations:

| From / To | Patient | Therapist | Clinic | Platform Support |
|---|---|---|---|---|
| **Patient** | ✅ Patient ↔ Patient | ✅ Patient ↔ Therapist | ✅ Patient ↔ Clinic | ✅ Patient ↔ Support |
| **Therapist** | ✅ Therapist ↔ Patient | ✅ Therapist ↔ Therapist | ✅ Therapist ↔ Clinic | ✅ Therapist ↔ Support |
| **Clinic** | ✅ Clinic ↔ Patient | ✅ Clinic ↔ Therapist | ✅ Clinic ↔ Clinic | ✅ Clinic ↔ Support |

- **All combinations are allowed.** A patient can message another patient. A therapist can message another therapist. A clinic can message another clinic. Everyone can message platform support.
- **How to find users to message:** Users can start a conversation from:
  - The therapist/clinic directory (message button on profiles).
  - Their own contact list (people they've interacted with — previous therapists, patients, etc.).
  - A **"New conversation"** search field where they can search for any user by name or email.
  - Contextual buttons throughout the platform (e.g., "Message this therapist" on a profile, "Message patient" from the therapist's patient list).

#### 4.12.2 Platform Support channel

- **Every authenticated user** (patient, therapist, clinic) has a dedicated **support conversation** with the platform.
- On the user's side, it looks like a chat with **"Suporte [APP_NAME]"** — always pinned at the top of their conversation list.
- On the platform admin side, all support conversations appear in a centralized **support inbox** where admins can view, respond, assign, and manage conversations.
- **Clinics** communicate with support as a business entity (clinic name + logo).
- This channel is for: bug reports, feature requests, billing questions, account issues, general inquiries.
- **Future AI integration:** This support channel is the primary candidate for AI-controlled responses. The architecture must support marking a conversation as `ai_managed` (AI responds automatically) vs. `human_managed` (admin responds manually) vs. `hybrid` (AI responds first, escalates to human if needed). For the MVP, all support conversations are `human_managed`.

#### 4.12.3 Conversation model

- Each conversation is a **persistent thread** between exactly two participants (a participant can be a user OR a clinic entity OR the platform support entity).
- Conversations are **created on first message** — no need to explicitly "start a conversation."
- Messages within a conversation are ordered chronologically with timestamps.
- **Message types (for future extensibility):**
  - `text` — plain text message (MVP).
  - `system` — system-generated messages (e.g., "Sessão agendada para [data]", "Resumo da sessão disponível", "Agendamento recorrente aprovado"). Auto-inserted by the platform on relevant events.
  - `ai` — AI-generated responses (future — not in MVP, but the schema must support this type from day one).
- **Read receipts:** Each participant tracks their last-read message, enabling unread count badges.
- **No group chats** in the MVP — all conversations are 1:1. Group functionality can be added later.

#### 4.12.4 Identity in conversations

- **Patients and therapists** message as themselves (their name and profile photo).
- **Clinics** message as the organization — the sender shows the clinic name and logo, NOT the individual clinic admin who typed the message. Internally, the system logs which admin user sent each message (for audit), but the other party only sees "Clínica [Name]."
- **Platform support** messages show "[APP_NAME] Suporte" with a platform logo/icon. Internally, each message is tied to the admin user who wrote it.

#### 4.12.5 Privacy and visibility rules

> **Core rule: each user sees ONLY their own conversations. Higher hierarchy levels can see downward — never upward, never sideways into private data.**

| Role | Can see their own conversations | Can see others' conversations |
|---|---|---|
| **Patient** | ✅ All their own conversations (with therapists, other patients, clinics, support) | ❌ Cannot see anyone else's conversations |
| **Therapist** | ✅ All their own conversations (with patients, other therapists, clinics, support) | ❌ Cannot see patients' conversations with other users. Cannot see other therapists' conversations. |
| **Clinic admin** | ✅ All clinic-entity conversations (clinic ↔ therapists, clinic ↔ patients, clinic ↔ other clinics, clinic ↔ support) | ✅ Can see **affiliated therapists' conversations** (therapist ↔ patients, therapist ↔ other therapists, therapist ↔ other clinics). ❌ Cannot see patients' private conversations (patient ↔ patient, patient ↔ non-affiliated therapist, patient ↔ support). |
| **Platform admin** | ✅ All support conversations (support inbox) | ✅ Can see **ALL conversations** across the entire platform (for audit, moderation, dispute resolution). |

- **RLS enforcement:** These visibility rules must be enforced at the database level via RLS policies, not just in the UI. A patient must not be able to access another user's conversation data via API.
- **Clinic visibility rationale:** Clinics can see their therapists' conversations for professional oversight (similar to a business monitoring employee communications on company channels). However, clinics CANNOT see patients' private conversations — only conversations where the therapist is a participant.

#### 4.12.6 UX (WhatsApp-like interface)

- **The messaging interface should feel like WhatsApp Web** — familiar, fast, and intuitive.
- **Layout:** Left sidebar with conversation list + right panel with active conversation.
- **Conversation list (left sidebar):**
  - All conversations sorted by most recent message (newest first).
  - **"Suporte [APP_NAME]"** always pinned at the top.
  - Each conversation shows: participant name/avatar (or clinic logo), last message preview (truncated), timestamp, unread badge count.
  - **Search bar** at the top to search conversations by participant name or message content.
  - **"New conversation" button** (➕) to start a conversation — opens a user search to find any user by name or email.
  - **Filters:** All, Unread, Patients, Therapists, Clinics, Support — to quickly filter conversation types.
- **Active conversation (right panel):**
  - Header: participant name/avatar, online status indicator, profile link.
  - Message area: scrollable, infinite scroll upward for older messages.
  - Each message: text content, timestamp, sent/delivered/read indicators.
  - **Message input:** Text field at the bottom with send button. Enter key sends, Shift+Enter for line breaks.
  - (Future: file attachments, voice messages — NOT in MVP but the UI should have placeholder/disabled icons for these).
- **Responsive / mobile:**
  - On mobile, the conversation list and active conversation are separate screens (tap conversation → full-screen chat, back button → list).
  - On desktop, side-by-side layout.
- **Accessible from every authenticated view** via a persistent chat icon/badge in the navigation bar.
- Clicking the icon opens the messaging panel (can be a sidebar overlay or a full page `/messages`).
- **Contextual entry points throughout the platform:**
  - "Enviar mensagem" button on therapist profiles, patient profiles, clinic profiles.
  - "Enviar mensagem" button in the therapist's patient list.
  - Quick-message icon on appointment cards and session journal entries.
  - Support link in the platform footer and help menu.
- **Notifications:** New messages trigger in-app badge updates immediately. Email notifications for unread messages follow a configurable delay (default: 10 minutes — if the message is still unread after the delay, an email is sent).

#### 4.12.7 Conversation management

- **Archive:** Users can archive conversations (moves to an "Archived" section, out of the main list). Archived conversations can be unarchived at any time. New messages in an archived conversation automatically unarchive it.
- **Mute:** Users can mute a conversation (disables notifications for that conversation — no badges, no emails — but messages still appear in the list).
- **Delete:** Users can delete a conversation from their view (soft-delete — the other participant still sees it). The messages are NOT deleted from the database — only hidden from the user's conversation list. Can be undone within 30 days.
- **Block:** Users can block another user. Blocked users cannot send new messages. Existing conversations are hidden. The blocked user does NOT receive a notification that they've been blocked — their messages simply show as "sent" but are never delivered. Platform admin can review and manage blocks.
- **Report:** Users can report a conversation or specific messages for abuse/harassment. Reports go to the platform admin's moderation inbox.

#### 4.12.8 AI-readiness (architecture requirements for future)

Although AI-controlled conversations are NOT in the MVP, the architecture **must be designed to support them without refactoring:**

- `conversations` table has a `mode` field: `human` (default, MVP) | `ai_managed` | `hybrid`.
- `messages` table has a `sender_type` field: `user` | `clinic_entity` | `platform_support` | `ai_agent` — the `ai_agent` type is defined but not used in the MVP.
- The message processing pipeline should be modular: incoming message → [middleware hook for AI interception] → deliver to recipient. In the MVP, the middleware hook is a no-op pass-through. In the future, it routes `ai_managed` conversations to an AI response generator before delivery.
- The support conversation should be the first to receive AI capabilities — the architecture should make it easy to flip a conversation's mode from `human` to `ai_managed` or `hybrid`.

---

### 4.13 UI pages, CRUD patterns, and component inventory

> **Every entity in the platform must have proper CRUD interfaces — listing pages, detail/individual pages, creation forms, edit forms, and delete/archive actions.** This section is a comprehensive inventory of all pages and UI components required. If an entity exists in the data model, it must have a corresponding UI for managing it. Do NOT implement backend-only entities with no frontend — every piece of data the user interacts with needs a proper interface.

#### 4.13.1 Global UI patterns (apply everywhere)

**Listing pages:**
- Every list of objects (therapists, patients, appointments, transactions, conversations, etc.) must have:
  - **Card or row layout** — each item rendered as a card (for visual entities like therapists/clinics) or a table row (for data-heavy lists like transactions).
  - **Pagination** (or infinite scroll for chat-like lists).
  - **Search bar** — filter by name, keyword, or relevant field.
  - **Filters** — contextual filter dropdowns/checkboxes (e.g., status, date range, type).
  - **Sort options** — at minimum: newest first, oldest first, alphabetical. Additional sorts where relevant (e.g., highest rated, lowest price).
  - **Empty state** — a friendly message when the list is empty (e.g., "Nenhum terapeuta encontrado" with a relevant CTA if applicable).
  - **Loading state** — skeleton loaders or spinners while data loads.
  - **Bulk actions** where applicable (e.g., select multiple → approve, archive, delete).

**Detail / individual pages:**
- Every entity that can be "opened" has a dedicated detail page (e.g., `/therapists/:id`, `/appointments/:id`, `/transactions/:id`).
- Detail pages include:
  - **Header** with key identifiers (name, avatar/logo, status badge).
  - **Tabs or sections** grouping related data (e.g., therapist profile → Profile | Calendar | Patients | Financials | Reviews).
  - **Action buttons** in a prominent location (top-right or header area): Edit, Delete/Archive, and entity-specific actions (e.g., Approve, Reject, Message, Book).
  - **Back button / breadcrumb navigation** to return to the listing page.

**Forms (create + edit):**
- All forms must have:
  - **Validation** — inline field errors in real-time + summary on submit.
  - **Required field indicators** (asterisk or similar).
  - **Save / Cancel buttons** — clearly labeled. Save shows a loading state while submitting.
  - **Confirmation modals** for destructive actions (delete, archive, revoke access).
  - **Autosave** for long forms where applicable (e.g., therapist profile editing) — or at minimum, a "You have unsaved changes" warning on navigation.

**Cards:**
- Cards are used for visual entities in listing pages and as summary widgets in dashboards.
- Each card shows: avatar/logo, primary label (name), secondary labels (role, specialty, etc.), key metric (rating, price, status), and an **action button** (View, Edit, Message, Book — context-dependent).
- Cards are **clickable** — clicking anywhere on the card navigates to the detail page. Action buttons are separate click targets that do NOT navigate.

**Status badges:**
- Color-coded badges for statuses throughout the platform:
  - Appointments: `Agendado` (blue), `Em andamento` (green), `Pausado` (yellow), `Concluído` (gray), `Cancelado` (red), `Faltou` (dark red).
  - Therapists/Clinics: `Pendente` (yellow), `Aprovado` (green), `Rejeitado` (red).
  - Transactions: `Pré-autorizado` (blue), `Capturado` (green), `Reembolsado` (orange), `Falhou` (red), `Liberado` (gray).
  - Recurring schedules: `Ativo` (green), `Pausado` (yellow), `Encerrado` (gray).
  - Refund requests: `Pendente` (yellow), `Aprovado` (green), `Negado` (red).

---

#### 4.13.2 Platform Admin pages

| Page | Route pattern | What it shows | Key actions |
|---|---|---|---|
| Dashboard | `/admin` | Key metrics (total users, revenue, sessions today, pending approvals, open support tickets) | Quick links to each section |
| Therapist list | `/admin/therapists` | All therapists (filterable by status: pending/approved/rejected, independent/affiliated) | Approve, Reject, View, Edit, Revoke access |
| Therapist detail | `/admin/therapists/:id` | Full profile, approval status, commission override, sessions, financials, reviews | Edit, Approve/Reject, Set commission override, Message |
| Clinic list | `/admin/clinics` | All clinics (filterable by status) | Approve, Reject, View, Edit |
| Clinic detail | `/admin/clinics/:id` | Clinic profile, affiliated therapists list, financials, reviews, commission override | Edit, Approve/Reject, Set commission override, View therapists |
| Patient list | `/admin/patients` | All patients (searchable, filterable) | View, Edit, Assign to therapist/clinic, Set per-patient price |
| Patient detail | `/admin/patients/:id` | Patient profile, current therapist, session history, transactions, messaging | Edit, Assign, Set price, Message |
| Appointment list | `/admin/appointments` | All appointments (filterable by status, date range, therapist, clinic) | View detail, Cancel |
| Appointment detail | `/admin/appointments/:id` | Full appointment data: participants, timing, status, payment, session record link | Cancel, View session record |
| Transaction list | `/admin/transactions` | All transactions (filterable by status, date, therapist, clinic, patient) | View detail, Process refund (if enabled) |
| Transaction detail | `/admin/transactions/:id` | Full breakdown: gross, platform fee, clinic commission, therapist share, status, gateway ref | Refund (if enabled) |
| Wallet overview | `/admin/wallets` | All wallets (therapists + clinics): balance, last movement | View movements, Process payout |
| Payout list | `/admin/payouts` | All payouts (filterable by status, recipient) | Process, View detail |
| Refund dashboard | `/admin/refunds` | All refund requests (filterable by status: pending/approved/denied) | Approve, Deny with reason |
| Commission settings | `/admin/settings/commissions` | Global rate, per-clinic overrides list, per-therapist overrides list | Edit global rate, Add/Edit/Remove overrides |
| AI prompt settings | `/admin/settings/ai-prompts` | All configurable AI prompts (transcription, base summary, clinical summary, longitudinal × 2, tags) with version history | Edit each prompt, View version history, Roll back |
| Platform settings | `/admin/settings` | APP_NAME, sender email, email service, access window timing, refund toggle + window, cancellation cutoff | Edit all settings |
| Support inbox | `/admin/support` | All support conversations, assignable to admin users | Respond, Assign, Close |
| Messaging moderation | `/admin/moderation` | Reported messages, user blocks, conversation audit | Review reports, Resolve, Remove content, Unblock |
| Review moderation | `/admin/reviews` | Flagged therapist and clinic reviews | Keep, Hide, Remove |

---

#### 4.13.3 Clinic Admin pages

| Page | Route pattern | What it shows | Key actions |
|---|---|---|---|
| Dashboard | `/clinic` | Clinic metrics (active therapists, total patients, upcoming sessions, revenue, pending items) | Quick links |
| Therapist roster | `/clinic/therapists` | List of affiliated therapists (card or table: name, CRP, status, commission rate, session count) | Invite new, View, Edit config, Activate/Deactivate |
| Therapist detail | `/clinic/therapists/:id` | Therapist profile, commission config (clinic-sourced / therapist-sourced rates), pricing policy, sessions, financials | Edit commission rates, Edit pricing policy, Set prices, Message |
| Invite therapist | `/clinic/therapists/invite` | Form to invite a new therapist (email, role info) | Send invite |
| Patient directory | `/clinic/patients` | All clinic patients (card or table: name, assigned therapist, session count, origin) | View, Assign to therapist, Access longitudinal analysis |
| Patient detail | `/clinic/patients/:id` | Patient profile, assigned therapist, session history, clinical longitudinal analysis (Track 2), pricing | View longitudinal, Set per-patient price, Message |
| Appointment list | `/clinic/appointments` | All appointments within the clinic (filterable) | View detail |
| Appointment detail | `/clinic/appointments/:id` | Full appointment data (within clinic scope) | View session record |
| Financial dashboard | `/clinic/financials` | Clinic revenue, platform fee, per-therapist breakdowns, wallet balance | View statements |
| Transaction list | `/clinic/financials/transactions` | Clinic transactions (filterable) | View detail |
| Wallet & transfers | `/clinic/financials/wallet` | Clinic wallet balance, transfer history, withdrawal history | Transfer to therapist, Request withdrawal |
| Transfer form | `/clinic/financials/wallet/transfer` | Form: select therapist, amount, reason | Submit transfer |
| Commission config | `/clinic/settings/commissions` | Default rates (clinic-sourced / therapist-sourced) + per-therapist override list | Edit defaults, Add/Edit/Remove overrides |
| Pricing management | `/clinic/settings/pricing` | Per-therapist pricing policy + per-patient price overrides | Toggle policy per therapist, Set prices |
| Clinic profile edit | `/clinic/settings/profile` | Clinic name, description, tagline, specialties, logo | Edit, Save |
| Clinic settings | `/clinic/settings` | Bank details/PIX, notification email, branding | Edit all |
| Messaging inbox | `/clinic/messages` | All clinic-entity conversations + therapist oversight | Send/read messages, View therapist conversations |
| Reviews | `/clinic/reviews` | Clinic reviews + affiliated therapists' reviews | View, Flag (clinic reviews) |

---

#### 4.13.4 Therapist pages

| Page | Route pattern | What it shows | Key actions |
|---|---|---|---|
| Dashboard | `/therapist` | Key metrics (active patients, upcoming sessions, revenue, unread messages, pending recurring requests) | Quick links |
| Calendar | `/therapist/calendar` | Internal calendar (FullCalendar) with availability slots, appointments (one-off + recurring with badge), Google Calendar busy times (if connected) | Add/edit/remove availability slots, View appointment detail, Block dates |
| Availability settings | `/therapist/calendar/availability` | Recurring availability config: day-of-week slots, blocked dates, session duration | Add slot, Edit slot, Remove slot, Block date range |
| Patient list | `/therapist/patients` | Active patients (card: name, origin badge, session count, last session date, next appointment) | View profile, Message, Create recurring schedule |
| Patient detail / profile | `/therapist/patients/:id` | **Tabbed layout:** Profile info | Session journal (Track 2) | Clinical longitudinal analysis | Recurring schedules | Pricing | Messaging | "Patient view" toggle (Track 1 read-only) | Add observation (any session), Add private note, View longitudinal versions, Message, Set per-patient price, Create/modify recurring |
| Session detail | `/therapist/sessions/:id` | Single session: clinical summary (Track 2, latest version + version history browser), observation history (CRUD: add, edit, delete observations), private notes, interruption log, audio segment info, **"Reabrir Sessão" button** (visible only after auto-finalization due to problems, within reopen visibility window) | Add/edit/delete observation, Add/edit private note, View version history, Toggle to patient's base summary (Track 1), Reopen session (only after auto-finalization) |
| Appointment list | `/therapist/appointments` | Upcoming and past appointments (filterable by status, patient, date) | View detail, Cancel (>24h), Join session room |
| Appointment detail | `/therapist/appointments/:id` | Appointment info: patient, timing, status, meeting link, payment status, recurring badge | Join room, Cancel, View session record |
| Recurring schedules | `/therapist/recurring` | All recurring schedules (active, paused, ended) with patient name, frequency, next session, total sessions | Create new, Pause, Resume, Modify, End, Approve/deny patient requests |
| Financial dashboard | `/therapist/financials` | Balance, total revenue, paid sessions, active recurring count | View statements |
| Transaction list | `/therapist/financials/transactions` | All transactions (filterable): date, patient, gross, fees, net, recurring badge | View detail |
| Payout/withdrawal | `/therapist/financials/withdraw` | Wallet balance, payout history, withdrawal request form | Request withdrawal |
| Profile edit | `/therapist/settings/profile` | Personal + professional data (name, CRP, bio, specialties, approaches, photo) | Edit, Save |
| Settings | `/therapist/settings` | Bank details/PIX, Google Calendar connection, OpenAI API key, notification email, default session price, session duration, per-patient price overrides | Edit all |
| Reviews | `/therapist/reviews` | All reviews received (list: rating, tags, text, patient name, date) | View, Flag for admin review |
| Messaging | `/therapist/messages` | WhatsApp-like messaging interface | All conversation management |

---

#### 4.13.5 Patient pages

| Page | Route pattern | What it shows | Key actions |
|---|---|---|---|
| Dashboard | `/patient` | Welcome, next upcoming session (with countdown + join link), active therapist card, unread messages badge, personal longitudinal ("Minha Jornada") teaser | Quick links to each section |
| Therapist directory | `/therapists` | Listing of all approved therapists (cards: photo, name, CRP, specialties, price, rating) + filters + sort | View profile, Book, Message |
| Therapist profile | `/therapists/:id` | Full therapist profile: bio, specialties, approach, availability calendar, reviews, clinic badge | Book session, Request recurring, Message, Leave review |
| Clinic directory | `/clinics` | Listing of all approved clinics (cards: logo, name, tagline, specialties, ratings) + filters + sort | View clinic page |
| Clinic profile | `/clinics/:id` | Clinic info + therapist roster (cards) + clinic reviews | View therapist, Leave clinic review |
| Calendar | `/patient/calendar` | Personal calendar: upcoming appointments (one-off + recurring with badge), past appointments (grayed), Google Calendar events (if connected, different color) | Cancel, Skip (recurring), End schedule, Request changes, View session detail |
| Recurring schedules | `/patient/recurring` | All recurring schedules (active, paused, ended): therapist name, frequency, next session, total sessions, status | Skip occurrence, End schedule, Request changes (→ therapist approval) |
| Session history | `/patient/sessions` | Chronological list of all completed sessions (cards: date, therapist, base summary preview, tags) | View session detail |
| Session detail | `/patient/sessions/:id` | Base summary (Track 1, read-only), key points, tags, "Resumo atualizado em [data]" indicator, **personal session notes** (editable) | Add/edit personal notes |
| Personal longitudinal ("Minha Jornada") | `/patient/journey` | AI-generated personal journey analysis (latest version + version history browser) | Browse versions |
| Payment history | `/patient/payments` | All transactions (cards/rows: date, therapist, amount, status) | View detail, Request refund (if enabled + within window) |
| Transaction detail | `/patient/payments/:id` | Transaction breakdown: amount, status, payment method, session link | Request refund (if enabled, button grayed out if disabled or outside window) |
| Payment methods | `/patient/settings/payment-methods` | Saved payment methods (list: card ending in XXXX, PIX, etc.) + default for recurring | Add, Remove, Set default |
| Profile edit | `/patient/settings/profile` | Personal data (name, email, phone, photo) | Edit, Save |
| Settings | `/patient/settings` | Google Calendar connection, notification preferences, payment methods | Edit all |
| Reviews (given) | `/patient/reviews` | Reviews the patient has left (therapist reviews + clinic reviews) | Edit, Delete own review |
| Messaging | `/patient/messages` | WhatsApp-like messaging interface | All conversation management |

---

#### 4.13.6 CRUD action buttons reference

Every entity with CRUD operations should have consistent, clearly labeled action buttons:

| Action | Button style | Requires confirmation? | Where it appears |
|---|---|---|---|
| **Create / Add** | Primary (filled, accent color) — e.g., "+ Novo Terapeuta", "+ Adicionar Observação" | No | Top of listing pages, within detail pages |
| **Edit** | Secondary (outline) — pencil icon or "Editar" | No | Detail page header, card hover/menu |
| **Delete / Remove** | Danger (red, outline) — trash icon or "Excluir" | ✅ Confirmation modal with reason field where applicable | Detail page header, card hover/menu |
| **Archive** | Neutral — "Arquivar" | ✅ Confirmation | Detail page, card menu |
| **Approve** | Success (green) — "Aprovar" | No (or lightweight confirmation for high-impact) | Admin listing rows, detail pages |
| **Reject** | Danger — "Rejeitar" | ✅ Confirmation modal with mandatory reason field | Admin listing rows, detail pages |
| **Save** | Primary — "Salvar" | No (loading spinner on click) | All forms |
| **Cancel** (form) | Ghost/link — "Cancelar" | ✅ If unsaved changes exist: "You have unsaved changes" warning | All forms |
| **Message** | Secondary — chat icon + "Enviar Mensagem" | No | Profile pages, patient/therapist cards |
| **Book** | Primary — "Agendar Sessão" | No (leads to booking flow) | Therapist profile page |

---

## 5. SUGGESTED STACK (VALIDATE WITH ME)

> **These are suggestions. Present trade-offs and ask me before deciding.**

| Layer | Suggestion | Alternative |
|---|---|---|
| Frontend | Next.js 14+ (App Router) + TypeScript + Tailwind CSS + shadcn/ui | — |
| Backend/API | Next.js API Routes (if monolith) OR FastAPI (Python) if separate backend preferred | — |
| Database | Supabase (PostgreSQL + Auth + Realtime + Storage) | Raw PostgreSQL + Prisma |
| Auth | Supabase Auth + Google OAuth | NextAuth.js |
| RLS | Supabase native RLS policies for clinic-scoped data isolation | Application-level middleware |
| Video calls | LiveKit (open-source, self-hostable WebRTC SFU with server-side recording) | Daily.co (managed), 100ms (managed) |
| Transcription | OpenAI Whisper API | Deepgram, AssemblyAI |
| AI summary | OpenAI GPT-4o | Claude API (Anthropic) |
| Calendar | FullCalendar.js (internal UI) + Google Calendar API (bidirectional sync) | — |
| Payments | Stripe Connect (default — marketplace model, pre-auth + capture, splits, refunds) | Asaas (BR-native), Mercado Pago |
| Email | Resend OR SendGrid | Nodemailer + SMTP |
| Realtime / Messaging | Supabase Realtime (WebSocket subscriptions for live message delivery + presence) | Socket.io, Pusher, Ably |
| Deploy | Vercel (frontend) + Railway/Fly.io (backend if separated) | Self-hosted VPS |
| Temp audio storage | Supabase Storage OR S3 (ephemeral — auto-delete after processing) | — |

---

## 6. DATA MODEL (INITIAL SKETCH)

> Expand this based on the specs. This is a starting point — **present the complete schema to me before implementing.**

### Single-identity architecture (critical)

> **Every person on the platform has exactly ONE `users.id`. There are no separate "patient IDs" or "therapist IDs" — there are only user IDs.** The `therapist_profiles` and `patient_profiles` tables are extensions of the `users` table, not independent identity systems. Every FK column named `patient_id`, `therapist_id`, `sender_user_id`, etc. is a **direct FK to `users.id`** — they are just semantically named for readability, but they all resolve to the same identity pool.

**Why this matters:**
- A patient who books with Therapist A and later books with Therapist B is the **same `users.id`** in both relationships. Session history, messaging, reviews, payments, and longitudinal analyses accumulate under a single identity.
- A therapist who is independent and later joins a clinic retains the **same `users.id`**. Their session history, patients, and reviews carry over.
- There must be **NO scenario** where the same physical person has two different IDs in the system. Email is the unique identifier at registration — `users.email` has a UNIQUE constraint.
- The `role` field on `users` determines what the person can do, not who they are. If a future need arises for a user to hold multiple roles (e.g., a therapist who is also a patient), the architecture should support it via a roles array or junction table — but for the MVP, each user has one role.

**Implementation rules:**
- `users.id` is a UUID (or Supabase's `auth.users.id` if using Supabase Auth).
- `therapist_profiles.user_id` FK → `users.id` (1:1 — one profile per user).
- `patient_profiles.user_id` FK → `users.id` (1:1 — one profile per user).
- **Every column named `patient_id`** in any table is a FK → `users.id` WHERE the user has `role = 'patient'` (or has a `patient_profiles` row). It is NOT a FK to `patient_profiles` — it points directly to `users.id`.
- **Every column named `therapist_id`** in any table is a FK → `users.id` WHERE the user has `role = 'therapist'`. Same principle.
- **Unique constraints that prevent duplicates:**
  - `users.email` — UNIQUE. One account per email.
  - `users.google_id` — UNIQUE (nullable). One Google account per user.
  - `therapist_profiles.user_id` — UNIQUE. One therapist profile per user.
  - `patient_profiles.user_id` — UNIQUE. One patient profile per user.
  - `reviews` — UNIQUE on `(patient_id, therapist_id)`. One review per patient-therapist pair.
  - `clinic_reviews` — UNIQUE on `(patient_id, clinic_id)`. One review per patient-clinic pair.
  - `recurring_schedules` — no duplicate active schedules for the same `(patient_id, therapist_id, day_of_week, start_time)`.
  - `conversation_participants` — UNIQUE on `(conversation_id, participant_id, participant_type)`. No duplicate participants in a conversation.
- **RLS policies must reference `auth.uid()` (the logged-in user's `users.id`)** — not any secondary ID. Every RLS policy resolves access by checking whether the requesting user's `users.id` matches the relevant FK in the row.
- **Cross-table joins always go through `users.id`:** When the system needs to find "all sessions for patient X", it queries `appointments WHERE patient_id = X`, where X is the user's `users.id`. When it needs "all conversations for user Y", it queries `conversation_participants WHERE participant_id = Y`. Same ID everywhere.
- **No orphaned profiles:** If a `users` row is deactivated, the corresponding `therapist_profiles` or `patient_profiles` row must also be deactivated (cascade or trigger). There must never be a profile without a parent user, or a user referenced by FKs that doesn't exist.

### Multi-tenancy and RLS strategy:
- Every table that contains clinic-scoped data must include a `clinic_id` column (nullable — NULL for independent therapists and platform-sourced patients).
- **RLS policies** must ensure that:
  - **All policies resolve identity via `auth.uid()` → `users.id`.** No secondary ID systems. The logged-in user's `users.id` is the sole identity anchor.
  - A clinic admin can only read/write rows where `clinic_id` matches their own clinic (determined by the admin's `users.id` → `clinic_admin` role → associated `clinics.id`).
  - A therapist can only read/write their own data (`therapist_id = auth.uid()`) and shared data for their patients. A therapist CANNOT access other therapists' data or patients' private data.
  - A patient can only read/write their own data (`patient_id = auth.uid()`). A patient CANNOT access other patients' data, therapist-private data, or clinical data (Track 2, observations, clinical longitudinal).
  - Platform admins bypass RLS (service role or admin policy).
  - **Clinic oversight exception:** Clinic admins can read (not write) rows belonging to their affiliated therapists for oversight purposes — specifically: therapist conversations (`visibility_clinic_id` match), session data (Track 2 summaries, observations), and clinical longitudinal analyses. This is the ONLY cross-user data access below platform admin level.
- Independent therapists have `clinic_id = NULL` and are governed by standard therapist-level policies.
- **FK integrity:** All `patient_id` and `therapist_id` columns are direct FKs to `users.id` with ON DELETE RESTRICT (prevent deletion of users with existing relationships). Deactivation (soft-delete via `is_active = false`) is the correct approach, not hard deletion.

### Core entities:
- `users` — **the single identity table for ALL users on the platform** (id UUID PK, email UNIQUE, password_hash, role: platform_admin|clinic_admin|therapist|patient, google_id UNIQUE nullable, created_at, updated_at, is_active boolean default true) — `id` is the universal identity anchor. EVERY `patient_id`, `therapist_id`, `sender_user_id`, `participant_id`, and similar FK across the entire schema points to `users.id`. There are no separate identity pools. `email` is the unique registration key — one account per email, period. `is_active = false` for deactivated accounts (soft-delete — never hard-delete users with existing relationships).
- `clinics` — clinic organizations (id, name, cnpj, responsible_person, contact_email, phone, logo_url, description text nullable, tagline text nullable, specialties_offered[] nullable, is_approved, approved_at, approved_by, created_at) — `description`, `tagline`, and `specialties_offered` are used for the clinic profile page and directory listing. `specialties_offered` can also be auto-aggregated from affiliated therapists' specialties. The platform is 100% online — no physical address fields.
- `clinic_settings` — per-clinic config (clinic_id, bank_name, bank_agency, bank_account, pix_key, notification_email_to, default_commission_pct_clinic_sourced, default_commission_pct_therapist_sourced) — `notification_email_to` is the email address where the clinic RECEIVES platform notifications (not a sender address — all emails are sent FROM the platform's sender address configured in `platform_settings`). Commission rates are the default rates the clinic takes from therapists, differentiated by patient origin.
- `platform_commission_overrides` — per-clinic and per-therapist platform tax overrides (id, target_type: clinic|therapist, target_id, custom_commission_pct, set_by_admin_id, created_at, updated_at) — when present, overrides the global commission rate for that specific clinic or therapist. Therapist-level overrides take precedence over clinic-level overrides.
- `therapist_profiles` — professional profile extension (user_id FK → users.id UNIQUE, clinic_id FK → clinics.id nullable, crp, bio, specialties[], approaches[], photo_url, default_session_price, session_duration, is_approved, approved_at, approved_by) — 1:1 with `users`. `user_id` IS the therapist's identity — when other tables reference `therapist_id`, they point to this same `users.id`.
- `clinic_therapist_config` — per-therapist config within a clinic (clinic_id, therapist_id, pricing_policy: clinic_controls|therapist_controls, commission_override_clinic_sourced nullable, commission_override_therapist_sourced nullable, clinic_set_default_price nullable) — `commission_override_*` fields override the clinic's default rates for this specific therapist. When NULL, the clinic's default from `clinic_settings` applies. Mirrors how `platform_commission_overrides` works at the platform level.
- `patient_pricing` — per-patient price overrides (id, therapist_id, patient_id, clinic_id nullable, custom_price, set_by: therapist|clinic_admin|platform_admin, created_at, updated_at) — when present, overrides the default price for that specific patient-therapist pair. Price resolution (highest to lowest): platform_admin-set patient_pricing → clinic_admin/therapist-set patient_pricing → clinic_set_default_price (if clinic controls) → therapist_profiles.default_session_price. Note: if multiple `patient_pricing` rows exist for the same patient-therapist pair (e.g., one set by platform_admin and one by clinic_admin), the `platform_admin` row takes precedence.
- `patient_profiles` — patient data extension (user_id FK → users.id UNIQUE, current_therapist_id FK → users.id nullable, origin: platform|platform_assigned|clinic|therapist, clinic_id FK → clinics.id nullable, assigned_by_admin_id FK → users.id nullable, assigned_at nullable) — 1:1 with `users`. `user_id` IS the patient's identity. `current_therapist_id` points to the therapist's `users.id`. A patient who sees multiple therapists over time retains the same `user_id` — session history and data accumulate under this single identity.
- `reviews` — patient reviews of therapists (id, patient_id FK, therapist_id FK, clinic_id FK nullable, star_rating int 1-5, review_text nullable, tags[] nullable, is_flagged boolean default false, flagged_by_therapist_id FK nullable, flagged_reason nullable, is_hidden boolean default false, hidden_by_admin_id FK nullable, created_at, updated_at) — one review per patient-therapist pair (UNIQUE constraint on patient_id + therapist_id). Patient can only create a review if they have at least one completed appointment with the therapist. Updates overwrite in place (not versioned). All reviews are attributed (patient's first name shown) — no anonymous option.
- `clinic_reviews` — patient reviews of clinics (id, patient_id FK, clinic_id FK, star_rating int 1-5, review_text nullable, tags[] nullable, is_flagged boolean default false, flagged_by_clinic_admin_id FK nullable, flagged_reason nullable, is_hidden boolean default false, hidden_by_admin_id FK nullable, created_at, updated_at) — one review per patient-clinic pair (UNIQUE constraint on patient_id + clinic_id). Patient can only create a clinic review if they have at least one completed appointment with any therapist affiliated with that clinic. Separate from therapist reviews — a patient can review both the therapist and the clinic independently.
- `availability_slots` — therapist availability slots (therapist_id, clinic_id nullable, day_of_week, start_time, end_time, is_recurring, specific_date, is_blocked)
- `recurring_schedules` — recurring appointment configurations (id, therapist_id FK, patient_id FK, clinic_id FK nullable, frequency: weekly|biweekly|custom, custom_interval_weeks int nullable, day_of_week int, start_time time, duration_minutes int, start_date date, end_condition: indefinite|after_n_occurrences|on_date, end_after_n int nullable, end_on_date date nullable, status: active|paused|ended, created_by_type: therapist|clinic_admin|patient_request, created_by_user_id FK, approved_by_user_id FK nullable, paused_at nullable, resumed_at nullable, ended_at nullable, created_at, updated_at) — defines the recurrence pattern. When `created_by_type: patient_request`, requires approval (`approved_by_user_id` is set when therapist/clinic approves). Individual appointments are auto-generated from this schedule on a rolling basis.
- `appointments` — bookings (id, therapist_id FK → users.id, patient_id FK → users.id, clinic_id FK → clinics.id nullable, recurring_schedule_id FK nullable, patient_origin: clinic_sourced|therapist_sourced|independent|platform_assigned, session_price_applied, platform_fee_pct_applied, clinic_commission_pct_applied nullable, scheduled_start, scheduled_end, status: waiting|in_progress|completed|cancelled|late_cancelled|no_show|payment_pending|payment_failed, video_room_id, meeting_link text, google_event_id nullable, payment_id nullable, is_auto_generated boolean default false, started_at, ended_at) — `therapist_id` and `patient_id` both point to `users.id` (same identity pool). `recurring_schedule_id` links to the parent recurring schedule (NULL for one-off). `session_price_applied`, `platform_fee_pct_applied`, and `clinic_commission_pct_applied` are resolved snapshots at generation time (immutable).
- `video_rooms` — video rooms (id, appointment_id, livekit_room_name text, room_token text nullable, meeting_url text, accessible_from timestamp, accessible_until timestamp, reopen_until timestamp nullable, reopen_count int default 0, reopen_button_visible_until timestamp nullable, status: pending|waiting|active|paused|closed|auto_finalized|reopened, total_pauses int default 0, therapist_joined_at, patient_joined_at, session_started_at, session_ended_at, last_paused_at nullable, last_resumed_at nullable, last_reopened_at nullable, auto_finalized_at nullable) — `accessible_from` = scheduled_start - N min. `accessible_until` = scheduled_end + M min. `status: closed` = therapist intentionally clicked "End Session" (final, no reopen). `status: auto_finalized` = access window or reopen timer expired while paused (problem case — eligible for reopen). `status: reopened` = session was auto-finalized and then reopened by therapist. `reopen_until` = `last_reopened_at + 50 min` (configurable). `reopen_button_visible_until` = `auto_finalized_at + 60 min` (configurable) — after this, audio is deleted and no reopen is possible. **Reopen is ONLY available when status = auto_finalized, NEVER when status = closed.**
- `session_audio_segments` — audio recording segments per session (id, video_room_id FK, segment_number int, segment_type: initial|resumed|reopened, audio_file_url text, started_at, ended_at nullable, transcription_text text nullable, is_transcribed boolean default false, created_at) — each "Start/Resume/Reopen Session" to "Pause/End Session" cycle creates a new segment. `segment_type` indicates whether the segment was from the initial session, a resume after pause, or a reopen after end. The full transcript is assembled by concatenating all segments' transcriptions in order with appropriate markers: `[Sessão pausada às HH:MM]` / `[Sessão retomada às HH:MM]` for pause/resume, `[Sessão reaberta às HH:MM]` for reopens. Audio files are deleted only after the reopen window has expired AND the combined transcript + summaries are confirmed saved.
- `session_interruptions` — interruption/lifecycle event log per session (id, video_room_id FK, event_type: pause|resume|disconnect|reconnect|reopen|end, participant_type: therapist|patient|system, participant_user_id FK nullable, reason text nullable, timestamp, interruption_duration_seconds int nullable) — logs every pause, resume, disconnection, reconnection, reopen, and end event. `event_type: reopen` = therapist reopened a finished session. `participant_type: system` for auto-finalization events. `interruption_duration_seconds` is calculated when the matching resume/reconnect occurs. Available to therapist (in session detail) and platform admin (for support/audit). Also passed to the AI pipeline as context metadata.
- `session_records` — post-session records (appointment_id, combined_transcript_text text, therapist_notes_private, total_segments int default 1, ai_generated_at, audio_deleted_at) — `combined_transcript_text` is the full assembled transcript from all audio segments (concatenated at session end with pause/resume markers). `total_segments` tracks how many audio segments contributed. Summaries live in `session_summary_versions`, not here.
- `session_summary_versions` — versioned AI summaries per session, dual-track (id, session_record_id FK, track: base|clinical, version_number int, summary text, key_points[], tags[], source: ai_generated|ai_auto_fallback|manual_edit, observation_snapshot_ids[] nullable, created_at) — every AI generation or manual edit creates a new row. `version_number` auto-increments **per track per session_record**. **Track `base`:** generated from transcript only, visible to patients. Version 1 created at session end (covers all audio segments). Observation changes do NOT affect this track. **Track `clinical`:** generated from transcript + observations, visible to therapist/clinic/admin only. Version 1 created at session end, new versions on observation changes. `observation_snapshot_ids` is only populated for clinical track versions. `source: ai_auto_fallback` applies to both tracks when auto-finalization generates them.
- `session_observations` — observation history per session (id, session_record_id FK, observation_text, is_initial boolean, created_at, updated_at, deleted_at nullable) — chronological list of therapist observations. `is_initial` = true for the observation submitted via the post-session popup. Soft-delete via `deleted_at`. **Strictly private: only visible to therapist, clinic admin (if affiliated), and platform admin. NEVER visible to the patient.** Every INSERT, UPDATE, or soft-DELETE on this table triggers automatic generation of a new `session_summary_versions` entry **on the clinical track only** — the base track is unaffected.
- `patient_session_notes` — patient's private journal entries per session (id, session_record_id FK, patient_id FK, note_text, created_at, updated_at) — the patient's personal reflections after a session. Strictly private: only the patient can read/write. NOT visible to therapists, clinic admins, or platform admins. NOT fed into any clinical AI pipeline (clinical summaries, clinical longitudinal analysis). **However, patient session notes DO feed into the patient's own personal longitudinal analysis (Track 1)** — this is the patient's private AI-generated journey overview. RLS must enforce patient-only access.
- `clinical_longitudinal_analyses` — versioned AI-generated clinical longitudinal analysis per patient-therapist pair (id, patient_id FK, therapist_id FK, clinic_id FK nullable, version_number int, narrative_summary text, recurring_themes[], progress_timeline[], unresolved_topics[], observation_insights text nullable, session_count_at_generation int, clinical_summary_version_ids[] nullable, created_at) — every generation creates a new version row. **Built exclusively from clinical track (Track 2) summary versions + observation data.** `clinical_summary_version_ids` records which clinical summary versions were used as input. **Visible to therapist and clinic admin only — NEVER to the patient.** The patient has their own separate longitudinal analysis (see below).
- `patient_longitudinal_analyses` — versioned AI-generated personal longitudinal analysis per patient-therapist pair (id, patient_id FK, therapist_id FK, version_number int, narrative_summary text, recurring_themes[], progress_reflection[], ongoing_topics[], session_count_at_generation int, base_summary_version_ids[] nullable, patient_note_ids[] nullable, created_at) — every generation creates a new version row. **Built exclusively from base track (Track 1) summary versions + patient session notes** — no clinical data. `base_summary_version_ids` records which base summary versions were used. `patient_note_ids` records which patient notes were included. **Visible ONLY to the patient** — therapists, clinic admins, and platform admins cannot see this (it contains patient's private notes). RLS must enforce patient-only access.
- `patient_longitudinal_notes` — therapist private annotations on the clinical longitudinal analysis (id, patient_id FK, therapist_id FK, longitudinal_analysis_id FK nullable, note_text, created_at, updated_at) — free-form notes NOT fed into AI. Linked to a specific clinical longitudinal version (optional) or general. Only for the clinical longitudinal — the patient's personal longitudinal has no external annotations.
- `transactions` — financials (id, appointment_id, patient_id, therapist_id, clinic_id nullable, patient_origin, gross_amount, platform_fee_pct, platform_fee_amount, clinic_commission_pct nullable, clinic_share_amount nullable, therapist_share_amount, status: pre_authorized|captured|refunded|failed|released, gateway_ref, pre_authorized_at nullable, captured_at nullable, refunded_at nullable) — `pre_authorized`: hold placed on payment method. `captured`: charged at session end. `refunded`: reversed by platform admin (only when refund feature is enabled). `failed`: capture or pre-auth failed. `released`: pre-auth released due to free cancellation (>24h). For clinic-affiliated sessions: `gross_amount - platform_fee_amount = post_platform_amount`, then `post_platform_amount * clinic_commission_pct = clinic_share_amount` and remainder = `therapist_share_amount`. Wallets are credited atomically at capture.
- `refund_requests` — patient refund requests (id, transaction_id FK, appointment_id FK, patient_id FK, therapist_id FK, clinic_id FK nullable, reason text, status: pending|approved|denied, reviewed_by_admin_id FK nullable, review_response text nullable, refund_amount, resolved_at nullable, created_at, updated_at) — patient can request within the configured refund window (default 7 days). **All review decisions are made exclusively by the platform admin** — therapists and clinics are NOT part of the refund workflow. They are notified of the outcome (wallet debit if approved) but have no input.
- `therapist_wallets` — digital wallet (therapist_id, balance, last_updated) — session-based credits come directly from the platform. May also receive voluntary transfers from the affiliated clinic.
- `clinic_wallets` — clinic digital wallet (clinic_id, balance, last_updated) — funded directly by the platform with the clinic's share. Clinic can hold funds and make voluntary transfers to affiliated therapists.
- `wallet_movements` — wallet ledger entries (wallet_id, wallet_type: therapist|clinic, type: credit|debit, amount, reference_type: session_commission|voluntary_transfer|withdrawal|refund, reference_id, description nullable, created_at)
- `clinic_transfers` — voluntary clinic-to-therapist transfers (id, clinic_id FK, therapist_id FK, amount, reason text, initiated_by_user_id FK, created_at) — discretionary transfers from clinic wallet to therapist wallet (bonuses, advances, reimbursements). Each transfer creates corresponding debit/credit entries in `wallet_movements` for both wallets. Balance validation: transfer fails if clinic wallet has insufficient funds.
- `payouts` — disbursements from platform to bank accounts (recipient_id, recipient_type: therapist|clinic, amount, status: pending|processing|completed|failed, bank_details_snapshot, requested_at, processed_at) — session-based payouts are all platform-to-recipient. Clinic voluntary transfers are internal wallet-to-wallet movements, not payouts.
- `platform_settings` — global config (key, value text — e.g., global_commission_rate, app_name, sender_email_from, email_service_provider, email_api_key, session_pre_access_minutes: 15, session_post_access_minutes: 45, session_reopen_duration_minutes: 50, session_reopen_button_visibility_minutes: 60, refund_enabled: false (default), refund_window_days: 7, cancellation_cutoff_hours, ai_prompt_transcription_instructions, ai_prompt_base_summary, ai_prompt_clinical_summary, ai_prompt_longitudinal_clinical, ai_prompt_longitudinal_patient, ai_prompt_tag_generation, etc.). `session_reopen_duration_minutes` = how long the reopened session can run (independent timer, overrides access window). `session_reopen_button_visibility_minutes` = how long after "End Session" the reopen button stays available. `refund_enabled` is a boolean feature flag. AI prompt keys store the full system prompt text used by the pipeline.
- `platform_settings_history` — version history for platform settings changes (id, setting_key, old_value text, new_value text, changed_by_admin_id FK, changed_at) — tracks every change to platform settings, especially AI prompts, so the admin can see what was active at any point in time and roll back if needed. When a summary is generated, the session_summary_versions row can reference the active prompt version via `changed_at` timestamp for audit traceability.
- `therapist_settings` — per-therapist config (therapist_id, bank_name, bank_agency, bank_account, pix_key, openai_api_key, google_connected, notification_email_to) — `notification_email_to` is the email address where the therapist RECEIVES platform notifications (not a sender address).
- `conversations` — messaging threads (id, mode: human|ai_managed|hybrid default 'human', created_at, updated_at, last_message_at, is_archived boolean default false) — no `type` field restriction — any user can message any other user. `mode` is for future AI integration (MVP: all are `human`). `is_archived` = true when user manually archives.
- `conversation_participants` — links participants to conversations (id, conversation_id FK, participant_type: user|clinic|platform_support, participant_id FK nullable, clinic_id FK nullable, visibility_clinic_id FK nullable, last_read_message_id FK nullable, is_muted boolean default false, is_deleted boolean default false, is_blocked boolean default false, created_at) — `participant_type: user` uses `participant_id` (user FK). `participant_type: clinic` uses `clinic_id`. `participant_type: platform_support` has both nullable. `visibility_clinic_id` = if the participant is a therapist affiliated with a clinic, this stores the clinic_id so the clinic admin can access this conversation for oversight (NULL for patients, independent therapists, and clinic-entity participants). `is_muted` / `is_deleted` / `is_blocked` are per-participant states — each participant manages their own view independently.
- `messages` — individual messages (id, conversation_id FK, sender_type: user|clinic_entity|platform_support|ai_agent, sender_user_id FK nullable, sender_clinic_id FK nullable, message_type: text|system|ai default 'text', content text, created_at, updated_at, deleted_at nullable) — `sender_type: clinic_entity` uses `sender_clinic_id` (the clinic as a business) but also records `sender_user_id` (which admin actually typed it — for internal audit only, not shown to recipients). `sender_type: ai_agent` reserved for future AI responses (not used in MVP). Soft-delete via `deleted_at`.
- `message_reports` — user reports of abusive/inappropriate messages (id, conversation_id FK, message_id FK nullable, reported_by_user_id FK, reason text, status: pending|reviewed|resolved, reviewed_by_admin_id FK nullable, resolution text nullable, created_at, resolved_at nullable) — reports go to the platform admin's moderation inbox.
- `user_blocks` — block list (id, blocker_user_id FK, blocked_user_id FK, created_at) — when a user blocks another, new messages from the blocked user are silently undelivered. Existing conversations are hidden from the blocker's list. Platform admin can review and manage blocks.

---

## 7. SUGGESTED IMPLEMENTATION PHASES

> **Present your own phased plan based on these specs and validate with me before starting.**

### Phase 1 — Foundation
- Project setup (repo, folder structure, configs, linting, env vars).
- Complete database schema + migrations + RLS policies. **Single-identity architecture: all FKs pointing to `users.id`, UNIQUE constraints on email/google_id, no orphaned profiles.**
- Authentication system (email + Google OAuth) with single-identity guarantee.
- RBAC (role-based access control) with middleware for all 4 roles.
- Platform settings infrastructure (key-value store with version history) including AI prompt configuration fields with sensible defaults.

### Phase 2 — Profiles, clinics, and discovery
- Therapist and patient profile CRUD.
- Clinic registration, profile (including directory-facing fields: description, tagline, specialties), and therapist invitation flow.
- Platform admin approval workflow (therapists + clinics).
- Therapist directory (`/therapists`) with filters — authenticated users only.
- Clinic directory (`/clinics`) with filters, linking to clinic profile pages with scoped therapist listings — authenticated users only.
- Auth-gate middleware: unauthenticated CTA clicks redirect to `/register` with `redirect_to` parameter.
- Individual therapist profile page and individual clinic profile page.
- Cross-linking between therapist profiles and clinic pages.
- Ratings and reviews system (submit, edit, flag, moderate, display on profile and directory).

### Phase 3 — Internal calendar, scheduling, and Google Calendar sync
- Internal calendar UI (FullCalendar.js or similar) embedded in therapist workspace.
- Therapist availability configuration (recurring slots, blocked dates, duration).
- Patient-facing availability view on therapist profile.
- Full booking flow with platform-generated meeting links and patient origin tracking.
- **Recurring appointments system:**
  - Recurring schedule CRUD (create, pause, resume, modify, end) for therapists and clinic admins.
  - Patient recurring request flow + therapist/clinic approval.
  - Auto-generation background job (rolling window of upcoming appointments).
  - Automated payment capture on generation + failure handling (retry, pause after N failures).
  - Conflict detection for recurring occurrences + skip/notify logic.
  - Recurring schedule management UI (therapist, clinic admin, patient views).
- Bidirectional Google Calendar sync (outbound: create individual events with platform link, no Google Meet; inbound: read external events as busy time).
- Conflict detection across internal appointments + synced Google Calendar events.
- Email notifications (confirmation with meeting link, reminders, cancellation, recurring schedule changes).

### Phase 4 — Video calls + AI
- LiveKit integration (or chosen alternative): room management API, server-side audio recording.
- Platform-native video call interface connected to LiveKit rooms via meeting links.
- Room creation with access window enforcement.
- Therapist-controlled session lifecycle: Start Session / Pause (auto on disconnect) / Resume Session / End Session.
- Session interruption tracking (pause/resume/disconnect/reconnect event logging).
- Reopen Session feature: 50-minute independent timer, multi-segment audio with reopen markers, AI re-generation on combined transcript.
- Auto-finalization fallback (access window or reopen timer expiry while paused).
- Multi-segment audio recording (one segment per active call period) + transcript concatenation with pause/resume markers.
- Patient waiting screen.
- Server-side audio capture (temporary, multi-segment for sessions with pause/resume cycles) + transcription (Whisper).
- Post-session popups: therapist observation + patient personal notes.
- Initial summary and key points generation (GPT).
- Audio deletion after successful DB persistence.
- Observation history system (CRUD, chronological entries, soft-delete).
- Patient session notes (private journal, not fed into AI).
- Automatic summary versioning triggered by observation changes (with debounce).
- Session journal / history (therapist view with observation timeline + summary versions, patient view with summary + personal notes).
- Dual-track longitudinal analysis: clinical longitudinal (Track 2 → therapist/clinic view), patient personal longitudinal (Track 1 + personal notes → patient view). Independent triggers, independent versioning, strict data isolation.

### Phase 5 — Financials
- Stripe Connect integration (marketplace accounts, pre-auth + capture, splits).
- Patient payment flow.
- Platform-automated commission engine: single atomic transaction that calculates platform fee + clinic/therapist shares and credits all wallets directly.
- Digital wallet system for therapists and clinics (all funded directly by platform).
- Withdrawal requests and platform-to-recipient payout processing.
- Financial dashboards (therapist + clinic admin + platform admin).

### Phase 6 — Messaging system (WhatsApp-like)
- Conversation and message data model + RLS policies enforcing privacy rules (patient conversations private, clinic oversight of therapist conversations, platform admin sees all).
- Realtime message delivery (Supabase Realtime / WebSocket subscriptions + presence indicators).
- WhatsApp-like UI: conversation list with filters/search, message thread with infinite scroll, persistent nav icon with unread badge, responsive (sidebar on desktop, full-screen on mobile).
- Open messaging: any user can message any user (patient↔patient, therapist↔therapist, patient↔therapist, clinic↔anyone, etc.).
- Business entity messaging for clinics (shared organizational inbox, clinic identity).
- Platform support conversations (all users + clinics ↔ support) with admin support inbox dashboard.
- Conversation management: archive, mute, delete, block, report.
- System-generated messages on key events.
- AI-readiness: `mode` field, `ai_agent` sender type, middleware hook (no-op in MVP).
- Notification integration (in-app badge + delayed email for unread messages).

### Phase 7 — Platform views and polish
- Implement four distinct view shells (`/admin/*`, `/clinic/*`, `/therapist/*`, `/patient/*`) with dedicated layouts, navbars, and dashboards.
- Complete platform admin view.
- Complete clinic admin view (self-contained organizational workspace).
- Ensure therapist view parity (independent vs. clinic-affiliated — same UI, different data scope).
- Patient view polish: personal calendar with Google Calendar overlay, recurring schedule management, session history, personal longitudinal analysis ("Minha Jornada"), refund button (disabled by default via feature flag).
- Settings pages (platform admin + clinic admin + therapist).
- Final landing page.
- Tests, UX refinements, responsiveness.

---

## 8. NON-FUNCTIONAL REQUIREMENTS

- **Responsiveness:** Mobile-first, functional across all screen sizes.
- **Security:** Health data is sensitive (LGPD — Brazil's data protection law). Encryption in transit (HTTPS) and at rest for sensitive data. Explicit consent required for audio recording. RLS policies for clinic data isolation. **Single-identity enforcement:** All user references across the schema resolve to `users.id` via FK constraints — no secondary identity systems, no ID mismatches between tables. UNIQUE constraints on `users.email` and `users.google_id` prevent duplicate accounts. **Dual-track data isolation:** RLS must enforce that patients can ONLY access base summary (Track 1) and their own personal notes — never clinical summaries (Track 2), therapist observations, therapist private notes, or longitudinal analyses. This is a hard privacy boundary, not just a UI concern.
- **Data retention:** No permanent audio storage. Temporary audio files must be deleted immediately after transcription and summary are persisted. Implement a cleanup job as a safety net for any orphaned audio files. Transcript text is retained permanently for summary re-generation when observations change.
- **AI generation reliability:** Since summaries are versioned (never overwritten), a failed generation simply means no new version is created — previous versions remain intact and accessible. Implement retry logic and notify the therapist if generation fails after retries. The system should never be in a state where a session has zero summary versions after the initial generation succeeds.
- **AI cost management:** Longitudinal analysis re-generation consumes more tokens as session history grows (all summaries + all observations are sent as input). Implement token-aware strategies: summarize older sessions more aggressively, use a sliding context window, or batch older data into a condensed historical context. Monitor API costs per patient-therapist pair.
- **Performance:** Lazy loading, code splitting, image optimization.
- **Accessibility:** Semantic HTML, proper contrast, keyboard navigation.
- **Language:** The entire platform UI must be in **Brazilian Portuguese (pt-BR)** — all labels, buttons, messages, emails, notifications, error states, tooltips, and copy. The architecture should be i18n-ready (use translation keys/files, not hardcoded strings) so other languages can be added later, but the MVP ships with pt-BR only. Code artifacts (variable names, comments, API docs, commit messages) remain in English.
- **Observability:** Structured logging, error tracking (Sentry or similar).
- **Testing:** At minimum, unit tests for critical business logic (financials, scheduling, recurring appointment auto-generation + conflict detection + payment failure handling, RBAC, RLS, **single-identity integrity (all FKs resolve to users.id, no orphaned profiles, no duplicate accounts by email)**, **dual-track summary isolation (patient cannot access Track 2 via API or UI)**, audio cleanup + multi-segment retention during access window and reopen window, observation-triggered summary versioning debounce, session-end fallback idempotency guard, **refund feature flag enforcement (API rejects requests when disabled, UI shows disabled button)**).

---

## 9. QUESTIONS YOU MUST ASK ME (AT MINIMUM)

In addition to any other questions you deem necessary, make sure to cover:

1. **Stripe Connect mode** — Standard (platform controls payouts) or Express (faster onboarding, Stripe handles payouts)? Standard gives more control but requires more compliance work.
2. **Automatic or manual payouts?** Since the platform handles ALL disbursements (to both therapists and clinics), should payouts be on-demand (recipient requests), on a fixed schedule (e.g., weekly), or configurable per recipient?
3. **Text chat in the video call?** Include in MVP?
4. **Review response** — should therapists be able to publicly reply to a patient's review (like Google Maps responses), or are reviews one-way only?
5. **Final stack** — validate each choice from the table above.
6. **Video call provider** — LiveKit is recommended (open-source, self-hostable, server-side recording). Alternatives: Daily.co (managed, easier), 100ms (managed). Confirm preference, and whether to self-host LiveKit on the VPS or use LiveKit Cloud.
7. **OpenAI key model** — per-therapist (each uses their own) or global (admin pays)?
8. **Deployment** — Vercel + cloud, or everything on a self-hosted VPS?
9. **Testing** — expected coverage level for the MVP.
10. **Design system** — do I have visual references, brand colors, logo?
11. **Terms of use and privacy policy** — will I provide the text or do I need a template?
12. **Per-patient pricing UX** — when a therapist (or clinic admin) sets a custom price for a specific patient, should the patient be notified of their custom rate, or just see it silently at booking time?
13. **Summary version retention** — should there be a maximum number of summary versions kept per session (e.g., keep last 50), or retain all versions indefinitely? Same question for longitudinal analysis versions. Consider storage implications as the platform scales.
14. **Patient origin tracking** — should a patient's origin be set once (at first assignment) and be immutable, or can it change?
15. **Audio processing failure** — what happens if the AI transcription/summary fails? Retry policy? Keep audio until success? Notify therapist to add manual notes?
16. **Clinic white-labeling** — should clinics be able to customize their workspace appearance (logo, colors) or is a standard platform look sufficient for the MVP?
17. **Platform-assigned patient commission** — when the platform admin assigns a patient to a clinic, should this be treated as a new commission category (with its own %) or should it map to `clinic_sourced`?
18. **Patient longitudinal tone** — the patient's personal longitudinal analysis should use a reflective, supportive tone. Should the AI address the patient directly (e.g., "You have explored themes of...") or use third-person ("The patient has explored...")?
19. **Longitudinal analysis minimum sessions** — current spec says 2 sessions minimum. Should this threshold be configurable by the platform admin or therapist?
20. **Auto-finalization alert** — when a session is paused and the access window is about to close, should the therapist receive a push/in-app alert before auto-finalization fires (e.g., "Sua sessão pausada será finalizada automaticamente em 10 minutos. Retorne para encerrá-la manualmente.")? If so, how many minutes before?
21. **Message notification delay** — how long should the system wait before sending an email notification for an unread message? Suggested default: 10 minutes. Should this be configurable per user?
22. **Message deletion** — should users be able to delete messages they sent? If so, should it be a soft-delete (message replaced with "mensagem apagada") or a hard delete?
23. **System messages** — which platform events should auto-generate system messages in conversations? (e.g., session scheduled, session completed, summary available, payment received, observation added). Provide the full list or confirm the suggested ones.
24. **Patient calendar default view** — should the patient calendar default to weekly, monthly, or agenda/list view?
25. **Recurring — monthly frequency** — should monthly recurrence be supported (e.g., first Thursday of every month), or is weekly/biweekly/custom-weeks sufficient?
26. **PIX via Stripe** — Stripe supports PIX in Brazil but PIX does not support pre-authorization/hold. Should PIX payments be charged immediately at booking (refundable via platform admin when refund feature is enabled), or should PIX be available only for one-off sessions (not recurring)?
27. **Recurring — rolling window size** — current spec suggests keeping the next 4 weeks pre-created. Should this be configurable by the platform admin?
28. **Access window extension** — if a session is actively running (not paused) when the access window closes (`scheduled_end + 45 min`), should the system forcibly end the call, or extend the window automatically while the call is active?
29. **AI prompt defaults** — should the platform ship with a set of default prompts for all AI fields (base summary, clinical summary, longitudinal analysis, tags, transcription), or should the platform admin be required to configure them before the AI pipeline can run?
30. **Messaging — file attachments** — should the MVP support file/image attachments in messages, or text-only for now with attachments added later?
31. **Messaging — clinic oversight notification** — should therapists be explicitly informed that their clinic can view their conversations (transparency), or should it be implicit (stated in terms of use only)?

---

## 10. DELIVERY FORMAT

- Clean code, commented where necessary, following framework conventions.
- README.md with local setup instructions and environment variables.
- Commits organized by feature/phase.
- API documentation (endpoints, payloads, responses) — Swagger/OpenAPI preferred.
- Database schema versioned via migrations.
- RLS policies documented and tested.

---

**Remember: Do NOT start coding until we have finalized all questions and I have approved the implementation plan.**