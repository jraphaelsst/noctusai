# META-LEADS-CHECKLIST.md — campaign-lead ingestion, end to end

> **Working tracker** for the Meta Lead-Ads ingestion initiative started 2026-08-03.
> Tick items as they land; every line names the file it touches so progress is auditable.
> Durable roadmap home: `project-history/roadmaps/meta-ads-console-2026-07.md` (Phase 3.2 —
> this checklist is its execution surface). Full rationale for every decision lives there and
> in the approved plan; this file is the *what shipped* view.

**Status:** 🟡 in progress · started 2026-08-03 · branch `feat/meta-leadgen-webhook`

**Prod posture (operator, 2026-08-03):** ❌ **no prod deploy until everything is built and
validated.** Slice 0 is on `dev` only. One promotion at the end, not a trickle.

**Build order right now:** Slices 1 · 2 · 3 · 4 · 5a · 6 (all independent of the peer branch) →
then pause. Slice 5b (live push) stays suspended until the peer's seed realtime work is assessed.

**Migration numbers claimed by this branch:** `040` (webhook inbox) · `041` (leads.meta_lead_id).
🔴 Re-check the highest number on `origin/dev` immediately before writing either — the peer
branch `feat/whatsapp-realtime-inbox` also declares `products/social-wiring/backend/migrations`.

---

## Why (one paragraph)

Campaign leads stopped arriving because nothing drives the pull path: the daily cron
(`meta_ads/scheduler.py`) syncs accounts/hierarchy/insights/activities but **never** calls
`LeadsSyncService`, so leads only moved when someone pressed "Sincronizar leads" — last done
2026-07-29. There is also no push path at all (no webhook, no Page subscription), and Meta
**permanently deletes** lead data after 90 days, so the un-synced tail expires silently. Fix =
a webhook for freshness + a scheduled sync for correctness, both landing in one idempotent
upsert keyed on Meta's own lead id.

---

## Slice 0 — Scheduled lead sync (the standalone fix) — ✅ code complete

- [x] `products/social-wiring/backend/app/modules/meta_ads/scheduler.py` — call
      `LeadsSyncService(...).sync_all(...)` inside `_sync_job_sync`, **last** in the try-block
- [x] Added a fifth DI seam `leads_service_factory=` (matches the module's Class-A convention,
      so the tests drive the real resolution instead of patching module globals)
- [x] Fold `forms_upserted` / `leads_upserted` / `records_gated` into the summary log line
- [x] Preserve `_target_org_id` safe-by-default gating (unset ⇒ skip, never fan out across tenants)
- [x] Test `test_daily_sync_calls_leads_sync_all` (the regression guard for this exact bug)
- [x] Test: unset org ⇒ leads service never constructed (fan-out guard covers the lead leg too)
- [x] Test: lead sync runs **after** the four ads calls (ordering is load-bearing)
- [x] Test: `records_gated` is visible in the summary log (no-silent-errors applies to logs)
- [x] Full `social-wiring` backend suite green — **1496 passed**, exit 0
- [x] Shipped as its own commit so it can be cherry-picked independently
- [ ] **Verify live:** `max(synced_at)` on `social_wiring.meta_ads_leads` advances after a run
      *(needs deploy + the 06:00 cron, or a manual job trigger)*

## Slice 1 — Seed: leadgen webhook capability (C1)

- [ ] NEW `seed/lib/backend/noctusai_lib/integrations/meta/leadgen_webhook.py`
  - [ ] `parse_leadgen_webhook(payload)` — **all** `entry[]` × **all** `changes[]`, never `[0]` only
  - [ ] `leadgen_challenge_response(...)` — `hmac.compare_digest`, constant-time
  - [ ] `LeadgenEvent` dataclass, `.raw` lossless, unix `created_time` → tz-aware UTC
- [ ] `get_lead(leadgen_id, page_id=None)` — Protocol + Fake + Real (Fake **raises** on miss)
- [ ] `subscribe_page_to_leadgen(page_id)` — ⚠️ `subscribed_fields` is a comma-joined **string**
- [ ] `list_page_subscribed_apps(page_id)` + `PageSubscription` type + mapper
- [ ] `unsubscribe_page_from_leadgen(page_id)`
- [ ] Exports in `meta/__init__.py.__all__`
- [ ] Tests: parser table-tests + adapter tests + Protocol-conformance (Fake ∧ Real)
- [ ] KB `KNOWLEDGE-BASE/CONTEXT/INTEGRATIONS/meta.md` §5 — flip webhook row to SHIPS
- [ ] **Merge gate:** grep proves a consumer exists under `products/` (no orphan factory)

## Slice 2 — Product: receiver + inbox (C2)

- [ ] Migration `products/social-wiring/backend/migrations/040_meta_webhook_events.sql`
      (`id TEXT PK` · `payload JSONB` · `status`/`attempts`/`error` · RLS · `service_role_bypass`)
- [ ] `config.py` — `meta_webhook_verify_token` + the two-secrets comment **in the code**
- [ ] `app_config_store.py` — `resolve_meta_webhook_verify_token()` (DB-first, env fallback)
- [ ] NEW `app/modules/meta_ads/routers/leadgen_router.py` (prefix `/api/meta/leadgen`)
  - [ ] `GET /webhook` — handshake, `PlainTextResponse(challenge)`, **not** `int()`
  - [ ] `POST /webhook` — HMAC via **App Secret** (`resolve_meta_app_creds()[1]`), `bypass_when_unset=False`
  - [ ] `GET`/`POST`/`DELETE /subscriptions[/{page_id}]` — operator bootstrap + status
- [ ] NEW `app/modules/meta_ads/services/leadgen_webhook_service.py`
      (`record_event` / `process_event` / `drain_pending` / `purge_processed`)
- [ ] Dedup: Redis SETNX (`get_webhook_dedup()`, TTL 24h) → inbox PK → `meta_ads_leads` PK
- [ ] Rename `LeadsSyncService._upsert_lead` → public `upsert_lead` (keep alias)
- [ ] Cold-form fallback — unknown `form_id` ⇒ `get_leadgen_form` + upsert, then proceed
- [ ] Org ladder: `meta_ads_lead_forms.page_id → org_id` → `META_ADS_ORG_ID` → park as `unresolved`
- [ ] Retry job `meta_leadgen_retry` (`*/15 * * * *`) + 90-day purge
- [ ] Register router in `meta_ads/__init__.py`; add public routes to the auth-boundary allowlist
- [ ] Status-code-pinned tests (200/401/403/duplicate/error/unresolved)
- [ ] `.env.example` — add the whole `META_*` block (currently **zero** entries)
- [ ] `KNOWLEDGE-BASE/CONTEXT/PATTERNS/security/webhook-signatures.md` — add to "Current adopters"
- [ ] `META-APP-VERIFICATION.md` §10 — rewrite from "optional / later" to the shipped runbook
- [ ] **Verify live:** Lead Ads Testing Tool → inbox `processed` + `meta_ads_leads` row with
      non-NULL name/email/phone + exactly one `negociacoes_venda` card; replay ⇒ no second card

## Slice 3 — Unified leads base (C2)

- [ ] Canonical `lead_sources` row `slug='meta-lead-ads'` via `modules/leads/seed_data.py`
- [ ] NEW `modules/leads/services/meta_ingest_service.py` — `meta_ads_leads` → `leads`
- [ ] Migration: nullable `leads.meta_lead_id`, unique-when-present
- [ ] Backfill the 958 stored leads (explicit, logged, idempotent)
- [ ] **Verify live:** test lead visible in `/api/leads` with origem "Meta Lead Ads"

## Slice 4 — Notification fan-out (C2)

- [ ] Generalize `notification_service.py` — extract `dispatch(...)` core from `notify_upload`
- [ ] `notify_new_lead(lead)` — in-app + WhatsApp + email
- [ ] Confirm `social-wiring` mounts the standard `notificacoes` router
- [ ] Fan-out runs **after** the 200 (never blocks the webhook response)
- [ ] **Verify live:** test lead triggers a real WhatsApp message + email + in-app badge

## Slice 5a — Webhook UI + ordering (C3) · **independent, build now**

- [ ] NEW `frontend/src/hooks/useMetaLeadgen.ts` (new file — keeps C3 disjoint from `useMetaAds.ts`)
- [ ] Subscription-management card in `pages/meta/AdsLeads.tsx`:
      per-Page subscribed/not-subscribed badges · "Assinar páginas" · "Cancelar" ·
      callback URL with copy · `verify_token_configured` warning · scope-missing banner
- [ ] Webhook health panel — last delivery received, inbox counts by `status`
- [ ] Newest-first: default sort → `data_entrada desc` (`leads_service.py`)
- [ ] `loading` gated on `isPending || isFetching`, never `isLoading`
- [ ] Complete loading / empty / error / not-configured states (no zeros-over-data)

## Slice 5b — Live push (C3) · 🔴 **SUSPENDED — do not build**

> Blocked by design, not by effort. The peer branch `feat/whatsapp-realtime-inbox` is building
> `seed/lib/backend/noctusai_lib/realtime` (SSE + Redis bus) for the WhatsApp/WAHA inbox. That is a
> **different live session** from this one (Meta Ads leads), but both would sit on the same seed
> realtime primitive, and shipping a second one (Supabase Realtime) would fork the seed.
> **Decision 2026-08-03 (operator):** finish all non-conflicting work first; once the peer lands,
> evaluate their transport together and decide how to touch that seed. Nothing here gets built
> until that assessment happens.

- [ ] ⏸ Evaluate the peer's landed `noctusai_lib/realtime` transport
- [ ] ⏸ Decide the Meta-leads live-session shape on top of it
- [ ] ⏸ Live lead list prepends via `queryClient.setQueryData` — no refetch, no polling
- [ ] ⏸ **Verify live:** lead appears with no refresh, no loading flash

## Slice 6 — erp-imobiliario consolidation (C2)

- [ ] Migrate `products/erp-imobiliario/backend/app/routers/meta_api.py` onto the seed capability
- [ ] Fix the HMAC-secret defect (was using `webhook_verify_token`; must be the **App Secret**)
- [ ] Delete the hand-rolled Graph client `app/services/meta_api_service.py`
- [ ] Replace `parse_lead_webhook` (drops batched deliveries) with the seed parser

## Slice 7 — CSV recovery importer (conditional)

- [ ] **Operator:** confirm whether pre-2026-04-28 exports / Meta notification emails exist
- [ ] If yes — add a Meta lead-export shape to `modules/leads/importer/shape_detector.py`
- [ ] If no — record "forward-only, history unrecoverable" in the roadmap decision log

---

## Operator steps (cannot be done in code)

Permissions, App Review, Live mode and OAuth callbacks are **already done**. Remaining, at
`developers.facebook.com`, and **only after Slice 2 is deployed to prod**:

- [ ] Products → Webhooks → **Page** object
- [ ] Callback URL `https://social.noctusai.com/api/meta/leadgen/webhook`
- [ ] Verify Token = the exact `META_WEBHOOK_VERIFY_TOKEN`
- [ ] **Verify and Save** (Meta GETs the endpoint synchronously — it must be live first)
- [ ] Tick the **`leadgen`** field → Subscribe *(app-level)*
- [ ] Run our bootstrap `POST /api/meta/leadgen/subscriptions` *(per-Page level)*

> ⚠️ App-level and per-Page subscription are **both** required. Either one alone delivers
> nothing, silently — the most common lead-ads misconfiguration.

---

## Gates before ship

- [ ] `noctus.dev.validate` on the integrated branch
- [ ] `compliance-reviewer` on the diff
- [ ] `security` advisory on the public receiver
- [ ] Gates re-run on the **merged tip** (per-branch green ≠ integration green)
- [ ] `noctus_vps_logs` — `meta-leadgen-webhook: secret unset` must be **absent**

---

## Decision log

| Date | Decision |
|---|---|
| 2026-08-03 | Leads land in `meta_ads_leads` (raw ledger) **and** normalize into `social_wiring.leads` (unified base) |
| 2026-08-03 | Arrival fans out to in-app + WhatsApp + email; list updates live via Supabase Realtime, no polling, newest-first |
| 2026-08-03 | History: Meta deletes leads after 90 days, unrecoverable by any means — forward-only unless off-platform exports exist |
| 2026-08-03 | erp-imobiliario consolidates onto the seed capability (verified dead: 0 config rows, 0 leads) |
| 2026-08-03 | No seed router factory — pure functions in seed, HTTP router in product (the orphaned `create_whatsapp_webhook_router` is the precedent against it) |
