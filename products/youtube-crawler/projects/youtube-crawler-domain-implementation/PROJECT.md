# YouTube Crawler — Domain Implementation

> **This is a living document, not a rigid checklist.**
> As we build and learn, this project document evolves. Revise phases, fold in
> optimizations, update the Change Log. See `CLAUDE.md → Engineering Philosophy
> → Projects are living documents`.
>
> **Filed by an assessment engineer (Engineer YT-ASSESS, 2026-05-11) — has
> NOT been through user interrogation.** Section 2 carries the assessment
> findings; the architect MUST run an interrogation pass with the user before
> dispatching Phase 1 to confirm scope, sequencing, and the open questions
> in §7.

- **Created:** 2026-05-11
- **Last updated:** 2026-05-11
- **Status:** Design draft — needs user interrogation before Phase 1 dispatch
- **Owner / stakeholders:** {{USER}} · architect
- **Related docs:**
  - `products/youtube-crawler/MASTER-PROMPT.md` (refreshed 2026-05-11)
  - `KB § CONTEXT/02-LANDSCAPE.md` (product description + canonical ports 8008/8150)
  - `KB § PATTERNS/whatsapp-chatbot-seed.md` (WAHA integration recipe)
  - `KB § PATTERNS/digest-seed.md` (BaseDigestService for SMTP digest)
  - `KB § PATTERNS/webhook-signatures.md` (if Google Pub/Sub adopted for Drive change notification)
  - `KB § PATTERNS/seed-fake-real-adapter.md` (canonical shape for Drive + YouTube + Fernet vault adapters)
- **Project slug:** `youtube-crawler-domain-implementation` (product-scoped: lives at `products/youtube-crawler/projects/youtube-crawler-domain-implementation/`; intent = `implementation` — the scaffold→production fill, not a migration or expansion)

---

## 1. Context & Purpose

YouTube Crawler was scaffolded against the seed framework on 2026-05-05 and containerized 2026-05-10 (`containerization-backlog-closure`), but its domain implementation never landed. As of 2026-05-11 the product has:

- Backend: `0` routers, `0` services (only seed wiring in `main.py` / `config.py` / `database.py` / `dependencies.py` / `rate_limit.py`).
- Frontend: 7 seed-template pages (Dashboard, Equipe, Login, AcceptInvite, Landing, ForgotPassword, NotFound) — no domain UI.
- Migration `001_youtube_crawler.sql`: schema + `status_pagina` + `invitations` only (carryover from the seed scaffold).
- Tests: 31 inherited framework-suite tests pass; `0` product-specific.
- Docs: MASTER-PROMPT had drifted to describe youtube-crawler as the "seed reference product" — refreshed 2026-05-11 in the same commit that files this project.

The platform LANDSCAPE describes the intended product as: **YouTube Data API v3 + Drive + WAHA + SMTP — quota-aware uploads with Fernet-encrypted refresh tokens.** This project ships that product.

The win: operators connect their Google account, drop source material into a designated Drive folder, and the system uploads to YouTube within daily-quota constraints, notifying them of progress / failures via WhatsApp and email.

---

## 2. Confirmed constraints

> **Filled by the assessment engineer from artifacts (MASTER-PROMPT, LANDSCAPE, scaffold migration); NOT yet validated with the user.** The architect's interrogation pass should confirm or correct each row and append new rows for anything surfaced.

- **Tenancy** — single `org_id` tenant boundary (inherited from seed; no per-channel sub-tenancy). *(Operator's Google account is bound to one org_id; multi-org operators reconnect per-org. Rules out account-level sharing.)*
- **Credentials storage** — Google refresh tokens stored Fernet-encrypted in a `youtube_crawler.google_credentials` table (one row per `(org_id, user_id)`). *(Rules out env-var-only storage; a service-account model would change everything — explicit choice to be per-user OAuth.)*
- **Drive watcher trigger** — periodic poll (interval TBD in Phase 2) vs Google Pub/Sub push notifications. **Open question §7 Q1.**
- **YouTube quota model** — daily-quota tracking server-side (cost-per-call table tabulated against the YouTube Data API public docs). Upload jobs pause at a configurable threshold (e.g. 90% of daily limit) instead of hard-failing on the 403. *(Drives the `quota_tracker` service; aligns with KB recurrence-rule for any future quota-aware product.)*
- **Notification channels** — WAHA + SMTP; both opt-in per operator. *(WAHA via the seed's `noctusai_lib.integrations.whatsapp` adapter — verify-the-seed-ships-it for WAHA Real adapter at Phase 3; SMTP via the seed's `noctusai_lib.integrations.smtp` adapter — same verify step.)*
- **Digest cadence** — daily + weekly; operator chooses. Uses `BaseDigestService` from `noctusai_lib.domain.digest`. *(N=5 adopter — preserves the cluster, no per-product orchestration.)*
- **Auth** — SSO via `make_get_current_user_org` factory (canonical pattern). *(Rules out custom JWT; aligns with adconnect's Phase-0 Option-A decision.)*
- **LGPD** — Google email + refresh token + channel handle are LGPD-sensitive; flagged at every write site via `noctus.dev.lgpd_flag`; Fernet column masked in audit logs.
- **Webhook receivers** — if Google Pub/Sub adopted for Drive change notification, the receiver follows the 5-pin compliance contract (seed canonical at `products/seed/backend/app/routers/webhook_router.py`). **Conditional on §7 Q1 outcome.**

---

## 3. Design principles

1. **Seed-first, always.** Domain routers attach via `create_product_app()`'s `standard_routers=[...]` seam. Never re-wire CORS / exception handlers / middleware locally.
2. **Fake+Real+factory at every seed-ward IO boundary.** YouTube Data API client, Drive client, WAHA notifier, SMTP sender, Fernet vault — each ships in Protocol + Fake + Real + factory shape per `KB § PATTERNS/seed-fake-real-adapter.md`. Build against the Fake; lift to the seed when N=2+.
3. **Quota-aware by design.** The YouTube upload pipeline is a state machine, not a fire-and-forget. Upload jobs are persisted; quota costs are deducted before issuing the API call; the pipeline pauses (not fails) at threshold.
4. **Operator-self-service credentials.** Operators connect / disconnect / rotate Google credentials through a UI; admin override exists but is rare.
5. **No silent failures.** Quota exhaustion, transient 5xx, token expiry — each surfaces a WAHA notification + dashboard banner + structured log. No `except: pass` anywhere.
6. **Verify the seed ships it.** Before consuming `noctusai_lib.integrations.{whatsapp,smtp,vault}`, read `__init__.py` exports + Real adapter file. Gap + this product as N=1 consumer → ship against Fake + file the seed real-adapter follow-up project.

---

## 3a. Seed-first analysis (REQUIRED)

This is a **single-product project** — by definition single-product. The §3a discipline still applies: every primitive being built must be evaluated for seed-level placement first.

Run the six-question checklist (`KB § GUIDES/seed-first-design.md § The seed-first checklist`) **per primitive**:

### Primitive 1 — Google OAuth + Fernet refresh-token vault
1. **Is the contract identical for every product?** Likely YES for any future product needing Google API access. The vault primitive (Fernet-encrypt arbitrary credential blobs) is even broader.
2. **Is the data source product-specific?** Refresh tokens are product-specific (different scopes per product), but the **vault primitive** (encrypt / decrypt / rotate) is uniform.
3. **Is the placement product-specific?** YES — credentials UI lives in the operator's product (here youtube-crawler), not in core.
4. **Is the visibility / permission rule the same?** YES — operator owns their own creds; admin override.
5. **Does the seam already exist in seed?** **Verify-the-seed-ships-it gate.** `noctusai_lib.integrations.vault` — check `__init__.py` + Real adapter file before Phase 1 starts. If gap → ship against Fake + file seed real-adapter project.
6. **Default-on or opt-in?** OPT-IN per operator (they must explicitly connect Google).

**Litmus:** the vault primitive lives in seed; this product is N=1 consumer. If another product (e.g. analytics, mailing) grows the same shape at N=2, the seed adapter graduates from Fake to Real.

### Primitive 2 — Drive watcher + drop-folder convention
1. **Identical contract?** Likely YES if another product ever needs Drive ingestion. Not yet recurring.
2. **Data source product-specific?** YES — the drop-folder ID is per-org-per-product.
3. **Placement?** Product-specific (the watcher runs in this product's container).
4. **Visibility?** Org-bounded.
5. **Existing seed seam?** No. `noctusai_lib.integrations.google_drive` does not exist (verify before Phase 2).
6. **Default-on?** OPT-IN — operator binds a folder.

**Litmus:** build in product first (N=1). If a second consumer surfaces, lift to `noctusai_lib.integrations.google_drive` (Protocol + Fake + Real + factory).

### Primitive 3 — YouTube Data API client + quota tracker
1. **Identical contract?** YouTube API is YouTube-specific. The **quota-tracker pattern** (cost-per-call table + threshold gating) is generic — applies to any vendor with daily quotas (Anthropic, OpenAI, WhatsApp Business, etc.). Recurrence-rule check at end of Phase 3.
2. **Data source?** Product-specific (this product's `upload_jobs` table).
3. **Placement?** Product.
4. **Visibility?** Org.
5. **Existing seam?** YouTube client: no. Quota-tracker pattern: not yet — file as candidate seed extraction once N=2 (LLM provider quota tracking is the obvious second adopter).
6. **Default-on?** Built-in — the pipeline always tracks quota.

### Primitive 4 — WAHA notifier
- **Verify-the-seed-ships-it gate.** `noctusai_lib.integrations.whatsapp` (`KB § PATTERNS/whatsapp-chatbot-seed.md`). Read exports + Real adapter file before Phase 3. Likely runtime-ready (imobi-scheduling consumes it).

### Primitive 5 — SMTP digest
- **Verify-the-seed-ships-it gate.** `noctusai_lib.integrations.smtp` + `noctusai_lib.domain.digest.BaseDigestService` (`KB § PATTERNS/digest-seed.md`). Read exports before Phase 4. N=4 adopter; runtime-ready expected.

**Phase plan implications:** every phase consumes seed primitives where they exist. Phases 1+2+3 each open with a verify-the-seed-ships-it audit (1-2 hours each) before the build step. **No replication framing in §6** — this product is N=1 by design.

**Litmus — per-product code count this design requires:**

- [x] **A small section** — product-specific data wiring around seed-shaped containers (credentials UI, upload dashboard, digest preferences). The primitives are seed-side; this product's code is the wiring + the product-specific routers/services.

---

## 4. Scope

**In scope:**
- Google OAuth flow (YouTube + Drive scopes); Fernet-encrypted refresh-token storage in `youtube_crawler.google_credentials`.
- Drive watcher: per-org drop folder; periodic poll OR Pub/Sub (§7 Q1); enqueues source files.
- YouTube upload pipeline: resumable upload, retry with backoff, persistence in `youtube_crawler.upload_jobs`.
- Quota tracker: cost-per-call table; daily window; threshold gating; pause-not-fail semantics.
- WAHA notification channel: progress + failure pushes per operator.
- SMTP digest: daily + weekly via `BaseDigestService`.
- Operator UI: credentials page, upload dashboard (with live quota gauge + job actions), digest preferences.
- Tests: framework-suite inheritance preserved; domain-specific service + integration tests; status-pinned router tests.
- LGPD flags at every PII write site.
- DEPLOYMENT.md (chatbot-operational-readiness pattern adopted at the relevant phase).

**Out of scope (for now — with reason):**
- Multi-channel YouTube (one operator → multiple channels). *(Deferred — single-channel-per-operator covers MVP; the data model can accept multi-channel later via a `channels` table.)*
- Video editing / transcoding. *(Out of platform scope; assume source is upload-ready.)*
- Analytics dashboards on YouTube performance. *(Future product or future phase; the API surface to fetch is small but distinct from the upload pipeline.)*
- Admin V2 (cross-org observability). *(Adconnect's V1 → V2 pattern: V1 is per-operator; V2 is admin observability; phased.)*

---

## 5. Architecture / Data Model

### Tables (migration `001_youtube_crawler.sql`, edited in-place per single-001 convention)

```
youtube_crawler.google_credentials
  id UUID PK
  org_id UUID NOT NULL
  user_id UUID NOT NULL  -- operator
  email TEXT NOT NULL    -- LGPD
  refresh_token_encrypted BYTEA NOT NULL  -- Fernet-encrypted
  scopes TEXT[] NOT NULL
  connected_at TIMESTAMPTZ DEFAULT now()
  revoked_at TIMESTAMPTZ
  UNIQUE(org_id, user_id)

youtube_crawler.drive_drop_folders
  id UUID PK
  org_id UUID NOT NULL
  user_id UUID NOT NULL
  drive_folder_id TEXT NOT NULL
  label TEXT  -- operator-friendly name
  active BOOL DEFAULT TRUE
  created_at TIMESTAMPTZ DEFAULT now()

youtube_crawler.upload_jobs
  id UUID PK
  org_id UUID NOT NULL
  user_id UUID NOT NULL
  source_drive_file_id TEXT NOT NULL
  source_filename TEXT NOT NULL
  state TEXT NOT NULL  -- pending | uploading | succeeded | failed | paused-quota
  youtube_video_id TEXT  -- populated on success
  quota_cost_units INT
  started_at TIMESTAMPTZ
  finished_at TIMESTAMPTZ
  last_error TEXT
  retry_count INT DEFAULT 0
  created_at TIMESTAMPTZ DEFAULT now()
  updated_at TIMESTAMPTZ DEFAULT now()  -- noctusai_lib.sql.updated_at_trigger

youtube_crawler.quota_ledger
  id UUID PK
  org_id UUID NOT NULL
  day DATE NOT NULL
  units_consumed INT NOT NULL DEFAULT 0
  UNIQUE(org_id, day)

youtube_crawler.notification_prefs
  id UUID PK
  org_id UUID NOT NULL
  user_id UUID NOT NULL
  waha_phone TEXT  -- LGPD
  smtp_email TEXT  -- LGPD
  waha_enabled BOOL DEFAULT FALSE
  smtp_enabled BOOL DEFAULT FALSE
  digest_cadence TEXT NOT NULL DEFAULT 'daily'  -- daily | weekly | both
  UNIQUE(org_id, user_id)
```

All tables: RLS enabled; `org_id`-scoped subquery policies via `noctusai_lib.sql.rls_subquery_policy`; `updated_at` triggers where applicable via `noctusai_lib.sql.updated_at_trigger`.

### Routers (under `app/routers/`)

- `credentials_router.py` — `POST /api/credentials/google/connect` (OAuth callback), `POST /api/credentials/google/disconnect`, `GET /api/credentials/google/status`.
- `drive_folders_router.py` — `GET / POST / DELETE /api/drive-folders`.
- `uploads_router.py` — `GET /api/uploads` (list with filters), `POST /api/uploads/{id}/retry`, `POST /api/uploads/{id}/cancel`.
- `quota_router.py` — `GET /api/quota/today`, `GET /api/quota/history`.
- `notification_prefs_router.py` — `GET / PUT /api/notification-prefs`.
- (Conditional on §7 Q1) `pubsub_webhook_router.py` — `POST /api/webhooks/google-pubsub` (5-pin compliance).

### Services (under `app/services/`)

- `google_oauth_service.py` — exchange code → refresh-token; Fernet-encrypt + persist; revocation.
- `vault_service.py` — wraps the seed vault primitive; decrypts on demand for the upload worker.
- `drive_watcher_service.py` — poll / Pub/Sub handler; enqueues `upload_jobs`.
- `upload_worker_service.py` — picks pending jobs, calls `quota_service.reserve`, invokes YouTube client, persists state transitions.
- `quota_service.py` — reads `quota_ledger`; reserve / commit / refund pattern; threshold gating.
- `waha_notifier_service.py` — wraps the seed WhatsApp adapter.
- `smtp_digest_service.py` — subclass of `BaseDigestService`; daily + weekly windows.

### Frontend pages

- `src/pages/Credentials.tsx` — connect / disconnect Google; show scope grants + connected email.
- `src/pages/UploadDashboard.tsx` — live job list (React Query polling), quota gauge, retry / cancel.
- `src/pages/DigestPreferences.tsx` — WAHA / SMTP toggles + cadence.

### Frontend hooks (under `src/hooks/`)

- `useGoogleCredentials.ts`, `useUploadJobs.ts`, `useQuotaToday.ts`, `useDriveFolders.ts`, `useNotificationPrefs.ts`.

Each hook uses tightly-typed query params matching the backend's Pydantic schemas (post `pf-frontend` 2026-05-11 lesson: `Record<string, any>` silently drops misroutes). Backend Pydantic schemas adopt `StrictHttpModel` from `noctusai_lib.api` per the strict-by-default pattern.

---

## 6. Implementation phases

Phase status-icon convention applies (see template). Each phase opens with a verify-the-seed-ships-it audit where relevant.

### Phase 1 — Credentials foundation (Google OAuth + Fernet vault)

- [ ] **Verify-the-seed-ships-it gate**: read `noctusai_lib/integrations/vault/__init__.py` + Real adapter; if gap → file `seed-vault-real-adapter` follow-up project, build against Fake.
- [ ] Migration edit (in-place 001): add `google_credentials` table + RLS subquery policy.
- [ ] Service: `google_oauth_service.py` (OAuth code-exchange + Fernet persist) — built against vault primitive (Fake or Real).
- [ ] Service: `vault_service.py` (thin wrap of seed vault if real).
- [ ] Router: `credentials_router.py` (connect / disconnect / status).
- [ ] Frontend hook: `useGoogleCredentials.ts`; page `Credentials.tsx`.
- [ ] LGPD flags on `email` + `refresh_token_encrypted` write sites.
- [ ] Tests: service unit tests (Fake vault); router status-pinned tests; frontend hook smoke.
- [ ] DEPLOYMENT.md scaffolded (chatbot-operational-readiness pattern adoption).

### Phase 2 — Drive watcher + drop-folder management

- [ ] **Verify-the-seed-ships-it gate**: search for `noctusai_lib.integrations.google_drive`; if absent (likely), file `seed-google-drive-adapter` follow-up project; build against ad-hoc Fake in this product for N=1.
- [ ] Migration edit (in-place 001): `drive_drop_folders` + RLS.
- [ ] Service: `drive_watcher_service.py` (poll-based v1; periodic task via FastAPI background task or APScheduler — TBD §7 Q2).
- [ ] Router: `drive_folders_router.py` (CRUD).
- [ ] Frontend: surface drop-folder selection in `Credentials.tsx` (or split into a `DriveFolders.tsx` page).
- [ ] Tests: watcher logic with Fake Drive client; status-pinned router tests.
- [ ] **Optimization-spotting:** if Drive client surface matches Calendar/Maps shape, recurrence-rule fires at N=2 → propose seed lift.

### Phase 3 — YouTube upload pipeline + quota tracker

- [ ] **Verify-the-seed-ships-it gate**: no seed YouTube adapter exists (N=1). Build product-side under `app/integrations/youtube_client.py` in Protocol + Fake + Real + factory shape — future-proof for seed lift.
- [ ] Migration edit (in-place 001): `upload_jobs` + `quota_ledger` + `updated_at` trigger.
- [ ] Service: `quota_service.py` (reserve / commit / refund) — pure-logic + DB; consider seed extraction if N=2 surfaces.
- [ ] Service: `upload_worker_service.py` (state machine: pending → uploading → succeeded / failed / paused-quota).
- [ ] Router: `uploads_router.py` + `quota_router.py`.
- [ ] Background task wiring (matches Phase 2 choice).
- [ ] Frontend: `UploadDashboard.tsx` + `useUploadJobs.ts` + `useQuotaToday.ts`; live quota gauge.
- [ ] Tests: state-machine unit tests; quota reserve/commit/refund unit tests; status-pinned router tests; integration test for happy path against Fake YouTube + Fake Drive.

### Phase 4 — WAHA notifications + SMTP digest

- [ ] **Verify-the-seed-ships-it gate**: read `noctusai_lib.integrations.whatsapp.__init__` + Real adapter (`KB § PATTERNS/whatsapp-chatbot-seed.md`). Read `noctusai_lib.integrations.smtp` if it exists; if absent → file seed-smtp-adapter follow-up, build against Fake.
- [ ] Migration edit (in-place 001): `notification_prefs` + RLS.
- [ ] Service: `waha_notifier_service.py` (thin wrap of seed adapter).
- [ ] Service: `smtp_digest_service.py` (subclass of `BaseDigestService`) — daily + weekly windows.
- [ ] Router: `notification_prefs_router.py`.
- [ ] Frontend: `DigestPreferences.tsx` + `useNotificationPrefs.ts`.
- [ ] Wire upload state transitions → WAHA push (failure + completion).
- [ ] Wire daily / weekly digest job → SMTP send.
- [ ] Tests: notifier service unit tests; digest narrative tests; status-pinned router tests.

### Phase 5 — Hardening + production readiness

- [ ] Adopt `chatbot-operational-readiness` (`KB § PATTERNS/chatbot-operational-readiness.md`): `retry_call`-wrapped external writes (YouTube uploads, WAHA pushes, SMTP sends), structured logs (already auto-wired by `create_product_app`), health endpoint via `standard_routers=["health"]` (already present), `DEPLOYMENT.md` (Phase 1 scaffold filled out), metrics-sink seam.
- [ ] `noctus.dev.review --product youtube-crawler` — clear all detectors (LGPD / webhook-pins / status-assertion / 10 new detectors).
- [ ] `noctus.hound.scan` — clear any cleanup queue items surfaced by the build.
- [ ] Frontend hook query-param types tightened (no `Record<string, any>`).
- [ ] CORS pinned to `@registry:own:youtube-crawler` (already config'd in `app/config.py`).
- [ ] Rate-limit decorators on every mutation route — using `DEFAULT_AUTH_RL` / `DEFAULT_PORTAL_RL` from `noctusai_lib.api.rate_limit_policies`.
- [ ] Operator-facing README / onboarding doc.

### Phase 6 — Deploy + dogfood

- [ ] `./start.sh` runs the full stack with YouTube Crawler reachable on 8008 / 8150.
- [ ] Cloudflare quick-tunnel verification for OAuth callback testing (`./start.sh tunnel youtube-crawler`).
- [ ] Operator dogfood: connect a real Google account, drop a small file, observe upload.
- [ ] Capture findings in `findings.md`; flip §6 phases to `✅`; close project.

---

## 7. Open questions

1. **Drive change-detection model: periodic poll vs Google Pub/Sub push?** — Pub/Sub is more efficient + lower-latency but adds webhook receiver complexity (5-pin compliance contract + Pub/Sub subscription management). Periodic poll is simpler but burns more quota at scale. **Recommendation:** start with periodic poll (Phase 2); reassess if quota footprint becomes a constraint OR if push-latency becomes a product requirement. *Needs answer before Phase 2 start.*
2. **Background task scheduler: FastAPI background-task + asyncio.sleep vs APScheduler vs Celery?** — For single-container deploys the first two are sufficient. Celery introduces broker dependency (Redis). **Recommendation:** APScheduler in-process (matches the seed's expected `lifespan_extra` shape, no extra container). *Needs answer before Phase 2.*
3. **Quota threshold pause behavior — pause-at-90% or pause-at-100%?** — 90% leaves headroom for manual operator-initiated uploads; 100% maximizes throughput but risks 403. **Recommendation:** 90% default, configurable per-org. *Decide during Phase 3 design step.*
4. **Multi-channel-per-operator: explicitly out-of-scope vs reserved as future-phase?** — §4 marks it out-of-scope. Confirm with user whether to leave the door open in the data model (nullable `channel_id` foreign key) or fully bake in single-channel. *User decision.*
5. **OAuth scope scope-set: full YouTube vs upload-only + Drive readonly?** — Upload-only narrows the blast radius if creds leak. Readonly Drive matches the drop-folder watcher need. **Recommendation:** narrow scopes; expand only if a sub-feature demands it. *User decision before Phase 1.*
6. **MVP target operator: internal-dogfood-only vs early external pilot?** — Drives the polish bar of Phase 5. *User decision.*
7. **Sequencing: linear (1→2→3→4→5→6) vs parallel chunks?** — Phase 1 (credentials) gates everything. Phase 2 (Drive) gates Phase 3 (upload pipeline reads from Drive). Phase 4 (notifications) is parallel to Phase 3 once Phase 1 lands. Phase 5+6 are tail-end. **Recommendation:** 1 → (2 ∥ partial-4-prep) → 3 ∥ 4 → 5 → 6. *Architect decision at dispatch time.*

---

## 8. Dependencies & blockers

- **Seed vault primitive** — verify availability + shape at Phase 1 start. Gap → seed-side project must land first OR build against Fake.
- **Seed Google Drive adapter** — almost certainly absent at scaffold time; build product-side first, lift on N=2.
- **Seed WhatsApp + SMTP adapters** — verify at Phase 4 start; expected runtime-ready (imobi-scheduling consumes WhatsApp).
- **Google Cloud project + OAuth client credentials** — the OWNER must provision a Google Cloud project, enable YouTube Data API v3 + Drive API, configure OAuth consent screen, and provide client_id / client_secret via `.env`. **Needed before Phase 1 integration testing.**
- **Test YouTube channel** — for dogfood (Phase 6); a non-production channel to avoid risking real content.

---

## 9. Success criteria

- All framework-suite tests stay green (31 → 31+ as domain tests land).
- `noctus.dev.review --product youtube-crawler` returns clean.
- `noctus.hound.scan` reports no urgent absorption / fusion / optimization queue items related to youtube-crawler.
- Operator can: connect Google → bind a Drive folder → drop a file → see upload progress → receive WAHA + SMTP notifications → see daily digest email.
- Quota tracker prevents 403s: at threshold the pipeline pauses without losing the queued job.
- Backend ports 8008 / 8150 verified working via `./start.sh`; cloudflare tunnel verified for OAuth callback.
- DEPLOYMENT.md present + complete.

---

## 10. How to use this plan

- **Phase-by-phase by default.** Execute one phase, then pause and wait for the user to say "continue" / "next phase" / "do phase N".
- **Live-tick tasks** as they complete; do not batch at phase end.
- **Verify-the-seed-ships-it gates** are NOT optional; skipping them generates consumer-side forks (silent recurrence-rule debt).
- **Revise the plan** when understanding changes — rewrite phases, split/merge tasks, append to §11 Change log.
- **Interrogate the user** before starting Phase 1 to lock §7 open questions Q1, Q2, Q5, Q6. The other questions can defer to their phase.

---

## 11. Change log

| Date | Change | By |
|---|---|---|
| 2026-05-11 | Initial draft by Engineer YT-ASSESS during assessment pass. NOT user-interrogated; architect must interrogate before Phase 1 dispatch. | Engineer YT-ASSESS (claude-opus-4-7) |
